# checkpoint-contract

Check whether a deterministic **data iterator** resumes with the expected batches,
order, occurrence counts, and termination. This small independent tool is for
data-pipeline and checkpoint-library maintainers who want a bounded oracle,
diagnostics, and replay for resume regressions. A custom `Session` API lets you
check another iterator without adopting either built-in framework adapter.

Version **0.1.0** requires Python
3.11+ and has zero runtime dependencies. It does not validate training, model,
optimizer, or distributed checkpoints, and a pass is not production validation.

## Try the core

From a source checkout or extracted source archive:

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements/build.txt
python -m pip install --no-build-isolation --no-deps .
python -I examples/custom_session.py
```

The example uses only the standard library and the installed package. It checks
a correct iterator and a deliberately faulty restore, prints both reports and a
schedule reduction, and exits successfully only when those controls behave as
expected.

The essential API call is:

```python
from checkpoint_contract import Contract, check

# make_session must create a fresh Session each time; see the runnable example.
result = check(make_session, [[0, 1], [2, 3], [4]], [1, 2], Contract())
```

Specify expected batches independently of the iterator under test. See the
[Session API and contract](docs/api.md) for freshness, exhaustion and serialization.

## Real adapters and CLI

After installing the optional [pinned dependencies](docs/compatibility.md):

```sh
python -I examples/hf_arrow.py
python -I examples/torchdata_resume.py
checkpoint-check run --adapter torchdata --case examples/regression.json --schedule 1,1,3 --generated-count 3 --seed 17 --report torch-report.json
checkpoint-check replay torch-report.json --report replay.json
```

Both examples use actual adapters with small synthetic local data: no network,
datasets downloaded from a hub, or model weights. HF uses version-sensitive Arrow
rebatching internals; TorchData uses `StatefulDataLoader` with zero workers.
**The HF example is a regression demonstration:** pinned datasets 5.0.1 is
affected and should report `fail` (exit 1). TorchData 0.11.0 should pass. See the
[compatibility matrix and historical replay path](docs/compatibility.md).

CLI exit codes are **0 pass, 1 fail, 2 error, 3 unsupported**. Missing optional
packages produce unsupported, not a detected bug. A fail means an observed
contract mismatch; an error means evaluation could not complete. A pass covers
only the supplied data, schedules, modes and call bounds. The CLI also works as
`python -m checkpoint_contract`; its commands remain `run` and `replay`.
See [reports, reduction and privacy](docs/api.md#reports-and-replay).

## Where it fits

[Hypothesis](https://hypothesis.readthedocs.io/en/latest/stateful.html) already
generates and shrinks state sequences.
[HF streaming resume](https://huggingface.co/docs/datasets/stream) and
[TorchData resume](https://docs.pytorch.org/data/main/stateful_dataloader_tutorial.html)
provide iterator state APIs; this tool adds an independent expected-output oracle,
diagnostics and replay around selected providers.
[PyTorch DCP](https://docs.pytorch.org/tutorials/recipes/distributed_checkpoint_recipe.html)
handles distributed storage and model state, outside this tool's scope.

[Contributing](CONTRIBUTING.md) · [Security and trust](SECURITY.md) ·
[Changelog](CHANGELOG.md) · [Release checklist](docs/releasing.md) ·
[Provenance](docs/provenance.md) · [MIT license](LICENSE)
