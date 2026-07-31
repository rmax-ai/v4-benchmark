# V4 Benchmark Harness — Spec

## Goal
Build a CLI tool that benchmarks DeepSeek V4-Pro vs V4-Flash-0731 on Max's most important Hermes cron job skills.

## Architecture

```
v4-benchmark/
├── tasks/                  # Frozen task definitions (YAML)
│   ├── okf-curation.yaml
│   ├── ai-paper-digest.yaml
│   ├── hn-digest.yaml
│   ├── gh-trending.yaml
│   └── email-processor.yaml
├── runner.py              # Main CLI: run benchmarks
├── evaluate.py            # Compare outputs, produce scores
├── report.py              # Generate factsheet (markdown + JSON)
├── results/               # Output directory (gitignored)
│   └── run-<ts>/
│       ├── <task>-<model>-run<N>.json
│       └── summary.json
├── requirements.txt
└── README.md
```

## Task Definition Format (tasks/*.yaml)

```yaml
name: okf-curation
description: "Daily knowledge graph curation using personal-knowledge-management skill"
skills:
  - personal-knowledge-management
prompt: |
  <the exact prompt from the cron job>
toolsets:
  - file
  - terminal
  - web
workdir: /home/rmax-10/src/rmax-ai/knowledge-graph
evaluation_focus:
  - correctness
  - depth
  - actionability
```

## Runner (runner.py)

CLI:
```
python runner.py --task okf-curation --model deepseek-v4-pro --runs 3
python runner.py --task all --models deepseek-v4-pro,deepseek-v4-flash --runs 3
python runner.py --task okf-curation --compare  # runs both models
```

Behavior:
1. Load task YAML
2. For each run (1..N):
   a. Construct a delegate_task call: goal=<prompt>, context=<skills+workdir info>, toolsets=<toolsets>
   b. Record start time
   c. Execute via `hermes chat -q -m <model> -s <skills> "<prompt>"` with a timeout
   d. Capture: stdout, stderr, exit code, wall time
   e. Parse token usage from output if available
   f. Save structured result to results/<run-ts>/<task>-<model>-run<N>.json
3. Print summary

Result JSON schema:
```json
{
  "task": "okf-curation",
  "model": "deepseek-v4-pro",
  "run": 1,
  "timestamp": "2026-07-31T20:00:00Z",
  "wall_time_s": 45.2,
  "exit_code": 0,
  "output": "<full agent output>",
  "token_usage": {"input": 12345, "output": 2345, "cache_hit": 10000},
  "errors": []
}
```

## Evaluator (evaluate.py)

```
python evaluate.py --run-dir results/run-20260731-200000
```

For each task, compares Pro vs Flash outputs across the N runs.

Dimensions (per the plan):
- **correctness** (0-10): factual errors, hallucinations, tool-use failures
- **depth** (0-10): non-obvious connections, synthesis quality
- **actionability** (0-10): directly usable vs needs rework
- **structure** (0-10): format quality, scannability
- **cost** ($): actual token cost

The evaluator uses an LLM judge (deepseek-v4-pro) to score outputs blind (model labels hidden). The judge gets:
- The task definition
- Output A and Output B (shuffled, unlabeled)
- The scoring rubric

Produces `evaluation.json` with per-dimension scores.

## Report Generator (report.py)

```
python report.py --eval results/run-<ts>/evaluation.json --output results/run-<ts>/factsheet.md
```

Produces a markdown factsheet with:
1. Summary verdict table
2. Per-task side-by-side comparison with excerpted examples
3. Cost comparison (total + per-task)
4. Recommendation: which tasks can move from Pro→Flash

## Implementation Notes

- Use Python 3.12+, stdlib + PyYAML only (minimal deps)
- `hermes chat -q` is the execution vehicle — it's what cron jobs use
- Model names: `deepseek-v4-pro` and `deepseek-v4-flash`
- The Flash model auto-routes to Flash-0731 since that's the current API default
- Results directory is gitignored
- All paths should be absolute or relative to repo root
- Handle failures gracefully: if a run times out or errors, record it and continue

## Task Prompts to Extract

Pull from existing cron jobs:
1. **okf-curation**: job `f43bc553c579` (OKF Daily Curation) — v4-pro currently
2. **ai-paper-digest**: job `a5b4ba412355` (AI Paper Digests) — v4-flash currently
3. **hn-digest**: job `d19fcaea85b0` (HN AI Digest) — v4-flash currently
4. **gh-trending**: job `d0f51980d125` (GitHub Trending Weekly Insights) — v4-pro currently
5. **email-processor**: job `02f405fb194e` (email-queue-processor) — v4-flash currently

Extract via: `hermes cron list` for structure, then inspect job files for full prompts.

## Deliverables

1. Working `runner.py` that can execute benchmarks
2. Working `evaluate.py` with LLM judge
3. Working `report.py` with factsheet output
4. 5 task YAML files with frozen prompts
5. README.md with usage instructions
6. requirements.txt (pyyaml only)
