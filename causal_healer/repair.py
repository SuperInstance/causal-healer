"""Repair log for tracking all fixes applied."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import time
from typing import Optional

from .types import RepairStrategy


@dataclass
class RepairEntry:
    """A single repair action log entry."""

    strategy: RepairStrategy
    target_id: str
    details: str
    success: bool
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy.value,
            "target_id": self.target_id,
            "details": self.details,
            "success": self.success,
            "timestamp": self.timestamp,
        }


class RepairLog:
    """Append-only log of all repair actions.

    Provides querying by strategy, target, and time range.
    """

    def __init__(self) -> None:
        self._entries: list[RepairEntry] = []

    def append(self, entry: RepairEntry) -> None:
        self._entries.append(entry)

    @property
    def entries(self) -> list[RepairEntry]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self):
        return iter(self._entries)

    def by_strategy(self, strategy: RepairStrategy) -> list[RepairEntry]:
        return [e for e in self._entries if e.strategy == strategy]

    def by_target(self, target_id: str) -> list[RepairEntry]:
        return [e for e in self._entries if e.target_id == target_id]

    def since(self, timestamp: float) -> list[RepairEntry]:
        return [e for e in self._entries if e.timestamp >= timestamp]

    def latest(self, n: int = 10) -> list[RepairEntry]:
        return self._entries[-n:]

    def clear(self) -> None:
        self._entries.clear()

    def to_json(self) -> str:
        return json.dumps([e.to_dict() for e in self._entries], indent=2)

    def summary(self) -> dict:
        if not self._entries:
            return {"total": 0, "strategies": {}, "success_rate": 0.0}
        strategies: dict[str, int] = {}
        successes = 0
        for e in self._entries:
            strategies[e.strategy.value] = strategies.get(e.strategy.value, 0) + 1
            if e.success:
                successes += 1
        return {
            "total": len(self._entries),
            "strategies": strategies,
            "success_rate": round(successes / len(self._entries), 3),
        }
