"""Synthetic good/faulty Session controls; no external dependencies or data."""

import json

from checkpoint_contract import Contract, check, reduce_schedule

# Hand-specified oracle, never obtained by draining the tested Session.
EXPECTED = [[0, 1], [2, 3], [4]]


class LocalSession:
    def __init__(self, faulty=False):
        self.rows = list(range(5))
        self.position = 0
        self.faulty = faulty

    def next_batch(self):
        if self.position >= len(self.rows):
            raise StopIteration
        batch = self.rows[self.position : self.position + 2]
        self.position += len(batch)
        return batch

    def snapshot(self):
        return {"position": self.position}

    def restore(self, state):
        self.position = state["position"]
        if self.faulty and self.position:
            self.position -= 1  # Deliberately repeat an occurrence on resume.

    def close(self):
        self.rows = []


def main():
    reports = {}
    for label, faulty in (("good", False), ("deliberately_faulty", True)):
        # Bind the flag so every evaluation creates a fresh, equivalent session.
        def evaluate(schedule, faulty=faulty):
            return check(lambda: LocalSession(faulty), EXPECTED, schedule, Contract())

        report = evaluate([1, 2])
        report["minimization"] = reduce_schedule([1, 2], evaluate, budget=50)
        reports[label] = report
    print(json.dumps(reports, indent=2))
    return (
        0
        if (
            reports["good"]["status"] == "pass"
            and reports["deliberately_faulty"]["status"] == "fail"
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
