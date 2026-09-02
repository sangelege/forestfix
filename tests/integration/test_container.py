from pathlib import Path

from forestfix.sandbox.container import ContainerConfig, DockerCommandExecutor


def test_docker_command_disables_network_and_drops_capabilities(tmp_path: Path) -> None:
    executor = DockerCommandExecutor(
        ContainerConfig(image="python:3.12-slim", network_access=False)
    )

    command = executor.build_command(["python", "-m", "pytest", "-q"], tmp_path)

    assert command[:8] == [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
    ]
    assert "--security-opt" in command
    assert "no-new-privileges" in command
    assert "--pids-limit" in command
    assert "--memory" in command
    assert "--cpus" in command
    assert "-w" in command
    assert command[-4:] == ["python", "-m", "pytest", "-q"]
