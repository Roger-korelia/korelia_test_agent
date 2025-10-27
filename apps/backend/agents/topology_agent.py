"""TopologyAgent tool entry."""
from typing import Dict, Any
from schema.topology_schema import TopologyModel
from graph.patcher import apply_patch
from graph.store import GraphStore


def topology_schema_validator(store: GraphStore, payload: Dict[str, Any]) -> Dict[str, Any]:
    errors = []
    try:
        model = TopologyModel(**payload)
    except Exception as e:
        return {"ok": False, "errors": [str(e)], "graph_patch": None}

    ops = []
    # blocks
    for b in model.topology.blocks:
        ops.append({"op":"add_node","node":{"id": b.id, "type":"FunctionBlock",
                                            "props":{"class": b.class_, "role": b.role}, "labels":["FTG"]}})
    # ports (signals)
    for s in model.topology.ports:
        ops.append({"op":"add_node","node":{"id": s.id, "type":"Signal",
                                            "props":{"kind": s.kind}, "labels":["FTG"]}})
    # connections
    for c in model.topology.connections:
        ops.append({"op":"add_edge","edge":{"id": f"{c.from_}__to__{c.to}", "type":"connects",
                                            "from": c.from_, "to": c.to, "props":{}}})

    patch = {"namespace":"FTG","ops":ops}
    apply_patch(store, patch)
    return {"ok": True, "errors": [], "graph_patch": patch}
