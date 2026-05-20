import subprocess
import shutil
import os
import re
from pathlib import Path

DOCKER_IMAGE = "ai-architect-sandbox"
DOCKER_BIN = shutil.which("docker") or "docker"

def build_image() -> None:
    dockerfile_dir = os.path.dirname(os.path.abspath(__file__))
    result = subprocess.run(
        [DOCKER_BIN, "build", "-t", DOCKER_IMAGE, "."],
        cwd=dockerfile_dir,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Docker build failed:\n{result.stderr}")

def run_tests(target_dir: str, test_file: str) -> dict:
    base = Path(target_dir).resolve()
    mock_dir = base
    if not mock_dir.exists():
        raise ValueError(f"target_dir does not exist: {mock_dir}")

    docker_cmd = [
        DOCKER_BIN, "run", "--rm",
        "--network", "none",
        "--memory", "256m",
        "--cpus", "0.5",
        "-v", f"{mock_dir}:/app:ro",
        DOCKER_IMAGE,
        "pytest", f"/app/{test_file}", "-v", "--tb=short"
    ]

    try:
        print("   [Docker] Spinning up isolated container...")
        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        output = result.stdout + result.stderr
        passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", output)) else 0
        failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", output)) else 0

        if result.returncode != 0 and passed == 0 and failed == 0:
            failed = 7

        return {
            "exit_code": result.returncode,
            "passed": passed,
            "failed": failed,
            "output": output
        }

    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "passed": 0, "failed": 7,
                "output": "TIMEOUT: Container exceeded 60s execution limit."}
    except Exception as e:
        return {"exit_code": -2, "passed": 0, "failed": 7,
                "output": f"CONTAINER FAULT: {e}"}


if __name__ == "__main__":
    import pprint
    build_image()
    pprint.pprint(run_tests(os.path.join(os.path.dirname(__file__), "..")))
