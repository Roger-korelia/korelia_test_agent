from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class Pin(BaseModel):
    name: str
    pin_id: str

class Param(BaseModel):
    name: str
    value: float | int | str
    unit: Optional[str] = None

class Component(BaseModel):
    ref: str
    class_: Optional[str] = None
    part_ref: Optional[str] = None
    pins: List[Pin]
    params: List[Param] = []
    class Config:
        fields = {"class_": "class"}

class Net(BaseModel):
    id: str
    type: Optional[str] = None

class Connection(BaseModel):
    pin: str
    net: str

class NetlistModel(BaseModel):
    design_id: str
    title: str
    components: List[Component]
    nets: List[Net]
    connections: List[Connection]
    graph_patch: Optional[Dict[str, Any]] = None
