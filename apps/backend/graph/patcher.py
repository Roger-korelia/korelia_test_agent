from typing import Dict, Any
from .store import GraphStore


def apply_patch(store: GraphStore, patch: Dict[str, Any]) -> None:
    """Apply a GraphPatch dictionary to the store (namespace ignored here; could be used to set labels)."""
    if not patch: return
    ops = patch.get("ops", [])
    ns = patch.get("namespace", None)

    for op in ops:
        kind = op.get("op")
        if kind == "add_node":
            node = op["node"]
            labels = node.get("labels")
            store.add_node(node["id"], node["type"], node.get("props"), labels)
        elif kind == "update_node":
            node = op["node"]
            store.update_node(node["id"], node.get("props", {}))
        elif kind == "remove_node":
            store.remove_node(op["id"])
        elif kind == "add_edge":
            edge = op["edge"]
            store.add_edge(edge["id"], edge["type"], edge["from"], edge["to"], edge.get("props"))
        elif kind == "update_edge":
            edge = op["edge"]
            store.update_edge(edge["id"], edge.get("from"), edge.get("to"), edge.get("props"))
        elif kind == "remove_edge":
            store.remove_edge(op["id"])
        else:
            raise ValueError(f"Unsupported op: {kind}")
