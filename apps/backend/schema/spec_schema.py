from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class Tol(BaseModel):
    type: str = "±"
    value: float
    unit: Optional[str] = None

class Quantity(BaseModel):
    value: float | int
    unit: Optional[str] = None
    tol: Optional[Tol] = None

class Metric(BaseModel):
    id: str
    name: str
    target: Optional[Quantity] = None
    priority: str = "should"
    acceptance: Optional[str] = None

class Environment(BaseModel):
    ambient: Optional[Quantity] = None
    cooling: Optional[str] = None
    mains: Optional[Dict[str, Any]] = None

class Constraint(BaseModel):
    id: str
    name: str
    min: Optional[Quantity] = None
    max: Optional[Quantity] = None

class Standard(BaseModel):
    id: str
    name: str

class SpecModel(BaseModel):
    design_id: str
    metrics: List[Metric]
    environment: Optional[Environment] = None
    constraints: List[Constraint] = Field(default_factory=list)
    standards: List[Standard] = Field(default_factory=list)
    graph_patch: Optional[Dict[str, Any]] = None
