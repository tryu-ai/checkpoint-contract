"""Synthetic provenance checks; no optional dependencies are imported."""

import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from checkpoint_contract import Case, Unsupported
from checkpoint_contract.adapters import _refresh_provenance, _source_identity, adapter


class ProvenanceTests(unittest.TestCase):
    def test_loaded_checkout_identity_is_separate_from_distribution_metadata(self):
        for name, package, source, runtime in (
            ("hf-arrow", "datasets", "datasets.iterable_dataset", "5.0.2.dev0"),
            (
                "torchdata",
                "torchdata",
                "torchdata.stateful_dataloader.stateful_dataloader",
                None,
            ),
        ):
            with self.subTest(adapter=name), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "source.py"
                content = b"# synthetic checkout source\n"
                path.write_bytes(content)
                root, implementation = ModuleType(package), ModuleType(source)
                if runtime is not None:
                    root.__version__ = runtime
                implementation.__file__ = str(path)
                provenance = {"adapter": name}
                with (
                    patch.dict(sys.modules, {package: root, source: implementation}),
                    patch("checkpoint_contract.adapters.version", return_value="5.0.1"),
                    patch(
                        "builtins.__import__",
                        side_effect=AssertionError("unexpected import"),
                    ),
                ):
                    _refresh_provenance(provenance)
                record = provenance["packages"][package]
                self.assertTrue(record["loaded"])
                self.assertEqual(record["runtime_version"], runtime)
                self.assertEqual(record["distribution_version"], "5.0.1")
                self.assertEqual(
                    record["source"],
                    {
                        "module": source,
                        "loaded": True,
                        "sha256": sha256(content).hexdigest(),
                    },
                )
                self.assertNotIn(tmp, str(provenance))

    def test_unavailable_source_has_null_hash(self):
        module = ModuleType("synthetic_source")
        with patch.dict(
            sys.modules, {"synthetic_source": module, "absent_source": None}
        ):
            self.assertEqual(
                _source_identity("synthetic_source"),
                {"module": "synthetic_source", "loaded": True, "sha256": None},
            )
            self.assertEqual(
                _source_identity("absent_source"),
                {"module": "absent_source", "loaded": False, "sha256": None},
            )

    def test_unsupported_modes_do_not_import(self):
        for name, mode in (
            ("hf-arrow", {"buffered_shuffle": True}),
            ("torchdata", {"in_order": False}),
        ):
            with (
                self.subTest(adapter=name),
                patch(
                    "builtins.__import__",
                    side_effect=AssertionError("unexpected import"),
                ),
            ):
                factory, _, _ = adapter(name, Case([[0]], 1, False), **mode)
                with self.assertRaises(Unsupported):
                    factory()
