from typing import Dict, Any, List, Callable
from .store import GraphStore
from .rulesets import RULESET_POWER_BASE

def run_rulesets(store: GraphStore, design_id: str) -> Dict[str, Any]:
    """Run all registered rulesets and return violations."""
    checks: List[str] = []
    violations: List[Dict[str, Any]] = []
    for name, fn in RULESET_POWER_BASE.items():
        checks.append(name)
        violations.extend(fn(store))
    return {"design_id": design_id, "checks_run": checks, "violations": violations}