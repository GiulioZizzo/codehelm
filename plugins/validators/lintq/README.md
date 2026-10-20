# codehelm-lintq

codehelm validator plugin for [LintQ](https://github.com/sola-st/LintQ), a set of
[CodeQL](https://codeql.github.com/) queries that find bugs in Qiskit programs.

`ValidatorLintQ` wraps a correctness validator (default `ValidatorExec`): the code must
first pass the problem's tests, then raise no LintQ warnings. Failures, LintQ findings
included, are fed back to the model by the repair strategy.

## Install

From the repository root, with codehelm already installed:

```bash
pip install -e plugins/validators/lintq
```

There is no manual LintQ setup: on first use the plugin downloads a pinned CodeQL CLI
(0.5-1 GB, checked against its published SHA-256) and a pinned LintQ commit, and installs
the CodeQL libraries LintQ needs. They are cached in `~/.cache/codehelm-lintq` (override
with `CODEHELM_LINTQ_HOME`). To download them ahead of time:

```bash
codehelm-lintq-install
```

A `codeql` already on `PATH` and a LintQ checkout in `LINTQ_DIR` are used instead, if present.

## Usage

```python
from codehelm_lintq import ValidatorLintQ
from codehelm.validator.validator_exec import ValidatorExec

validator = ValidatorLintQ(ValidatorExec())
```

Each sample gets a `lintq_result.json` (`passed`, `tests_passed`, `lintq_findings`), and
`get_summary()` writes `lintq_summary.json` next to the correctness `summary.json`. See
`examples/mellea_lintq/` for a full run with Mellea.

## Tests

From the repository root (the LintQ tests are skipped until CodeQL and LintQ are installed;
the end-to-end ones also need Ollama, see `examples/mellea_lintq/README.md`):

```bash
pytest plugins/validators/lintq/tests -v
```
