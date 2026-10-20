#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#

"""
LintQ validator: the code must pass a correctness validator, then LintQ.

CodeQL and LintQ are downloaded on first use (see install.py).
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from codehelm.utils.utils import extract_code_from_llm_response
from codehelm.validator.validator_base import BaseValidator
from codehelm.validator.validator_exec import ValidatorExec
from codehelm_lintq.install import codeql, lintq_dir


def run_lintq(code: str) -> list[str]:
    """Run the LintQ queries over code; return one [rule-id] message per finding."""
    lintq = lintq_dir()
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(f"{tmp}/src")
        Path(f"{tmp}/src/candidate.py").write_text(code)
        for cmd in (
            ["database", "create", f"{tmp}/db", "--language=python", f"--source-root={tmp}/src"],
            [
                "database",
                "analyze",
                f"{tmp}/db",
                f"{lintq}/LintQ-all.qls",
                "--format=sarifv2.1.0",
                f"--output={tmp}/out.sarif",
                f"--additional-packs={lintq}/qlint/codeql/src:{lintq}/qlint/codeql/lib",
            ],
        ):
            subprocess.run([codeql(), *cmd], check=True, capture_output=True)
        with open(f"{tmp}/out.sarif") as f:
            results = [r for run in json.load(f)["runs"] for r in run["results"]]
    return [f"[{r['ruleId']}] {r['message']['text']}" for r in results]


class ValidatorLintQ(BaseValidator):
    """Pass only if correctness_validator passes and LintQ raises no warnings.

    LintQ runs only on code that passes the tests: linting code that does not run is
    pointless, and each LintQ run builds a CodeQL database (~20s).

    Writes lintq_result.json in each sample directory (last attempt wins);
    :meth:get_summary collates them into lintq_summary.json.
    """

    def __init__(self, correctness_validator=None):
        self.correctness_validator = correctness_validator or ValidatorExec()

    def setup(self, **kwargs):
        self._base_sample_dir = Path(kwargs["sample_dir"])
        self.correctness_validator.setup(**kwargs)

    def validate(self, raw):
        # Test correctness before linting
        tests_passed, failure_info = self.correctness_validator.validate(raw)
        findings = None  # None = LintQ not run
        if tests_passed is True:
            if not isinstance(raw, str):
                raw = str(raw.last_output())
            findings = run_lintq(extract_code_from_llm_response(raw))
            failure_info = ["LintQ warnings:\n" + "\n".join(findings)] if findings else None

        passed = tests_passed is True and not findings
        result = {"passed": passed, "tests_passed": tests_passed is True, "lintq_findings": findings}
        with open(self._base_sample_dir / "lintq_result.json", "w") as f:
            json.dump(result, f, indent=4)

        # Always a list (or None), as runners join it with "\n".
        if isinstance(failure_info, str):
            failure_info = [failure_info]
        return passed, failure_info

    def get_summary(self, results_dir, test_folder_pattern="sample_*") -> dict:
        """Write the correctness summary (summary.json) and lintq_summary.json."""
        self.correctness_validator.get_summary(results_dir, test_folder_pattern)

        results = [
            json.loads((d / "lintq_result.json").read_text())
            for d in sorted(Path(results_dir).glob(test_folder_pattern))
            if (d / "lintq_result.json").exists()
        ]
        summary = {
            "total": len(results),
            "tests_passed": sum(r["tests_passed"] for r in results),
            "flagged_by_lintq": sum(bool(r["lintq_findings"]) for r in results),
            "passed": sum(r["passed"] for r in results),  # tests passed and no LintQ warnings
        }
        with open(Path(results_dir) / "lintq_summary.json", "w") as f:
            json.dump(summary, f, indent=4)

        print(
            f"LintQ: {summary['passed']}/{summary['total']} passed tests and LintQ "
            f"({summary['tests_passed']} passed tests, {summary['flagged_by_lintq']} flagged by LintQ)"
        )
        return summary
