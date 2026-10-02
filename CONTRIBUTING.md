# Contributing

Keep the tool small: bounded deterministic iterator contracts, independent
expectations, and useful failure diagnostics. Explain the contract and regression
when proposing a change. Add a focused test for changed behavior; distinguish
synthetic faults from evidence produced by real frameworks. Do not copy upstream
implementations or include private data, checkpoints or runtime logs.

In a Python 3.11.15 virtual environment, from the checkout:

```sh
python -m pip install -r requirements/build.txt -r requirements/dev.txt
python -m pip install --no-build-isolation --no-deps .
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -I examples/custom_session.py
```

`python -m unittest discover -s tests` also runs the core suite. Schema validation
tests require the pinned jsonschema dependency; otherwise they skip. Optional
frameworks are not needed for core tests. The integration and installed-package
suites are explicit opt-ins; see [compatibility](docs/compatibility.md) and
[release checks](docs/releasing.md). Do not enable fixed-source tests against the
known affected HF release merely to get a green integration job.

Include commands, environment versions and outcomes when sharing a patch. Do not
claim checks that were not run. Preserve JSON v1 replay compatibility and document
changes to contract or reduction semantics. Contributions are proposed under the
project's MIT license; there is no additional CLA defined here.
