"""Opt-in fixed-source integration suite; see docs/compatibility.md."""

import os
import unittest

from checkpoint_contract import Case, check
from checkpoint_contract.adapters import adapter


@unittest.skipUnless(
    os.environ.get("CHECKPOINT_CONTRACT_INTEGRATION") == "1", "fixed-source opt-in"
)
class AdapterTests(unittest.TestCase):
    def test_actual_batch_size_forwarding(self):
        for name in ("hf-arrow", "torchdata"):
            for size in (2, 4):
                for drop in (False, True):
                    with self.subTest(adapter=name, batch_size=size, drop_last=drop):
                        case = Case([[0, 1, 2], [3, 4, 5, 6]], size, drop)
                        factory, _, _ = adapter(name, case)
                        session = factory()
                        observed = []
                        try:
                            for _ in range(9):
                                try:
                                    observed.append(session.next_batch())
                                except StopIteration:
                                    break
                            else:
                                self.fail("adapter did not exhaust within bound")
                        finally:
                            session.close()
                        self.assertEqual(observed, case.batches())
                        self.assertEqual(len(observed[0]), size)

    def test_real_adapters(self):
        for name in ("hf-arrow", "torchdata"):
            for tables in (
                [[0, 1], [2, 3, 4, 5, 6], [7, 8], [9, 10, 11]],
                [[], [0, 1], [], [2], []],
                [],
                [[]],
            ):
                for drop in (False, True):
                    with self.subTest(adapter=name, tables=tables, drop_last=drop):
                        case = Case(tables, 4, drop)
                        factory, contract, _ = adapter(name, case)
                        report = check(
                            factory,
                            case.batches(),
                            [1],
                            contract,
                            next_epoch_batches=case.batches(),
                        )
                        self.assertEqual(report["status"], "pass", report)

    def test_documented_unsupported(self):
        for name, mode in (
            ("hf-arrow", {"buffered_shuffle": True}),
            ("torchdata", {"in_order": False}),
        ):
            case = Case([[0]], 1, False)
            factory, contract, _ = adapter(name, case, **mode)
            self.assertEqual(
                check(
                    factory,
                    case.batches(),
                    [1],
                    contract,
                    next_epoch_batches=case.batches(),
                )["status"],
                "unsupported",
            )
