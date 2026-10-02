# checkpoint-contract 0.1.0

Bounded deterministic **data-iterator** resume verification. Built for data-pipeline and checkpoint-library maintainers.

The standard-library-only core compares independently specified expected batches
with baseline and restored sessions, including checkpoints before and after
observed exhaustion. It reports divergence, occurrence counts and bounded
termination, with schedule reduction that preserves observable failure details.

The custom Session API supports other iterators. Optional adapters exercise HF
Arrow rebatching internals and TorchData StatefulDataLoader using small local
synthetic data. CLI `run` and `replay` use JSON v1; older v1 replay configurations
remain supported. Reports contain no raw checkpoint dumps.

The reference compatibility path pins Python 3.11.15, datasets 5.0.1, pyarrow
25.0.1, torch 2.14.1 and torchdata 0.11.0. HF 5.0.1 is known affected: the supplied
regression is expected to fail while the TorchData control should pass. The
corrected-source suite is separate. These are regression controls, not claims
of new upstream bug discoveries.

Install from a source checkout/archive following README. MIT licensed, with no
core runtime dependencies. This release does not validate training/model/optimizer
checkpoints, distributed execution or durable storage. See docs for trust and
coverage limits.
