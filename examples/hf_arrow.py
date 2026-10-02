"""Real HF Arrow/rebatch regression on synthetic local IDs; no network/weights.

Requires optional HF dependencies. datasets 5.0.1 is expected to exit 1 (fail).
The report goes to stdout; redirect it to a file for CLI replay.
"""

import json
from pathlib import Path

from checkpoint_contract.__main__ import EXIT, run_config


def main():
    config = json.loads(Path(__file__).with_name("hf_arrow_config.json").read_text())
    report = run_config(config)
    print(json.dumps(report, indent=2))
    return EXIT[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
