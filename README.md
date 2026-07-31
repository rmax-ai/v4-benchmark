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
