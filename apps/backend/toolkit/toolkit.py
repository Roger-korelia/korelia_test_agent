import json
from typing import Dict, Any, List, Tuple
from pydantic import ValidationError

from apps.backend.graph.store import GraphStore
from apps.backend.graph.patcher import apply_patch
from apps.backend.graph.engine import run_rulesets
from apps.backend.schema.spec_schema import SpecModel
from apps.backend.schema.topology_schema import TopologyModel
from apps.backend.schema.netlist_schema import NetlistModel  # ← nuevo schema


# ------------------------
# Helpers de normalización
# ------------------------

def _urn_net(net_id: str) -> str:
    return f"urn:cig:net:{net_id}"

def _urn_cmp(ref: str) -> str:
    return f"urn:cig:cmp:{ref}"

def _urn_pin_of_cmp(cmp_urn: str, pin_id: str) -> str:
    # Pin node único por componente
    return f"{cmp_urn}#pin:{pin_id}"

def _urn_inst(ref: str) -> str:
    return f"urn:cig:inst:{ref}"

def _urn_port_of_inst(inst_urn: str, port_id: str) -> str:
    return f"{inst_urn}#port:{port_id}"

def _urn_subckt(name: str) -> str:
    return f"urn:cig:subckt:{name}"

def _param_to_props(p) -> Dict[str, Any]:
    """
    Convierte Param del nuevo schema a props planas del nodo de componente/instancia.
    - Si p.quantity: {"name": {"value": <>, "unit": <>}}
    - Si p.value:    {"name": <value>}
    """
    if getattr(p, "quantity", None) is not None:
        q = p.quantity
        return {p.name: {"value": q.value, "unit": q.unit}}
    else:
        return {p.name: p.value}

def _is_ground_like(net_obj) -> bool:
    """
    Heurística robusta: detecta tierra si:
    - Net.type == "GROUND", o
    - id contiene "gnd" o "ground" (case-insensitive)
    """
    try:
        if getattr(net_obj, "type", None) and str(net_obj.type).lower() == "ground":
            return True
        nid = getattr(net_obj, "id", "") or ""
        nid_l = nid.lower()
        return ("gnd" in nid_l) or ("ground" in nid_l)
    except Exception:
        return False


class Toolkit:
    def __init__(self) -> None:
        self.store = GraphStore()

    def apply_spec_json(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        try:
            model = SpecModel(**spec)
        except ValidationError as e:
            return {"ok": False, "errors": json.loads(e.json()), "graph_patch": None}

        ops = []
        for m in model.metrics:
            props = {"name": m.name, "priority": m.priority}
            if m.target: props["target"] = m.target.dict()
            if m.acceptance: props["acceptance"] = m.acceptance
            ops.append({"op":"add_node","node":{"id": m.id, "type":"Requirement", "props": props, "labels":["DIG"]}})
        if model.environment:
            env_id = f"urn:dig:env:{model.design_id.split(':')[-1]}"
            ops.append({"op":"add_node","node":{"id": env_id, "type":"Environment",
                                                "props": model.environment.dict(), "labels":["DIG"]}})
        patch = {"namespace":"DIG","ops":ops}
        apply_patch(self.store, patch)
        return {"ok": True, "errors": [], "graph_patch": patch}

    # ============================
    # TOPOLOGY (nuevo TopologyModel)
    # ============================
    def apply_topology_json(self, topo: Dict[str, Any]) -> Dict[str, Any]:
        try:
            model = TopologyModel(**topo)
        except ValidationError as e:
            return {"ok": False, "errors": json.loads(e.json()), "graph_patch": None}

        ops: List[Dict[str, Any]] = []

        # Blocks → FunctionBlock
        for b in model.blocks:
            props_b: Dict[str, Any] = {"domain": getattr(b, "domain", None)}
            cls_b = getattr(b, "class_", None)
            if cls_b is not None:
                props_b["class"] = getattr(cls_b, "value", cls_b)
            ops.append({
                "op":"add_node",
                "node":{
                    "id": b.id,
                    "type":"FunctionBlock",
                    "props": props_b,
                    "labels":["FTG"]
                }
            })

        # Ports → Signal (funcionales)
        for p in model.ports:
            ops.append({
                "op":"add_node",
                "node":{
                    "id": p.id,
                    "type":"Signal",
                    "props":{"kind": p.kind, "domain": getattr(p, "domain", None)},
                    "labels":["FTG"]
                }
            })

        # Connections (edges funcionales)
        for c in model.connections:
            edge_id = f"{c.from_}__to__{c.to}"
            ops.append({
                "op":"add_edge",
                "edge":{"id": edge_id, "type":"connects", "from": c.from_, "to": c.to, "props": {}}
            })

        patch = {"namespace":"FTG","ops":ops}
        apply_patch(self.store, patch)
        return {"ok": True, "errors": [], "graph_patch": patch}

    # ============================
    # NETLIST (nuevo NetlistModel)
    # ============================
    def apply_netlist_json(self, netlist: Dict[str, Any]) -> Dict[str, Any]:
        try:
            model = NetlistModel(**netlist)
        except ValidationError as e:
            return {"ok": False, "warnings": [], "errors": json.loads(e.json()),
                    "applied_patch": None, "violations": None}

        ops: List[Dict[str, Any]] = []

        # ---- Nets
        for n in model.nets:
            urn = _urn_net(n.id)
            props = {"type": getattr(n, "type", None), "domain": getattr(n, "domain", None),
                     "is_reference_ground": getattr(n, "is_reference_ground", False)}
            ops.append({
                "op":"add_node",
                "node":{"id": urn, "type":"Net", "props": props, "labels":["CIG"]}
            })

        # ---- Subcircuit definitions (opcionales)
        for s in getattr(model, "subcircuits", []) or []:
            s_urn = _urn_subckt(s.name)
            # Guardamos definición como nodo
            ops.append({
                "op":"add_node",
                "node":{
                    "id": s_urn,
                    "type":"SubcircuitDef",
                    "props": {"name": s.name},
                    "labels":["CIG"]
                }
            })
            # (Opcional) Puedes materializar también sus puertos internos como nodos/edges en otro namespace.

        # ---- Components
        for c in model.components:
            cid = _urn_cmp(c.ref)
            cls = getattr(c, "class_", None)
            cls_str = getattr(cls, "value", cls)
            props: Dict[str, Any] = {
                "part_ref": getattr(c, "part_ref", None),
                "domain": getattr(c, "domain", None),
            }
            if cls_str is not None:
                props["class"] = cls_str
            ops.append({
                "op":"add_node",
                "node":{"id": cid, "type":"ComponentInstance", "props": props, "labels":["CIG"]}
            })
            # Params como props planas/jerárquicas
            for p in getattr(c, "params", []) or []:
                ops.append({"op":"update_node", "node":{"id": cid, "props": _param_to_props(p)}})
            # Pins del componente
            for pin in c.pins:
                pin_urn = _urn_pin_of_cmp(cid, pin.pin_id)
                ops.append({
                    "op":"add_node",
                    "node":{"id": pin_urn, "type":"Pin", "props":{"name": pin.name, "role": getattr(pin, "role", None)}, "labels":["CIG"]}
                })
                ops.append({
                    "op":"add_edge",
                    "edge":{"id": f"{pin_urn}__of", "type":"pinOf", "from": pin_urn, "to": cid, "props": {}}
                })

        # ---- Instances (de subcircuit)
        for inst in getattr(model, "instances", []) or []:
            iid = _urn_inst(inst.ref)
            props = {"of": inst.of, "domain": getattr(inst, "domain", None)}
            ops.append({
                "op":"add_node",
                "node":{"id": iid, "type":"SubcircuitInstance", "props": props, "labels":["CIG"]}
            })
            # Params
            for p in getattr(inst, "params", []) or []:
                ops.append({"op":"update_node", "node":{"id": iid, "props": _param_to_props(p)}})

            # Materializa port_map como puertos/pines de la instancia conectados a nets superiores
            for port_id, net_id in (inst.port_map or {}).items():
                port_urn = _urn_port_of_inst(iid, port_id)
                net_urn = _urn_net(net_id)
                # Crea el puerto
                ops.append({
                    "op":"add_node",
                    "node":{"id": port_urn, "type":"Port", "props":{"name": port_id}, "labels":["CIG"]}
                })
                ops.append({
                    "op":"add_edge",
                    "edge":{"id": f"{port_urn}__of", "type":"portOf", "from": port_urn, "to": iid, "props": {}}
                })
                # Conecta a net
                ops.append({
                    "op":"add_edge",
                    "edge":{"id": f"{port_urn}__on__{net_urn}", "type":"onNet", "from": port_urn, "to": net_urn, "props": {}}
                })

        # ---- Connections (component_ref + pin_id → net)
        # Puede referenciar ComponentInstance o SubcircuitInstance.
        for con in model.connections:
            ref = con.component_ref
            net_urn = _urn_net(con.net)

            # ¿Es componente?
            cmp_urn = _urn_cmp(ref)
            inst_urn = _urn_inst(ref)

            if self.store.exists_node(cmp_urn):
                pin_urn = _urn_pin_of_cmp(cmp_urn, con.pin_id)
                # Asegura existencia del pin si por cualquier motivo no se creó (robustez)
                if not self.store.exists_node(pin_urn):
                    ops.append({
                        "op":"add_node",
                        "node":{"id": pin_urn, "type":"Pin", "props":{"name": con.pin_id}, "labels":["CIG"]}
                    })
                    ops.append({
                        "op":"add_edge",
                        "edge":{"id": f"{pin_urn}__of", "type":"pinOf", "from": pin_urn, "to": cmp_urn, "props": {}}
                    })
                ops.append({
                    "op":"add_edge",
                    "edge":{"id": f"{pin_urn}__on__{net_urn}", "type":"onNet", "from": pin_urn, "to": net_urn, "props": {}}
                })

            # ¿Es instancia?
            elif self.store.exists_node(inst_urn):
                # Para conexiones explícitas a una instancia, modelamos el "pin" como un puerto adicional
                port_urn = _urn_port_of_inst(inst_urn, con.pin_id)
                if not self.store.exists_node(port_urn):
                    ops.append({
                        "op":"add_node",
                        "node":{"id": port_urn, "type":"Port", "props":{"name": con.pin_id}, "labels":["CIG"]}
                    })
                    ops.append({
                        "op":"add_edge",
                        "edge":{"id": f"{port_urn}__of", "type":"portOf", "from": port_urn, "to": inst_urn, "props": {}}
                    })
                ops.append({
                    "op":"add_edge",
                    "edge":{"id": f"{port_urn}__on__{net_urn}", "type":"onNet", "from": port_urn, "to": net_urn, "props": {}}
                })

            else:
                # Si no existe aún (orden de creación), igual añadimos edge y que el patcher resuelva más tarde.
                # O puedes acumular un warning explícito:
                pass

        patch = {"namespace":"CIG","ops":ops}
        apply_patch(self.store, patch)

        # -----------------
        # Warnings/violations
        # -----------------
        warnings: List[str] = []
        errors: List[str] = []

        # Ground detection robusta (no dependas del prefijo 'urn:cig:net:gnd')
        try:
            # Si tienes acceso al modelo, úsalo:
            has_gnd = any(_is_ground_like(n) for n in model.nets)
        except Exception:
            # fallback a inspección del store
            net_ids = list(self.store.nodes_by_type("Net"))
            has_gnd = any(("gnd" in nid.lower() or "ground" in nid.lower()) for nid in net_ids)

        if not has_gnd:
            warnings.append(
                "No ground-like net found. Marca alguna net con type='GROUND' o con id que contenga 'GND'."
            )

        viols = run_rulesets(self.store, model.design_id)
        high = [v for v in viols.get("violations", []) if v.get("severity") == "high"]
        ok = len(high) == 0 and len(errors) == 0

        return {"ok": ok, "warnings": warnings, "errors": errors,
                "applied_patch": patch, "violations": viols}
