#!/usr/bin/env python3
"""Evaluate benchmark results using an LLM judge for blind comparison."""

import argparse
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

import yaml


JUDGE_PROMPT_TEMPLATE = """You are evaluating two AI agent outputs for the same task. Output A and Output B are from different models. Score each on:

1. correctness (0-10): factual accuracy, absence of hallucinations
2. depth (0-10): non-obvious insights, synthesis quality, nuance
3. actionability (0-10): directly usable output vs needs rework
4. structure (0-10): format quality, clarity, scannability

For each dimension, give a score and a 1-sentence justification.
Then pick an overall winner.

Task: {task_description}
Evaluation focus: {evaluation_focus}

OUTPUT A:
{output_a}

OUTPUT B:
{output_b}

Respond with a JSON object:
{{"scores_a": {{"correctness": N, "depth": N, "actionability": N, "structure": N}}, "scores_b": {{...}}, "justifications": {{...}}, "winner": "A" or "B" or "tie", "notes": "..."}}"""


def load_task_def(task_name: str, tasks_dir: str = "tasks") -> dict | None:
    """Load a task definition if available."""
    task_path = os.path.join(tasks_dir, f"{task_name}.yaml")
    if os.path.exists(task_path):
        with open(task_path, "r") as f:
            return yaml.safe_load(f)
    return None


def load_run_results(run_dir: str) -> dict[str, list[dict]]:
    """Load all result JSONs from a run directory, grouped by task.

    Returns: {task_name: [result_dict, ...]}
    """
    results_by_task: dict[str, list[dict]] = {}

    if not os.path.isdir(run_dir):
        print(f"Error: run directory not found: {run_dir}", file=sys.stderr)
        sys.exit(1)

    for fname in sorted(os.listdir(run_dir)):
        if not fname.endswith(".json") or fname == "summary.json":
            continue
        fpath = os.path.join(run_dir, fname)
        try:
            with open(fpath, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: skipping {fname}: {e}", file=sys.stderr)
            continue

        task_name = data.get("task", "unknown")
        if task_name not in results_by_task:
            results_by_task[task_name] = []
        results_by_task[task_name].append(data)

    return results_by_task


def pair_outputs(results: list[dict]) -> list[tuple[dict, dict]]:
    """Pair Pro and Flash results for the same task. Returns list of (pro_result, flash_result)."""
    pro_results = [r for r in results if "pro" in r.get("model", "")]
    flash_results = [r for r in results if "flash" in r.get("model", "")]

    pro_results.sort(key=lambda r: r.get("run", 0))
    flash_results.sort(key=lambda r: r.get("run", 0))

    pairs = []
    for i in range(min(len(pro_results), len(flash_results))):
        pairs.append((pro_results[i], flash_results[i]))
    return pairs


def truncate_output(text: str, max_chars: int = 8000) -> str:
    """Truncate output text to a reasonable size for the judge."""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n\n[... output truncated ...]\n\n" + text[-half:]


def call_judge(prompt: str, timeout: int = 300) -> dict | None:
    """Call the LLM judge via hermes chat and parse the JSON response."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".txt",
        prefix="judge_prompt_",
        delete=False,
    ) as tf:
        tf.write(prompt)
        prompt_file = tf.name

    try:
        shell_cmd = (
            f'hermes chat -q -m deepseek-v4-pro "$(cat {prompt_file})"'
        )

        result = subprocess.run(
            shell_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        stdout = result.stdout

        if result.returncode != 0:
            print(
                f"Warning: judge exited with code {result.returncode}: "
                f"{result.stderr[:300]}",
                file=sys.stderr,
            )

        # Try to extract JSON from the output
        return extract_json(stdout)

    except subprocess.TimeoutExpired:
        print("Warning: judge timed out", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("Error: hermes command not found in PATH", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Warning: judge error: {e}", file=sys.stderr)
        return None
    finally:
        try:
            os.unlink(prompt_file)
        except OSError:
            pass


def extract_json(text: str) -> dict | None:
    """Extract a JSON object from text that may contain surrounding content."""
    # First try to find a JSON block
    json_match = re.search(r'\{[^{}]*"scores_a"[^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    # Try to find any JSON object
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    print("Warning: could not parse JSON from judge output", file=sys.stderr)
    return None


def compute_cost(token_usage: dict) -> float:
    """Compute approximate cost from token usage.

    DeepSeek pricing (approx per 1M tokens):
    - V4-Pro: $1.10 input, $4.40 output, $0.14 cache hit
    - V4-Flash: $0.14 input, $0.56 output, $0.014 cache hit
    """
    model_pricing = {
        "deepseek-v4-pro": {
            "input": 1.10 / 1_000_000,
            "output": 4.40 / 1_000_000,
            "cache_hit": 0.14 / 1_000_000,
        },
        "deepseek-v4-flash": {
            "input": 0.14 / 1_000_000,
            "output": 0.56 / 1_000_000,
            "cache_hit": 0.014 / 1_000_000,
        },
    }

    input_tokens = token_usage.get("input", 0)
    output_tokens = token_usage.get("output", 0)
    cache_hit = token_usage.get("cache_hit", 0)

    # We don't know the model from token_usage alone, so try both and return reasonable estimate
    # For the evaluation, we compute using the result's own model
    return 0.0  # Cost is computed at the result level, not from usage dict alone


def evaluate_run(
    run_dir: str,
    tasks_dir: str = "tasks",
    timeout: int = 300,
) -> dict:
    """Evaluate all results in a run directory.

    Returns the evaluation dict that is saved to evaluation.json.
    """
    results_by_task = load_run_results(run_dir)

    if not results_by_task:
        print("Error: no result files found in run directory", file=sys.stderr)
        sys.exit(1)

    evaluations = {}
    total_cost_pro = 0.0
    total_cost_flash = 0.0

    model_pricing = {
        "deepseek-v4-pro": {
            "input": 1.10 / 1_000_000,
            "output": 4.40 / 1_000_000,
            "cache_hit": 0.14 / 1_000_000,
        },
        "deepseek-v4-flash": {
            "input": 0.14 / 1_000_000,
            "output": 0.56 / 1_000_000,
            "cache_hit": 0.014 / 1_000_000,
        },
    }

    for task_name, results in sorted(results_by_task.items()):
        print(f"\n{'=' * 60}")
        print(f"Evaluating task: {task_name}")
        print(f"{'=' * 60}")

        task_def = load_task_def(task_name, tasks_dir)
        description = task_def.get("description", task_name) if task_def else task_name
        evaluation_focus = (
            task_def.get("evaluation_focus", ["correctness", "depth", "actionability"])
            if task_def
            else ["correctness", "depth", "actionability"]
        )

        pairs = pair_outputs(results)
        if not pairs:
            print("  No Pro/Flash pairs found, skipping")
            continue

        task_evaluations = []
        task_cost_pro = 0.0
        task_cost_flash = 0.0

        for i, (pro_result, flash_result) in enumerate(pairs):
            run_idx = i + 1
            print(f"  Judging run {run_idx}...", end=" ", flush=True)

            # Randomize A/B labeling
            swap = random.choice([True, False])
            if swap:
                result_a = flash_result
                result_b = pro_result
            else:
                result_a = pro_result
                result_b = flash_result

            prompt = JUDGE_PROMPT_TEMPLATE.format(
                task_description=description,
                evaluation_focus=", ".join(evaluation_focus),
                output_a=truncate_output(result_a.get("output", "")),
                output_b=truncate_output(result_b.get("output", "")),
            )

            scores = call_judge(prompt, timeout)

            if scores is None:
                print("FAILED (no parseable score)")
                continue

            # Determine which scores belong to which model
            if swap:
                # result_a was Flash, result_b was Pro
                scores_pro = scores.get("scores_b", {})
                scores_flash = scores.get("scores_a", {})
                winner_label = scores.get("winner", "tie")
                if winner_label == "B":
                    winner = "pro"
                elif winner_label == "A":
                    winner = "flash"
                else:
                    winner = winner_label
            else:
                # result_a was Pro, result_b was Flash
                scores_pro = scores.get("scores_a", {})
                scores_flash = scores.get("scores_b", {})
                winner_label = scores.get("winner", "tie")
                if winner_label == "A":
                    winner = "pro"
                elif winner_label == "B":
                    winner = "flash"
                else:
                    winner = winner_label

            # Compute costs
            pro_tokens = pro_result.get("token_usage", {})
            flash_tokens = flash_result.get("token_usage", {})

            def _cost(tokens: dict, pricing: dict) -> float:
                return (
                    tokens.get("input", 0) * pricing["input"]
                    + tokens.get("output", 0) * pricing["output"]
                    + tokens.get("cache_hit", 0) * pricing["cache_hit"]
                )

            run_cost_pro = _cost(pro_tokens, model_pricing["deepseek-v4-pro"])
            run_cost_flash = _cost(flash_tokens, model_pricing["deepseek-v4-flash"])

            task_cost_pro += run_cost_pro
            task_cost_flash += run_cost_flash

            eval_entry = {
                "run": run_idx,
                "scores_pro": scores_pro,
                "scores_flash": scores_flash,
                "justifications": scores.get("justifications", {}),
                "winner": winner,
                "notes": scores.get("notes", ""),
                "cost_pro": round(run_cost_pro, 6),
                "cost_flash": round(run_cost_flash, 6),
            }
            task_evaluations.append(eval_entry)

            print(
                f"winner={winner} "
                f"(pro=${run_cost_pro:.4f}, flash=${run_cost_flash:.4f})"
            )

        evaluations[task_name] = {
            "description": description,
            "runs": task_evaluations,
            "total_cost_pro": round(task_cost_pro, 6),
            "total_cost_flash": round(task_cost_flash, 6),
        }
        total_cost_pro += task_cost_pro
        total_cost_flash += task_cost_flash

    eval_doc = {
        "run_dir": run_dir,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "tasks": evaluations,
        "aggregate": {
            "total_cost_pro": round(total_cost_pro, 6),
            "total_cost_flash": round(total_cost_flash, 6),
            "cost_savings": round(total_cost_pro - total_cost_flash, 6),
            "savings_percent": (
                round(
                    (total_cost_pro - total_cost_flash) / total_cost_pro * 100, 1
                )
                if total_cost_pro > 0
                else 0.0
            ),
        },
    }

    return eval_doc


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate benchmark results using LLM judge"
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        help="Path to the run directory containing result JSON files",
    )
    parser.add_argument(
        "--tasks-dir",
        default="tasks",
        help="Directory containing task YAML files (default: tasks)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout per judge call in seconds (default: 300)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path for evaluation.json (default: <run-dir>/evaluation.json)",
    )

    args = parser.parse_args()

    run_dir = os.path.abspath(args.run_dir)
    tasks_dir = os.path.abspath(args.tasks_dir)

    print(f"Run directory: {run_dir}")
    print(f"Tasks directory: {tasks_dir}")

    eval_doc = evaluate_run(run_dir, tasks_dir, args.timeout)

    output_path = args.output or os.path.join(run_dir, "evaluation.json")
    with open(output_path, "w") as f:
        json.dump(eval_doc, f, indent=2)

    print(f"\nEvaluation saved to: {output_path}")

    # Print summary
    agg = eval_doc.get("aggregate", {})
    print(f"\nAggregate results:")
    print(f"  Total Pro cost:   ${agg.get('total_cost_pro', 0):.4f}")
    print(f"  Total Flash cost: ${agg.get('total_cost_flash', 0):.4f}")
    print(f"  Cost savings:     ${agg.get('cost_savings', 0):.4f} "
          f"({agg.get('savings_percent', 0)}%)")


if __name__ == "__main__":
    main()
