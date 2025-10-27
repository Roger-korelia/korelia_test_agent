from __future__ import annotations
from typing import Dict, Any, List
from .store import GraphStore
from .patcher import apply_patch
from .rulesets import RULES_POWER_BASE


def to_cig_from_netlist_json(netlist: Dict[str, Any]) -> Dict[str, Any]:
    """Create a CIG graph_patch from a netlist.json body."""
    ops: List[Dict[str, Any]] = []

    # Nets
    for net in netlist.get("nets", []):
        ops.append({
            "op": "add_node",
            "node": {"id": net["id"], "type": "Net", "props": {"type": net.get("type")}, "labels": ["CIG"]}
        })

    # Components & Pins
    for comp in netlist.get("components", []):
        cid = f"urn:cig:cmp:{comp['ref']}"
        ops.append({"op": "add_node", "node": {"id": cid, "type": "ComponentInstance",
                                               "props": {"class": comp.get("class"), "part_ref": comp.get("part_ref")},
                                               "labels": ["CIG"]}})
        for p in comp.get("params", []):
            # store param directly on component props
            ops.append({"op":"update_node","node":{"id": cid, "props": {p["name"]: {"value": p.get("value"), "unit": p.get("unit")}}}})
        for pin in comp.get("pins", []):
            ops.append({"op": "add_node", "node": {"id": pin["pin_id"], "type": "Pin", "props": {"name": pin["name"]}, "labels": ["CIG"]}})
            ops.append({"op": "add_edge", "edge": {"id": f"{pin['pin_id']}__of",
                                                   "type": "pinOf", "from": pin["pin_id"], "to": cid, "props": {}}})

    # Connections
    for c in netlist.get("connections", []):
        ops.append({"op": "add_edge", "edge": {"id": f"{c['pin']}__on__{c['net']}", "type": "onNet",
                                               "from": c["pin"], "to": c["net"], "props": {}}})

    return {"namespace": "CIG", "ops": ops}


def run_rulesets(store: GraphStore, design_id: str) -> Dict[str, Any]:
    checks = []
    viols: List[Dict[str, Any]] = []
    for name, fn in RULES_POWER_BASE.items():
        checks.append(name)
        viols.extend(fn(store))
    return {
        "design_id": design_id,
        "checks_run": checks,
        "violations": viols
    }


def graph_apply_netlist_json(store: GraphStore, netlist: Dict[str, Any]) -> Dict[str, Any]:
    """Apply netlist.json → CIG patch, then run validators and return summary."""
    patch = to_cig_from_netlist_json(netlist)
    apply_patch(store, patch)

    # minimal structural checks
    errors = []
    warnings = []

    # ensure at least one ground-like net
    has_gnd = any(n.lower().startswith("urn:cig:net:gnd") for n in store.nodes_by_type("Net"))
    if not has_gnd:
        warnings.append("No ground-like net found (id startswith urn:cig:net:GND).")

    viol = run_rulesets(store, netlist.get("design_id", "unknown"))
    high = [v for v in viol["violations"] if v.get("severity") == "high"]
    ok = len(high) == 0 and len(errors) == 0

    return {
        "ok": ok,
        "warnings": warnings,
        "errors": errors,
        "applied_patch": patch,
        "violations": viol
    }
