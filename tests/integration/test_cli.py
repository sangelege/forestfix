import json
import subprocess
import sys


def test_demo_command_runs_without_model_credentials() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "forestfix.cli", "demo"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["baseline"]["reproduced"] is True
    assert payload["good_candidate"]["accepted"] is True
    assert payload["cheating_candidate"]["stage"] == "policy_rejected"
