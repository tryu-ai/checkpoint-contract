from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    tables: list[list[int]]
    batch_size: int
    drop_last: bool

    def __post_init__(self):
        if type(self.batch_size) is not int or self.batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")
        if type(self.drop_last) is not bool:
            raise ValueError("drop_last must be a boolean")
        if type(self.tables) is not list or any(
            type(t) is not list for t in self.tables
        ):
            raise ValueError("tables must be a list of lists")
        ids = [x for t in self.tables for x in t]
        if any(type(x) is not int for x in ids) or len(set(ids)) != len(ids):
            raise ValueError("tables must contain unique integer occurrence IDs")

    @classmethod
    def from_dict(cls, data):
        if type(data) is not dict or set(data) != {"tables", "batch_size", "drop_last"}:
            raise ValueError("case requires exactly tables, batch_size, drop_last")
        return cls(**data)

    def batches(self):
        # Independent oracle: no adapter or tested iterator is consulted.
        rows = [x for table in self.tables for x in table]
        if self.drop_last:
            rows = rows[: len(rows) // self.batch_size * self.batch_size]
        return [
            rows[i : i + self.batch_size] for i in range(0, len(rows), self.batch_size)
        ]

    def as_dict(self):
        return {
            "tables": [t[:] for t in self.tables],
            "batch_size": self.batch_size,
            "drop_last": self.drop_last,
        }
