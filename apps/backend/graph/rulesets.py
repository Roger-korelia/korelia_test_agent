from __future__ import annotations
from typing import Dict, Any, List, Callable
from .store import GraphStore
from .context import get_context_values


def check_kcl_degree(store: GraphStore) -> List[Dict[str, Any]]:
    """Very simple: warn if a net has <2 connections."""
    viols = []
    for net_id in store.nodes_by_type("Net"):
        deg = 0
        for u,v,k,data in store.edges_iter():
            if u == net_id or v == net_id:
                deg += 1
        if deg < 2:
            viols.append({
                "id": f"viol:KCL:{net_id}",
                "rule": "KCL",
                "severity": "medium",
                "context": {"net": net_id, "degree": deg},
                "message": f"Net {net_id} has insufficient connections (deg={deg}).",
                "suggested_fixes": []
            })
    return viols


def ratings_vds_margin(store: GraphStore) -> List[Dict[str, Any]]:
    ctx = get_context_values(store)
    Vbus_peak = ctx.get("Vbus_peak", None)
    if Vbus_peak is None:
        return []
    viols = []
    for cmp_id in store.nodes_by_type("ComponentInstance"):
        props = store.node_props(cmp_id)
        Vds = None
        if "Vds_max" in props:
            v = props["Vds_max"]
            Vds = v.get("value", v) if isinstance(v, dict) else v
        if Vds is not None and Vds < 1.1 * Vbus_peak:
            viols.append({
                "id": f"viol:Ratings:Vds:{cmp_id}",
                "rule": "Ratings:Vds_margin",
                "severity": "high",
                "context": {"node": cmp_id, "param": "Vds_max", "evidence": {"Vbus_peak": Vbus_peak}},
                "message": f"Vds_max {Vds}V < 1.1*Vbus_peak {1.1*Vbus_peak:.1f}V",
                "suggested_fixes": []
            })
    return viols


def anti_ideal_loop(store: GraphStore) -> List[Dict[str, Any]]:
    # Placeholder: in real impl, detect source-source ideal loops
    return []


RULES_POWER_BASE: Dict[str, Callable[[GraphStore], List[Dict[str, Any]]]] = {
    "KCL": check_kcl_degree,
    "Ratings:Vds_margin": ratings_vds_margin,
    "AntiIdealLoop": anti_ideal_loop,
}
