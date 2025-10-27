from typing import List, Dict, Any
from graph.store import GraphStore
from graph.context import get_context_values

def kcl_degree(store: GraphStore) -> List[Dict[str, Any]]:
    out = []
    for net_id in store.nodes_by_type("Net"):
        deg = 0
        for u, v, _, _ in store.g.edges(keys=True, data=True):
            if u == net_id or v == net_id:
                deg += 1
        if deg < 2:
            out.append({
                "id": f"viol:KCL:{net_id}",
                "rule": "KCL",
                "severity": "medium",
                "context": {"net": net_id, "degree": deg},
                "message": f"Net {net_id} has insufficient connections (deg={deg}).",
                "suggested_fixes": []
            })
    return out

def vds_margin(store: GraphStore) -> List[Dict[str, Any]]:
    ctx = get_context_values(store)
    vbus = ctx.get("Vbus_peak")
    if vbus is None:
        return []
    out = []
    for cid in store.nodes_by_type("ComponentInstance"):
        props = store.node_props(cid)
        vds = None
        if "Vds_max" in props:
            vv = props["Vds_max"]
            vds = vv.get("value", vv) if isinstance(vv, dict) else vv
        if vds is not None and vds < 1.1 * vbus:
            out.append({
                "id": f"viol:Ratings:Vds:{cid}",
                "rule": "Ratings:Vds_margin",
                "severity": "high",
                "context": {"node": cid, "param": "Vds_max", "evidence": {"Vbus_peak": vbus}},
                "message": f"Vds_max {vds}V < 1.1*Vbus_peak {1.1*vbus:.1f}V",
                "suggested_fixes": []
            })
    return out

RULESET_POWER_BASE = {
    "KCL": kcl_degree,
    "Ratings:Vds_margin": vds_margin,
}
