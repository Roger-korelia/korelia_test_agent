"""SpecAgent tool entry (bind this function to a LangChain Tool)."""
from typing import Dict, Any
from schema.spec_schema import SpecModel
from graph.patcher import apply_patch
from graph.store import GraphStore


def spec_schema_validator(store: GraphStore, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate spec.json and return {ok, errors, graph_patch}. Apply DIG patch with requirements & environment."""
    errors = []
    try:
        model = SpecModel(**payload)
    except Exception as e:
        return {"ok": False, "errors": [str(e)], "graph_patch": None}

    # Build a simple DIG patch
    ops = []
    for m in model.metrics:
        props = {"name": m.name}
        if m.target:
            props["target"] = m.target.dict()
        props["priority"] = m.priority
        if m.acceptance:
            props["acceptance"] = m.acceptance
        ops.append({"op":"add_node", "node": {"id": m.id, "type": "Requirement", "props": props, "labels":["DIG"]}})

    if model.environment:
        env_id = f"urn:dig:env:{model.design_id.split(':')[-1]}"
        ops.append({"op":"add_node", "node": {"id": env_id, "type": "Environment",
                                              "props": model.environment.dict(), "labels":["DIG"]}})

    patch = {"namespace":"DIG", "ops": ops}
    apply_patch(store, patch)
    return {"ok": True, "errors": [], "graph_patch": patch}
