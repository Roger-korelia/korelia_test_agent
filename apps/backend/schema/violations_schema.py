from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class FixPatch(BaseModel):
    description: str
    graph_patch: Dict[str, Any]

class Violation(BaseModel):
    id: str
    rule: str
    severity: str
    context: Dict[str, Any]
    message: str
    suggested_fixes: List[FixPatch] = []

class ViolationsModel(BaseModel):
    design_id: str
    checks_run: List[str]
    violations: List[Violation]
