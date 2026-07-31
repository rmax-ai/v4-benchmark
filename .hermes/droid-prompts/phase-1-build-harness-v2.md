IMPLEMENT the following changes. Do NOT produce a research report. Write code now and run the verification commands at the end.

WORKING DIRECTORY: /home/rmax-10/src/rmax-ai/v4-benchmark
PYTHON: 3.12, use uv for package management (uv venv, uv pip install)

FILE 1: requirements.txt
Content: pyyaml

FILE 2: .gitignore
Content:
results/
__pycache__/
.venv/
*.pyc

FILE 3: tasks/okf-curation.yaml
```yaml
name: okf-curation
description: "Daily knowledge graph curation using personal-knowledge-management skill"
skills:
  - personal-knowledge-management
prompt: |
  You are the OKF Daily Curation agent. Run the full daily curation pipeline against the knowledge graph at /home/rmax-10/src/rmax-ai/knowledge-graph.

  Steps:
  1. Scan the knowledge graph for new or modified place files since the last curation run
  2. Identify entities that lack cross-references or have stale information
  3. Enrich under-connected nodes by finding relationships to other entities in the graph
  4. Add bidirectional links between related entities
  5. Update any outdated descriptions or metadata
  6. Report: what was changed, what still needs attention

  Work autonomously. Do not ask questions.
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

FILE 4: tasks/ai-paper-digest.yaml
```yaml
name: ai-paper-digest
description: "Daily AI paper digest from arXiv using arxiv skill"
skills:
  - arxiv
prompt: |
  You are running a daily AI paper digest for Max. It's morning in Amsterdam (CEST, UTC+2).

  Search arXiv for the most important AI/ML papers from the last 24 hours across:
  - Large language models and transformers
  - AI agents and agentic systems
  - Reinforcement learning and alignment
  - Computer vision and multimodal models
  - AI infrastructure and systems

  For each paper found:
  - Provide title, authors, and a 2-3 sentence summary of the key contribution
  - Note if it's particularly relevant to Max's work (agent infrastructure, MCP, governed AI workflows)

  Produce a ranked digest of the top 5-8 papers. Sort by relevance and potential impact.
  Format as a clear, scannable digest with paper titles as headings.
toolsets:
  - web
  - file
  - terminal
workdir: /home/rmax-10/src/rmax-ai/knowledge-graph
evaluation_focus:
  - correctness
  - depth
  - actionability
```

FILE 5: tasks/hn-digest.yaml
```yaml
name: hn-digest
description: "Hacker News AI-focused story digest"
skills: []
prompt: |
  You are running an AI-focused Hacker News digest for Max.

  Fetch the top 30 stories from Hacker News (use the HN API or web extraction).
  Filter for stories related to:
  - AI, machine learning, LLMs
  - Software engineering and developer tools
  - Startups and technology business
  - Open source projects
  - Infrastructure and DevOps

  For each relevant story:
  - Provide the title and a 1-2 sentence summary
  - Include the HN points and comment count
  - Note why it matters

  Produce a ranked digest of the top 5-8 most interesting stories.
  Format as a clear digest with story titles as headings.
toolsets:
  - web
  - file
evaluation_focus:
  - correctness
  - depth
  - actionability
```

FILE 6: tasks/gh-trending.yaml
```yaml
name: gh-trending
description: "Weekly GitHub trending repositories analysis and insights"
skills: []
prompt: |
  You are producing the weekly GitHub Trending Consolidated Insights report.

  Analyze this week's trending repositories on GitHub. Focus on:
  - AI/ML tools and frameworks
  - Developer tools and infrastructure
  - New programming languages or paradigms
  - Notable open source projects

  For each significant repository:
  - Name, description, language, stars gained this week
  - What problem it solves and who it's for
  - Technical assessment: architecture quality, code health signals
  - Relevance to Max's work (agent infrastructure, MCP, governed AI)

  Produce a consolidated insights report with:
  1. Top 10 trending repos with analysis
  2. Emerging trends and patterns across repos
  3. Recommendations: which repos are worth deeper investigation

  Format as a structured markdown report.
toolsets:
  - web
  - terminal
  - file
evaluation_focus:
  - correctness
  - depth
  - actionability
```

FILE 7: tasks/email-processor.yaml
```yaml
name: email-processor
description: "Process pending emails from inbox using himalaya CLI"
skills:
  - himalaya
prompt: |
  Process pending emails from me@rmax.io in the email queue.

  Steps:
  1. Check the email queue for pending messages
  2. For each pending email:
     a. Read the full content
     b. Categorize: action required, FYI, newsletter, spam
     c. For action-required: draft a response or note what action is needed
     d. For newsletters: extract key highlights
  3. Produce a summary report:
     - Total emails processed
     - Action items identified
     - Key highlights from newsletters
     - Anything urgent that needs immediate attention

  Work autonomously. Process all pending emails.
toolsets:
  - terminal
  - web
evaluation_focus:
  - correctness
  - actionability
  - structure
```

FILE 8: runner.py
Create a CLI using argparse that:
- Loads task YAML files from tasks/<name>.yaml
- Runs `hermes chat -q -m <model> -s <skill1,skill2> "<prompt>"` 
- Supports --task, --model, --runs, --compare flags
- Captures stdout, stderr, exit_code, wall_time for each run
- Saves structured JSON results to results/<timestamp>/<task>-<model>-run<N>.json
- Uses subprocess.run with timeout=300
- Uses tempfile for prompts with special characters
- Handles errors gracefully (log and continue)
- Creates results directory if missing

Result JSON schema:
```python
{
    "task": str,
    "model": str,
    "run": int,
    "timestamp": str,  # ISO format
    "wall_time_s": float,
    "exit_code": int,
    "output": str,  # full stdout
    "stderr": str,
    "token_usage": {"input": int, "output": int, "cache_hit": int},
    "errors": list[str]
}
```

The --compare flag runs both deepseek-v4-pro and deepseek-v4-flash for the task.

FILE 9: evaluate.py
CLI using argparse that:
- Loads all result JSONs from a run directory
- For each task, constructs a blind comparison prompt for an LLM judge
- Calls the judge via `hermes chat -q -m deepseek-v4-pro` with both outputs (shuffled, labels hidden)
- Judge scores each output on correctness, depth, actionability, structure (0-10)
- Computes cost from token_usage
- Saves evaluation.json

Judge prompt template (in Python code):
"""
You are evaluating two AI agent outputs for the same task. Output A and Output B are from different models. Score each on:

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
{{"scores_a": {{"correctness": N, "depth": N, "actionability": N, "structure": N}}, "scores_b": {{...}}, "justifications": {{...}}, "winner": "A" or "B" or "tie", "notes": "..."}}
"""

FILE 10: report.py
CLI using argparse that:
- Reads evaluation.json
- Generates a markdown factsheet with:
  1. Title: "DeepSeek V4-Pro vs V4-Flash-0731 — Skill Benchmark"
  2. Summary table: Task | Pro Score | Flash Score | Winner | Cost Savings
  3. Per-task sections with score breakdowns and excerpts
  4. Aggregate cost comparison
  5. Recommendations

FILE 11: README.md
```markdown
# v4-benchmark

Benchmark harness comparing DeepSeek V4-Pro vs V4-Flash-0731 on Hermes agent skills.

## Setup
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

## Usage

### Run a single benchmark
python runner.py --task okf-curation --model deepseek-v4-pro --runs 3

### Compare both models
python runner.py --task okf-curation --compare --runs 3

### Run all benchmarks
python runner.py --task all --compare --runs 3

### Evaluate results
python evaluate.py --run-dir results/run-<timestamp>

### Generate report
python report.py --eval results/run-<timestamp>/evaluation.json
```

AFTER writing all files, run these verification commands:
1. cd /home/rmax-10/src/rmax-ai/v4-benchmark && python runner.py --help
2. cd /home/rmax-10/src/rmax-ai/v4-benchmark && python evaluate.py --help
3. cd /home/rmax-10/src/rmax-ai/v4-benchmark && python report.py --help
4. ls -la tasks/
5. cd /home/rmax-10/src/rmax-ai/v4-benchmark && uv venv && uv pip install pyyaml

If any command fails, fix the code and re-run until all pass. Do NOT skip verification.
