"""Standard-library-only bounded checking; snapshots are never compared."""

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass
from random import Random
from typing import Callable, Literal, Protocol

ID = str | int


class Session(Protocol):
    def next_batch(self) -> list[ID]: ...
    def snapshot(self) -> object: ...
    def restore(self, state: object) -> None: ...
    def close(self) -> None: ...


class Unsupported(Exception):
    """Documented unavailable adapter/mode, not a detected resume defect."""


@dataclass(frozen=True)
class Contract:
    exact_resume: bool = True
    exhausted_restore: Literal["empty", "next_epoch", "unsupported"] = "empty"
    reason: str | None = None


def _schedule(schedule):
    if (
        type(schedule) is not list
        or not schedule
        or any(type(n) is not int or n <= 0 for n in schedule)
    ):
        raise ValueError("schedule must be a nonempty list of positive integers")


def _batches(batches):
    if type(batches) is not list or any(
        type(b) is not list or not b or any(type(x) not in (str, int) for x in b)
        for b in batches
    ):
        raise ValueError("expected batches must be a list of nonempty ID lists")


def _counts(batches):
    c = Counter(x for batch in batches for x in batch)
    return [
        {"id": x, "count": n}
        for x, n in sorted(c.items(), key=lambda p: (type(p[0]).__name__, repr(p[0])))
    ]


def _difference(expected, actual, phase, terminated):
    if expected == actual and terminated:
        return None
    first = next(
        (i for i in range(min(len(expected), len(actual))) if expected[i] != actual[i]),
        min(len(expected), len(actual)),
    )
    e = expected[first] if first < len(expected) else None
    a = actual[first] if first < len(actual) else None
    row = next(
        (i for i in range(min(len(e or []), len(a or []))) if e[i] != a[i]),
        min(len(e or []), len(a or [])),
    )
    return {
        "failure_class": "output_mismatch"
        if expected != actual
        else "termination_bound",
        "phase": phase,
        "first_divergence": {
            "batch": first,
            "row_in_batch": row,
            "expected_batch": e,
            "actual_batch": a,
        },
        "expected_ids": expected,
        "actual_ids": actual,
        "expected_multiplicities": _counts(expected),
        "actual_multiplicities": _counts(actual),
        "observed_stop_iteration": terminated,
    }


def check(
    factory: Callable[[], Session],
    expected_batches: list[list[ID]],
    schedule: list[int],
    contract: Contract,
    *,
    next_epoch_batches: list[list[ID]] | None = None,
    serializer=None,
) -> dict:
    """Check independent expectations. Optional serializer has dumps/loads methods.

    Every probe uses fresh sessions. Bounds count next_batch calls per probe;
    a blocking factory/session cannot be time-limited here (executor isolation).
    """
    result = {
        "status": "error",
        "schedule": deepcopy(schedule),
        "checks": [],
        "failure": None,
        "snapshot_transport": "serializer" if serializer is not None else "deepcopy",
    }
    current = None
    phase = "configuration"
    try:
        _schedule(schedule)
        _batches(expected_batches)
        if (
            not isinstance(contract, Contract)
            or type(contract.exact_resume) is not bool
            or contract.exhausted_restore not in ("empty", "next_epoch", "unsupported")
            or (contract.reason is not None and type(contract.reason) is not str)
        ):
            raise ValueError("invalid contract")
        result["contract"] = asdict(contract)
        if next_epoch_batches is not None:
            _batches(next_epoch_batches)
        if contract.exhausted_restore == "next_epoch" and next_epoch_batches is None:
            raise ValueError(
                "next_epoch requires independently known next_epoch_batches"
            )
        bound = len(expected_batches) + 2
        result["bounds"] = {
            "current_epoch_calls_per_probe": bound,
            "next_epoch_calls": len(next_epoch_batches or []) + 2,
        }
        if not contract.exact_resume:
            raise Unsupported(contract.reason or "exact resume unsupported")

        def fresh():
            nonlocal current
            current = factory()

        def close():
            nonlocal current
            old, current = current, None
            if old is not None:
                old.close()

        def resume():
            state = current.snapshot()
            state = (
                serializer.loads(serializer.dumps(state))
                if serializer is not None
                else deepcopy(state)
            )
            close()
            fresh()
            current.restore(state)  # before next_batch creates a resumed iterator

        def read():
            batch = current.next_batch()
            if (
                type(batch) is not list
                or not batch
                or any(type(x) not in (str, int) for x in batch)
            ):
                raise TypeError("session returned an invalid batch")
            return batch[:]

        def drain(limit, scheduled=False):
            out, index, remaining = [], 0, schedule[0]
            for _ in range(limit):
                try:
                    out.append(read())
                except StopIteration:
                    return out, True
                if scheduled:
                    remaining -= 1
                    if remaining == 0:
                        resume()
                        index = (index + 1) % len(schedule)
                        remaining = schedule[index]
            return out, False

        def verify(expected, actual, stopped):
            failure = _difference(expected, actual, phase, stopped)
            result["checks"].append(
                {"phase": phase, "status": "fail" if failure else "pass"}
            )
            if failure:
                result.update(status="fail", failure=failure)
                return False
            return True

        for phase in ("baseline", "initial_restore", "scheduled_restore"):
            fresh()
            if phase != "baseline":
                resume()
            actual, stopped = drain(bound, phase == "scheduled_restore")
            close()
            if not verify(expected_batches, actual, stopped):
                return result

        # Deliberately do not ask for StopIteration before this snapshot.
        phase = "before_stop_iteration"
        fresh()
        prefix = []
        for _ in expected_batches:
            try:
                prefix.append(read())
            except StopIteration:
                verify(expected_batches, prefix, True)
                return result
        if prefix != expected_batches:
            verify(expected_batches, prefix, True)
            return result
        resume()
        actual, stopped = drain(2)
        close()
        if not verify([], actual, stopped):
            return result

        phase = "after_stop_iteration"
        if contract.exhausted_restore == "unsupported":
            result["checks"].append(
                {"phase": phase, "status": "unsupported", "reason": contract.reason}
            )
            result["status"] = "unsupported"
            return result
        fresh()
        actual, stopped = drain(bound)
        if not verify(expected_batches, actual, stopped):
            return result
        resume()
        expected = (
            next_epoch_batches if contract.exhausted_restore == "next_epoch" else []
        )
        actual, stopped = drain(len(expected) + 2)
        close()
        if verify(expected, actual, stopped):
            result["status"] = "pass"
        return result
    except Unsupported as exc:
        result.update(status="unsupported", reason=str(exc))
    except Exception as exc:
        result.update(
            status="error",
            error={"phase": phase, "type": type(exc).__name__, "message": str(exc)},
        )
    finally:
        if current is not None:
            try:
                current.close()
            except Exception as exc:
                result.update(
                    status="error",
                    error={
                        "phase": "close",
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                )
    return result


def generate_schedules(seed: int, count: int, *, max_length=6, max_step=5):
    if (
        type(seed) is not int
        or type(count) is not int
        or not 0 <= count <= 100
        or any(type(v) is not int or not 1 <= v <= 100 for v in (max_length, max_step))
    ):
        raise ValueError("invalid generation bounds (count 0..100; length/step 1..100)")
    rng = Random(seed)
    return [
        [rng.randint(1, max_step) for _ in range(rng.randint(1, max_length))]
        for _ in range(count)
    ]


def reduce_schedule(schedule, evaluate, *, budget=50):
    """Greedy local reduction preserving the observable failure, not its cause.

    Missing synthetic diagnostic fields remain distinct from explicit None.
    Fingerprints detach evaluator-owned values before any subsequent evaluation.
    """
    _schedule(schedule)
    if type(budget) is not int or not 1 <= budget <= 1000:
        raise ValueError("reduction budget must be 1..1000")
    current = schedule[:]
    first = evaluate(current)
    calls = 1

    def fingerprint(r):
        f = r.get("failure") or {}
        return deepcopy(
            {
                **({"status": r["status"]} if "status" in r else {}),
                **{
                    key: f[key]
                    for key in (
                        "failure_class",
                        "phase",
                        "expected_ids",
                        "actual_ids",
                        "observed_stop_iteration",
                    )
                    if key in f
                },
            }
        )

    def typed(value):
        # Preserve nesting and scalar types (e.g. integer 1 versus bool True).
        if type(value) is list:
            return (list, tuple(typed(item) for item in value))
        if type(value) is dict:
            return (dict, tuple((key, typed(item)) for key, item in value.items()))
        return (type(value), value)

    observable = fingerprint(first)
    target = typed(observable)
    if observable.get("status") != "fail":
        return {"schedule": current, "status": "not_applicable", "evaluations": calls}
    while True:
        candidates = (
            [current[:i] + current[i + 1 :] for i in range(len(current))]
            if len(current) > 1
            else []
        )
        candidates += [
            current[:i] + [n - 1] + current[i + 1 :]
            for i, n in enumerate(current)
            if n > 1
        ]
        for candidate in candidates:
            if calls >= budget:
                return {
                    "schedule": current,
                    "status": "budget_exhausted",
                    "evaluations": calls,
                }
            outcome = evaluate(candidate)
            calls += 1
            if outcome.get("status") in ("error", "unsupported"):
                return {
                    "schedule": current,
                    "status": "inconclusive",
                    "evaluations": calls,
                }
            if typed(fingerprint(outcome)) == target:
                current = candidate
                break
        else:
            return {
                "schedule": current,
                "status": "1-minimal",
                "evaluations": calls,
                "edits": [
                    "delete one entry (nonempty)",
                    "decrement one entry by one (positive)",
                ],
                "preserved_failure": [
                    observable.get(key) for key in ("status", "failure_class", "phase")
                ],
                "observable_fingerprint": observable,
            }
