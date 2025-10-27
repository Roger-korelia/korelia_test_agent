from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class Block(BaseModel):
    id: str
    class_: str | None = None  # alias due to reserved word
    role: Optional[str] = None

    class Config:
        fields = {"class_": "class"}

class Port(BaseModel):
    id: str
    kind: str

class Connection(BaseModel):
    from_: str
    to: str
    class Config:
        fields = {"from_": "from"}

class TopologyBody(BaseModel):
    blocks: List[Block]
    ports: List[Port]
    connections: List[Connection]
    assumptions: List[Dict[str, Any]] = []

class TopologyModel(BaseModel):
    design_id: str
    topology: TopologyBody
    graph_patch: Optional[Dict[str, Any]] = None
