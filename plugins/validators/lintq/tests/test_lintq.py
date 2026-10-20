"""Tests for the LintQ validator plugin, run from the repository root.

The first tests run offline; the last ones run the whole Mellea pipeline with a real LLM.
LintQ tests are skipped until CodeQL and LintQ are installed (codehelm-lintq-install).
"""

import json
import os
import urllib.request
from pathlib import Path

import pytest
import yaml
from codehelm_lintq import ValidatorLintQ
from codehelm_lintq.install import is_installed

from codehelm.algorithms.validator_feedback.feeback import Feedback
from codehelm.utils.utils import resolve_env_vars
from codehelm.validator.validator_exec import ValidatorExec


def _ollama_available():
    """Check if an Ollama server is running locally."""
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        return True
    except OSError:
        return False


# Reusable skip markers
requires_lintq = pytest.mark.skipif(
    not is_installed(),
    reason="CodeQL and LintQ are not installed yet: run codehelm-lintq-install.",
)
requires_ollama = pytest.mark.skipif(
    not _ollama_available(),
    reason="An Ollama server on localhost:11434 is required but not available.",
)
# tests/test_configs/mellea.yaml reads these through "env:" values
requires_litellm_env = pytest.mark.skipif(
    not all(v in os.environ for v in ("MODEL_ID", "API_BASE", "OPENAI_API_KEY")),
    reason="MODEL_ID, API_BASE and OPENAI_API_KEY are required for the LiteLLM test.",
)

CHECK = "def check(candidate):\n    assert candidate().num_qubits == 2\n"
CLEAN = (
    "from qiskit import QuantumCircuit\n"
    "def bell():\n"
    "    qc = QuantumCircuit(2, 2)\n"
    "    qc.h(0)\n"
    "    qc.cx(0, 1)\n"
    "    qc.measure([0, 1], [0, 1])\n"
    "    return qc\n"
)
# Passes CHECK, but measures qubit 0 twice and applies a gate after measuring it.
BUGGY = (
    "from qiskit import QuantumCircuit\n"
    "def bell():\n"
    "    qc = QuantumCircuit(2, 2)\n"
    "    qc.h(0)\n"
    "    qc.measure(0, 0)\n"
    "    qc.x(0)\n"
    "    qc.measure(0, 0)\n"
    "    return qc\n"
)


def _setup(validator, tmp_path, test=CHECK, entry_point="bell", prompt="Write bell()."):
    validator.setup(
        sample_dir=str(tmp_path / "sample_0"),
        sample_num=0,
        test=test,
        test_format="human_eval",
        entry_point=entry_point,
        prompt=prompt,
    )
    return validator


def test_lintq_skipped_when_tests_fail(tmp_path):
    """LintQ is not run on code that fails the tests (so this runs without codeql)."""
    v = _setup(ValidatorLintQ(), tmp_path)
    passed, failure_info = v.validate("def bell():\n    return None")
    # fails, with failure_info as a list (runners join it with newlines)
    assert passed is False and isinstance(failure_info, list)
    result = json.loads((tmp_path / "sample_0" / "lintq_result.json").read_text())
    # LintQ was not run: lintq_findings is None, not []
    assert result == {"passed": False, "tests_passed": False, "lintq_findings": None}


@requires_lintq
def test_lintq_clean_and_buggy(tmp_path):
    v = _setup(ValidatorLintQ(), tmp_path)
    # correct code with no LintQ warnings passes (markdown fence stripped)
    assert v.validate(f"```python\n{CLEAN}```") == (True, None)

    passed, failure_info = v.validate(BUGGY)
    # passes the tests but LintQ flags it, and the warnings are the failure reason
    assert passed is False and failure_info[0].startswith("LintQ warnings:")

    summary = v.get_summary(tmp_path)
    # summary counts the last attempt: tests passed, flagged by LintQ, not passed
    assert summary == {"total": 1, "tests_passed": 1, "flagged_by_lintq": 1, "passed": 0}


# --- End-to-end: MelleaRunner + LLM + correctness + LintQ ------------------------


class RecordingFeedback(Feedback):
    """Feedback that records the failure info it receives, i.e. what reaches the model."""

    def __init__(self):
        super().__init__()
        self.failures = []

    def repair(self, prompt, failure_info):
        self.failures.append(failure_info)
        return super().repair(prompt, failure_info)


def _bell_dataset(tmp_path):
    """A one-problem dataset, so the end-to-end tests need no dataset file."""
    dataset = tmp_path / "bell_dataset.json"
    dataset.write_text(json.dumps([{
        "prompt": "Write a Python function `bell()` that returns a QuantumCircuit with 2 qubits and "
                  "2 classical bits that prepares a Bell state and measures both qubits.",
        "test": CHECK,
        "entry_point": "bell",
    }]))
    return str(dataset)


def _run_mellea_lintq(config_path, results_dir, dataset):
    from codehelm.algorithms.validator_feedback.mellea_strategy import (
        MelleaFeedbackStrategy,
    )
    from codehelm.orchestration.mellea import MelleaRunner

    with open(config_path, "r") as file:
        config = yaml.safe_load(file)
    resolve_env_vars(config)

    feedback = RecordingFeedback()
    runner = MelleaRunner(config,
                          results_dir=str(results_dir),
                          validator=ValidatorLintQ(ValidatorExec()),
                          repair_strategy=MelleaFeedbackStrategy(feedback))
    runner.parse_data(dataset=dataset,
                      num_samples=config["num_samples"])
    summary = runner.validator.get_summary(results_dir)
    return config, summary, feedback.failures


def _check_results(results_dir, summary, num_samples, failures):
    """The pipeline ran correctly, whatever the model generated."""
    # one lintq_result.json per sample
    assert summary["total"] == num_samples
    n_failed = 0
    for sample_dir in Path(results_dir).glob("sample_*"):
        result = json.loads((sample_dir / "lintq_result.json").read_text())
        # passed = tests passed and LintQ ran without findings
        assert result["passed"] == (result["tests_passed"] and result["lintq_findings"] == [])
        if not result["passed"]:
            n_failed += 1
            # Mellea used the whole loop budget (3 attempts -> 2 retry dirs)
            assert (sample_dir / "retry_1").is_dir()
    # every failed sample sent at least 2 failures (2 repairs) back to the model
    assert len(failures) >= 2 * n_failed
    # no failure was fed back with an empty reason
    assert all(failures)


@requires_lintq
@requires_ollama
def test_mellea_lintq_ollama(tmp_path):
    _, summary, failures = _run_mellea_lintq("examples/mellea_lintq/config.yaml", tmp_path, _bell_dataset(tmp_path))
    _check_results(tmp_path, summary, 1, failures)


@requires_lintq
@requires_ollama
def test_mellea_lintq_feedback_ollama(tmp_path):
    """Code that passes the tests but breaks a LintQ rule: the LintQ warning must reach the model."""
    dataset = tmp_path / "lintq_dataset.json"
    dataset.write_text(json.dumps([{
        "prompt": "Write a Python function `build()` that creates a QuantumCircuit with 2 qubits and "
                  "2 classical bits, applies H on qubit 0, measures qubit 0 into bit 0, then applies X "
                  "on qubit 0 and measures qubit 0 into bit 0 again. Return the circuit.",
        "test": CHECK,
        "entry_point": "build",
    }]))
    results_dir = tmp_path / "results"
    _, summary, failures = _run_mellea_lintq("examples/mellea_lintq/config.yaml", results_dir, str(dataset))
    _check_results(results_dir, summary, 1, failures)
    # the LintQ warning reached the model as repair feedback
    assert any("LintQ warnings" in f for f in failures)


@requires_lintq
@requires_litellm_env
def test_mellea_lintq_litellm(tmp_path):
    _, summary, failures = _run_mellea_lintq("tests/test_configs/mellea.yaml", tmp_path, _bell_dataset(tmp_path))
    _check_results(tmp_path, summary, 1, failures)
