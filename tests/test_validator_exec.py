#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#

"""Tests for the correctness validator (ValidatorExec) and its use from Mellea (no LLM needed).

The LintQ validator is tested in its plugin: plugins/validators/lintq/tests.
"""

import json
import threading

import pytest

from codehelm.validator import validator_exec
from codehelm.validator.validator_exec import ValidatorExec

CHECK = "def check(candidate):\n    assert candidate().num_qubits == 2\n"


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


def test_exec_quantumkatas_format(tmp_path):
    """QuantumKatas tests are a test_<entry_point>() function instead of check()."""
    v = _setup(ValidatorExec(), tmp_path, test="def test_add():\n    assert add(1, 2) == 3\n", entry_point="add")
    # check() is missing, so test_add() runs and passes
    assert v.validate("def add(a, b):\n    return a + b") == (True, None)


def test_exec_prepends_code_stub_prompt(tmp_path):
    """A code-stub prompt (imports + signature) is prepended to the completion."""
    v = _setup(ValidatorExec(), tmp_path, prompt="from qiskit import QuantumCircuit\n")
    passed, _ = v.validate("def bell():\n    return QuantumCircuit(2)")
    # the stub's import makes QuantumCircuit available to the completion
    assert passed is True


def test_exec_timeout_off_main_thread(tmp_path, monkeypatch):
    """Mellea validates on a worker thread, where SIGALRM is unavailable."""
    monkeypatch.setattr(validator_exec, "EXECUTION_TIMEOUT_SECONDS", 1)
    v = _setup(ValidatorExec(), tmp_path)
    out = {}
    worker = threading.Thread(target=lambda: out.update(r=v.validate("while True:\n    pass")))
    worker.start()
    worker.join(timeout=10)
    # the infinite loop was interrupted instead of hanging the thread
    assert not worker.is_alive()
    # reported as a failed timeout
    assert out["r"][0] is False and "timeout" in out["r"][1]
    # the result file is written on timeout too (get_summary needs it)
    assert json.loads((tmp_path / "sample_0" / "validator_result.json").read_text()) == {"passed": False}


def test_mellea_validation_fn_wraps_tuple():
    """codehelm (passed, info) tuples must become Mellea ValidationResults."""
    pytest.importorskip("mellea")
    from codehelm.orchestration.mellea import _to_mellea_validation_fn

    failed = _to_mellea_validation_fn(lambda ctx: (False, ["a", "b"]))(None)
    # a failed tuple becomes a falsy ValidationResult with the joined reason
    assert not bool(failed) and failed.reason == "a\nb"
    # a passed tuple becomes a truthy ValidationResult
    assert bool(_to_mellea_validation_fn(lambda ctx: (True, None))(None))
