from typing import List, Dict, Any, Callable, Optional, Set
from .store import GraphStore
from .context import get_context_values


# ---------- Helpers específicos del grafo ----------

def _is_onnet_edge(store: GraphStore, u: str, v: str, key: Any) -> bool:
    data = store.g.edges[u, v, key]
    return data.get("type") == "onNet"

def _is_pinof_edge(store: GraphStore, u: str, v: str, key: Any) -> bool:
    data = store.g.edges[u, v, key]
    return data.get("type") == "pinOf"

def _onnet_sources_to_net(store: GraphStore, net_id: str) -> Set[str]:
    """Terminales (pins/ports) conectados a la net vía onNet (terminal -> net)."""
    sources: Set[str] = set()
    if net_id not in store.g:
        return sources
    for u, v, key in store.g.in_edges(net_id, keys=True):
        if _is_onnet_edge(store, u, v, key):
            sources.add(u)
    return sources

def _pins_of_component(store: GraphStore, cmp_id: str) -> Set[str]:
    """Pins que pertenecen a un componente (pinOf: pin -> component)."""
    pins: Set[str] = set()
    if cmp_id not in store.g:
        return pins
    for u, v, key in store.g.in_edges(cmp_id, keys=True):
        if _is_pinof_edge(store, u, v, key):
            pins.add(u)
    return pins

def _net_of_terminal(store: GraphStore, terminal_node_id: str) -> Optional[str]:
    """Net conectada a un pin/port (onNet: terminal -> net)."""
    if terminal_node_id not in store.g:
        return None
    for _, v, key in store.g.out_edges(terminal_node_id, keys=True):
        if _is_onnet_edge(store, terminal_node_id, v, key):
            return v
    return None

def _get_numeric_param(value_or_dict: Any, unit_map: Dict[str, float] | None = None) -> Optional[float]:
    """Acepta escalar o dict {'value','unit'}; aplica escala si hay unidad."""
    unit_map = unit_map or {}
    if value_or_dict is None:
        return None
    if isinstance(value_or_dict, (int, float)):
        return float(value_or_dict)
    if isinstance(value_or_dict, dict):
        val = value_or_dict.get("value", None)
        if val is None:
            return None
        unit = value_or_dict.get("unit", None)
        scale = unit_map.get(str(unit).lower(), 1.0) if unit else 1.0
        try:
            return float(val) * scale
        except Exception:
            return None
    return None


# ---------- Reglas ----------

def kcl_degree(store: GraphStore) -> List[Dict[str, Any]]:
    """
    KCL simple: una net debe tener ≥ 2 terminales eléctricos.
    Cuenta únicamente terminales conectados por edges 'onNet'.
    """
    out: List[Dict[str, Any]] = []
    for net_id in store.nodes_by_type("Net"):
        terminals = _onnet_sources_to_net(store, net_id)
        deg = len(terminals)
        if deg < 2:
            sev = "high" if deg == 0 else "medium"
            out.append({
                "id": f"viol:KCL:{net_id}",
                "rule": "KCL",
                "severity": sev,
                "context": {"net": net_id, "degree": deg, "terminals": list(terminals)},
                "message": f"Net {net_id} has insufficient terminations (deg={deg}).",
                "suggested_fixes": [
                    "Conecta el retorno o elimina la net si está sin uso",
                    "Verifica que todos los pins previstos estén realmente en la net (onNet)"
                ]
            })
    return out


def vds_margin(store: GraphStore) -> List[Dict[str, Any]]:
    """
    Check: Vds_max >= 1.1 * Vbus_peak
    Se aplica a MOSFET/IGBT (amplía si procede). Acepta escalar o {'value','unit'}.
    """
    ctx = get_context_values(store)
    vbus = ctx.get("Vbus_peak")
    if vbus is None:
        return []

    unit_map = {"v": 1.0, "kv": 1000.0, "mv": 1e-3}
    out: List[Dict[str, Any]] = []
    for cid in store.nodes_by_type("ComponentInstance"):
        props = store.node_props(cid) or {}
        cls = (props.get("class") or "").lower()
        if cls not in ("mosfet", "igbt"):
            continue
        vds = _get_numeric_param(props.get("Vds_max"), unit_map=unit_map)
        if vds is None:
            continue
        margin_req = 1.1 * float(vbus)
        if vds < margin_req:
            out.append({
                "id": f"viol:Ratings:Vds:{cid}",
                "rule": "Ratings:Vds_margin",
                "severity": "high",
                "context": {"node": cid, "param": "Vds_max", "evidence": {"Vbus_peak": vbus}},
                "message": f"Vds_max {vds} V < 1.1*Vbus_peak {margin_req:.2f} V",
                "suggested_fixes": [
                    "Selecciona un MOSFET con mayor Vds_max",
                    "Reduce Vbus_peak o aumenta margen de seguridad"
                ]
            })
    return out


def anti_ideal_loop(store: GraphStore) -> List[Dict[str, Any]]:
    """
    Mínimo útil: detectar fuente ideal con + y - en la misma net.
    Requiere que los pins tengan role/name coherentes (+/-).
    """
    out: List[Dict[str, Any]] = []
    for cid in store.nodes_by_type("ComponentInstance"):
        props = store.node_props(cid) or {}
        cls = (props.get("class") or "").lower()
        if cls not in ("source", "voltage_source", "current_source"):
            continue

        # pins del componente (pinOf: pin -> component)
        pins = set()
        for u, v, key in store.g.in_edges(cid, keys=True):
            if store.g.edges[u, v, key].get("type") == "pinOf":
                pins.add(u)

        pos, neg = set(), set()
        for p in pins:
            pprops = store.node_props(p) or {}
            role = (pprops.get("role") or "").lower()
            name = (pprops.get("name") or "").lower()
            if role in ("+", "pos", "positive") or name in ("+", "pos", "positive"):
                pos.add(p)
            if role in ("-", "neg", "negative") or name in ("-", "neg", "negative"):
                neg.add(p)

        if not pos or not neg:
            continue

        for pp in pos:
            net_p = _net_of_terminal(store, pp)
            if not net_p:
                continue
            for nn in neg:
                net_n = _net_of_terminal(store, nn)
                if net_n and net_n == net_p:
                    out.append({
                        "id": f"viol:AntiIdealLoop:{cid}",
                        "rule": "AntiIdealLoop",
                        "severity": "high",
                        "context": {"source": cid, "net": net_p, "pins": {"pos": pp, "neg": nn}},
                        "message": f"Fuente ideal '{cid}' tiene + y - en la misma net ({net_p}).",
                        "suggested_fixes": [
                            "Corrige el cableado: los terminales no pueden compartir net",
                            "Añade impedancia si estás creando un lazo de prueba"
                        ]
                    })
                    break
    return out


# ---------- Registro ----------

RULESET_POWER_BASE: Dict[str, Callable[[GraphStore], List[Dict[str, Any]]]] = {
    "KCL": kcl_degree,
    "Ratings:Vds_margin": vds_margin,
    "AntiIdealLoop": anti_ideal_loop,
}
