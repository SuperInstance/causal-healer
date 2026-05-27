"""Chain health scoring for causal chain integrity."""

from __future__ import annotations

from dataclasses import dataclass, field

from .diagnosis import CausalNode, DiagnosisEngine, NodeStatus
from .validator import ChainValidator


@dataclass
class HealthScore:
    """Overall health score for a causal chain."""

    score: float  # 0.0 – 1.0
    total_nodes: int
    healthy_nodes: int
    degraded_nodes: int
    failed_nodes: int
    issues: int
    grade: str  # A / B / C / D / F

    @property
    def is_healthy(self) -> bool:
        return self.score >= 0.8

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "grade": self.grade,
            "total_nodes": self.total_nodes,
            "healthy_nodes": self.healthy_nodes,
            "degraded_nodes": self.degraded_nodes,
            "failed_nodes": self.failed_nodes,
            "issues": self.issues,
        }


def _grade(score: float) -> str:
    if score >= 0.9:
        return "A"
    if score >= 0.8:
        return "B"
    if score >= 0.6:
        return "C"
    if score >= 0.4:
        return "D"
    return "F"


class ChainHealth:
    """Scores the integrity of a causal chain.

    Combines node status ratios and validation issues into a single
    health metric.
    """

    def __init__(self, engine: DiagnosisEngine) -> None:
        self._engine = engine
        self._validator = ChainValidator(engine)

    def score(self) -> HealthScore:
        """Compute the current health score."""
        nodes = list(self._engine.nodes.values())
        total = len(nodes)
        if total == 0:
            return HealthScore(
                score=1.0, total_nodes=0, healthy_nodes=0,
                degraded_nodes=0, failed_nodes=0, issues=0, grade="A",
            )

        healthy = sum(1 for n in nodes if n.status == NodeStatus.HEALTHY)
        degraded = sum(1 for n in nodes if n.status == NodeStatus.DEGRADED)
        failed = sum(1 for n in nodes if n.status == NodeStatus.FAILED)

        # Weighted score: healthy=1.0, degraded=0.5, failed=0.0
        raw = (healthy * 1.0 + degraded * 0.5) / total

        # Penalize for validation issues
        validation = self._validator.validate()
        error_count = len(validation.errors)
        warning_count = len(validation.warnings)

        penalty = error_count * 0.05 + warning_count * 0.02
        final = max(0.0, min(1.0, raw - penalty))

        return HealthScore(
            score=round(final, 3),
            total_nodes=total,
            healthy_nodes=healthy,
            degraded_nodes=degraded,
            failed_nodes=failed,
            issues=error_count + warning_count,
            grade=_grade(final),
        )
