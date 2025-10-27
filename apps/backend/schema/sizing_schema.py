from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class Var(BaseModel):
    name: str
    value: Optional[float] = None
    unit: Optional[str] = None
    ref: Optional[str] = None

class Equation(BaseModel):
    id: str
    equation_latex: str
    variables: List[Var]
    result: Dict[str, Any]
    rationale: Optional[str] = None

class Binding(BaseModel):
    target_ref: str
    param: str
    value: Dict[str, Any]

class SizingModel(BaseModel):
    design_id: str
    equations: List[Equation]
    bindings: List[Binding]
    graph_patch: Optional[Dict[str, Any]] = None
