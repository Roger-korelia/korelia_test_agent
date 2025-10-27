from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field


Namespace = Literal["DIG","FTG","ESG","CIG","VRG","PDG","MBG","WMG"]

class NodeModel(BaseModel):
    id: str
    type: str
    labels: Optional[List[str]] = None
    props: Dict[str, Any] = Field(default_factory=dict)

class EdgeModel(BaseModel):
    id: str
    type: str
    from_: str = Field(..., alias="from")
    to: str
    props: Dict[str, Any] = Field(default_factory=dict)

class OpAddNode(BaseModel):
    op: Literal["add_node"]
    node: NodeModel

class OpUpdateNode(BaseModel):
    op: Literal["update_node"]
    node: NodeModel

class OpRemoveNode(BaseModel):
    op: Literal["remove_node"]
    id: str

class OpAddEdge(BaseModel):
    op: Literal["add_edge"]
    edge: EdgeModel

class OpUpdateEdge(BaseModel):
    op: Literal["update_edge"]
    edge: EdgeModel

class OpRemoveEdge(BaseModel):
    op: Literal["remove_edge"]
    id: str

PatchOp = OpAddNode | OpUpdateNode | OpRemoveNode | OpAddEdge | OpUpdateEdge | OpRemoveEdge

class GraphPatch(BaseModel):
    namespace: Namespace
    ops: List[PatchOp]
