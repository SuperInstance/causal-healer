"""Validator for checking causal chain consistency."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .diagnosis import CausalNode, DiagnosisEngine, NodeStatus


@dataclass
class ValidationIssue:
    """A single validation problem."""

    severity: str  # "error" | "warning"
    node_id: str
    message: str


@dataclass
class ValidationResult:
    """Result of validating a causal chain."""

    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]


class ChainValidator:
    """Validates causal chain consistency.

    Checks for:
    - Cycles in the dependency graph
    - Dangling references to missing nodes
    - Status inconsistencies (healthy depends on failed)
    - Orphan nodes (unreachable from any entry point)
    """

    def __init__(self, engine: DiagnosisEngine) -> None:
        self._engine = engine

    def validate(self) -> ValidationResult:
        """Run all validation checks and return a result."""
        issues = self._check_dangling_refs()
        issues += self._check_cycles()
        issues += self._check_status_consistency()
        issues += self._check_orphans()

        return ValidationResult(
            valid=len([i for i in issues if i.severity == "error"]) == 0,
            issues=issues,
        )

    def validate_node(self, node_id: str) -> ValidationResult:
        """Validate a single node and its immediate dependencies."""
        node = self._engine.get_node(node_id)
        if node is None:
            return ValidationResult(
                valid=False,
                issues=[ValidationIssue("error", node_id, f"Node '{node_id}' not found")],
            )

        issues: list[ValidationIssue] = []

        for dep_id in node.dependencies:
            dep = self._engine.get_node(dep_id)
            if dep is None:
                issues.append(
                    ValidationIssue("error", node_id, f"Dangling dependency '{dep_id}'")
                )
            elif dep.status == NodeStatus.FAILED and node.status == NodeStatus.HEALTHY:
                issues.append(
                    ValidationIssue(
                        "warning",
                        node_id,
                        f"Healthy node depends on failed '{dep_id}'",
                    )
                )

        return ValidationResult(
            valid=len([i for i in issues if i.severity == "error"]) == 0,
            issues=issues,
        )

    # ------------------------------------------------------------------

    def _check_dangling_refs(self) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for node in self._engine.nodes.values():
            for dep_id in node.dependencies:
                if dep_id not in self._engine.nodes:
                    issues.append(
                        ValidationIssue(
                            "error",
                            node.id,
                            f"Dangling dependency '{dep_id}'",
                        )
                    )
        return issues

    def _check_cycles(self) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        visited: set[str] = set()

        def _dfs(node_id: str, path: set[str]) -> None:
            if node_id in path:
                issues.append(
                    ValidationIssue("error", node_id, f"Cycle detected involving '{node_id}'")
                )
                return
            if node_id in visited:
                return
            visited.add(node_id)
            path.add(node_id)
            node = self._engine.get_node(node_id)
            if node:
                for dep_id in node.dependencies:
                    _dfs(dep_id, path)
            path.discard(node_id)

        for nid in self._engine.nodes:
            _dfs(nid, set())

        return issues

    def _check_status_consistency(self) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for node in self._engine.nodes.values():
            if node.status == NodeStatus.HEALTHY:
                for dep_id in node.dependencies:
                    dep = self._engine.get_node(dep_id)
                    if dep and dep.status == NodeStatus.FAILED:
                        issues.append(
                            ValidationIssue(
                                "warning",
                                node.id,
                                f"Healthy node depends on failed '{dep_id}'",
                            )
                        )
        return issues

    def _check_orphans(self) -> list[ValidationIssue]:
        """Find nodes that no other node depends on and have no dependencies."""
        all_deps: set[str] = set()
        for node in self._engine.nodes.values():
            all_deps.update(node.dependencies)

        issues: list[ValidationIssue] = []
        for node in self._engine.nodes.values():
            if node.id not in all_deps and not node.dependencies:
                issues.append(
                    ValidationIssue(
                        "warning",
                        node.id,
                        "Orphan node: not reachable and has no dependencies",
                    )
                )
        return issues
