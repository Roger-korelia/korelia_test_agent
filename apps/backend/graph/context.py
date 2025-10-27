from typing import Dict, Any
from .store import GraphStore


def get_context_values(store: GraphStore) -> Dict[str, Any]:
    """Collects design context values from DIG/ESG into a flat dict for rules (e.g., Vbus_peak, T_ambient)."""
    ctx: Dict[str, Any] = {}
    # naive extraction: scan nodes for props with simple names
    for n, data in store.g.nodes(data=True):
        props = data.get("props", {})
        for k,v in props.items():
            if isinstance(v, dict) and "value" in v:
                ctx[k] = v["value"]
            elif isinstance(v, (int,float)):
                ctx[k] = v
    # typical keys you might set via ESG/DIG bindings
    if "T_ambient" not in ctx and "ambient" in ctx:
        ctx["T_ambient"] = ctx["ambient"]
    return ctx
