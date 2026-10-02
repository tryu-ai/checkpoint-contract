"""CLI roundtrip tests use a synthetic adapter; no optional imports are executed."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_core import Synthetic

from checkpoint_contract import Contract
from checkpoint_contract.__main__ import main
from checkpoint_contract.adapters import _version


class CLITests(unittest.TestCase):
    def test_json_replay_and_exit_codes(self):
        def fake_adapter(name, case):
            return (
                lambda: Synthetic(case.batches()),
                Contract(),
                {"adapter": "synthetic", "packages": {}},
            )

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("checkpoint_contract.__main__.adapter", fake_adapter),
        ):
            case = Path(tmp) / "case.json"
            report = Path(tmp) / "report.json"
            replay = Path(tmp) / "replay.json"
            case.write_text(
                json.dumps(
                    {"tables": [[0], [], [1, 2]], "batch_size": 2, "drop_last": False}
                )
            )
            self.assertEqual(
                main(
                    [
                        "run",
                        "--adapter",
                        "hf-arrow",
                        "--case",
                        str(case),
                        "--schedule",
                        "1,2",
                        "--generated-count",
                        "3",
                        "--seed",
                        "9",
                        "--report",
                        str(report),
                    ]
                ),
                0,
            )
            original = json.loads(report.read_text())
            checker = original["provenance"]["checker"]
            self.assertEqual(checker["version"], _version("checkpoint-contract"))
            self.assertEqual(len(checker["sources"]), 5)
            for source in checker["sources"]:
                self.assertTrue(source["loaded"])
                self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(main(["replay", str(report), "--report", str(replay)]), 0)
            self.assertEqual(original, json.loads(replay.read_text()))
            self.assertEqual(
                main(
                    [
                        "run",
                        "--adapter",
                        "hf-arrow",
                        "--case",
                        str(case),
                        "--schedule",
                        "0",
                        "--report",
                        str(report),
                    ]
                ),
                2,
            )
            self.assertEqual(json.loads(report.read_text())["status"], "error")

    def test_fail_and_unsupported_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp) / "case.json"
            report = Path(tmp) / "report.json"
            case.write_text(
                '{"tables": [[0], [1]], "batch_size": 1, "drop_last": false}'
            )
            args = [
                "run",
                "--adapter",
                "hf-arrow",
                "--case",
                str(case),
                "--schedule",
                "1",
                "--report",
                str(report),
            ]
            for contract, fault, code in (
                (Contract(), "repeat", 1),
                (Contract(False), None, 3),
            ):
                with patch(
                    "checkpoint_contract.__main__.adapter",
                    return_value=(
                        lambda: Synthetic([[0], [1]], fault=fault),
                        contract,
                        {"adapter": "synthetic"},
                    ),
                ):
                    self.assertEqual(main(args), code)
