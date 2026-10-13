# Correctness + LintQ with Mellea

`ValidatorLintQ` (`src/codehelm/validator/validator_lintq.py`) wraps a correctness
validator (default `ValidatorExec`): the code must first pass the problem's tests, then
raise no [LintQ](https://github.com/sola-st/LintQ) warnings. Failures, LintQ findings
included, are fed back to the model by the repair strategy. It is adapted from Mellea's
`qiskit_code_validation` example.

## Setup

LintQ needs the [CodeQL CLI](https://codeql.github.com/) on `PATH`:

```bash
git clone --depth 1 https://github.com/sola-st/LintQ.git
(cd LintQ/qlint/codeql/src && codeql pack install)
export LINTQ_DIR="$(pwd)/LintQ"
```

`config.yaml` uses a local [Ollama](https://ollama.com/) server:

```bash
ollama pull hf.co/Qiskit/mistral-small-3.2-24b-qiskit-GGUF:latest
```

## Run

```bash
python examples/mellea_lintq/run.py
```

The script downloads [Qiskit HumanEval](https://github.com/qiskit-community/qiskit-human-eval)
and runs its first `num_samples` problems (set in `config.yaml`). Everything is written to
`results/` (then `results_v2/`, ...) in this folder: the problems used (`dataset.json`),
a `sample_N/` folder per problem with its `lintq_result.json` (`passed`, `tests_passed`,
`lintq_findings`), and `summary.json` and `lintq_summary.json` collating them. `ValidatorExec` handles both
Qiskit HumanEval (`check(candidate)`) and QuantumKatas (`test_<entry_point>()`) tests.

The same setup is tested end to end in `tests/test_lintq.py`.
