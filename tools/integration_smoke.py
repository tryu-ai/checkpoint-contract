"""Pinned compatibility controls, executed against an installed distribution."""

import json
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    require(sys.version_info[:3] == (3, 11, 15), "requires Python 3.11.15")
    for package, expected in (
        ("checkpoint-contract", "0.1.0"),
        ("datasets", "5.0.1"),
        ("pyarrow", "25.0.1"),
        ("torch", "2.14.1"),
        ("torchdata", "0.11.0"),
    ):
        actual = version(package)
        # Official torch CPU wheels add a local version suffix.
        accepted = {expected, expected + "+cpu"} if package == "torch" else {expected}
        require(actual in accepted, f"{package}: expected {accepted}, got {actual}")

    examples = Path(__file__).resolve().parents[1] / "examples"
    with tempfile.TemporaryDirectory() as tmp:
        for filename, status, code in (
            ("hf_arrow.py", "fail", 1),
            ("torchdata_resume.py", "pass", 0),
        ):
            result = subprocess.run(
                [sys.executable, "-I", str(examples / filename)],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=180,
            )
            require(
                result.returncode == code,
                f"{filename}: {result.stderr}\n{result.stdout}",
            )
            report = json.loads(result.stdout)
            require(report["status"] == status, f"{filename}: wrong report status")
            if status == "fail":
                require(
                    report["config"]["schedules"] == [[1, 1, 3]],
                    "HF fixture schedule changed",
                )
                require(len(report["runs"]) == 1, "HF fixture must have one run")
                run = report["runs"][0]
                known = {
                    "status": "fail",
                    "failure_class": "output_mismatch",
                    "phase": "scheduled_restore",
                    "expected_ids": [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11]],
                    "actual_ids": [[0, 1, 2, 3], [4, 5, 6, 7], [10, 11]],
                    "observed_stop_iteration": True,
                }
                failure = run["failure"]
                require(run["status"] == known["status"], "HF run must fail")
                for key, expected in known.items():
                    if key != "status":
                        require(
                            failure[key] == expected,
                            f"HF known diagnostic changed: {key}",
                        )
                require(
                    failure["observed_stop_iteration"] is True,
                    "HF must observe exhaustion",
                )
                minimized = run["minimization"]
                require(
                    minimized["status"] == "1-minimal", "HF reduction must be 1-minimal"
                )
                require(minimized["schedule"] == [1], "HF schedule must reduce to [1]")
                require(
                    minimized["observable_fingerprint"] == known,
                    "HF reduction must retain the known observable failure",
                )
                require(
                    minimized["observable_fingerprint"]["observed_stop_iteration"]
                    is True,
                    "HF reduction must retain observed exhaustion",
                )
                require(
                    minimized["preserved_failure"]
                    == ["fail", "output_mismatch", "scheduled_restore"],
                    "HF reduction changed the preserved failure",
                )
            source = Path(tmp) / "original.json"
            target = Path(tmp) / "replayed.json"
            source.write_text(json.dumps(report), encoding="utf-8")
            replay = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-m",
                    "checkpoint_contract",
                    "replay",
                    str(source),
                    "--report",
                    str(target),
                ],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=180,
            )
            require(replay.returncode == code, f"replay failed: {replay.stderr}")
            rerun = json.loads(target.read_text(encoding="utf-8"))
            require(rerun["config"] == report["config"], "replay changed configuration")
            require(rerun["runs"] == report["runs"], "replay changed diagnostics")
            require(rerun["status"] == status, "replay changed outcome")
            print(f"{filename}: expected {status}; replay matched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
