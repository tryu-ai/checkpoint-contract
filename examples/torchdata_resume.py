"""Real TorchData resume on synthetic local IDs; no network or model weights.

Requires optional TorchData dependencies. Pinned TorchData should exit 0 (pass).
The report goes to stdout; redirect it to a file for CLI replay.
"""

import json
from pathlib import Path

from checkpoint_contract.__main__ import EXIT, run_config


def main():
    config = json.loads(Path(__file__).with_name("torchdata_config.json").read_text())
    report = run_config(config)
    print(json.dumps(report, indent=2))
    return EXIT[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
