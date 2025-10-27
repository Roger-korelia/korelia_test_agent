import json
from typing import Dict
try:
    from langchain_core.tools import tool
except Exception:
    from langchain.tools import tool

from ..toolkit.toolkit import Toolkit

_THREADS: Dict[str, Toolkit] = {}

def _get_toolkit(thread_id: str) -> Toolkit:
    tk = _THREADS.get(thread_id)
    if tk is None:
        tk = Toolkit()
        _THREADS[thread_id] = tk
    return tk

@tool("spec_schema_validator")
def spec_schema_validator(spec_json: str, thread_id: str = "default") -> str:
    tk = _get_toolkit(thread_id)
    try:
        payload = json.loads(spec_json)
    except Exception as e:
        return json.dumps({"ok": False, "errors": [f"JSON inválido: {e}"]}, ensure_ascii=False)
    return json.dumps(tk.apply_spec_json(payload), ensure_ascii=False)

@tool("topology_schema_validator")
def topology_schema_validator(topology_json: str, thread_id: str = "default") -> str:
    tk = _get_toolkit(thread_id)
    try:
        payload = json.loads(topology_json)
    except Exception as e:
        return json.dumps({"ok": False, "errors": [f"JSON inválido: {e}"]}, ensure_ascii=False)
    return json.dumps(tk.apply_topology_json(payload), ensure_ascii=False)

@tool("analytical_size_schema_validator")
def analytical_size_schema_validator(sizing_json: str, thread_id: str = "default") -> str:
    tk = _get_toolkit(thread_id)
    try:
        payload = json.loads(sizing_json)
    except Exception as e:
        return json.dumps({"ok": False, "errors": [f"JSON inválido: {e}"]}, ensure_ascii=False)
    return json.dumps(tk.apply_sizing_json(payload), ensure_ascii=False)

@tool("graph_apply_netlist_json")
def graph_apply_netlist_json(netlist_json: str, allow_autolock: str = "true", thread_id: str = "default") -> str:
    """Aplica una netlist propuesta en JSON al builder por capas del toolkit y valida."""
    tk = _get_toolkit(thread_id)
    try:
        payload = json.loads(netlist_json)
    except Exception as e:
        return json.dumps({"error": f"JSON inválido: {e}"}, ensure_ascii=False)
    try:
        res = tk.apply_netlist_json(payload)
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

@tool("graph_dump")
def graph_dump(thread_id: str = "default") -> str:
    """Devuelve un volcado del grafo actual (nodos/edges) para debug."""
    tk = _get_toolkit(thread_id)
    return json.dumps(tk.store.to_dict(), ensure_ascii=False)
