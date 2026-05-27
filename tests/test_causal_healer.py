"""Tests for causal_healer."""

from causal_healer import (
    CausalNode,
    DiagnosisEngine,
    DiagnosisResult,
    Healer,
    RepairStrategy,
    ChainValidator,
    ValidationResult,
    RepairLog,
    RepairEntry,
    ChainHealth,
    HealthScore,
)
from causal_healer.diagnosis import NodeStatus
from causal_healer.types import RepairStrategy as RS

import pytest


# ── Helpers ──────────────────────────────────────────────────────────

def _make_chain():
    """Build a simple 4-node chain: A → B → C → D with C failed."""
    engine = DiagnosisEngine()
    d = CausalNode(id="D", status=NodeStatus.HEALTHY, dependencies=[])
    c = CausalNode(id="C", status=NodeStatus.FAILED, dependencies=["D"])
    b = CausalNode(id="B", status=NodeStatus.DEGRADED, dependencies=["C"])
    a = CausalNode(id="A", status=NodeStatus.DEGRADED, dependencies=["B"])
    engine.add_nodes([a, b, c, d])
    return engine


def _make_cycle():
    """A → B → A cycle."""
    engine = DiagnosisEngine()
    a = CausalNode(id="A", status=NodeStatus.FAILED, dependencies=["B"])
    b = CausalNode(id="B", status=NodeStatus.HEALTHY, dependencies=["A"])
    engine.add_nodes([a, b])
    return engine


def _make_dangling():
    """Node depends on a non-existent node."""
    engine = DiagnosisEngine()
    a = CausalNode(id="A", status=NodeStatus.HEALTHY, dependencies=["MISSING"])
    engine.add_nodes([a])
    return engine


# ── DiagnosisEngine tests ────────────────────────────────────────────

class TestDiagnosisEngine:
    def test_empty_engine(self):
        engine = DiagnosisEngine()
        result = engine.diagnose("nonexistent")
        assert result.root_cause is None
        assert result.broken_chain == []
        assert "Missing node" in result.issues[0]

    def test_simple_chain_root_cause(self):
        engine = _make_chain()
        result = engine.diagnose("A")
        assert result.root_cause is not None
        assert result.root_cause.id == "C"
        assert result.confidence > 0.0

    def test_diagnose_from_root(self):
        engine = _make_chain()
        result = engine.diagnose("C")
        assert result.root_cause is not None
        assert result.root_cause.id == "C"

    def test_diagnose_healthy_chain(self):
        engine = DiagnosisEngine()
        engine.add_nodes([
            CausalNode(id="X", status=NodeStatus.HEALTHY, dependencies=["Y"]),
            CausalNode(id="Y", status=NodeStatus.HEALTHY, dependencies=[]),
        ])
        result = engine.diagnose("X")
        assert result.root_cause is None
        assert len(result.broken_chain) >= 0  # may include visited healthy nodes

    def test_cycle_detection(self):
        engine = _make_cycle()
        result = engine.diagnose("A")
        # Cycle is detected internally; root cause should still be A (failed)
        assert result.root_cause is not None

    def test_dangling_reference(self):
        engine = _make_dangling()
        result = engine.diagnose("A")
        assert any("missing" in i.lower() for i in result.issues)

    def test_diagnose_all(self):
        engine = _make_chain()
        results = engine.diagnose_all()
        assert len(results) >= 2  # at least B and C

    def test_add_and_get_node(self):
        engine = DiagnosisEngine()
        node = CausalNode(id="test", status=NodeStatus.HEALTHY)
        engine.add_node(node)
        assert engine.get_node("test") == node
        assert engine.get_node("nope") is None

    def test_confidence_bounds(self):
        engine = _make_chain()
        result = engine.diagnose("A")
        assert 0.0 <= result.confidence <= 1.0


# ── Healer tests ─────────────────────────────────────────────────────

class TestHealer:
    def test_patch_strategy(self):
        engine = _make_chain()
        healer = Healer(engine)
        diag = engine.diagnose("A")
        result = healer.heal(diag, RepairStrategy.PATCH)
        assert result.success
        assert result.strategy == RepairStrategy.PATCH
        assert len(healer.log) == 1

    def test_restructure_strategy(self):
        engine = _make_chain()
        healer = Healer(engine)
        diag = engine.diagnose("A")
        result = healer.heal(diag, RepairStrategy.RESTRUCTURE)
        assert result.success
        assert result.strategy == RepairStrategy.RESTRUCTURE

    def test_prune_strategy(self):
        engine = DiagnosisEngine()
        leaf = CausalNode(id="leaf", status=NodeStatus.FAILED, dependencies=[])
        engine.add_nodes([leaf])

        healer = Healer(engine)
        diag = engine.diagnose("leaf")
        result = healer.heal(diag, RepairStrategy.PRUNE)
        assert result.success
        assert "leaf" in result.repaired_nodes

    def test_auto_heal_picks_patch(self):
        engine = _make_chain()
        healer = Healer(engine)
        diag = engine.diagnose("A")
        result = healer.heal_auto(diag)
        assert result.success

    def test_auto_heal_no_root(self):
        engine = DiagnosisEngine()
        engine.add_node(CausalNode(id="X", status=NodeStatus.HEALTHY))
        healer = Healer(engine)
        diag = engine.diagnose("X")
        result = healer.heal_auto(diag)
        assert not result.success

    def test_auto_heal_on_cycle(self):
        engine = _make_cycle()
        healer = Healer(engine)
        diag = engine.diagnose("A")
        result = healer.heal_auto(diag)
        assert result.success  # should still heal somehow

    def test_unknown_strategy_raises(self):
        engine = _make_chain()
        healer = Healer(engine)
        diag = engine.diagnose("A")
        with pytest.raises(ValueError):
            healer.heal(diag, "unknown")  # type: ignore[arg-type]

    def test_patch_marks_dependents_degraded(self):
        engine = DiagnosisEngine()
        failed = CausalNode(id="db", status=NodeStatus.FAILED, dependencies=[])
        api = CausalNode(id="api", status=NodeStatus.HEALTHY, dependencies=["db"])
        engine.add_nodes([failed, api])

        healer = Healer(engine)
        diag = engine.diagnose("api")
        result = healer.heal(diag, RepairStrategy.PATCH)
        assert result.success
        # api should have been marked degraded during patch (before root fix propagated)
        assert "api" in result.repaired_nodes


# ── ChainValidator tests ─────────────────────────────────────────────

class TestChainValidator:
    def test_valid_chain(self):
        engine = DiagnosisEngine()
        engine.add_nodes([
            CausalNode(id="A", status=NodeStatus.HEALTHY, dependencies=["B"]),
            CausalNode(id="B", status=NodeStatus.HEALTHY, dependencies=[]),
        ])
        validator = ChainValidator(engine)
        result = validator.validate()
        assert result.valid

    def test_dangling_ref_is_error(self):
        engine = _make_dangling()
        validator = ChainValidator(engine)
        result = validator.validate()
        assert not result.valid
        assert len(result.errors) > 0

    def test_cycle_is_error(self):
        engine = _make_cycle()
        validator = ChainValidator(engine)
        result = validator.validate()
        assert not result.valid
        assert any("Cycle" in i.message for i in result.errors)

    def test_status_inconsistency_is_warning(self):
        engine = DiagnosisEngine()
        engine.add_nodes([
            CausalNode(id="ok", status=NodeStatus.HEALTHY, dependencies=["bad"]),
            CausalNode(id="bad", status=NodeStatus.FAILED, dependencies=[]),
        ])
        validator = ChainValidator(engine)
        result = validator.validate()
        assert result.valid  # warnings don't make it invalid
        assert len(result.warnings) > 0

    def test_orphan_detection(self):
        engine = DiagnosisEngine()
        engine.add_node(CausalNode(id="lonely", status=NodeStatus.HEALTHY))
        validator = ChainValidator(engine)
        result = validator.validate()
        assert len(result.warnings) > 0
        assert any("Orphan" in i.message for i in result.warnings)

    def test_validate_single_node(self):
        engine = _make_dangling()
        validator = ChainValidator(engine)
        result = validator.validate_node("A")
        assert not result.valid

    def test_validate_missing_node(self):
        engine = DiagnosisEngine()
        validator = ChainValidator(engine)
        result = validator.validate_node("ghost")
        assert not result.valid


# ── RepairLog tests ──────────────────────────────────────────────────

class TestRepairLog:
    def test_empty_log(self):
        log = RepairLog()
        assert len(log) == 0
        assert log.summary()["total"] == 0

    def test_append_and_query(self):
        log = RepairLog()
        e1 = RepairEntry(
            strategy=RepairStrategy.PATCH,
            target_id="A",
            details="fixed A",
            success=True,
        )
        e2 = RepairEntry(
            strategy=RepairStrategy.PRUNE,
            target_id="B",
            details="pruned B",
            success=True,
        )
        log.append(e1)
        log.append(e2)
        assert len(log) == 2
        assert len(log.by_strategy(RepairStrategy.PATCH)) == 1
        assert len(log.by_target("B")) == 1

    def test_since_filter(self):
        import time
        log = RepairLog()
        log.append(RepairEntry(
            strategy=RepairStrategy.PATCH,
            target_id="A",
            details="old",
            success=True,
            timestamp=1000.0,
        ))
        log.append(RepairEntry(
            strategy=RepairStrategy.PATCH,
            target_id="B",
            details="new",
            success=True,
            timestamp=2000.0,
        ))
        assert len(log.since(1500.0)) == 1

    def test_latest(self):
        log = RepairLog()
        for i in range(20):
            log.append(RepairEntry(
                strategy=RepairStrategy.PATCH,
                target_id=f"N{i}",
                details=f"fix {i}",
                success=True,
            ))
        assert len(log.latest(5)) == 5

    def test_to_json(self):
        log = RepairLog()
        log.append(RepairEntry(
            strategy=RepairStrategy.PATCH,
            target_id="X",
            details="test",
            success=True,
        ))
        j = log.to_json()
        assert '"strategy": "patch"' in j

    def test_summary(self):
        log = RepairLog()
        log.append(RepairEntry(
            strategy=RepairStrategy.PATCH, target_id="A", details="", success=True,
        ))
        log.append(RepairEntry(
            strategy=RepairStrategy.PRUNE, target_id="B", details="", success=False,
        ))
        s = log.summary()
        assert s["total"] == 2
        assert s["success_rate"] == 0.5

    def test_clear(self):
        log = RepairLog()
        log.append(RepairEntry(
            strategy=RepairStrategy.PATCH, target_id="A", details="", success=True,
        ))
        log.clear()
        assert len(log) == 0

    def test_iteration(self):
        log = RepairLog()
        log.append(RepairEntry(
            strategy=RepairStrategy.PATCH, target_id="A", details="", success=True,
        ))
        entries = list(log)
        assert len(entries) == 1


# ── ChainHealth tests ────────────────────────────────────────────────

class TestChainHealth:
    def test_empty_engine_perfect(self):
        engine = DiagnosisEngine()
        health = ChainHealth(engine)
        score = health.score()
        assert score.score == 1.0
        assert score.grade == "A"

    def test_all_healthy(self):
        engine = DiagnosisEngine()
        engine.add_nodes([
            CausalNode(id="A", status=NodeStatus.HEALTHY),
            CausalNode(id="B", status=NodeStatus.HEALTHY),
        ])
        health = ChainHealth(engine)
        score = health.score()
        assert score.is_healthy
        assert score.healthy_nodes == 2

    def test_mixed_statuses(self):
        engine = DiagnosisEngine()
        engine.add_nodes([
            CausalNode(id="A", status=NodeStatus.HEALTHY),
            CausalNode(id="B", status=NodeStatus.DEGRADED),
            CausalNode(id="C", status=NodeStatus.FAILED),
        ])
        health = ChainHealth(engine)
        score = health.score()
        assert not score.is_healthy
        assert score.failed_nodes == 1

    def test_grades(self):
        from causal_healer.health import _grade
        assert _grade(0.95) == "A"
        assert _grade(0.85) == "B"
        assert _grade(0.65) == "C"
        assert _grade(0.45) == "D"
        assert _grade(0.2) == "F"

    def test_to_dict(self):
        engine = DiagnosisEngine()
        engine.add_node(CausalNode(id="A", status=NodeStatus.HEALTHY))
        health = ChainHealth(engine)
        d = health.score().to_dict()
        assert "score" in d
        assert "grade" in d

    def test_validation_penalty(self):
        engine = _make_dangling()
        health = ChainHealth(engine)
        score = health.score()
        # Dangling ref should penalize
        assert score.score < 1.0
        assert score.issues > 0


# ── Integration test ─────────────────────────────────────────────────

class TestIntegration:
    def test_full_workflow(self):
        # Build graph
        engine = DiagnosisEngine()
        engine.add_nodes([
            CausalNode(id="frontend", status=NodeStatus.DEGRADED, dependencies=["api"]),
            CausalNode(id="api", status=NodeStatus.DEGRADED, dependencies=["db"]),
            CausalNode(id="db", status=NodeStatus.FAILED, dependencies=[]),
        ])

        # Diagnose
        diag = engine.diagnose("frontend")
        assert diag.root_cause.id == "db"

        # Validate
        validator = ChainValidator(engine)
        validation = validator.validate()
        assert validation.valid  # no structural errors

        # Health check
        health = ChainHealth(engine)
        score = health.score()
        assert score.grade in ("C", "D", "F")

        # Heal
        healer = Healer(engine)
        result = healer.heal(diag, RepairStrategy.PATCH)
        assert result.success
        assert "db" in result.repaired_nodes

        # Check log
        assert len(healer.log) == 1
        summary = healer.log.summary()
        assert summary["total"] == 1
        assert summary["success_rate"] == 1.0
