# causal-healer

Diagnose and repair broken causal chains in agent reasoning.

Part of the [Cocapn fleet](https://github.com/Lucineer/the-fleet).

---

## Install

```bash
pip install -e ".[dev]"
```

## Quick Start

```python
from causal_healer import (
    CausalNode, DiagnosisEngine, Healer, RepairStrategy,
    ChainValidator, ChainHealth, NodeStatus,
)

# 1. Build a causal graph
engine = DiagnosisEngine()
engine.add_nodes([
    CausalNode(id="frontend", status=NodeStatus.DEGRADED, dependencies=["api"]),
    CausalNode(id="api", status=NodeStatus.DEGRADED, dependencies=["db"]),
    CausalNode(id="db", status=NodeStatus.FAILED, dependencies=[]),
])

# 2. Diagnose — find the root cause
diag = engine.diagnose("frontend")
print(diag.root_cause.id)          # "db"
print(diag.confidence)             # ~0.88
print(diag.issues)                 # []

# 3. Validate structural integrity
validator = ChainValidator(engine)
result = validator.validate()
print(result.valid)                # True
print(result.warnings)             # []

# 4. Score chain health
health = ChainHealth(engine)
score = health.score()
print(score.grade)                 # "D"
print(score.is_healthy)            # False

# 5. Heal — apply a repair strategy
healer = Healer(engine)
heal_result = healer.heal(diag, RepairStrategy.PATCH)
print(heal_result.success)         # True
print(heal_result.repaired_nodes)  # ["api", "db"]

# Or let the healer pick the best strategy automatically:
auto_result = healer.heal_auto(diag)

# 6. Inspect the repair log
print(healer.log.summary())
# {"total": 1, "strategies": {"patch": 1}, "success_rate": 1.0}
```

## Architecture

| Module | Purpose |
|---|---|
| `diagnosis.py` | `DiagnosisEngine` — trace causal chains, find root causes, detect cycles & dangling refs |
| `healer.py` | `Healer` — three repair strategies: **patch**, **restructure**, **prune** |
| `validator.py` | `ChainValidator` — check cycles, dangling refs, status consistency, orphans |
| `repair.py` | `RepairLog` — append-only audit log with querying & JSON export |
| `health.py` | `ChainHealth` — A–F grading with weighted scoring & validation penalties |

## Repair Strategies

| Strategy | Description |
|---|---|
| `PATCH` | Fix inconsistent statuses, mark root cause as healthy |
| `RESTRUCTURE` | Rewire dependencies to bypass broken nodes |
| `PRUNE` | Remove failed leaf nodes from the chain |

`heal_auto()` picks the best strategy based on the diagnosis: prunes leaf failures, restructures around cycles/missing nodes, and patches everything else.

## Running Tests

```bash
python -m pytest tests/ -q
```

## License

MIT — SuperInstance & Lucineer (DiGennaro et al.)
