"""Inspect a 0.1.0 wheel and sdist without importing or extracting their code.

This is a release content policy, not a general malware or secret scanner.
"""

import argparse
import configparser
import json
import re
import stat
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

PACKAGE = {
    "checkpoint_contract/" + name
    for name in (
        "__init__.py",
        "__main__.py",
        "adapters.py",
        "cases.py",
        "core.py",
        "schema.py",
        "schemas/report-v1.json",
    )
}
SOURCE = PACKAGE | {
    "LICENSE",
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "pyproject.toml",
    "MANIFEST.in",
    ".python-version",
    ".gitignore",
    ".github/workflows/ci.yml",
    "docs/api.md",
    "docs/compatibility.md",
    "docs/provenance.md",
    "docs/releasing.md",
    "docs/release-notes-0.1.0.md",
    "examples/custom_session.py",
    "examples/hf_arrow.py",
    "examples/torchdata_resume.py",
    "examples/regression.json",
    "examples/hf_arrow_config.json",
    "examples/torchdata_config.json",
    "requirements/build.txt",
    "requirements/dev.txt",
    "requirements/integration.txt",
    "requirements/constraints.txt",
    "tools/release_check.py",
    "tools/integration_smoke.py",
    "tests/test_core.py",
    "tests/test_adapters.py",
    "tests/test_cli.py",
    "tests/test_installed.py",
    "tests/test_provenance.py",
    "tests/test_schema.py",
    "tests/test_release_check.py",
    "tests/test_public_contracts.py",
}
DIST_INFO = "checkpoint_contract-0.1.0.dist-info/"
EGG_INFO = "checkpoint_contract.egg-info/"
WHEEL_FILES = PACKAGE | {
    DIST_INFO + name
    for name in (
        "METADATA",
        "WHEEL",
        "RECORD",
        "entry_points.txt",
        "top_level.txt",
        "licenses/LICENSE",
    )
}
SDIST_GENERATED = {"PKG-INFO", "setup.cfg"} | {
    EGG_INFO + name
    for name in (
        "PKG-INFO",
        "SOURCES.txt",
        "dependency_links.txt",
        "entry_points.txt",
        "requires.txt",
        "top_level.txt",
    )
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_name(name):
    path = PurePosixPath(name)
    require(
        bool(name)
        and not path.is_absolute()
        and ".." not in path.parts
        and "\\" not in name
        and ":" not in name
        and name == path.as_posix(),
        f"unsafe archive member: {name!r}",
    )


def read_archive(path):
    files = {}
    total = 0

    def add(name, size, read):
        nonlocal total
        safe_name(name)
        require(name not in files, f"duplicate member: {name}")
        total += size
        require(size <= 2_000_000 and total <= 10_000_000, "unexpected archive size")
        files[name] = read()

    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                safe_name(member.filename.rstrip("/"))
                mode = member.external_attr >> 16
                require(not stat.S_ISLNK(mode), "wheel contains symlink")
                if not member.is_dir():
                    add(member.filename, member.file_size, lambda: archive.read(member))
    else:
        with tarfile.open(path, "r:gz") as archive:
            for member in archive:
                safe_name(member.name)
                require(
                    member.isdir() or member.isfile(),
                    "sdist contains link/special file",
                )
                if member.isfile():
                    add(
                        member.name,
                        member.size,
                        lambda: archive.extractfile(member).read(),
                    )
        prefix = "checkpoint_contract-0.1.0/"
        require(all(name.startswith(prefix) for name in files), "unexpected sdist root")
        files = {name[len(prefix) :]: data for name, data in files.items()}
    return files


def check_metadata(data):
    meta = BytesParser().parsebytes(data)
    require(meta["Name"] == "checkpoint-contract", "wrong distribution name")
    require(meta["Version"] == "0.1.0", "wrong distribution version")
    require(meta["Requires-Python"] == ">=3.11", "wrong Python requirement")
    require(meta["License-Expression"] == "MIT", "missing MIT expression")
    require("LICENSE" in meta.get_all("License-File", []), "missing license metadata")
    require(
        meta["Description-Content-Type"] == "text/markdown", "missing Markdown README"
    )
    require(
        "# checkpoint-contract" in meta.get_payload(), "README missing from metadata"
    )
    require(
        not meta.get_all("Project-URL") and not meta["Home-page"],
        "unreviewed project URL",
    )
    require(
        set(meta.get_all("Provides-Extra", [])) == {"hf-arrow", "torchdata"},
        "wrong extras",
    )
    dependencies = meta.get_all("Requires-Dist", [])
    expected = {
        "datasets;extra=='hf-arrow'",
        "pyarrow;extra=='hf-arrow'",
        "torch;extra=='torchdata'",
        "torchdata;extra=='torchdata'",
    }
    normalized = {re.sub(r"\s+", "", dep).replace('"', "'") for dep in dependencies}
    require(
        normalized == expected and len(dependencies) == 4,
        "unexpected runtime dependencies or optional dependency metadata",
    )


def check_contents(files, *, wheel):
    required = WHEEL_FILES if wheel else SOURCE | {"PKG-INFO"}
    allowed = WHEEL_FILES if wheel else SOURCE | SDIST_GENERATED
    require(
        required <= files.keys(),
        f"missing intended files: {sorted(required - files.keys())}",
    )
    require(
        files.keys() <= allowed, f"unexpected files: {sorted(files.keys() - allowed)}"
    )
    for name, data in files.items():
        text = data.decode("utf-8")  # All intended release files are text.
        require(
            not re.search(r"/(?:Users|home)/[^\s/]+/", text), f"private path in {name}"
        )
        require(not re.search(r"[A-Z]:\\Users\\", text), f"private path in {name}")
        require(
            not re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", text),
            f"private key in {name}",
        )
        require(
            not re.search(r"AKIA[A-Z0-9]{16}", text), f"credential pattern in {name}"
        )
    license_name = DIST_INFO + "licenses/LICENSE" if wheel else "LICENSE"
    license_text = files[license_name].decode("utf-8")
    require(
        "Copyright (c) 2026 checkpoint-contract contributors" in license_text,
        "wrong copyright",
    )
    require('THE SOFTWARE IS PROVIDED "AS IS"' in license_text, "incomplete license")
    schema = json.loads(files["checkpoint_contract/schemas/report-v1.json"])
    require(
        schema["$id"] == "urn:checkpoint-contract:report:v1", "wrong schema resource"
    )
    metadata = DIST_INFO + "METADATA" if wheel else "PKG-INFO"
    check_metadata(files[metadata])
    if wheel:
        entry = configparser.ConfigParser()
        entry.read_string(files[DIST_INFO + "entry_points.txt"].decode("utf-8"))
        require(
            dict(entry["console_scripts"])
            == {"checkpoint-check": "checkpoint_contract.__main__:main"},
            "wrong console entry point",
        )
        wheel_meta = BytesParser().parsebytes(files[DIST_INFO + "WHEEL"])
        require(wheel_meta["Root-Is-Purelib"] == "true", "wheel must be pure Python")
        require(wheel_meta.get_all("Tag") == ["py3-none-any"], "unexpected wheel tag")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("sdist", type=Path)
    args = parser.parse_args(argv)
    require(
        args.wheel.name == "checkpoint_contract-0.1.0-py3-none-any.whl",
        "wrong wheel filename",
    )
    require(
        args.sdist.name == "checkpoint_contract-0.1.0.tar.gz", "wrong sdist filename"
    )
    wheel = read_archive(args.wheel)
    sdist = read_archive(args.sdist)
    check_contents(wheel, wheel=True)
    check_contents(sdist, wheel=False)
    for name in PACKAGE:
        require(wheel[name] == sdist[name], f"wheel/sdist source mismatch: {name}")
    require(
        wheel[DIST_INFO + "licenses/LICENSE"] == sdist["LICENSE"], "license mismatch"
    )
    print("0.1.0 wheel/sdist content, metadata, license and schema checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
