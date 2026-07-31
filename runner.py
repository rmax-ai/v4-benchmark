#!/usr/bin/env python3
"""Benchmark runner: execute Hermes agent tasks and capture results."""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

import yaml


def load_task(task_name: str, tasks_dir: str = "tasks") -> dict:
    """Load a task definition from a YAML file."""
    task_path = os.path.join(tasks_dir, f"{task_name}.yaml")
    if not os.path.exists(task_path):
        print(f"Error: task file not found: {task_path}", file=sys.stderr)
        sys.exit(1)
    with open(task_path, "r") as f:
        return yaml.safe_load(f)


def list_tasks(tasks_dir: str = "tasks") -> list[str]:
    """List all available task names from the tasks directory."""
    if not os.path.isdir(tasks_dir):
        return []
    tasks = []
    for fname in sorted(os.listdir(tasks_dir)):
        if fname.endswith(".yaml"):
            tasks.append(fname[:-5])  # strip .yaml
    return tasks


def parse_token_usage(output: str) -> dict:
    """Attempt to extract token usage stats from hermes output."""
    usage = {"input": 0, "output": 0, "cache_hit": 0}

    # Try to find JSON token usage block
    json_match = re.search(
        r'"token_?usage"\s*:\s*\{[^}]+\}',
        output,
        re.IGNORECASE,
    )
    if json_match:
        try:
            block = json_match.group(0)
            # The block looks like: "token_usage": {...}
            # Extract just the JSON part
            inner = block[block.index("{") : block.rindex("}") + 1]
            data = json.loads(inner)
            usage["input"] = int(data.get("input", data.get("input_tokens", 0)))
            usage["output"] = int(data.get("output", data.get("output_tokens", 0)))
            usage["cache_hit"] = int(
                data.get("cache_hit", data.get("cache_read_input_tokens", 0))
            )
            return usage
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

    # Fallback: scan for labeled token counts
    patterns = {
        "input": [
            r"(?:input|prompt)\s*tokens?:?\s*(\d[\d,]*)",
            r'"input_?tokens"\s*:\s*(\d+)',
        ],
        "output": [
            r"(?:output|completion)\s*tokens?:?\s*(\d[\d,]*)",
            r'"output_?tokens"\s*:\s*(\d+)',
        ],
        "cache_hit": [
            r"cache\s*(?:hit|read)\s*tokens?:?\s*(\d[\d,]*)",
            r'"cache_?(?:hit|read_input_tokens)"\s*:\s*(\d+)',
        ],
    }

    for key, pats in patterns.items():
        for pat in pats:
            m = re.search(pat, output, re.IGNORECASE)
            if m:
                try:
                    usage[key] = int(m.group(1).replace(",", ""))
                except ValueError:
                    pass
                break

    return usage


def run_single(
    task_def: dict,
    model: str,
    run_index: int,
    timeout: int = 300,
) -> dict:
    """Run a single benchmark and return the result record."""
    task_name = task_def["name"]
    prompt = task_def["prompt"]
    skills = task_def.get("skills", [])
    workdir = task_def.get("workdir", os.getcwd())

    errors = []
    stdout = ""
    stderr = ""
    exit_code = -1
    wall_time_s = 0.0

    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        # Build command as list — no shell=True, no quoting issues
        cmd = ["hermes", "chat", "-q", prompt, "-m", model]
        if skills:
            cmd.extend(["-s", ",".join(skills)])

        start = time.perf_counter()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
        )
        wall_time_s = time.perf_counter() - start

        stdout = result.stdout
        stderr = result.stderr
        exit_code = result.returncode

        if result.returncode != 0:
            errors.append(
                f"Hermes exited with code {result.returncode}: {stderr[:500]}"
            )

    except subprocess.TimeoutExpired:
        wall_time_s = timeout
        exit_code = -1
        errors.append(f"Timeout after {timeout}s")
        stderr = "TimeoutExpired"

    except FileNotFoundError:
        exit_code = -1
        errors.append("hermes command not found in PATH")
        stderr = "FileNotFoundError: hermes"

    except Exception as e:
        exit_code = -1
        errors.append(f"Unexpected error: {e}")
        stderr = str(e)

    # Parse token usage from stdout
    token_usage = parse_token_usage(stdout) if stdout else {
        "input": 0,
        "output": 0,
        "cache_hit": 0,
    }

    return {
        "task": task_name,
        "model": model,
        "run": run_index,
        "timestamp": timestamp,
        "wall_time_s": round(wall_time_s, 2),
        "exit_code": exit_code,
        "output": stdout,
        "stderr": stderr,
        "token_usage": token_usage,
        "errors": errors,
    }


def run_benchmarks(
    task_names: list[str],
    models: list[str],
    n_runs: int,
    results_dir: str,
    tasks_dir: str = "tasks",
    timeout: int = 300,
) -> str:
    """Run all benchmarks and return the results directory path."""
    os.makedirs(results_dir, exist_ok=True)

    for task_name in task_names:
        task_def = load_task(task_name, tasks_dir)
        print(f"\n{'=' * 60}")
        print(f"Task: {task_def['name']} — {task_def['description']}")
        print(f"{'=' * 60}")

        for model in models:
            print(f"\n  Model: {model}")
            for run_i in range(1, n_runs + 1):
                print(f"    Run {run_i}/{n_runs}...", end=" ", flush=True)

                result = run_single(task_def, model, run_i, timeout)

                status = "OK" if result["exit_code"] == 0 else "FAIL"
                print(
                    f"{status} ({result['wall_time_s']:.1f}s, "
                    f"in={result['token_usage']['input']}, "
                    f"out={result['token_usage']['output']})"
                )

                # Save result JSON
                out_name = f"{task_name}-{model}-run{run_i}.json"
                out_path = os.path.join(results_dir, out_name)
                with open(out_path, "w") as f:
                    json.dump(result, f, indent=2)

    # Write summary
    summary = {
        "tasks": task_names,
        "models": models,
        "n_runs": n_runs,
        "results_dir": results_dir,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    summary_path = os.path.join(results_dir, "summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nResults saved to: {results_dir}")
    return results_dir


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark runner for Hermes agent tasks"
    )
    parser.add_argument(
        "--task",
        required=True,
        help="Task name (e.g., okf-curation) or 'all' for all tasks",
    )
    parser.add_argument(
        "--model",
        default="deepseek-v4-pro",
        help="Model name (default: deepseek-v4-pro)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of runs per task/model (default: 1)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run both deepseek-v4-pro and deepseek-v4-flash",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout per run in seconds (default: 300)",
    )
    parser.add_argument(
        "--tasks-dir",
        default="tasks",
        help="Directory containing task YAML files (default: tasks)",
    )
    parser.add_argument(
        "--results-dir",
        default=None,
        help="Custom results directory (default: auto-generated with timestamp)",
    )

    args = parser.parse_args()

    # Determine task list
    if args.task == "all":
        task_names = list_tasks(args.tasks_dir)
        if not task_names:
            print("Error: no tasks found in tasks directory", file=sys.stderr)
            sys.exit(1)
        print(f"Running all tasks: {', '.join(task_names)}")
    else:
        task_names = [args.task]

    # Determine model list
    if args.compare:
        models = ["deepseek-v4-pro", "deepseek-v4-flash"]
    else:
        models = [args.model]

    # Create results directory
    if args.results_dir:
        results_dir = args.results_dir
    else:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        results_dir = os.path.join("results", f"run-{ts}")

    print(f"Models: {', '.join(models)}")
    print(f"Runs per model: {args.runs}")
    print(f"Results directory: {results_dir}")

    run_benchmarks(
        task_names=task_names,
        models=models,
        n_runs=args.runs,
        results_dir=results_dir,
        tasks_dir=args.tasks_dir,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    main()
