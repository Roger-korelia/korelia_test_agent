from __future__ import annotations
from typing import List, Optional, Dict, Any, Literal, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator, AliasChoices
from enum import Enum


# ---------- Enums y tipos base ----------

class NetType(str, Enum):
    AC = "AC"
    DC = "DC"
    MIXED = "MIXED"
    SIGNAL = "SIGNAL"
    POWER = "POWER"
    GROUND = "GROUND"

class PortKind(str, Enum):
    INPUT = "input"
    OUTPUT = "output"
    INOUT = "inout"
    GROUND = "ground"
    SENSE = "sense"
    AUX = "aux"

class Domain(str, Enum):
    PRIMARY = "primary"     # lado de red / primario
    SECONDARY = "secondary" # lado aislado
    CONTROL = "control"     # lógica/control
    CHASSIS = "chassis"     # tierra chasis/PE

class ComponentClass(str, Enum):
    GENERIC = "Generic"
    AC_IN = "AC_In"
    BRIDGE = "BridgeRectifier"
    INDUCTOR = "Inductor"
    CAPACITOR = "Capacitor"
    RESISTOR = "Resistor"
    DIODE = "Diode"
    DIODE_FAST = "DiodeFast"
    MOSFET = "MOSFET"
    BJT = "BJT"
    TRANSFORMER = "Transformer"
    CONTROLLER = "Controller"
    DRIVER = "Driver"
    CONNECTOR = "Connector"
    IC = "IC"
    SUBCKT = "SubcircuitRef"
    SOURCE = "Source"

ParamValue = Union[float, int, str]


# ---------- Unidades y parámetros ----------

class Quantity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: ParamValue
    unit: Optional[str] = None  # p.ej. "uF", "V", "mH", "Hz"

class Param(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    quantity: Optional[Quantity] = None
    # Permite parámetros no-escalares (tablas, curvas, etc.)
    value: Optional[ParamValue] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _exclusive_fields(self):
        # Evita conflicto si se establecen ambos
        if self.quantity is not None and self.value is not None:
            raise ValueError("Param admite 'quantity' o 'value', pero no ambos.")
        if self.quantity is None and self.value is None:
            raise ValueError("Param requiere 'quantity' o 'value'.")
        return self


# ---------- Pines, puertos, nets ----------

class Pin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    pin_id: str  # identificador estable (el que usará Connection)
    role: Optional[str] = None  # ej. D/G/S, A/K, +/-, ~
    metadata: Dict[str, Any] = Field(default_factory=dict)

class Port(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: PortKind
    domain: Optional[Domain] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class Net(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    type: Optional[NetType] = None
    domain: Optional[Domain] = None
    is_reference_ground: bool = False  # marca GND de referencia del dominio
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ---------- Componentes, instancias y subcircuitos ----------

class Component(BaseModel):
    """Instancia de componente físico/lógico. NO contiene conexiones. Las conexiones van en NetlistModel.connections."""
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    ref: str
    class_: Optional[ComponentClass] = Field(
        default=None,
        alias="class",
        validation_alias=AliasChoices("class", "Class", "class_"),
        description="Clase del componente. Valores permitidos: Generic|AC_In|BridgeRectifier|Inductor|Capacitor|Resistor|Diode|DiodeFast|MOSFET|BJT|Transformer|Controller|Driver|Connector|IC|SubcircuitRef|Source."
    )
    part_ref: Optional[str] = None
    pins: List[Pin] = Field(
        description="Lista de pines del componente. Cada pin requiere 'name' y 'pin_id'. Los 'pin_id' deben ser únicos dentro del mismo componente."
    )
    params: List[Param] = Field(default_factory=list)
    domain: Optional[Domain] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("pins")
    @classmethod
    def _unique_pin_ids(cls, v: List[Pin]):
        seen = set()
        for p in v:
            if p.pin_id in seen:
                raise ValueError(f"Pin duplicado en componente: pin_id='{p.pin_id}'")
            seen.add(p.pin_id)
        return v

class Subcircuit(BaseModel):
    """Definición jerárquica reusable (plantilla)."""
    model_config = ConfigDict(extra="forbid")
    name: str
    ports: List[Pin]                         # interfaz del subcircuito
    components: List[Component] = Field(default_factory=list)
    nets: List[Net] = Field(default_factory=list)
    connections: List["Connection"] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class Instance(BaseModel):
    """Instancia de un Subcircuit en el netlist superior."""
    model_config = ConfigDict(extra="forbid")
    ref: str
    of: str                  # nombre del Subcircuit al que referencia
    # Mapeo pin-subckt -> net superior
    port_map: Dict[str, str] = Field(default_factory=dict)
    params: List[Param] = Field(default_factory=list)
    domain: Optional[Domain] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ---------- Conexiones ----------

class Connection(BaseModel):
    """Conexión eléctrica entre un pin de componente/instancia y una Net."""
    model_config = ConfigDict(extra="forbid")
    component_ref: str = Field(description="Referencia del componente o instancia (coincide con Component.ref o Instance.ref).")
    pin_id: str = Field(description="Identificador de pin (coincide con Component.pins[*].pin_id o el puerto de una instancia).")
    net: str = Field(description="ID de Net existente en 'nets'.")
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ---------- Modelos de Topología y Netlist ----------

class TopologyBlock(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    id: str
    class_: ComponentClass = Field(
        alias="class",
        default=ComponentClass.GENERIC,
        validation_alias=AliasChoices("class", "Class", "class_")
    )
    domain: Optional[Domain] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class TopologyEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_: str = Field(alias="from")
    to: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class TopologyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    design_id: str
    blocks: List[TopologyBlock]
    ports: List[Port] = Field(default_factory=list)
    connections: List[TopologyEdge] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("blocks")
    @classmethod
    def _unique_block_ids(cls, v: List[TopologyBlock]):
        ids = [b.id for b in v]
        if len(ids) != len(set(ids)):
            raise ValueError("IDs de bloques duplicados en TopologyModel.")
        return v


class NetlistModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = "1.0.0"
    design_id: str
    title: str
    components: List[Component] = Field(default_factory=list, description="Instancias de componentes con sus pines. NO incluir conexiones aquí.")
    instances: List[Instance] = Field(default_factory=list)
    subcircuits: List[Subcircuit] = Field(default_factory=list)
    nets: List[Net] = Field(description="Todas las Nets utilizadas en 'connections'. Debe incluir 'ground' si se referencia tierra.")
    connections: List[Connection] = Field(description="Conexiones {component_ref, pin_id, net}. No colocar dentro de 'components'.")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_integrity(self):
        # --- unicidad de nets ---
        net_ids = [n.id for n in self.nets]
        if len(net_ids) != len(set(net_ids)):
            raise ValueError("IDs de nets duplicados.")
        nets_set = set(net_ids)

        # --- unicidad de componentes e instancias ---
        comp_refs = [c.ref for c in self.components]
        inst_refs = [i.ref for i in self.instances]
        all_refs = comp_refs + inst_refs
        if len(all_refs) != len(set(all_refs)):
            raise ValueError("Refs duplicadas entre componentes/instancias.")

        comp_dict = {c.ref: c for c in self.components}
        subckt_names = {s.name for s in self.subcircuits}

        # --- instancias: subcircuito existente y nets válidos ---
        for inst in self.instances:
            if inst.of not in subckt_names:
                raise ValueError(f"Instance '{inst.ref}' referencia subcircuito inexistente '{inst.of}'.")
            # port_map -> nets válidos
            for port_pin, net in inst.port_map.items():
                if net not in nets_set:
                    raise ValueError(f"Instance '{inst.ref}' port_map usa net inexistente '{net}'.")

        # --- conexiones: componente o instancia existe, pin existe, net existe ---
        for con in self.connections:
            if con.net not in nets_set:
                raise ValueError(f"Connection usa net inexistente '{con.net}'.")
            # ¿ref es componente o instancia?
            if con.component_ref in comp_dict:
                comp = comp_dict[con.component_ref]
                pin_ids = {p.pin_id for p in comp.pins}
                if con.pin_id not in pin_ids:
                    raise ValueError(
                        f"Pin '{con.pin_id}' no existe en componente '{con.component_ref}'."
                    )
            elif con.component_ref in inst_refs:
                # Si es una instancia, el pin debe mapearse vía port_map al net superior (opcional reforzar aquí)
                pass
            else:
                raise ValueError(
                    f"Connection referencia '{con.component_ref}' inexistente (ni componente ni instancia)."
                )
        return self
