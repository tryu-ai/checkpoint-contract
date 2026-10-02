"""Adversarial checks for the release archive inspection policy."""

import importlib.util
import io
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "release_check", Path(__file__).resolve().parents[1] / "tools/release_check.py"
)
release_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_check)


class ReleaseCheckTests(unittest.TestCase):
    def test_rejects_runtime_evidence_even_with_all_required_members(self):
        files = {name: b"" for name in release_check.WHEEL_FILES}
        files["reports/local-run.json"] = b"{}"
        with self.assertRaisesRegex(ValueError, "unexpected files"):
            release_check.check_contents(files, wheel=True)

    def test_rejects_private_paths_inside_intended_files(self):
        files = {name: b"" for name in release_check.WHEEL_FILES}
        # Assemble a synthetic path so the test itself is safe to distribute.
        files["checkpoint_contract/core.py"] = b"/" + b"Users/example/private/data"
        with self.assertRaisesRegex(ValueError, "private path"):
            release_check.check_contents(files, wheel=True)

    def test_rejects_traversal_and_absolute_members_without_extracting(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("../escape", "/absolute", "a/../escape", "C:\\escape"):
                path = Path(tmp) / "bad.whl"
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr(name, "untrusted")
                with self.subTest(name=name), self.assertRaises(ValueError):
                    release_check.read_archive(path)

    def test_rejects_sdist_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.tar.gz"
            with tarfile.open(path, "w:gz") as archive:
                entry = tarfile.TarInfo("checkpoint_contract-0.1.0/link")
                entry.type = tarfile.SYMTYPE
                entry.linkname = "../../outside"
                archive.addfile(entry)
            with self.assertRaises(ValueError):
                release_check.read_archive(path)

    def test_reads_regular_sdist_without_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "safe.tar.gz"
            with tarfile.open(path, "w:gz") as archive:
                entry = tarfile.TarInfo("checkpoint_contract-0.1.0/README.md")
                entry.size = 5
                archive.addfile(entry, io.BytesIO(b"hello"))
            self.assertEqual(release_check.read_archive(path), {"README.md": b"hello"})

    def test_metadata_rejects_unconditional_runtime_dependency(self):
        metadata = (
            "Name: checkpoint-contract\nVersion: 0.1.0\nRequires-Python: >=3.11\n"
            "License-Expression: MIT\nLicense-File: LICENSE\n"
            "Description-Content-Type: text/markdown\n"
            "Provides-Extra: hf-arrow\nProvides-Extra: torchdata\n"
            'Requires-Dist: datasets; extra == "hf-arrow"\n'
            'Requires-Dist: pyarrow; extra == "hf-arrow"\n'
            'Requires-Dist: torch; extra == "torchdata"\n'
            'Requires-Dist: torchdata; extra == "torchdata"\n'
            "\n# checkpoint-contract\n"
        ).encode()
        release_check.check_metadata(metadata)
        with self.assertRaises(ValueError):
            release_check.check_metadata(
                metadata.replace(
                    b'Requires-Dist: torch; extra == "torchdata"',
                    b"Requires-Dist: torch",
                )
            )
