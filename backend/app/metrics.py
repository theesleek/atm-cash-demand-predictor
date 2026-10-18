from __future__ import annotations

from collections import Counter
from threading import Lock


_values: Counter[str] = Counter()
_lock = Lock()


def increment_metric(name: str, amount: int = 1) -> None:
    with _lock:
        _values[name] += amount


def snapshot_metrics() -> dict[str, int]:
    with _lock:
        return dict(_values)
