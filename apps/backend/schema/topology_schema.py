from __future__ import annotations
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from enum import Enum
import re


# ---------- Enums útiles ----------

class PortKind(str, Enum):
    INPUT = "input"
    OUTPUT = "output"
    INOUT = "inout"
    GROUND = "ground"
    SENSE = "sense"
    AUX = "aux"

class Domain(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    CONTROL = "control"
    CHASSIS = "chassis"
    UNKNOWN = "unknown"


# ---------- Modelos ----------

ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_\-:.]*$")  # URN-friendly

class Block(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    id: str
    class_: Optional[str] = Field(default=None, alias="class")   # alias para JSON
    role: Optional[str] = None
    domain: Optional[Domain] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, v: str) -> str:
        if not ID_RE.match(v):
            raise ValueError(f"Block.id inválido: '{v}'")
        return v

class Port(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: PortKind
    domain: Optional[Domain] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, v: str) -> str:
        if not ID_RE.match(v):
            raise ValueError(f"Port.id inválido: '{v}'")
        return v

class Connection(BaseModel):
    """Conexión funcional entre dos endpoints (blocks o ports). Los IDs deben existir directamente en 'blocks' o 'ports', sin notación jerárquica."""
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    from_: str = Field(alias="from", description="ID de Block o Port existente en 'blocks' o 'ports'. NO usar notación jerárquica como 'BlockID.PortID'.")
    to: str = Field(description="ID de Block o Port existente en 'blocks' o 'ports'. NO usar notación jerárquica como 'BlockID.PortID'.")
    metadata: Dict[str, Any] = Field(default_factory=dict)  # etiquetas/dirección/etc.

    @field_validator("from_", "to")
    @classmethod
    def _valid_endpoint(cls, v: str) -> str:
        if not ID_RE.match(v):
            raise ValueError(f"Connection endpoint inválido: '{v}'")
        return v

class Assumption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    source: Optional[str] = None     # “user”, “agent”, “datasheet:XYZ”
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class TopologyModel(BaseModel):
    """
    v2: formato plano recomendado.
    Si aún recibes el objeto anidado { topology: { ... } }, puedes aceptarlo
    con un paso previo de normalización (ver nota abajo).
    """
    model_config = ConfigDict(extra="forbid")
    design_id: str
    blocks: List[Block] = Field(default_factory=list)
    ports: List[Port] = Field(default_factory=list)
    connections: List[Connection] = Field(default_factory=list)
    assumptions: List[Assumption] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    graph_patch: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _uniqueness_checks(self):
        bid = [b.id for b in self.blocks]
        pid = [p.id for p in self.ports]

        if len(bid) != len(set(bid)):
            raise ValueError("Block IDs duplicados.")
        if len(pid) != len(set(pid)):
            raise ValueError("Port IDs duplicados.")

        # Los endpoints de conexiones deben existir como Block o Port ID
        known = set(bid) | set(pid)
        for c in self.connections:
            if c.from_ not in known:
                raise ValueError(f"Connection.from '{c.from_}' no existe (block/port).")
            if c.to not in known:
                raise ValueError(f"Connection.to '{c.to}' no existe (block/port).")

        return self
