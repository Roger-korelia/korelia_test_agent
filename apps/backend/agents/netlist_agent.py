"""NetlistAgent tool entry (reflexive loop is orchestrated outside; this tool just applies/validates)."""
from typing import Dict, Any
from schema.netlist_schema import NetlistModel
from graph.validators import graph_apply_netlist_json
from graph.store import GraphStore


def graph_apply_netlist_json_tool(store: GraphStore, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        _ = NetlistModel(**payload)  # schema check
    except Exception as e:
        return {"ok": False, "warnings": [], "errors": [str(e)], "applied_patch": None, "violations": None}
    return graph_apply_netlist_json(store, payload)
