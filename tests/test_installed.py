"""Opt-in wheel smoke check, launched outside the checkout with isolated Python."""

import json
import os
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(
    os.environ.get("CHECKPOINT_CONTRACT_INSTALLED") == "1",
    "installed distribution only",
)
class InstalledTests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("CHECKPOINT_CONTRACT_CORE_ONLY") == "1", "core-only environment"
    )
    def test_missing_optional_packages_are_unsupported_and_replayable(self):
        case = Path(__file__).resolve().parents[1] / "examples/regression.json"
        with tempfile.TemporaryDirectory() as tmp:
            for adapter in ("hf-arrow", "torchdata"):
                report = Path(tmp) / "report.json"
                replay = Path(tmp) / "replay.json"
                for command, target in (
                    (["run", "--adapter", adapter, "--case", str(case)], report),
                    (["replay", str(report)], replay),
                ):
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-I",
                            "-m",
                            "checkpoint_contract",
                            *command,
                            "--report",
                            str(target),
                        ],
                        cwd=tmp,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    self.assertEqual(result.returncode, 3, result.stderr)
                    data = json.loads(target.read_text())
                    self.assertEqual(data["status"], "unsupported")
                    self.assertIn(
                        "optional dependency missing", data["runs"][0]["reason"]
                    )

    def test_installed_resource_and_console_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    "import json, checkpoint_contract; "
                    "from importlib.metadata import version; "
                    "print(json.dumps({'schema': checkpoint_contract.report_schema(), "
                    "'file': checkpoint_contract.__file__, "
                    "'version': version('checkpoint-contract')}))",
                ],
                cwd=tmp,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            installed = json.loads(probe.stdout)
            self.assertEqual(
                installed["schema"]["$id"], "urn:checkpoint-contract:report:v1"
            )
            self.assertTrue(installed["version"])
            self.assertTrue(
                any(
                    Path(installed["file"])
                    .resolve()
                    .is_relative_to(Path(sysconfig.get_path(key)).resolve())
                    for key in ("purelib", "platlib")
                ),
                "resource must come from installed wheel, not an editable checkout",
            )
            script = Path(sysconfig.get_path("scripts")) / "checkpoint-check"
            env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            report = Path(tmp) / "report.json"
            result = subprocess.run(
                [str(script), "replay", "missing.json", "--report", str(report)],
                cwd=tmp,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            data = json.loads(report.read_text())
            self.assertEqual(data["schema"], "checkpoint-contract/v1")
            self.assertEqual(data["error"]["type"], "FileNotFoundError")
