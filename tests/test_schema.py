"""Structural tests use synthetic sessions, never historical-library evidence."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from test_core import Synthetic

from checkpoint_contract import Case, Contract, report_schema
from checkpoint_contract.__main__ import main, run_config

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None


def config():
    return {
        "adapter": "hf-arrow",
        "case": Case([[0, 1], [2]], 2, False).as_dict(),
        "schedules": [[1, 1, 3]],
        "generation": {"seed": 0, "count": 0},
        "reduction_budget": 10,
    }


def fake_adapter(name, case):
    return lambda: Synthetic(case.batches()), Contract(), {"adapter": "synthetic"}


class ResourceReplayTests(unittest.TestCase):
    def test_resource_and_v1_replay_regenerates_results(self):
        schema = report_schema()
        self.assertEqual(
            schema["properties"]["schema"]["const"], "checkpoint-contract/v1"
        )
        schema.clear()
        self.assertIn("$defs", report_schema())
        # A synthetic v1-shaped full report, not real historical evidence.
        with patch(
            "checkpoint_contract.__main__.adapter",
            return_value=(
                lambda: Synthetic([[0, 1], [2]], fault="repeat"),
                Contract(),
                {"adapter": "synthetic"},
            ),
        ):
            previous = run_config(config())
        previous["provenance"]["checker"]["version"] = "0.1.0"  # v1 metadata
        for run in previous["runs"]:
            run["minimization"].pop("observable_fingerprint", None)
        self.assertEqual(previous["status"], "fail")
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch(
                "checkpoint_contract.__main__.adapter", side_effect=fake_adapter
            ) as selected,
        ):
            source, target = Path(tmp) / "old.json", Path(tmp) / "new.json"
            source.write_text(json.dumps(previous))
            self.assertEqual(main(["replay", str(source), "--report", str(target)]), 0)
            current = json.loads(target.read_text())
            self.assertEqual(current["config"], previous["config"])
            self.assertEqual(current["status"], "pass")
            self.assertTrue(current["runs"][0]["checks"])
            selected.assert_called_once()
            if Draft202012Validator is not None:
                validator = Draft202012Validator(report_schema())
                validator.validate(previous)
                validator.validate(current)
            previous["config"]["generation"]["count"] = 1
            source.write_text(json.dumps(previous))
            selected.reset_mock()
            self.assertEqual(main(["replay", str(source), "--report", str(target)]), 2)
            selected.assert_not_called()

    def test_replay_ignores_old_outcomes_and_provenance(self):
        previous = {
            "schema": "checkpoint-contract/v1",
            "config": config(),
            "status": "invalid old status",
            "runs": "invalid old runs",
            "provenance": ["invalid old provenance"],
        }
        if Draft202012Validator is not None:
            self.assertFalse(Draft202012Validator(report_schema()).is_valid(previous))
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("checkpoint_contract.__main__.adapter", side_effect=fake_adapter),
        ):
            source, target = Path(tmp) / "old.json", Path(tmp) / "new.json"
            source.write_text(json.dumps(previous))
            self.assertEqual(main(["replay", str(source), "--report", str(target)]), 0)
            current = json.loads(target.read_text())
            self.assertEqual(current["config"], previous["config"])
            self.assertEqual(current["status"], "pass")
            self.assertEqual(current["provenance"]["adapter"], "synthetic")


@unittest.skipIf(Draft202012Validator is None, "optional jsonschema unavailable")
class SchemaTests(unittest.TestCase):
    def setUp(self):
        schema = report_schema()
        Draft202012Validator.check_schema(schema)
        self.validator = Draft202012Validator(schema)

    def test_full_reports_all_statuses_and_missing_provenance(self):
        for status, contract, fault in (
            ("pass", Contract(), None),
            ("fail", Contract(), "repeat"),
            ("unsupported", Contract(False), None),
            ("unsupported", Contract(exhausted_restore="unsupported"), None),
            ("error", Contract(), None),
        ):

            def factory():
                if status == "error":
                    raise RuntimeError("synthetic adapter error")
                return Synthetic([[0, 1], [2]], fault=fault)

            with (
                self.subTest(status=status),
                patch(
                    "checkpoint_contract.__main__.adapter",
                    return_value=(factory, contract, {"adapter": "synthetic"}),
                ),
            ):
                report = run_config(config())
                self.assertEqual(report["status"], status)
                self.validator.validate(report)
                if status == "fail":
                    minimization = report["runs"][0]["minimization"]
                    self.assertEqual(minimization["status"], "1-minimal")
                    self.assertEqual(len(minimization["preserved_failure"]), 3)
                    for key, value in (
                        ("actual_ids", [[True]]),
                        ("expected_ids", "bad"),
                        ("observed_stop_iteration", None),
                    ):
                        malformed = deepcopy(report)
                        malformed["runs"][0]["minimization"]["observable_fingerprint"][
                            key
                        ] = value
                        self.assertFalse(self.validator.is_valid(malformed))
                    legacy = deepcopy(report)
                    del legacy["runs"][0]["minimization"]["observable_fingerprint"]
                    self.validator.validate(legacy)
                    malformed = deepcopy(report)
                    del malformed["runs"][0]["failure"]["first_divergence"]["batch"]
                    self.assertFalse(self.validator.is_valid(malformed))
                del report["provenance"]
                report["future_extension"] = {"note": "permitted"}
                self.validator.validate(report)

    def test_configuration_and_output_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "bad.json", Path(tmp) / "report.json"
            for contents in (
                "{",
                "{}",
                json.dumps({"schema": "checkpoint-contract/v1", "config": {}}),
            ):
                source.write_text(contents)
                self.assertEqual(
                    main(["replay", str(source), "--report", str(target)]), 2
                )
                self.validator.validate(json.loads(target.read_text()))
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(main(["replay", str(source), "--report", tmp]), 2)
            self.validator.validate(json.loads(stderr.getvalue()))

    def test_rejects_missing_contract_keys_and_invalid_diagnostics(self):
        with patch("checkpoint_contract.__main__.adapter", side_effect=fake_adapter):
            valid = run_config(config())
        for path in (
            ("schema",),
            ("config", "case", "batch_size"),
            ("runs", 0, "bounds"),
            ("runs", 0, "checks", 0, "phase"),
            ("runs", 0, "minimization", "evaluations"),
        ):
            invalid = deepcopy(valid)
            node = invalid
            for key in path[:-1]:
                node = node[key]
            del node[path[-1]]
            self.assertFalse(self.validator.is_valid(invalid), path)
        for status in ("success", None, 0):
            self.assertFalse(self.validator.is_valid({**valid, "status": status}))
        invalid = deepcopy(valid)
        invalid["runs"][0].update(status="fail", failure={})
        self.assertFalse(self.validator.is_valid(invalid))
        self.assertFalse(
            self.validator.is_valid(
                {"schema": "checkpoint-contract/v1", "status": "pass"}
            )
        )
