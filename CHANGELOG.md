# Changelog

## 0.1.0

- Bounded deterministic data-iterator checks for baseline, initial and scheduled
  restores, and checkpoints before and after observed exhaustion.
- Custom Session API, independently specified expected batches, optional
  serializer roundtrips, seeded schedules and bounded local schedule reduction.
- Real optional HF Arrow/rebatch and TorchData adapters with synthetic local cases.
- CLI run/replay, JSON v1 schema, source provenance and observable-failure
  fingerprints. Older v1 replay configurations remain supported.
- Runnable examples, known-regression compatibility checks, pinned validation
  dependencies, MIT license and source/wheel inspection tools.
