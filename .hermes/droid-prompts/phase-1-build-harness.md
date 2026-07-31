IMPLEMENT the v4-benchmark harness as specified in SPEC.md. Do NOT produce a research report. Write code now and run the verification commands.

## Context

Repo: /home/rmax-10/src/rmax-ai/v4-benchmark (fresh, only SPEC.md exists)
Python: 3.12, use uv for package management
Project: Benchmark harness comparing deepseek-v4-pro vs deepseek-v4-flash on Hermes cron job skills

## What to build (4 Python files + 5 task YAMLs + requirements.txt + README.md)

### 1. requirements.txt
Just `pyyaml` — minimal deps. Use stdlib for everything else.

### 2. tasks/*.yaml (5 files)

Extract the EXACT prompts from these cron jobs. Use `hermes cron list` to see them, then inspect the job files for full prompts. The jobs live in ~/.hermes/cron/jobs.json or similar.

Tasks to extract:
- **okf-curation**: job f43bc553c579 (OKF Daily Curation) — skills: personal-knowledge-management, toolsets: file/terminal/web, workdir: /home/rmax-10/src/rmax-ai/knowledge-graph
- **ai-paper-digest**: job a5b4ba412355 (AI Paper Digests) — skills: arxiv, toolsets: web/file/terminal, workdir: /home/rmax-10/src/rmax-ai/knowledge-graph
- **hn-digest**: job d19fcaea85b0 (HN AI Digest) — no skills, just prompt
- **gh-trending**: job d0f51980d125 (GitHub Trending Weekly Insights) — script: gh-trending-insights.py
- **email-processor**: job 02f405fb194e (email-queue-processor) — skills: himalaya, script: email_queue_process.sh

Format each YAML exactly like:
```yaml
name: okf-curation
description: "..."
skills:
  - skill-name
prompt: |
  exact multiline prompt here
toolsets:
  - file
  - terminal
  - web
workdir: /absolute/path
evaluation_focus:
  - correctness
  - depth
  - actionability
```

If you cannot extract the exact prompt from cron storage, write a representative prompt based on the job name/description/skills that exercises the same capability. The runner must work with these.

### 3. runner.py

CLI using argparse. Commands:

```
python runner.py --task okf-curation --model deepseek-v4-pro --runs 3
python runner.py --task all --models deepseek-v4-pro,deepseek-v4-flash --runs 3
python runner.py --task okf-curation --compare  # runs both models, N runs each
```

Behavior:
1. Load task YAML from tasks/<name>.yaml
2. Construct a shell command: `hermes chat -q -m <model> -s <skills> "<prompt>"` with --cwd if workdir set
3. Execute it N times per model
4. For each run, capture: stdout, stderr, exit code, wall time
5. Save structured result JSON to results/<run-timestamp>/<task>-<model>-run<N>.json
6. Print progress and summary

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

Handle: timeouts (default 300s per run), non-zero exits, missing hermes CLI. Use subprocess.run with timeout. Use tempfile for prompts with special chars. The --compare flag runs both models and produces a comparison summary.

### 4. evaluate.py

```
python evaluate.py --run-dir results/run-20260731-200000
```

Loads all result JSONs from the run directory. For each task, compares Pro vs Flash outputs.

Scoring approach:
- For each task, pass both outputs to an LLM judge (hermes chat -q -m deepseek-v4-pro) with a structured rubric
- The judge sees outputs A and B (shuffled, model labels hidden)
- Scores each on: correctness (0-10), depth (0-10), actionability (0-10), structure (0-10)
- Computes cost from token_usage fields
- Produces evaluation.json

Judge prompt template should be in the code, asking the LLM to:
1. Read both outputs
2. Score each on the 4 dimensions with brief justifications
3. Note any hallucinations or errors
4. Pick a winner for each dimension

Output evaluation.json schema:
```json
{
  "run_dir": "results/run-20260731-200000",
  "evaluated_at": "2026-07-31T21:00:00Z",
  "tasks": {
    "okf-curation": {
      "models": {
        "deepseek-v4-pro": {
          "scores": {"correctness": 8, "depth": 9, "actionability": 7, "structure": 8},
          "avg_cost": 0.012,
          "avg_wall_time_s": 45.2,
          "errors": 0
        },
        "deepseek-v4-flash": {
          "scores": {"correctness": 7, "depth": 7, "actionability": 8, "structure": 7},
          "avg_cost": 0.003,
          "avg_wall_time_s": 22.1,
          "errors": 1
        }
      },
      "verdict": "Pro wins on depth and correctness, Flash is faster/cheaper and adequate for actionability",
      "cost_savings_if_switch": "$0.009/run"
    }
  }
}
```

### 5. report.py

```
python report.py --eval results/run-<ts>/evaluation.json --output results/run-<ts>/factsheet.md
```

Generates a markdown factsheet with:
1. Title and metadata
2. Summary table: Task | Pro Score | Flash Score | Winner | Cost Savings if Switch
3. Per-task detailed comparison with excerpted output examples
4. Aggregate cost comparison
5. Recommendation section: which tasks should move Pro→Flash

### 6. README.md

Usage instructions, setup (uv venv && uv pip install -r requirements.txt), examples.

## Implementation Rules

- All Python files must be executable (`chmod +x`)
- Use Python 3.12+ features (pathlib, f-strings, type hints)
- Handle errors gracefully: log and continue, don't crash on single-run failures
- Create results/ directory if missing, add to .gitignore
- Run `uv venv && uv pip install pyyaml` to set up deps
- Verify each file runs with --help before finishing

## Verification (run these after writing code)

```bash
cd /home/rmax-10/src/rmax-ai/v4-benchmark
python runner.py --help
python evaluate.py --help
python report.py --help
ls -la tasks/
cat tasks/okf-curation.yaml | head -5
```

Do NOT skip verification. Write all files, then run the verification commands.
