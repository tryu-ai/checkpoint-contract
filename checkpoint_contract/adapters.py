"""Real optional adapters. Third-party imports happen only on session creation."""

import sys
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .cases import Case
from .core import Contract, Unsupported


def _version(name):
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _source_identity(name):
    """Identify one loaded source file, without importing or disclosing its path."""
    module = sys.modules.get(name)
    filename = vars(module).get("__file__") if module is not None else None
    digest = None
    if filename and Path(filename).suffix == ".py":
        try:
            digest = sha256(Path(filename).read_bytes()).hexdigest()
        except OSError:
            pass
    return {"module": name, "loaded": module is not None, "sha256": digest}


def _refresh_provenance(provenance):
    sources = {
        "hf-arrow": {"datasets": "datasets.iterable_dataset", "pyarrow": None},
        "torchdata": {
            "torch": None,
            "torchdata": "torchdata.stateful_dataloader.stateful_dataloader",
        },
    }
    if provenance["adapter"] not in sources:
        return
    packages = {}
    for name, source in sources[provenance["adapter"]].items():
        module = sys.modules.get(name)
        runtime_version = (
            vars(module).get("__version__") if module is not None else None
        )
        packages[name] = {
            "loaded": module is not None,
            "runtime_version": runtime_version
            if isinstance(runtime_version, str)
            else None,
            "distribution_version": _version(name),
        }
        if source:
            packages[name]["source"] = _source_identity(source)
    provenance["packages"] = packages


def adapter(name: str, case: Case, *, buffered_shuffle=False, in_order=True):
    if name not in ("hf-arrow", "torchdata"):
        raise ValueError("unknown adapter")
    if type(buffered_shuffle) is not bool or type(in_order) is not bool:
        raise ValueError("adapter mode flags must be boolean")
    contract = Contract(
        exhausted_restore="empty" if name == "hf-arrow" else "next_epoch"
    )
    packages = ("datasets", "pyarrow") if name == "hf-arrow" else ("torch", "torchdata")
    provenance = {
        "adapter": name,
        "packages": {},
        "private_api": name == "hf-arrow",
        "settings": {"buffered_shuffle": buffered_shuffle}
        if name == "hf-arrow"
        else {"num_workers": 0, "shuffle": False, "in_order": in_order},
    }

    def factory():
        if name == "hf-arrow" and buffered_shuffle:
            raise Unsupported("HF buffered shuffle is unsupported")
        if name == "torchdata" and not in_order:
            raise Unsupported("TorchData in_order=False is unsupported")
        try:
            return _HF(case) if name == "hf-arrow" else _Torch(case)
        except ModuleNotFoundError as exc:
            if exc.name and exc.name.split(".")[0] in packages:
                raise Unsupported(f"optional dependency missing: {exc.name}") from exc
            raise
        finally:
            _refresh_provenance(provenance)

    return factory, contract, provenance


class _HF:
    def __init__(self, case):
        import pyarrow as pa
        from datasets.iterable_dataset import (
            ArrowExamplesIterable,
            RebatchedArrowExamplesIterable,
        )

        # All source tables, closures and iterable state are fresh per session.
        tables = [pa.table({"id": pa.array(t, type=pa.int64())}) for t in case.tables]

        def generate_tables():
            for i, table in enumerate(tables):
                yield str(i), table

        source = ArrowExamplesIterable(generate_tables, {})
        self.stream = RebatchedArrowExamplesIterable(
            source, batch_size=case.batch_size, drop_last_batch=case.drop_last
        )
        self.stream._init_state_dict()
        self.iterator = None

    def next_batch(self):
        if self.iterator is None:
            self.iterator = iter(self.stream.iter_arrow())
        _, table = next(self.iterator)
        return table.column("id").to_pylist()

    def snapshot(self):
        from copy import deepcopy

        return deepcopy(self.stream.state_dict())

    def restore(self, state):
        if self.iterator is not None:
            raise RuntimeError("restore must precede resumed iterator creation")
        self.stream.load_state_dict(state)

    def close(self):
        if self.iterator is not None:
            self.iterator.close()
        self.iterator = None


def _identity(batch):
    return batch


class _Torch:
    def __init__(self, case):
        import torch
        from torchdata.stateful_dataloader import StatefulDataLoader

        self.loader = StatefulDataLoader(
            [x for table in case.tables for x in table],
            batch_size=case.batch_size,
            drop_last=case.drop_last,
            num_workers=0,
            shuffle=False,
            in_order=True,
            generator=torch.Generator().manual_seed(0),
            collate_fn=_identity,
        )
        self.iterator = None

    def next_batch(self):
        if self.iterator is None:
            self.iterator = iter(self.loader)
        return list(next(self.iterator))

    def snapshot(self):
        from copy import deepcopy

        return deepcopy(self.loader.state_dict())

    def restore(self, state):
        if self.iterator is not None:
            raise RuntimeError("restore must precede resumed iterator creation")
        self.loader.load_state_dict(state)

    def close(self):
        self.iterator = None
        self.loader = None
