"""Healer with repair strategies for causal chains."""

from __future__ import annotations

from dataclasses import dataclass, field
from .types import RepairStrategy
from typing import Optional
import copy
import time

from .diagnosis import CausalNode, DiagnosisResult, DiagnosisEngine, NodeStatus
from .repair import RepairLog, RepairEntry


from .types import RepairStrategy


@dataclass
class HealResult:
    """Result of a healing operation."""

    success: bool
    strategy: RepairStrategy
    target_id: str
    message: str
    repaired_nodes: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


class Healer:
    """Applies repair strategies to fix broken causal chains.

    Supports three strategies:

    - **patch**: Correct node statuses without changing graph structure.
    - **restructure**: Rewire dependencies to bypass broken nodes.
    - **prune**: Remove failed leaf nodes entirely.
    """

    def __init__(self, engine: DiagnosisEngine) -> None:
        self._engine = engine
        self.log = RepairLog()

    def heal(
        self,
        diagnosis: DiagnosisResult,
        strategy: RepairStrategy = RepairStrategy.PATCH,
    ) -> HealResult:
        """Attempt to heal based on diagnosis using *strategy*."""
        if strategy == RepairStrategy.PATCH:
            return self._patch(diagnosis)
        elif strategy == RepairStrategy.RESTRUCTURE:
            return self._restructure(diagnosis)
        elif strategy == RepairStrategy.PRUNE:
            return self._prune(diagnosis)
        raise ValueError(f"Unknown strategy: {strategy}")

    def heal_auto(self, diagnosis: DiagnosisResult) -> HealResult:
        """Automatically pick the best strategy for the diagnosis."""
        root = diagnosis.root_cause
        if root is None:
            return HealResult(
                success=False,
                strategy=RepairStrategy.PATCH,
                target_id="",
                message="No root cause identified; nothing to heal",
            )

        # If root cause has no dependencies and is a leaf, prune it
        deps_with_issues = [
            d for d in root.dependencies
            if self._engine.get_node(d) is not None
            and self._engine.get_node(d).status != NodeStatus.HEALTHY  # type: ignore[union-attr]
        ]
        if not root.dependencies and not deps_with_issues:
            return self._prune(diagnosis)

        # If chain has structural issues, restructure
        if any("Cycle" in i or "missing" in i.lower() for i in diagnosis.issues):
            return self._restructure(diagnosis)

        return self._patch(diagnosis)

    # ------------------------------------------------------------------
    # Strategy implementations
    # ------------------------------------------------------------------

    def _patch(self, diagnosis: DiagnosisResult) -> HealResult:
        """Patch: fix inconsistent statuses by propagating root cause state."""
        patched: list[str] = []
        root = diagnosis.root_cause

        if root is None:
            return HealResult(
                success=False,
                strategy=RepairStrategy.PATCH,
                target_id="",
                message="No root cause to patch",
            )

        # Mark nodes that depend on failed root as degraded
        for node_id, node in self._engine.nodes.items():
            if root.id in node.dependencies and node.status == NodeStatus.HEALTHY:
                node.status = NodeStatus.DEGRADED
                patched.append(node.id)

        # Mark root as healthy (simulating a fix)
        root.status = NodeStatus.HEALTHY
        patched.append(root.id)

        entry = RepairEntry(
            strategy=RepairStrategy.PATCH,
            target_id=root.id,
            details=f"Patched {len(patched)} nodes",
            success=True,
        )
        self.log.append(entry)

        return HealResult(
            success=True,
            strategy=RepairStrategy.PATCH,
            target_id=root.id,
            message=f"Patched {len(patched)} nodes back to consistent state",
            repaired_nodes=patched,
        )

    def _restructure(self, diagnosis: DiagnosisResult) -> HealResult:
        """Restructure: bypass broken nodes by rewiring dependencies."""
        root = diagnosis.root_cause
        if root is None:
            return HealResult(
                success=False,
                strategy=RepairStrategy.RESTRUCTURE,
                target_id="",
                message="No root cause to restructure around",
            )

        rewired: list[str] = []

        # For every node that depends on root, point to root's dependencies instead
        root_deps = list(root.dependencies)
        for node_id, node in self._engine.nodes.items():
            if root.id in node.dependencies:
                node.dependencies = [
                    d for d in node.dependencies if d != root.id
                ] + [d for d in root_deps if d not in node.dependencies]
                rewired.append(node.id)

        entry = RepairEntry(
            strategy=RepairStrategy.RESTRUCTURE,
            target_id=root.id,
            details=f"Rewired {len(rewired)} nodes to bypass",
            success=True,
        )
        self.log.append(entry)

        return HealResult(
            success=True,
            strategy=RepairStrategy.RESTRUCTURE,
            target_id=root.id,
            message=f"Rewired {len(rewired)} nodes to bypass '{root.id}'",
            repaired_nodes=rewired,
        )

    def _prune(self, diagnosis: DiagnosisResult) -> HealResult:
        """Prune: remove failed leaf nodes from the chain."""
        pruned: list[str] = []
        nodes = self._engine.nodes

        for node_id, node in list(nodes.items()):
            # Prune leaf nodes (nothing depends on them) that are failed
            is_depended_on = any(
                node_id in other.dependencies
                for other in nodes.values()
                if other.id != node_id
            )
            if not is_depended_on and node.status == NodeStatus.FAILED:
                pruned.append(node_id)

        # Remove references to pruned nodes
        for node in nodes.values():
            node.dependencies = [
                d for d in node.dependencies if d not in pruned
            ]

        entry = RepairEntry(
            strategy=RepairStrategy.PRUNE,
            target_id=",".join(pruned) if pruned else "none",
            details=f"Pruned {len(pruned)} failed leaf nodes",
            success=True,
        )
        self.log.append(entry)

        return HealResult(
            success=True,
            strategy=RepairStrategy.PRUNE,
            target_id=",".join(pruned),
            message=f"Pruned {len(pruned)} failed leaf nodes",
            repaired_nodes=pruned,
        )
