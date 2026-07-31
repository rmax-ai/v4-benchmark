#!/usr/bin/env python3
"""Generate a markdown factsheet from evaluation results."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone


def compute_avg_scores(scores_list: list[dict]) -> dict:
    """Compute average scores across multiple runs."""
    if not scores_list:
        return {"correctness": 0, "depth": 0, "actionability": 0, "structure": 0}

    keys = ["correctness", "depth", "actionability", "structure"]
    avg = {}
    for key in keys:
        vals = [s.get(key, 0) for s in scores_list if isinstance(s.get(key), (int, float))]
        avg[key] = round(sum(vals) / len(vals), 1) if vals else 0
    return avg


def count_winners(runs: list[dict]) -> dict:
    """Count winners across runs."""
    counts = {"pro": 0, "flash": 0, "tie": 0}
    for run in runs:
        w = run.get("winner", "tie")
        counts[w] = counts.get(w, 0) + 1
    return counts


def generate_report(eval_path: str, output_path: str | None = None) -> str:
    """Generate a markdown factsheet from evaluation.json."""
    if not os.path.exists(eval_path):
        print(f"Error: evaluation file not found: {eval_path}", file=sys.stderr)
        sys.exit(1)

    with open(eval_path, "r") as f:
        eval_data = json.load(f)

    lines = []

    # Title
    lines.append(
        "# DeepSeek V4-Pro vs V4-Flash-0731 — Skill Benchmark"
    )
    lines.append("")
    lines.append(
        f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*"
    )
    lines.append(
        f"*Source: `{os.path.basename(os.path.dirname(eval_path))}/{os.path.basename(eval_path)}`*"
    )
    lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append(
        "| Task | Pro Score | Flash Score | Winner | Cost Savings |"
    )
    lines.append(
        "|------|-----------|-------------|--------|--------------|"
    )

    tasks = eval_data.get("tasks", {})
    for task_name, task_data in sorted(tasks.items()):
        pro_scores = []
        flash_scores = []
        for run in task_data.get("runs", []):
            pro_scores.append(run.get("scores_pro", {}))
            flash_scores.append(run.get("scores_flash", {}))

        pro_avg = compute_avg_scores(pro_scores)
        flash_avg = compute_avg_scores(flash_scores)

        pro_total = sum(pro_avg.values())
        flash_total = sum(flash_avg.values())

        winners = count_winners(task_data.get("runs", []))
        if winners["pro"] > winners["flash"]:
            winner_str = "Pro"
        elif winners["flash"] > winners["pro"]:
            winner_str = "Flash"
        else:
            winner_str = "Tie"

        cost_pro = task_data.get("total_cost_pro", 0)
        cost_flash = task_data.get("total_cost_flash", 0)
        savings = cost_pro - cost_flash
        savings_pct = (savings / cost_pro * 100) if cost_pro > 0 else 0

        lines.append(
            f"| {task_name} | {pro_total:.1f} | {flash_total:.1f} | "
            f"{winner_str} | ${savings:.4f} ({savings_pct:.0f}%) |"
        )

    lines.append("")

    # Aggregate cost comparison
    agg = eval_data.get("aggregate", {})
    lines.append("## Cost Comparison")
    lines.append("")
    lines.append(f"- **Total Pro cost:** ${agg.get('total_cost_pro', 0):.4f}")
    lines.append(f"- **Total Flash cost:** ${agg.get('total_cost_flash', 0):.4f}")
    lines.append(
        f"- **Savings:** ${agg.get('cost_savings', 0):.4f} "
        f"({agg.get('savings_percent', 0)}%)"
    )
    lines.append("")

    # Per-task sections
    lines.append("## Per-Task Analysis")
    lines.append("")

    for task_name, task_data in sorted(tasks.items()):
        lines.append(f"### {task_name}")
        lines.append("")
        lines.append(f"*{task_data.get('description', '')}*")
        lines.append("")

        for run in task_data.get("runs", []):
            run_idx = run.get("run", "?")
            winner = run.get("winner", "tie")

            lines.append(f"**Run {run_idx}** — Winner: **{winner}**")
            lines.append("")
            lines.append("| Dimension | Pro | Flash |")
            lines.append("|-----------|-----|-------|")

            sp = run.get("scores_pro", {})
            sf = run.get("scores_flash", {})

            for dim in ["correctness", "depth", "actionability", "structure"]:
                lines.append(
                    f"| {dim} | {sp.get(dim, '-')} | {sf.get(dim, '-')} |"
                )

            lines.append("")
            lines.append(
                f"Cost: Pro ${run.get('cost_pro', 0):.4f} vs "
                f"Flash ${run.get('cost_flash', 0):.4f}"
            )
            lines.append("")

            notes = run.get("notes", "")
            if notes:
                lines.append(f"> {notes}")
                lines.append("")

        # Task-level totals
        cost_pro = task_data.get("total_cost_pro", 0)
        cost_flash = task_data.get("total_cost_flash", 0)
        savings = cost_pro - cost_flash
        savings_pct = (savings / cost_pro * 100) if cost_pro > 0 else 0
        lines.append(f"**Task cost:** Pro ${cost_pro:.4f} | Flash ${cost_flash:.4f} | Savings ${savings:.4f} ({savings_pct:.0f}%)")
        lines.append("")

    # Recommendations
    lines.append("## Recommendations")
    lines.append("")

    recommendations = []
    for task_name, task_data in sorted(tasks.items()):
        winners = count_winners(task_data.get("runs", []))
        cost_pro = task_data.get("total_cost_pro", 0)
        cost_flash = task_data.get("total_cost_flash", 0)
        savings_pct = (
            (cost_pro - cost_flash) / cost_pro * 100 if cost_pro > 0 else 0
        )

        total_runs = sum(winners.values())
        pro_win_pct = (winners["pro"] / total_runs * 100) if total_runs > 0 else 0
        flash_win_pct = (winners["flash"] / total_runs * 100) if total_runs > 0 else 0

        if flash_win_pct >= pro_win_pct and savings_pct > 50:
            rec = (
                f"- **{task_name}**: Strong candidate for Flash migration. "
                f"Flash won or tied {flash_win_pct:.0f}% of runs with "
                f"{savings_pct:.0f}% cost savings."
            )
        elif flash_win_pct >= pro_win_pct:
            rec = (
                f"- **{task_name}**: Consider Flash with monitoring. "
                f"Flash performed comparably ({flash_win_pct:.0f}% win/tie rate) "
                f"with {savings_pct:.0f}% savings."
            )
        else:
            rec = (
                f"- **{task_name}**: Keep on Pro. "
                f"Pro won {pro_win_pct:.0f}% of runs; quality difference "
                f"justifies the ${cost_pro - cost_flash:.4f} premium."
            )
        recommendations.append(rec)

    lines.extend(recommendations)
    lines.append("")

    report = "\n".join(lines)

    if output_path:
        with open(output_path, "w") as f:
            f.write(report)
        print(f"Report saved to: {output_path}")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Generate markdown factsheet from evaluation results"
    )
    parser.add_argument(
        "--eval",
        required=True,
        help="Path to evaluation.json",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path for the markdown report (default: print to stdout)",
    )

    args = parser.parse_args()

    report = generate_report(args.eval, args.output)

    if not args.output:
        print(report)


if __name__ == "__main__":
    main()
