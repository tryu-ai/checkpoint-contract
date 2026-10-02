# Dependencies and compatibility

The core has zero runtime dependencies. Python 3.11.15 is the pinned reference
interpreter; CI also targets Python 3.12.15 for the core. The pins below define
the release validation path; other optional versions require separate checks.

| Component | Reference version / expectation |
| --- | --- |
| Build tools | setuptools 84.0.0, wheel 0.48.0 |
| Development | pytest 9.1.1, jsonschema 4.26.0, ruff 0.16.10 |
| HF Arrow/rebatch | datasets 5.0.1, pyarrow 25.0.1: known affected regression should FAIL |
| TorchData | torch 2.14.1, torchdata 0.11.0: deterministic regression fixture should PASS |
| HF corrected source | `482480c8b7e6452f7f54faa4ba448083eff07486`: fixed-source suite expects PASS |

Direct pins live in `requirements/`; build, development and integration files
include `constraints.txt` relative to their own location. The constraints lock
54 resolved reference versions from CPython 3.11.15 on macOS arm64. They are not
a universal platform lock or wheel hash manifest: other platforms may require
additional platform-specific dependencies, and wheel availability can differ.
Actual wheel hashes remain in external validation evidence. Record the resolved
dependencies, wheel hashes and source identities for each validation environment.
Broad optional extras (`.[hf-arrow]`, `.[torchdata]`) declare integrations without
invented upper bounds. They are not tested-version guarantees; use the pins for
the reference path.

## Provision and run the pinned integration smoke check

In the source checkout/archive and a Python 3.11.15 virtual environment with the
core installed, on Linux CPU:

```sh
python -m pip install --no-deps -c requirements/constraints.txt torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements/integration.txt
python -m pip check
python -I tools/integration_smoke.py
```

The first command installs only the official CPU wheel with `--no-deps`, because
the CPU index lacks the project's pinned `filelock==4.0.9` dependency.
The second command resolves dependencies from PyPI using the existing integration
pins and constraints, against the installed CPU Torch. Under PEP 440,
`torch==2.14.1` accepts `2.14.1+cpu`: a version specifier without a local suffix
ignores the candidate's local suffix, so the installed CPU wheel satisfies the
unchanged pin. After all installations, `pip check` fails on missing dependencies
or installed versions that violate package dependency requirements, validating
the dependencies deferred by `--no-deps` before the smoke check runs.

Other platforms may install the reference pins from their
usual official package index when suitable wheels are available. No framework
data or weights are downloaded by examples or smoke checks. Dependency
installation itself requires a package index or a preprovisioned wheel cache.

The smoke script checks reference versions, runs both executable examples from
outside the checkout against the installed module, and replays their reports.
It requires TorchData `pass` and the exact known HF `output_mismatch` at
`scheduled_restore`: expected `[[0,1,2,3],[4,5,6,7],[8,9,10,11]]`, actual
`[[0,1,2,3],[4,5,6,7],[10,11]]`, with observed `StopIteration`. The HF schedule
`[1,1,3]` must reduce to `[1]` with status `1-minimal` while retaining that
observable failure fingerprint. An unexpected HF pass or a different failure
fails the negative control.
Neither checker nor adapter changes its outcome based on package version.
Framework examples retain normal checker exit codes; the smoke script exits 0
only when the expected compatibility outcomes hold.

HF uses `ArrowExamplesIterable`, `RebatchedArrowExamplesIterable` and private
`_init_state_dict`; installed incompatible APIs are errors. Its exhausted restore
contract is empty. TorchData uses `StatefulDataLoader`, `num_workers=0`,
`shuffle=False`, `in_order=True` and a fresh seeded generator; observed exhaustion
restores the next epoch. HF buffered shuffle and TorchData `in_order=False` are
explicitly unsupported API modes. Missing optional packages are unsupported.

## Historical regression replay

These are known upstream regressions, not discoveries attributed to this tool.
The following source pairs provide affected and corrected reference cases.

| Adapter | Affected source: expected fail | Corrected source: expected pass |
| --- | --- | --- |
| HF | `b74f51177908d6b9bf375112abfb3b105d36b775` | `482480c8b7e6452f7f54faa4ba448083eff07486` |
| TorchData | `fe6b4054e5e8b19f3dae615e852ef47515179abf` | `f15fd3a23312f704d1f82b740ba7d7b09c6dcbd8` |

Use separately prepared environments for each source, the same
`examples/regression.json`, schedule `1,1,3`, seed 17 and generated count 3:

```sh
checkpoint-check run --adapter hf-arrow --case examples/regression.json --schedule 1,1,3 --seed 17 --generated-count 3 --report affected.json
# In the corrected-source environment, with the original report available:
checkpoint-check replay affected.json --report corrected.json
```

Repeat with `--adapter torchdata` in the first command for its pair. Affected HF
historically loses occurrence IDs 8 and 9; affected TorchData resumes empty after
observed exhaustion instead of starting the next epoch. Keep both reports and
compare equal configurations, diagnoses, versions and source hashes. A commit
label alone is not an attestation of loaded source.

The older full matrix in `tests/test_adapters.py` expects corrected HF behavior,
including empty source tables. It is distinct from the pinned release smoke:

```sh
# Only with the corrected HF source above and the compatible TorchData stack:
CHECKPOINT_CONTRACT_INTEGRATION=1 python -m unittest discover -s tests -p test_adapters.py
```

Do not set that flag for the datasets 5.0.1 CI job. Failing it on the known
affected release is compatibility evidence, not a reason to skip or weaken the
historical negative controls.
