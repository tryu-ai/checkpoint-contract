# Contract and API

`check(factory, expected_batches, schedule, contract, *, next_epoch_batches=None,
serializer=None)` returns one run dictionary. `Contract()` requires exact resume
and an empty stream after restoring observed exhaustion. `Session` is a structural
protocol; inheritance is not required. See [the runnable example](../examples/custom_session.py).

## Fresh sessions and independent expectations

Every factory call must create an independent dataset, iterator, sampler, RNG and
loader as applicable. Do not return a singleton or share mutable iterator state.
The checker closes the old session, creates a new one, then calls `restore`
before its first `next_batch`. A session implements:

| Method | Responsibility |
| --- | --- |
| `next_batch()` | Return a nonempty list of string/integer occurrence IDs; raise `StopIteration` at EOF. |
| `snapshot()` | Return state sufficient to resume, detached from mutable live iterator state. |
| `restore(state)` | Load state before starting the resumed iterator. |
| `close()` | Release resources; cleanup exceptions are errors. |

Expected batches must be specified independently, not captured from the iterator's
uninterrupted run. An incorrect baseline fails instead of becoming the oracle.
Use occurrence IDs rather than content labels when repeated content must be
distinguished. The custom API permits repeated IDs, but indistinguishable
occurrences limit what it can detect. IDs must be exact `str` or `int`, not bools.

The built-in `Case(tables, batch_size, drop_last)` requires unique integer IDs.
Its independent oracle flattens the handwritten tables, truncates for drop-last,
and slices batches without consulting either framework. JSON cases require
exactly those three fields; batch size is positive and drop-last is boolean.
An empty expected epoch is `[]`, never `[[]]`.

## Schedules and exhaustion

A schedule is a nonempty list of positive integers counting **batches between
checkpoints**, repeated cyclically: `[1, 2]` saves after one batch, then two more,
then one more, and so on. Probes separately check baseline, initial restore,
scheduled restores, a snapshot just after the last batch but before observed
`StopIteration`, and a snapshot after observed `StopIteration`.

`Contract(exhausted_restore="next_epoch")` requires independently specified
`next_epoch_batches`. `"empty"` expects no more batches; `"unsupported"` leaves
that phase unsupported and prevents an overall pass. `exact_resume=False` also
produces unsupported, with an optional `reason`.

Each current-epoch drain is bounded by expected batch count + 2 calls; the
next-epoch drain uses next-epoch batch count + 2. Bounds detect some runaway
output, but cannot interrupt a blocking factory or method. Use process isolation
and an external timeout for wall time and resource limits.

## Snapshot transport

The default transport is local `deepcopy`, not durable checkpoint serialization.
Snapshots are never compared for equality or written into reports. Supplying a
trusted object with `dumps(state)` and `loads(payload)` exercises that roundtrip;
it does not by itself test filesystem durability, crash consistency, storage
atomicity, or portability. Snapshot methods, deepcopy hooks and serializer
methods can execute code. Never deserialize untrusted pickle or other executable
formats. See [security notes](../SECURITY.md).

## Reports and replay

`check` returns an individual run, not a complete CLI envelope. Full CLI reports
include config, runs, minimization, provenance and scope. `report_schema()` returns
a fresh Draft 2020-12 schema dictionary without a third-party dependency. The
packaged resource is `checkpoint_contract/schemas/report-v1.json`.

| Status / CLI exit | Interpretation |
| --- | --- |
| `pass` / 0 | Supplied contract held for these bounded probes. |
| `fail` / 1 | Output or bounded termination differed from expectations. Check oracle and adapter too. |
| `error` / 2 | Invalid configuration, incompatible API, unexpected exception or cleanup failure. |
| `unsupported` / 3 | Missing optional dependency or explicitly unsupported contract/mode. |

For multiple schedules, aggregate precedence is error, fail, unsupported, pass.
Argument-parser usage errors use stderr and exit 2 without a JSON report.
Configuration errors after parsing generate JSON; report write errors use stderr.

`checkpoint-check run --help` lists arguments. The first schedule comes from
`--schedule` (default `1,2,3`); `--generated-count` adds at most 100 seeded schedules
with default lengths 1..6 and steps 1..5. CLI schedule length is at most 100 and
each step at most 1,000,000. Reduction budgets are 1..1000 (default 50).

`checkpoint-check replay old.json --report new.json` rechecks the embedded case
and schedules in the current environment. It validates the schema identifier and
configuration, including regenerated schedules; it ignores old outcomes and
provenance. It does not validate the entire old envelope against JSON Schema,
install dependencies, recover raw checkpoints or select source commits. Old
`checkpoint-contract/v1` reports remain replayable; the schema identifier is
independent of package version. Optional full-envelope validation with `jsonschema`
checks structure, not authenticity, oracle correctness or semantic consistency.

Reports expose IDs, expected/actual batches, multiplicities and exception messages.
Messages may contain paths or sensitive text from user code/dependencies. Use
synthetic IDs and inspect reports before sharing. Provenance deliberately omits
filesystem paths, but this is not a general redaction guarantee.

Provenance separates loaded runtime versions, distribution metadata and hashes of
selected loaded source files. Hashes are computed at report time, not an
attestation of the whole environment or proof files were unchanged since import.
Missing source or metadata is null. Installed metadata can differ from the loaded
checkout. No report is cryptographically authenticated.

## Schedule reduction

`reduce_schedule(schedule, evaluate, budget=50)` repeatedly evaluates fresh runs.
It greedily deletes an entry or decrements one by one, keeping a nonempty positive
schedule. A `1-minimal` result means no such single edit preserves the observable
failure; it is not globally minimal and does not minimize data or establish cause.

The fingerprint preserves status, failure class, phase, exact nested expected and
actual IDs (types, order, batching and multiplicities), and observed termination.
It detaches evaluator-owned values. Missing fields in lightweight synthetic runs
differ from explicit null. Other diagnostics may change. The legacy three-field
`preserved_failure` remains; `observable_fingerprint` is an optional v1 schema
extension on a 1-minimal result. Budget exhaustion and inconclusive evaluations
do not establish minimality. A non-failing input is `not_applicable`.

## Explicit limits

No exhaustive bug discovery, nondeterministic equivalence, multiprocess worker
state, distributed training, GPU state, model/optimizer state, cloud storage,
performance or production validation is claimed. The two adapters exercise small
deterministic single-process cases, not their frameworks' entire resume APIs.
Custom Session implementations can extend coverage, but their contracts, oracles
and unsupported modes remain the caller's responsibility.
