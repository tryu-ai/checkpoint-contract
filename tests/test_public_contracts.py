"""Public contract checks for release acceptance.

Run this stdlib unittest module against the selected candidate. No path
injection: import resolution must select that candidate. Set
CHECKPOINT_RELEASE_INSTALLED=1 only in a noneditable installed environment.
These tests do not install dependencies or access the network.
"""

import copy
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from checkpoint_contract import Case, Contract, check, report_schema


class Tape:
    def __init__(self, batches, following=None):
        self.batches = copy.deepcopy(batches)
        self.following = copy.deepcopy(following)
        self.position = 0
        self.stopped = False
        self.closed = False

    def next_batch(self):
        if self.position == len(self.batches):
            self.stopped = True
            raise StopIteration
        value = self.batches[self.position][:]
        self.position += 1
        return value

    def snapshot(self):
        return (self.position, self.stopped)

    def restore(self, state):
        self.position, self.stopped = state
        if self.stopped and self.following is not None:
            self.batches = copy.deepcopy(self.following)
            self.position = 0
            self.stopped = False

    def close(self):
        self.closed = True


class PublicContracts(unittest.TestCase):
    def test_mixed_ids_remain_distinct_in_failure_and_json(self):
        expected = [[1, "1", "雪"], [-2, ""]]
        actual = [["1", "1", "雪"], [-2, ""]]
        good = check(lambda: Tape(expected), expected, [2], Contract())
        self.assertEqual(good["status"], "pass")
        result = check(lambda: Tape(actual), expected, [2], Contract())
        result = json.loads(json.dumps(result, ensure_ascii=False))
        self.assertEqual(result["status"], "fail")
        failure = result["failure"]
        self.assertEqual(failure["expected_ids"], expected)
        self.assertEqual(failure["actual_ids"], actual)
        counts = {
            (type(item["id"]), item["id"]): item["count"]
            for item in failure["expected_multiplicities"]
        }
        self.assertEqual(counts[(int, 1)], 1)
        self.assertEqual(counts[(str, "1")], 1)

    def test_independently_different_next_epoch_and_its_bound(self):
        first, following = [[8]], [["b", "a"], ["c"], ["d"]]
        result = check(
            lambda: Tape(first, following),
            first,
            [3],
            Contract(exhausted_restore="next_epoch"),
            next_epoch_batches=following,
        )
        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(result["bounds"]["current_epoch_calls_per_probe"], 3)
        self.assertEqual(result["bounds"]["next_epoch_calls"], 5)
        bad = check(
            lambda: Tape(first, first),
            first,
            [3],
            Contract(exhausted_restore="next_epoch"),
            next_epoch_batches=following,
        )
        self.assertEqual(bad["status"], "fail")
        self.assertEqual(bad["failure"]["phase"], "after_stop_iteration")

    def test_restore_error_closes_new_session_and_is_not_a_mismatch(self):
        sessions = []

        class BrokenRestore(Tape):
            def restore(self, state):
                raise RuntimeError("deliberate restore exception")

        def factory():
            session = BrokenRestore([[7]])
            sessions.append(session)
            return session

        result = check(factory, [[7]], [1], Contract())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["phase"], "initial_restore")
        self.assertEqual(result["error"]["type"], "RuntimeError")
        self.assertIsNone(result["failure"])
        self.assertEqual(len(sessions), 3)
        self.assertTrue(all(s.closed for s in sessions))

    def test_case_export_and_batches_are_detached(self):
        case = Case([[9, -1], [], [4]], 2, False)
        exported = case.as_dict()
        batches = case.batches()
        exported["tables"][0].clear()
        batches[0][0] = 100
        self.assertEqual(case.as_dict()["tables"], [[9, -1], [], [4]])
        self.assertEqual(case.batches(), [[9, -1], [4]])


# A fresh process blocks optional imports even when the environment has them.
# It does not fake adapter results; real dependency absence must be unsupported.
GUARDED_CLI = r"""
import importlib.abc
import sys
class MissingOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch', 'torchdata', 'datasets', 'pyarrow'}:
            raise ModuleNotFoundError('blocked optional dependency', name=fullname)
sys.meta_path.insert(0, MissingOptional())
from checkpoint_contract.__main__ import main
raise SystemExit(main(sys.argv[1:]))
"""


class DependencyFreeCLI(unittest.TestCase):
    def invoke(self, args):
        return subprocess.run(
            [sys.executable, "-c", GUARDED_CLI, *args],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_help_needs_no_framework(self):
        for args in (["--help"], ["run", "--help"], ["replay", "--help"]):
            with self.subTest(args=args):
                result = self.invoke(args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout.lower())
                self.assertNotIn("Traceback", result.stderr)

    def test_usage_errors_remain_conventional_exit_two(self):
        for args in ([], ["unknown"], ["run", "--adapter", "unknown"]):
            with self.subTest(args=args):
                result = self.invoke(args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage:", result.stderr.lower())
                self.assertNotIn("Traceback", result.stderr)

    def test_each_missing_stack_run_and_stdout_replay_are_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp) / "case with spaces.json"
            case.write_text(
                json.dumps(
                    {
                        "tables": [[4, 2], [9]],
                        "batch_size": 2,
                        "drop_last": False,
                    }
                ),
                encoding="utf-8",
            )
            for adapter in ("hf-arrow", "torchdata"):
                with self.subTest(adapter=adapter):
                    report = Path(tmp) / (adapter + ".json")
                    result = self.invoke(
                        [
                            "run",
                            "--adapter",
                            adapter,
                            "--case",
                            str(case),
                            "--schedule",
                            "2,1",
                            "--report",
                            str(report),
                        ]
                    )
                    self.assertEqual(result.returncode, 3, result.stderr)
                    self.assertEqual(result.stdout, "")
                    old = json.loads(report.read_text(encoding="utf-8"))
                    self.assertEqual(old["schema"], "checkpoint-contract/v1")
                    self.assertEqual(old["status"], "unsupported")
                    self.assertEqual(old["runs"][0]["status"], "unsupported")
                    replay = self.invoke(["replay", str(report)])
                    self.assertEqual(replay.returncode, 3, replay.stderr)
                    new = json.loads(replay.stdout)
                    self.assertEqual(new["status"], "unsupported")
                    self.assertEqual(new["config"], old["config"])
                    self.assertNotIn("Traceback", replay.stderr)


@unittest.skipUnless(
    os.environ.get("CHECKPOINT_RELEASE_INSTALLED") == "1",
    "opt in after noneditable installation and run outside the checkout",
)
class InstalledReleaseMetadata(unittest.TestCase):
    def test_no_mandatory_runtime_dependencies_and_expected_extras(self):
        distribution = importlib.metadata.distribution("checkpoint-contract")
        requirements = distribution.requires or []
        # All dependency declarations belong to optional extras. This narrow
        # contract intentionally needs no packaging/requirements parser dependency.
        for requirement in requirements:
            self.assertIn(";", requirement, requirement)
            self.assertIn("extra ==", requirement.split(";", 1)[1], requirement)
        self.assertTrue(
            {"hf-arrow", "torchdata"}.issubset(
                set(distribution.metadata.get_all("Provides-Extra") or [])
            )
        )
        scripts = [
            ep
            for ep in distribution.entry_points
            if ep.group == "console_scripts" and ep.name == "checkpoint-check"
        ]
        self.assertEqual(len(scripts), 1)
        self.assertEqual(scripts[0].value, "checkpoint_contract.__main__:main")

    def test_distribution_owns_schema_resource(self):
        distribution = importlib.metadata.distribution("checkpoint-contract")
        matches = [
            p
            for p in distribution.files or []
            if str(p) == "checkpoint_contract/schemas/report-v1.json"
        ]
        self.assertEqual(len(matches), 1)
        packaged = json.loads(
            distribution.locate_file(matches[0]).read_text(encoding="utf-8")
        )
        self.assertEqual(packaged, report_schema())
        self.assertEqual(packaged["$id"], "urn:checkpoint-contract:report:v1")


if __name__ == "__main__":
    unittest.main()
