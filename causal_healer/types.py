"""Shared enums and types."""

from enum import Enum


class RepairStrategy(str, Enum):
    """Available repair strategies."""

    PATCH = "patch"
    RESTRUCTURE = "restructure"
    PRUNE = "prune"
