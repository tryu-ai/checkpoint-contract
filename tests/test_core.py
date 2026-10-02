"""Synthetic sessions only: these tests are not evidence about upstream libraries."""

import unittest
from copy import deepcopy

from checkpoint_contract import (
    Case,
    Contract,
    check,
    generate_schedules,
    reduce_schedule,
)
from checkpoint_contract.__main__ import run_config


class Synthetic:
    def __init__(self, batches, *, next_epoch=False, fault=None):
        self.batches = deepcopy(batches)
        self.index = 0
        self.stopped = False
        self.next_epoch = next_epoch
        self.fault = fault
        self.closed = False

    def next_batch(self):
        assert not self.closed
        if self.index >= len(self.batches):
            self.stopped = True
            raise StopIteration
        batch = self.batches[self.index]
        self.index += 1
        return batch[:]

    def snapshot(self):
        return {"position": [self.index], "stopped": self.stopped, "opaque": {1, 2}}

    def restore(self, state):
        self.index = state["position"][0]
        if self.next_epoch and state["stopped"]:
            self.index = 0
        if self.fault == "repeat" and self.index:
            self.index -= 1
        if self.fault == "skip" and self.index < len(self.batches):
            self.index += 1
        if self.fault == "premature_epoch" and self.index == len(self.batches):
            self.index = 0

    def close(self):
        self.closed = True


class CoreTests(unittest.TestCase):
    def test_independent_case_oracle(self):
        for drop, expected in [(False, [[0, 1, 2], [3]]), (True, [[0, 1, 2]])]:
            self.assertEqual(
                Case([[], [0], [], [1, 2, 3], []], 3, drop).batches(), expected
            )
        self.assertEqual(Case([[], []], 3, True).batches(), [])
        for data in [
            dict(tables=[[1, 1]], batch_size=1, drop_last=False),
            dict(tables=[[True]], batch_size=1, drop_last=False),
            dict(tables=[], batch_size=True, drop_last=False),
        ]:
            with self.assertRaises(ValueError):
                Case.from_dict(data)

    def test_restore_modes_and_freshness(self):
        for batches in ([], [[0]], [[0, 1], [2, 3], [4]]):
            for mode in ("empty", "next_epoch"):
                sessions = []

                def factory():
                    s = Synthetic(batches, next_epoch=mode == "next_epoch")
                    sessions.append(s)
                    return s

                r = check(
                    factory,
                    batches,
                    [1, 2],
                    Contract(exhausted_restore=mode),
                    next_epoch_batches=batches,
                )
                self.assertEqual(r["status"], "pass", r)
                self.assertTrue(all(s.closed for s in sessions))
                self.assertGreater(len(sessions), 5)

    def test_fault_diagnostics(self):
        expected = [[0], [1], [2]]
        r = check(
            lambda: Synthetic(expected, fault="repeat"), expected, [1], Contract()
        )
        self.assertEqual(r["status"], "fail")
        f = r["failure"]
        self.assertEqual(f["phase"], "scheduled_restore")
        self.assertEqual(f["first_divergence"]["batch"], 1)
        self.assertEqual(f["actual_multiplicities"], [{"id": 0, "count": 5}])
        self.assertFalse(f["observed_stop_iteration"])

    def test_baseline_is_not_truth(self):
        for wrong in ([[1], [0]], [[0, 1]], [[0], [0]]):
            r = check(lambda: Synthetic(wrong), [[0], [1]], [1], Contract())
            self.assertEqual(r["status"], "fail")
            self.assertEqual(r["failure"]["phase"], "baseline")

    def test_explicit_before_stop_boundary(self):
        r = check(
            lambda: Synthetic([[0]], fault="premature_epoch"), [[0]], [10], Contract()
        )
        self.assertEqual(r["failure"]["phase"], "before_stop_iteration")

    def test_after_stop_requires_known_epoch(self):
        r = check(
            lambda: Synthetic([[0]], next_epoch=True),
            [[0]],
            [1],
            Contract(exhausted_restore="next_epoch"),
        )
        self.assertEqual(r["status"], "error")
        r = check(
            lambda: Synthetic([[0]]),
            [[0]],
            [1],
            Contract(exhausted_restore="next_epoch"),
            next_epoch_batches=[[0]],
        )
        self.assertEqual(r["failure"]["phase"], "after_stop_iteration")

    def test_unsupported_and_invalid(self):
        def factory():
            return Synthetic([[0]])

        for contract in (
            Contract(False, reason="unsupported"),
            Contract(exhausted_restore="unsupported"),
        ):
            self.assertEqual(
                check(factory, [[0]], [1], contract)["status"], "unsupported"
            )
        for schedule in ([], [0], [-1], [True], [1.5]):
            self.assertEqual(
                check(factory, [[0]], schedule, Contract())["status"], "error"
            )

    def test_generation_and_reduction(self):
        schedules = generate_schedules(42, 10)
        self.assertEqual(schedules, generate_schedules(42, 10))
        self.assertTrue(all(s and all(n > 0 for n in s) for s in schedules))

        def evaluate(s):
            return {
                "status": "fail" if 2 in s else "pass",
                "failure": {"failure_class": "x", "phase": "p"},
            }

        r = reduce_schedule([3, 2, 4], evaluate)
        self.assertEqual(r["schedule"], [2])
        self.assertEqual(r["status"], "1-minimal")
        self.assertEqual(
            reduce_schedule([3, 2, 4], evaluate, budget=1)["status"], "budget_exhausted"
        )

    def test_serializer_is_explicit(self):
        import pickle

        r = check(lambda: Synthetic([[0]]), [[0]], [1], Contract(), serializer=pickle)
        self.assertEqual(r["status"], "pass")
        self.assertEqual(r["snapshot_transport"], "serializer")

    def test_reduction_preserves_phase_class_and_ignores_extra_diagnostics(self):
        def outcome(
            phase="scheduled_restore", failure_class="output_mismatch", **extra
        ):
            return {
                "status": "fail",
                "failure": {"phase": phase, "failure_class": failure_class, **extra},
            }

        original = [2, 2]
        for changed in (
            outcome(phase="baseline"),
            outcome(failure_class="termination_bound"),
        ):
            result = reduce_schedule(
                original, lambda s: outcome() if s == original else changed
            )
            self.assertEqual(result["schedule"], original)
            self.assertEqual(result["status"], "1-minimal")
        for status in ("error", "unsupported"):
            result = reduce_schedule(
                original, lambda s: outcome() if s == original else {"status": status}
            )
            self.assertEqual(result["status"], "inconclusive")
            self.assertEqual(result["schedule"], original)
        result = reduce_schedule(
            original,
            lambda s: outcome(diagnostic="old" if s == original else "different"),
        )
        self.assertEqual(result["schedule"], [1])
        self.assertEqual(original, [2, 2])
        # Unselected diagnostics may differ; no root-cause guarantee.

    def test_reduction_preserves_observable_mismatch(self):
        original = [2, 2]
        failure = {
            "phase": "scheduled_restore",
            "failure_class": "output_mismatch",
            "expected_ids": [[0, 1], [2]],
            "actual_ids": [[0, 1]],
            "observed_stop_iteration": True,
        }
        for change in (
            {"actual_ids": [[0, 1], [2], [2]]},  # Missing becomes duplicate.
            {"actual_ids": [[1, 0]]},
            {"actual_ids": [[0], [1]]},
            {"actual_ids": [[0, "1"]]},
            {"actual_ids": [[0, True]]},  # Invalid IDs must not alias integers.
            {"expected_ids": [[0, 1], [3]]},
            {"expected_ids": [[1, 0], [2]]},
            {"expected_ids": [[0], [1, 2]]},
            {"observed_stop_iteration": False},
        ):
            with self.subTest(change=change):
                result = reduce_schedule(
                    original,
                    lambda s: {
                        "status": "fail",
                        "failure": failure if s == original else {**failure, **change},
                    },
                )
                self.assertEqual(result["schedule"], original)
                self.assertEqual(result["status"], "1-minimal")
                self.assertEqual(result["evaluations"], 5)
                self.assertEqual(
                    result["preserved_failure"],
                    ["fail", "output_mismatch", "scheduled_restore"],
                )
                self.assertEqual(
                    result["observable_fingerprint"], {"status": "fail", **failure}
                )

        result = reduce_schedule(
            original, lambda s: {"status": "fail", "failure": deepcopy(failure)}
        )
        self.assertEqual(result["schedule"], [1])

    def test_reduction_field_presence_and_detached_target(self):
        for key in (
            "failure_class",
            "phase",
            "expected_ids",
            "actual_ids",
            "observed_stop_iteration",
        ):
            for original_has_key in (True, False):
                with self.subTest(key=key, original_has_key=original_has_key):
                    result = reduce_schedule(
                        [2],
                        lambda s: {
                            "status": "fail",
                            "failure": {key: None}
                            if (s == [2]) == original_has_key
                            else {},
                        },
                    )
                    self.assertEqual(result["schedule"], [2])

        shared = {
            "status": "fail",
            "failure": {
                "failure_class": "output_mismatch",
                "phase": "scheduled_restore",
                "expected_ids": [[0], [1]],
                "actual_ids": [[0]],
                "observed_stop_iteration": True,
            },
        }
        expected = deepcopy(shared["failure"])

        def evaluate(s):
            if s != [2]:
                shared["failure"]["actual_ids"][0].append(1)
            return shared

        result = reduce_schedule([2], evaluate)
        self.assertEqual(result["schedule"], [2])
        shared["failure"]["expected_ids"][0].append(99)
        self.assertEqual(
            result["observable_fingerprint"], {"status": "fail", **expected}
        )

    def test_reduction_is_not_global_minimization(self):
        def evaluate(s):
            return {
                "status": "fail" if s in ([3], [1]) else "pass",
                "failure": {"phase": "p", "failure_class": "x"},
            }

        result = reduce_schedule([3], evaluate)
        self.assertEqual(result["status"], "1-minimal")
        self.assertEqual(result["schedule"], [3])

    def test_replay_configuration_validated_before_adapter_execution(self):
        with self.assertRaises(ValueError):
            run_config(
                {
                    "adapter": "hf-arrow",
                    "case": Case([[0]], 1, False).as_dict(),
                    "schedules": [[1], [99]],
                    "generation": {"seed": 0, "count": 0},
                    "reduction_budget": 1,
                }
            )


if __name__ == "__main__":
    unittest.main()
