"""AnalyticalSizer tool entry."""
from typing import Dict, Any
from schema.sizing_schema import SizingModel
from graph.patcher import apply_patch
from graph.store import GraphStore


def analytical_size_schema_validator(store: GraphStore, payload: Dict[str, Any]) -> Dict[str, Any]:
    errors = []
    try:
        model = SizingModel(**payload)
    except Exception as e:
        return {"ok": False, "errors": [str(e)], "graph_patch": None}

    ops = []

    # Add ESG variables/equations as nodes
    for eq in model.equations:
        ops.append({"op":"add_node","node":{"id": eq.id, "type":"Equation",
                                            "props":{"equation_latex": eq.equation_latex,
                                                     "variables":[v.dict() for v in eq.variables],
                                                     "result": eq.result,
                                                     "rationale": eq.rationale},
                                            "labels":["ESG"]}})
    # Bindings into FTG/CIG props
    for b in model.bindings:
        ops.append({"op":"update_node","node":{"id": b.target_ref, "props": {b.param: b.value}}})

    patch = {"namespace":"ESG","ops":ops}
    apply_patch(store, patch)
    return {"ok": True, "errors": [], "graph_patch": patch}
