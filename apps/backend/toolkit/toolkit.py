import json
from typing import Dict, Any, List
from pydantic import ValidationError

from graph.store import GraphStore
from graph.patcher import apply_patch
from rules.engine import run_rulesets
from schema.spec_schema import SpecModel
from schema.topology_schema import TopologyModel
from schema.netlist_schema import NetlistModel

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

    def apply_topology_json(self, topo: Dict[str, Any]) -> Dict[str, Any]:
        try:
            model = TopologyModel(**topo)
        except ValidationError as e:
            return {"ok": False, "errors": json.loads(e.json()), "graph_patch": None}
        ops = []
        for b in model.topology.blocks:
            ops.append({"op":"add_node","node":{"id": b.id, "type":"FunctionBlock",
                                                "props":{"class": b.class_, "role": b.role}, "labels":["FTG"]}})
        for p in model.topology.ports:
            ops.append({"op":"add_node","node":{"id": p.id, "type":"Signal",
                                                "props":{"kind": p.kind}, "labels":["FTG"]}})
        for c in model.topology.connections:
            ops.append({"op":"add_edge","edge":{"id": f"{c.from_}__to__{c.to}", "type":"connects",
                                                "from": c.from_, "to": c.to, "props":{}}})
        patch = {"namespace":"FTG","ops":ops}
        apply_patch(self.store, patch)
        return {"ok": True, "errors": [], "graph_patch": patch}


    def apply_netlist_json(self, netlist: Dict[str, Any]) -> Dict[str, Any]:
        try:
            model = NetlistModel(**netlist)
        except ValidationError as e:
            return {"ok": False, "warnings": [], "errors": json.loads(e.json()),
                    "applied_patch": None, "violations": None}
        ops = []
        for n in model.nets:
            ops.append({"op":"add_node","node":{"id": n.id, "type":"Net", "props":{"type": n.type}, "labels":["CIG"]}})
        for c in model.components:
            cid = f"urn:cig:cmp:{c.ref}"
            ops.append({"op":"add_node","node":{"id": cid, "type":"ComponentInstance",
                                                "props":{"class": c.class_, "part_ref": c.part_ref}, "labels":["CIG"]}})
            for p in c.params:
                ops.append({"op":"update_node","node":{"id": cid, "props": {p.name: {"value": p.value, "unit": p.unit}}}})
            for pin in c.pins:
                ops.append({"op":"add_node","node":{"id": pin.pin_id, "type":"Pin", "props":{"name": pin.name}, "labels":["CIG"]}})
                ops.append({"op":"add_edge","edge":{"id": f"{pin.pin_id}__of", "type":"pinOf", "from": pin.pin_id, "to": cid, "props":{}}})
        for con in model.connections:
            ops.append({"op":"add_edge","edge":{"id": f"{con.pin}__on__{con.net}", "type":"onNet",
                                                "from": con.pin, "to": con.net, "props":{}}})
        patch = {"namespace":"CIG","ops":ops}
        apply_patch(self.store, patch)

        warnings, errors = [], []
        has_gnd = any(n.lower().startswith("urn:cig:net:gnd") for n in self.store.nodes_by_type("Net"))
        if not has_gnd:
            warnings.append("No ground-like net found (id startswith urn:cig:net:GND).")

        viols = run_rulesets(self.store, model.design_id)
        high = [v for v in viols["violations"] if v.get("severity") == "high"]
        ok = len(high) == 0 and len(errors) == 0
        return {"ok": ok, "warnings": warnings, "errors": errors, "applied_patch": patch, "violations": viols}
