import argparse
import json
import platform
import sys
from pathlib import Path

from .adapters import _refresh_provenance, _source_identity, _version, adapter
from .cases import Case
from .core import _schedule, check, generate_schedules, reduce_schedule
from .schema import REPORT_SCHEMA

SCHEMA = REPORT_SCHEMA
EXIT = {"pass": 0, "fail": 1, "error": 2, "unsupported": 3}


def run_config(config):
    if type(config) is not dict or set(config) != {
        "adapter",
        "case",
        "schedules",
        "reduction_budget",
        "generation",
    }:
        raise ValueError("invalid replay configuration")
    case = Case.from_dict(config["case"])
    schedules = config["schedules"]
    if type(schedules) is not list or not 1 <= len(schedules) <= 101:
        raise ValueError("requires 1..101 schedules")
    for schedule in schedules:
        _schedule(schedule)
        if len(schedule) > 100 or max(schedule) > 1000000:
            raise ValueError("CLI schedule bounds exceeded")
    budget = config["reduction_budget"]
    if type(budget) is not int or not 1 <= budget <= 1000:
        raise ValueError("reduction budget must be 1..1000")
    generation = config["generation"]
    if type(generation) is not dict or set(generation) != {"seed", "count"}:
        raise ValueError("invalid generation config")
    generated = generate_schedules(**generation)
    if schedules[1:] != generated:
        raise ValueError("generated schedules do not match seed/count")
    factory, contract, provenance = adapter(config["adapter"], case)
    expected = case.batches()

    def evaluate(schedule):
        return check(factory, expected, schedule, contract, next_epoch_batches=expected)

    runs = []
    for schedule in schedules:
        result = evaluate(schedule)
        result["minimization"] = (
            reduce_schedule(schedule, evaluate, budget=budget)
            if result["status"] == "fail"
            else {"status": "not_applicable", "schedule": None, "evaluations": 0}
        )
        runs.append(result)
    status = next(
        (
            s
            for s in ("error", "fail", "unsupported")
            if any(r["status"] == s for r in runs)
        ),
        "pass",
    )
    _refresh_provenance(provenance)
    checker = {
        "version": _version("checkpoint-contract"),
        "sources": [
            _source_identity(name)
            for name in (
                "checkpoint_contract",
                __name__,
                "checkpoint_contract.core",
                "checkpoint_contract.cases",
                "checkpoint_contract.adapters",
            )
        ],
    }
    return {
        "schema": SCHEMA,
        "config": config,
        "status": status,
        "runs": runs,
        "provenance": {
            **provenance,
            "python": platform.python_version(),
            "checker": checker,
        },
        "scope": "bounded deterministic data-iterator checks; no raw checkpoints",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Bounded deterministic data-iterator resume-contract checker"
    )
    subs = parser.add_subparsers(dest="command", required=True)
    run = subs.add_parser("run")
    run.add_argument("--adapter", choices=("hf-arrow", "torchdata"), required=True)
    run.add_argument("--case", required=True)
    run.add_argument("--schedule", default="1,2,3")
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--generated-count", type=int, default=0)
    run.add_argument("--reduction-budget", type=int, default=50)
    run.add_argument("--report", required=True)
    replay = subs.add_parser("replay")
    replay.add_argument("source")
    replay.add_argument("--report", help="new report path; default stdout")
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            config = {
                "adapter": args.adapter,
                "case": json.loads(Path(args.case).read_text()),
                "schedules": [[int(x) for x in args.schedule.split(",")]]
                + generate_schedules(args.seed, args.generated_count),
                "generation": {"seed": args.seed, "count": args.generated_count},
                "reduction_budget": args.reduction_budget,
            }
        else:
            previous = json.loads(Path(args.source).read_text())
            if type(previous) is not dict or previous.get("schema") != SCHEMA:
                raise ValueError("unsupported report schema")
            config = previous["config"]
        report = run_config(config)
    except Exception as exc:
        report = {
            "schema": SCHEMA,
            "status": "error",
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        try:
            Path(args.report).write_text(encoded)
        except OSError as exc:
            print(
                json.dumps(
                    {
                        "schema": SCHEMA,
                        "status": "error",
                        "error": {"type": type(exc).__name__, "message": str(exc)},
                    }
                ),
                file=sys.stderr,
            )
            return EXIT["error"]
    else:
        print(encoded, end="")
    return EXIT[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
