"""Generate Qiskit code with Mellea, repairing it until it passes the tests and LintQ
or maximum budget is reached.

Downloads Qiskit HumanEval and runs the first num_samples problems of config.yaml
(see README.md for the setup):

    python examples/mellea_lintq/run.py
"""

import json
import os
from pathlib import Path

import yaml
from codehelm_lintq import ValidatorLintQ

from codehelm.algorithms.validator_feedback.feeback import Feedback
from codehelm.algorithms.validator_feedback.mellea_strategy import (
    MelleaFeedbackStrategy,
)
from codehelm.orchestration.mellea import MelleaRunner
from codehelm.utils.utils import resolve_env_vars, resolve_folder_savedir, urlopen
from codehelm.validator.validator_exec import ValidatorExec

HERE = Path(__file__).parent

with open(HERE / "config.yaml", "r") as file:
    config = yaml.safe_load(file)
resolve_env_vars(config)

results_dir = resolve_folder_savedir(str(HERE / config["result_path"]))
os.makedirs(results_dir)

# Download the dataset and keep the first num_samples problems, saved with the results
# (urlopen uses certifi's CA bundle, avoiding certificate errors on some Python builds)
with urlopen(config["dataset_url"]) as response:
    dataset = json.load(response)[: config["num_samples"]]
dataset_path = os.path.join(results_dir, "dataset.json")
with open(dataset_path, "w") as f:
    json.dump(dataset, f, indent=4)

# Run with Mellea
runner = MelleaRunner(config,
                      results_dir=results_dir,
                      validator=ValidatorLintQ(ValidatorExec()),
                      repair_strategy=MelleaFeedbackStrategy(Feedback()))
runner.parse_data(dataset=dataset_path,
                  num_samples=config["num_samples"])
_ = runner.validator.get_summary(results_dir)  # summary.json + lintq_summary.json
