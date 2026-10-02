# Release validation checklist

Run the checks below on the release revision and record the results. The CI
workflow tests Linux Python 3.11/3.12 and does not publish artifacts.

## Local reference commands

From a clean checkout/archive in Python 3.11.15, create a virtual environment and
install the exact build/development pins as in CONTRIBUTING. Keep optional
frameworks out of this first environment. Python 3.12.15 core coverage uses the same
commands. Provision packages from an approved index or verified local wheels;
offline runs may add `--no-index --find-links` to installation commands.

```sh
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -c 'from setuptools.build_meta import build_sdist, build_wheel; build_sdist("dist"); build_wheel("dist")'
python -I tools/release_check.py dist/checkpoint_contract-0.1.0-py3-none-any.whl dist/checkpoint_contract-0.1.0.tar.gz
python -m pip install --force-reinstall --no-deps dist/checkpoint_contract-0.1.0-py3-none-any.whl
python -I examples/custom_session.py
CHECKPOINT_CONTRACT_INSTALLED=1 CHECKPOINT_CONTRACT_CORE_ONLY=1 python -m unittest discover -s tests -p test_installed.py
python -m pip install --force-reinstall --no-deps --no-build-isolation dist/checkpoint_contract-0.1.0.tar.gz
python -I examples/custom_session.py
CHECKPOINT_CONTRACT_INSTALLED=1 CHECKPOINT_CONTRACT_CORE_ONLY=1 python -m unittest discover -s tests -p test_installed.py
```

Start with an empty `dist/` and no stale build metadata. The content inspector
requires the intended package, schema, examples, docs, tests and license in the
sdist, and only package files and distribution metadata/license in the wheel.
It rejects unexpected members (including logs, private notes, secrets/config and
runtime reports), unsafe paths/links, common private-path/key patterns, unexpected
runtime dependencies and mismatched package bytes. It reads archives without
extracting or importing them. It is a narrow release policy, not a comprehensive
secret or malware scanner; manually review the artifacts too.

The installed tests launch isolated Python outside the checkout and check the
resource location and actual console script. `CHECKPOINT_CONTRACT_CORE_ONLY=1`
also requires real missing-dependency run/replay results to be unsupported/3.
Do not set it in an environment containing optional frameworks.

After each wheel or sdist installation, also run the public contract suite from
outside the checkout (with the virtual environment still active):

```sh
release_source=$(pwd)
(
  contract_tmp=$(mktemp -d)
  trap 'rm -rf "$contract_tmp"' EXIT
  cd "$contract_tmp"
  CHECKPOINT_RELEASE_INSTALLED=1 python -I "$release_source/tests/test_public_contracts.py"
)
```

This suite includes CLI probes and two installed metadata/resource checks.
Ordinary source-suite runs skip those two checks unless explicitly opted in;
those skips are not installed-package validation. CI opts in after both artifact
installations.

For final acceptance, repeat the README verbatim from an extracted source archive
in a fresh environment. Also run the examples by absolute path with `python -I`
from a directory outside the checkout. Verify `checkpoint_contract.__file__`
points into that environment's site-packages. Test wheel and sdist installation
separately in clean environments rather than relying only on an in-place upgrade.

In a separate Python 3.11.15 environment, install the package and pinned
integration stack, then run `python -I tools/integration_smoke.py` as described in
[compatibility](compatibility.md). This requires the old HF negative control to
fail and current TorchData to pass. Separately rerun both historical affected/fixed
source pairs and the opt-in corrected-source matrix. Do not substitute the
fixed-source matrix for the pinned negative-control job.

## Release checklist

- Record the source revision, interpreter, dependency versions, commands, exit
  codes and artifact hashes. Include failures, skips and coverage limits.
- Check JSON v1 replay, reduction fingerprints, report schemas and privacy.
- Review the source, artifacts, README, changelog, release notes, MIT license and
  dependency notices. Keep private evidence and runtime reports out of artifacts.
- Run remote CI on the exact release revision and resolve failures before tagging.
- Tag the checked revision, attach the verified wheel and sdist to the release,
  and record their hashes. Rebuild and revalidate artifacts if the source changes.
