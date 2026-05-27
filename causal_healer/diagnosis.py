"""Diagnosis engine for detecting broken and inconsistent causal chains."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time


class NodeStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass
class CausalNode:
    """A single node in a causal chain."""

    id: str
    status: NodeStatus = NodeStatus.HEALTHY
    dependencies: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CausalNode):
            return NotImplemented
        return self.id == other.id


@dataclass
class DiagnosisResult:
    """Result of diagnosing a causal chain."""

    root_cause: Optional[CausalNode]
    broken_chain: list[CausalNode]
    confidence: float
    issues: list[str]
    timestamp: float = field(default_factory=time.time)


class DiagnosisEngine:
    """Engine for detecting broken and inconsistent causal chains.

    Traverses causal graphs to identify root causes of failures and
    inconsistencies in agent reasoning chains.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, CausalNode] = {}

    def add_node(self, node: CausalNode) -> None:
        """Register a causal node."""
        self._nodes[node.id] = node

    def add_nodes(self, nodes: list[CausalNode]) -> None:
        """Register multiple causal nodes."""
        for n in nodes:
            self.add_node(n)

    def get_node(self, node_id: str) -> Optional[CausalNode]:
        """Look up a node by id."""
        return self._nodes.get(node_id)

    @property
    def nodes(self) -> dict[str, CausalNode]:
        return dict(self._nodes)

    def diagnose(self, start_id: str) -> DiagnosisResult:
        """Diagnose causal chain starting from *start_id*.

        Traverses dependencies to find the root cause of failure or degradation.
        Returns a :class:`DiagnosisResult` with the identified root cause,
        the full broken chain, confidence score, and detected issues.
        """
        issues: list[str] = []
        visited: set[str] = set()
        chain: list[CausalNode] = []

        root = self._trace_root(start_id, visited, chain, issues)

        confidence = self._compute_confidence(chain, root)

        return DiagnosisResult(
            root_cause=root,
            broken_chain=chain,
            confidence=confidence,
            issues=issues,
        )

    def diagnose_all(self) -> list[DiagnosisResult]:
        """Run diagnosis from every failed/degraded node."""
        results: list[DiagnosisResult] = []
        for node in self._nodes.values():
            if node.status != NodeStatus.HEALTHY:
                results.append(self.diagnose(node.id))
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _trace_root(
        self,
        current_id: str,
        visited: set[str],
        chain: list[CausalNode],
        issues: list[str],
    ) -> Optional[CausalNode]:
        if current_id in visited:
            issues.append(f"Cycle detected at node '{current_id}'")
            return None
        visited.add(current_id)

        node = self._nodes.get(current_id)
        if node is None:
            issues.append(f"Missing node '{current_id}' referenced in chain")
            return None

        chain.append(node)

        # Check for dangling dependency references
        for dep_id in node.dependencies:
            if dep_id not in self._nodes:
                issues.append(
                    f"Node '{current_id}' depends on missing node '{dep_id}'"
                )

        # Status inconsistency: healthy node depends on failed node
        if node.status == NodeStatus.HEALTHY:
            for dep_id in node.dependencies:
                dep = self._nodes.get(dep_id)
                if dep and dep.status == NodeStatus.FAILED:
                    issues.append(
                        f"Node '{current_id}' is healthy but depends on failed '{dep_id}'"
                    )

        # Recurse into failed/degraded dependencies first
        for dep_id in node.dependencies:
            dep = self._nodes.get(dep_id)
            if dep and dep.status != NodeStatus.HEALTHY:
                candidate = self._trace_root(dep_id, visited, chain, issues)
                if candidate is not None:
                    return candidate

        # If this node itself is failed with no deeper cause, it's the root
        if node.status != NodeStatus.HEALTHY:
            return node

        return None

    def _compute_confidence(
        self, chain: list[CausalNode], root: Optional[CausalNode]
    ) -> float:
        if not chain:
            return 0.0
        failed = sum(1 for n in chain if n.status != NodeStatus.HEALTHY)
        ratio = failed / len(chain)
        base = 0.4 + ratio * 0.4
        # Bonus for finding a root cause
        if root is not None:
            base = min(base + 0.15, 0.98)
        return round(base, 3)
