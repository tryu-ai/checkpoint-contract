"""Versioned report schema, available without third-party dependencies."""

import json
from importlib.resources import files

REPORT_SCHEMA = "checkpoint-contract/v1"


def report_schema():
    """Return a fresh schema dictionary from installed package data.

    Describes report structure only; does not authenticate reports or validate
    replay semantics. Optional external JSON Schema validators can consume it.
    """
    resource = files("checkpoint_contract").joinpath("schemas/report-v1.json")
    return json.loads(resource.read_text(encoding="utf-8"))
