# orchestrated_pipeline.py
# =========================================================
# Pipeline reflexivo con histórico por paso e integración de tools graph-first
# =========================================================
import os
import json
import base64
import datetime as dt
from typing import Literal, Dict, Any, List, Optional, TypedDict, Tuple
from dotenv import load_dotenv

# LangChain / LangGraph
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from langchain.agents import create_agent

# --- Esquemas ---
from schema.spec_schema import SpecModel
from schema.topology_schema import TopologyModel
from schema.sizing_schema import SizingModel
from schema.netlist_schema import NetlistModel
# --- Toolkit (grafo) y herramientas externas
#   Asegúrate de que estos módulos existen en tu repo
from toolkit.toolkit import Toolkit  # tu clase Toolkit (apply_*_json)
from tools.run_tools import (
    spice_autorun,
    kicad_cli_exec,
    kicad_project_manager,
    kicad_erc,
    kicad_drc,
)
from spice_toolkit import SpiceToolkit  # si usas un wrapper propio, ajusta el import


# =========================================================
# Config y LLM
# =========================================================
load_dotenv()
os.environ.setdefault("NGSPICE", r"C:\Program Files\Spice64\bin\ngspice.exe")
os.environ.setdefault("KICAD_CLI", r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe")

llm_base = ChatOpenAI(model="gpt-4.1-nano", temperature=0.1)


# =========================================================
# STATE MODELS (reflexivo + histórico)
# =========================================================
StepName = Literal["spec", "topology", "sizing", "netlist", "simulation", "kicad", "documentation"]

class FeedbackItem(TypedDict):
    kind: Literal["error","warning","violation","info"]
    message: str
    context: Dict[str, Any]

class AttemptRecord(TypedDict):
    timestamp: str
    payload_in: Optional[str]       # prompt o JSON de entrada que generó el intento (si aplica)
    tool_output: Optional[str]      # cadena JSON devuelta por la tool
    ok: bool
    feedback: List[FeedbackItem]

class ProcessStepData(TypedDict):
    status: Literal["pending","in_progress","completed","failed","needs_improvement"]
    attempts: int
    last_updated: Optional[str]
    result: Optional[Dict[str, Any]]       # último resultado parseado
    feedback: List[FeedbackItem]           # feedback acumulado
    history: List[AttemptRecord]           # todos los intentos

class IntentData(TypedDict):
    intent_id: str
    timestamp: str
    overall_status: Literal["in_progress","completed","failed","needs_improvement"]
    total_attempts: int
    steps: Dict[StepName, ProcessStepData]

class WorkflowState(TypedDict):
    messages: List[BaseMessage]
    current_task: str
    workflow_step: StepName
    should_proceed: bool
    agent_feedback: str
    intent_history: List[IntentData]
    current_intent: IntentData


# =========================================================
# Helpers de tiempo/estado
# =========================================================
def _now() -> str:
    return dt.datetime.now().isoformat()

def _new_step() -> ProcessStepData:
    return {
        "status": "pending",
        "attempts": 0,
        "last_updated": None,
        "result": None,
        "feedback": [],
        "history": [],
    }

def _new_intent(intent_id: str) -> IntentData:
    return {
        "intent_id": intent_id,
        "timestamp": _now(),
        "overall_status": "in_progress",
        "total_attempts": 0,
        "steps": {
            "spec": _new_step(),
            "topology": _new_step(),
            "sizing": _new_step(),
            "netlist": _new_step(),
            "simulation": _new_step(),
            "kicad": _new_step(),
            "documentation": _new_step(),
        },
    }


# =========================================================
# THREAD REGISTRIES (separados) + Tools del grafo
# =========================================================
_GRAPH_THREADS: Dict[str, Toolkit] = {}
_SPICE_THREADS: Dict[str, SpiceToolkit] = {}

def _get_graph_toolkit(thread_id: str) -> Toolkit:
    tk = _GRAPH_THREADS.get(thread_id)
    if tk is None:
        tk = Toolkit()
        _GRAPH_THREADS[thread_id] = tk
    return tk

def _get_spice_toolkit(thread_id: str) -> SpiceToolkit:
    tk = _SPICE_THREADS.get(thread_id)
    if tk is None:
        tk = SpiceToolkit(ground="0")
        _SPICE_THREADS[thread_id] = tk
    return tk


# =========================================================
# Tools util / filesystem
# =========================================================
@tool("save_local_file")
def save_local_file(path: str, content: str, binary: str = "false") -> str:
    """Guarda contenido en el filesystem real. binary='true' para bytes en base64."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if binary.lower() == "true":
        with open(path, "wb") as f:
            f.write(base64.b64decode(content))
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    return json.dumps({"saved": path}, ensure_ascii=False)


# =========================================================
# Tools de grafo/JSON (spec/topology/sizing/netlist)
# =========================================================
@tool("spec_schema_validator")
def spec_schema_validator(spec_json: str, thread_id: str = "default") -> str:
    """Valida y aplica spec.json (DIG). Devuelve {ok, errors[], graph_patch}."""
    tk = _get_graph_toolkit(thread_id)
    try:
        payload = json.loads(spec_json)
    except Exception as e:
        return json.dumps({"ok": False, "errors": [f"JSON inválido: {e}"]}, ensure_ascii=False)
    return json.dumps(tk.apply_spec_json(payload), ensure_ascii=False)

@tool("topology_schema_validator")
def topology_schema_validator(topology_json: str, thread_id: str = "default") -> str:
    """Valida y aplica topology.json (FTG). Devuelve {ok, errors[], graph_patch}."""
    tk = _get_graph_toolkit(thread_id)
    try:
        payload = json.loads(topology_json)
    except Exception as e:
        return json.dumps({"ok": False, "errors": [f"JSON inválido: {e}"]}, ensure_ascii=False)
    return json.dumps(tk.apply_topology_json(payload), ensure_ascii=False)

@tool("analytical_size_schema_validator")
def analytical_size_schema_validator(sizing_json: str, thread_id: str = "default") -> str:
    """Valida y aplica sizing.json (ESG + bindings). Devuelve {ok, errors[], graph_patch}."""
    tk = _get_graph_toolkit(thread_id)
    try:
        payload = json.loads(sizing_json)
    except Exception as e:
        return json.dumps({"ok": False, "errors": [f"JSON inválido: {e}"]}, ensure_ascii=False)
    return json.dumps(tk.apply_sizing_json(payload), ensure_ascii=False)

@tool("graph_apply_netlist_json")
def graph_apply_netlist_json(netlist_json: str, allow_autolock: str = "true", thread_id: str = "default") -> str:
    """Aplica netlist.json → CIG y ejecuta validaciones. Devuelve {ok,warnings,errors,violations,applied_patch}."""
    tk = _get_graph_toolkit(thread_id)
    try:
        payload = json.loads(netlist_json)
    except Exception as e:
        return json.dumps({"error": f"JSON inválido: {e}"}, ensure_ascii=False)
    try:
        res = tk.apply_netlist_json(payload)  # allow_autolock no-op aquí
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# =========================================================
# Registry de tools (callables)
# =========================================================
_TOOL_REGISTRY: Dict[str, Any] = {
    # graph-first tools
    "spec_schema_validator": spec_schema_validator,
    "topology_schema_validator": topology_schema_validator,
    "analytical_size_schema_validator": analytical_size_schema_validator,
    "graph_apply_netlist_json": graph_apply_netlist_json,

    # external EDA
    "spice_autorun": spice_autorun,
    "kicad_project_manager": kicad_project_manager,
    "kicad_cli_exec": kicad_cli_exec,
    "kicad_erc": kicad_erc,
    "kicad_drc": kicad_drc,

    # utils
    "save_local_file": save_local_file,
}


# =========================================================
# Subagents (prompts + tool lists)
# =========================================================
class SubAgent:
    def __init__(self, name: str, description: str, prompt: str, tools: List[str]):
        self.name = name
        self.description = description
        self.prompt = prompt
        self.tools = tools

subagents = {
    "spec_agent": SubAgent(
        name="spec-agent",
        description="Genera especificaciones.",
        prompt=(
            "Eres ingeniero de requisitos. Devuelve SOLO JSON válido con el esquema spec.json: "
            "{design_id, metrics[], environment?, constraints[], standards[]}. "
            "No inventes valores si no están en el enunciado; usa target=null."
        ),
        tools=["spec_schema_validator"],
    ),
    "topology_agent": SubAgent(
        name="topology-agent",
        description="Genera topología funcional.",
        prompt=(
            "Eres arquitecto analógico. Elige una topología del catálogo permitido y define bloques/puertos/conexiones. "
            "Devuelve SOLO topology.json: {design_id, topology:{blocks[], ports[], connections[], assumptions[]}}. "
            "No inventes clases fuera del catálogo."
        ),
        tools=["topology_schema_validator"],
    ),
    "analytical_sizer_agent": SubAgent(
        name="analytical-size-agent",
        description="Calcula valores iniciales.",
        prompt=(
            "Eres diseñador de circuitos. Calculas valores iniciales con fórmulas explícitas. "
            "Devuelve SOLO sizing.json: {design_id, equations[], bindings[]}. "
            "Usa variables con unidades y añade rationale."
        ),
        tools=["analytical_size_schema_validator"],
    ),
    "netlist_agent": SubAgent(
        name="netlist-agent",
        description="Construye netlist CIG y corrige con feedback.",
        prompt=(
            "Eres NetlistAgent. Ciclo: propuesta→aplicar→leer feedback→corregir.\n"
            "Devuelve SOLO netlist.json: {design_id, title, components[], nets[], connections[]}. "
            "Reglas: GND único por dominio (urn:cig:net:GND_*), evitar loops ideales (añade ESR/Rser), "
            "ratings (Vds_max ≥ 1.1×Vbus_peak si está en contexto)."
        ),
        tools=["graph_apply_netlist_json"],
    ),
    "simulation_agent": SubAgent(
        name="simulation-agent",
        description="Ejecuta simulaciones SPICE y analiza resultados.",
        prompt=(
            "Eres SimulationAgent. Compila un plan mínimo suficiente para medir criterios de aceptación. "
            "Usa spice_autorun y devuelve JSON con {status, kpis?, log?}."
        ),
        tools=["spice_autorun"],
    ),
    "kicad_agent": SubAgent(
        name="kicad-agent",
        description="Crea proyecto KiCad y ejecuta ERC/DRC.",
        prompt=(
            "Eres KiCadAgent. Sigue: create_project → get_project_path → ERC → (opcional) DRC. "
            "Devuelve JSON con {status, artifacts?, log?}."
        ),
        tools=["kicad_project_manager","kicad_cli_exec","kicad_erc","kicad_drc","save_local_file"],
    ),
    "doc_agent": SubAgent(
        name="doc-agent",
        description="Genera informe de especificación y verificación.",
        prompt=(
            "Eres DocAgent. Con requisitos y resultados (SPICE/ERC/DRC), "
            "genera un reporte final. Devuelve JSON con {status, report_path?}."
        ),
        tools=[],
    ),
}


# =========================================================
# Helpers de feedback/decisión
# =========================================================
def _feedback_from_tool_response(data: Dict[str, Any]) -> List[FeedbackItem]:
    out: List[FeedbackItem] = []
    for e in (data.get("errors") or []):
        out.append({"kind":"error","message": str(e), "context": {}})
    for w in (data.get("warnings") or []):
        out.append({"kind":"warning","message": str(w), "context": {}})
    if "violations" in data:
        vset = data["violations"]
        for v in vset.get("violations", []):
            out.append({
                "kind": "violation",
                "message": v.get("message",""),
                "context": {
                    "rule": v.get("rule"),
                    "severity": v.get("severity"),
                    "context": v.get("context", {})
                }
            })
    if data.get("ok") is True and not out:
        out.append({"kind":"info","message":"Validación OK", "context": {}})
    return out

def _decide_proceed(data: Dict[str, Any], step: StepName) -> Tuple[bool, str]:
    if step in ("spec","topology","sizing"):
        if not isinstance(data, dict) or "ok" not in data:
            return False, "Respuesta no válida (falta 'ok')"
        if data["ok"] is False:
            return False, f"Errores: {data.get('errors')}"
        return True, "OK"
    if step == "netlist":
        if "violations" in data:
            highs = [v for v in data["violations"].get("violations", []) if v.get("severity") == "high"]
            if highs:
                return False, f"{len(highs)} violaciones severas"
        if data.get("ok") is False:
            return False, f"Errores: {data.get('errors')}"
        return True, "OK"
    # simulation/kicad/doc: usar 'status'
    status = (data.get("status") or "").lower()
    if status == "completed":
        return True, "OK"
    if status == "failed":
        return False, data.get("error","Fallo")
    return True, "OK"

def _push_attempt(state: WorkflowState, step: StepName, payload_in: Optional[str], tool_output_str: str):
    intent = state["current_intent"]
    s = intent["steps"][step]
    try:
        parsed = json.loads(tool_output_str)
    except Exception:
        parsed = {"ok": False, "errors": ["Tool devolvió respuesta no JSON"], "raw": tool_output_str}
    fb = _feedback_from_tool_response(parsed)
    ok, fb_note = _decide_proceed(parsed, step)

    s["attempts"] += 1
    s["last_updated"] = _now()
    s["result"] = parsed
    s["feedback"].extend(fb)
    s["history"].append({
        "timestamp": s["last_updated"],
        "payload_in": payload_in,
        "tool_output": tool_output_str,
        "ok": ok,
        "feedback": fb
    })
    s["status"] = "completed" if ok else ("needs_improvement" if fb else "failed")

    intent["total_attempts"] += 1
    state["should_proceed"] = ok
    state["agent_feedback"] = fb_note

    if not ok and step in ("spec","topology","sizing","netlist"):
        intent["overall_status"] = "needs_improvement"
    elif all(intent["steps"][k]["status"] == "completed" for k in intent["steps"]):
        intent["overall_status"] = "completed"


# =========================================================
# Orquestador y routing
# =========================================================
MAX_RETRIES: Dict[StepName, int] = {
    "spec": 3, "topology": 3, "sizing": 3, "netlist": 4, "simulation": 2, "kicad": 2, "documentation": 1
}

def _next_step(step: StepName) -> StepName:
    order = ["spec","topology","sizing","netlist","simulation","kicad","documentation"]
    i = order.index(step)
    return order[min(i+1, len(order)-1)]

def orchestrator_node(state: WorkflowState) -> WorkflowState:
    step = state.get("workflow_step","spec")
    intent = state["current_intent"]
    s = intent["steps"][step]
    print(f"🎯 ORCHESTRATOR: step={step} attempts={s['attempts']} status={s['status']} should_proceed={state.get('should_proceed')}")

    if state.get("should_proceed", True):
        nxt = _next_step(step)
        state["workflow_step"] = nxt
        print(f"➡️ AVANZAR: {step} → {nxt}")
        return state

    # No procede: reintentar si quedan retries
    retries_left = MAX_RETRIES[step] - s["attempts"]
    if retries_left > 0:
        state["workflow_step"] = step
        print(f"🔁 REINTENTAR: {step} (quedan {retries_left}) | feedback={state.get('agent_feedback')}")
        return state

    # Fallback si se agotaron intentos
    if step in ("netlist","simulation"):
        print("↩️ fallback: volver a netlist si la simulación falla repetidamente")
        state["workflow_step"] = "netlist"
        state["should_proceed"] = False
        state["agent_feedback"] = "Simulación fallida repetidamente; ajusta netlist."
        return state

    intent["overall_status"] = "failed"
    state["workflow_step"] = "documentation"
    state["should_proceed"] = True
    state["agent_feedback"] = f"Se agotaron reintentos en {step}. Generar informe."
    print(f"⛔ SIN RETRIES en {step} → documentación")
    return state

def route_after_orchestrator(state: WorkflowState) -> str:
    step = state.get("workflow_step","spec")
    return {
        "spec": "spec_agent",
        "topology": "topology_agent",
        "sizing": "analytical_sizer_agent",
        "netlist": "netlist_agent",
        "simulation": "sim_agent",
        "kicad": "kicad_agent",
        "documentation": "doc_agent",
    }.get(step, "doc_agent")


# ====== CONTEXTO SIMPLE PARA SUBAGENTES ======

import json
from typing import List, Dict, Any, Literal

StepName = Literal["spec","topology","sizing","netlist","simulation","kicad","documentation"]

def _clip_text(s: str, max_chars: int) -> str:
    if len(s) <= max_chars: 
        return s
    return s[:max_chars] + f"\n...[{len(s)-max_chars} chars clipped]"

def _brief_workflow_state(state: Dict[str, Any],
                          steps: List[StepName] = None,
                          max_history_per_step: int = 1,
                          max_chars: int = 3000) -> str:
    """
    Convierte el WorkflowState a un texto compacto y legible (sin lógica extra).
    - Limita history por step a 'max_history_per_step'
    - Recorta longitud total a 'max_chars'
    """
    if steps is None:
        steps = ["spec","topology","sizing","netlist","simulation","kicad","documentation"]

    ci = state.get("current_intent", {})
    out: Dict[str, Any] = {
        "design_task": state.get("current_task"),
        "workflow_step": state.get("workflow_step"),
        "overall_status": ci.get("overall_status"),
        "total_attempts": ci.get("total_attempts"),
        "steps": {}
    }

    sdict = ci.get("steps", {})
    for step in steps:
        s = sdict.get(step, {})
        hist: List[Dict[str, Any]] = s.get("history", [])[-max_history_per_step:] if s else []
        out["steps"][step] = {
            "status": s.get("status"),
            "attempts": s.get("attempts"),
            "last_updated": s.get("last_updated"),
            # último resultado parseado tal cual (ok/errors/violations...)
            "last_result": s.get("result"),
            # últimos intentos (solo payload_in y ok + primer feedback)
            "last_attempts": [
                {
                    "ts": h.get("timestamp"),
                    "ok": h.get("ok"),
                    "payload_in": h.get("payload_in"),
                    "first_feedback": (h.get("feedback") or [None])[0]
                } for h in hist
            ]
        }

    # encabezado ultra corto con guía
    header = (
        "## CONTEXTO DE PROYECTO (resumen del WorkflowState)\n"
        "- design_task: objetivo del usuario\n"
        "- workflow_step: paso actual\n"
        "- steps[*].last_result: último JSON validado por la tool de ese paso\n"
        "- steps[*].last_attempts: intentos previos (payload_in y primer feedback)\n\n"
    )
    body = json.dumps(out, ensure_ascii=False, indent=2)
    text = header + body
    return _clip_text(text, max_chars)

# =========================================================
# Nodos de agentes (invocan LLM+tools y registran histórico)
# =========================================================
# ====== SPEC ======
def spec_agent_node(state: WorkflowState) -> WorkflowState:
    task = state.get("current_task","")
    state["current_intent"]["steps"]["spec"]["status"] = "in_progress"

    ctx = _brief_workflow_state(state, steps=["spec"], max_history_per_step=2, max_chars=2500)

    agent = create_agent(
        model=llm_base,
        tools=[ _TOOL_REGISTRY["spec_schema_validator"] ],
        system_prompt=subagents["spec_agent"].prompt + "\n\n" + ctx + f"\n\nGenera 'spec.json' para: {task}\nDevuelve SOLO JSON."
    )
    try:
        result = agent.invoke({"input": f"Genera spec.json para: {task}"})
        output_str = result.get("output", str(result))
        _push_attempt(state, "spec", payload_in=task, tool_output_str=output_str)
    except Exception as e:
        _push_attempt(state, "spec", payload_in=task, tool_output_str=json.dumps({"ok":False,"errors":[str(e)]}))
    return state

# ====== TOPOLOGY ======
def topology_agent_node(state: WorkflowState) -> WorkflowState:
    task = state.get("current_task","")
    state["current_intent"]["steps"]["topology"]["status"] = "in_progress"

    # pasamos spec + topology previos
    ctx = _brief_workflow_state(state, steps=["spec","topology"], max_history_per_step=2, max_chars=3000)

    agent = create_agent(
        model=llm_base,
        tools=[ _TOOL_REGISTRY["topology_schema_validator"] ],
        system_prompt=subagents["topology_agent"].prompt + "\n\n" + ctx + "\n\nGenera 'topology.json' coherente con spec. Devuelve SOLO JSON."
    )
    try:
        result = agent.invoke({"input": f"Genera topology.json para: {task}"})
        output_str = result.get("output", str(result))
        _push_attempt(state, "topology", payload_in=task, tool_output_str=output_str)
    except Exception as e:
        _push_attempt(state, "topology", payload_in=task, tool_output_str=json.dumps({"ok":False,"errors":[str(e)]}))
    return state

# ====== SIZING ======
def analytical_sizer_agent_node(state: WorkflowState) -> WorkflowState:
    task = state.get("current_task","")
    state["current_intent"]["steps"]["sizing"]["status"] = "in_progress"

    # pasamos spec + topology + sizing previos
    ctx = _brief_workflow_state(state, steps=["spec","topology","sizing"], max_history_per_step=2, max_chars=3200)

    agent = create_agent(
        model=llm_base,
        tools=[ _TOOL_REGISTRY["analytical_size_schema_validator"] ],
        system_prompt=subagents["analytical_sizer_agent"].prompt + "\n\n" + ctx + "\n\nGenera 'sizing.json' usando ecuaciones explícitas. Devuelve SOLO JSON."
    )
    try:
        result = agent.invoke({"input": f"Genera sizing.json para: {task}"})
        output_str = result.get("output", str(result))
        _push_attempt(state, "sizing", payload_in=task, tool_output_str=output_str)
    except Exception as e:
        _push_attempt(state, "sizing", payload_in=task, tool_output_str=json.dumps({"ok":False,"errors":[str(e)]}))
    return state

# ====== NETLIST (con feedback previo) ======
def netlist_agent_node(state: WorkflowState) -> WorkflowState:
    task = state.get("current_task","")
    state["current_intent"]["steps"]["netlist"]["status"] = "in_progress"

    # pasamos todo lo anterior + netlist previo para que vea violaciones/errores
    ctx = _brief_workflow_state(
        state,
        steps=["spec","topology","sizing","netlist"],
        max_history_per_step=3,
        max_chars=4000
    )

    agent = create_agent(
        model=llm_base,
        tools=[ _TOOL_REGISTRY["graph_apply_netlist_json"] ],
        system_prompt=subagents["netlist_agent"].prompt + "\n\n" + ctx + "\n\nConstruye y valida 'netlist.json'. Si hay violations/errors previos, corrígelos. Devuelve SOLO JSON."
    )
    try:
        result = agent.invoke({"input": "Construye y valida netlist.json"})
        output_str = result.get("output", str(result))
        _push_attempt(state, "netlist", payload_in="netlist_build", tool_output_str=output_str)
    except Exception as e:
        _push_attempt(state, "netlist", payload_in="netlist_build", tool_output_str=json.dumps({"ok":False,"errors":[str(e)]}))
    return state


def sim_agent_node(state: WorkflowState) -> WorkflowState:
    step = "simulation"
    state["current_intent"]["steps"][step]["status"] = "in_progress"

    # Requiere netlist válido antes de simular
    last_netlist_result = state["current_intent"]["steps"]["netlist"]["result"]
    netlist_ok = last_netlist_result and (last_netlist_result.get("ok", True))
    if not netlist_ok:
        _push_attempt(
            state, step,
            payload_in="no-netlist",
            tool_output_str=json.dumps({"status":"failed","error":"No netlist válido"})
        )
        return state

    # Contexto: netlist (para ver violaciones previas) + simulation (intentos previos)
    ctx = _brief_workflow_state(
        state,
        steps=["netlist","simulation"],
        max_history_per_step=2,
        max_chars=3500
    )

    sim_agent = create_agent(
        model=llm_base,
        tools=[ _TOOL_REGISTRY["spice_autorun"] ],
        system_prompt=subagents["simulation_agent"].prompt + "\n\n" + ctx + "\n\nEjecuta la simulación SPICE usando el netlist aprobado y devuelve SOLO JSON con el formato {status, kpis?, log?}. Si falla, explica la causa en 'log'."
    )

    try:
        res = sim_agent.invoke({"input": "spice_run"})
        output_str = res.get("output", str(res))
        _push_attempt(state, step, payload_in="spice_run", tool_output_str=output_str)
    except Exception as e:
        _push_attempt(state, step, payload_in="spice_run", tool_output_str=json.dumps({"status":"failed","error":str(e)}))
    return state


def kicad_agent_node(state: WorkflowState) -> WorkflowState:
    step = "kicad"
    state["current_intent"]["steps"][step]["status"] = "in_progress"

    # Contexto: netlist + simulation + kicad (para ver artefactos previos/errores)
    ctx = _brief_workflow_state(
        state,
        steps=["netlist","simulation","kicad"],
        max_history_per_step=2,
        max_chars=3800
    )

    kicad_agent = create_agent(
        model=llm_base,
        tools=[
            _TOOL_REGISTRY["kicad_project_manager"],
            _TOOL_REGISTRY["kicad_cli_exec"],
            _TOOL_REGISTRY["kicad_erc"],
            _TOOL_REGISTRY["kicad_drc"],
            _TOOL_REGISTRY["save_local_file"],
        ],
        system_prompt=subagents["kicad_agent"].prompt + "\n\n" + ctx + "\n\nCrea el proyecto en KiCad y ejecuta ERC (y DRC si procede). Devuelve SOLO JSON con {status, artifacts?, log?}. Si falta kicad-cli, informa en 'log' y status='failed'."
    )

    try:
        res = kicad_agent.invoke({"input": "kicad_flow"})
        output_str = res.get("output", str(res))
        _push_attempt(state, step, payload_in="kicad_flow", tool_output_str=output_str)
    except Exception as e:
        _push_attempt(state, step, payload_in="kicad_flow", tool_output_str=json.dumps({"status":"failed","error":str(e)}))
    return state


def doc_agent_node(state: WorkflowState) -> WorkflowState:
    step = "documentation"
    state["current_intent"]["steps"][step]["status"] = "in_progress"
    # Aquí podrías generar un informe real; para ejemplo, marcamos completado.
    report = {"status": "completed", "report_path": "reports/final_report.md"}
    _push_attempt(state, step, payload_in="doc_flow", tool_output_str=json.dumps(report, ensure_ascii=False))
    return state


# =========================================================
# Construcción del grafo
# =========================================================
def create_workflow_graph():
    g = StateGraph(WorkflowState)
    g.add_node("orchestrator", orchestrator_node)
    g.add_node("spec_agent", spec_agent_node)
    g.add_node("topology_agent", topology_agent_node)
    g.add_node("analytical_sizer_agent", analytical_sizer_agent_node)
    g.add_node("netlist_agent", netlist_agent_node)
    g.add_node("sim_agent", sim_agent_node)
    g.add_node("kicad_agent", kicad_agent_node)
    g.add_node("doc_agent", doc_agent_node)

    g.set_entry_point("orchestrator")
    g.add_conditional_edges("orchestrator", route_after_orchestrator, {
        "spec_agent": "spec_agent",
        "topology_agent": "topology_agent",
        "analytical_sizer_agent": "analytical_sizer_agent",
        "netlist_agent": "netlist_agent",
        "sim_agent": "sim_agent",
        "kicad_agent": "kicad_agent",
        "doc_agent": "doc_agent",
    })
    # tras cada nodo vuelve al orquestador (que decide avanzar/reintentar)
    for n in ["spec_agent","topology_agent","analytical_sizer_agent","netlist_agent","sim_agent","kicad_agent","doc_agent"]:
        g.add_edge(n, "orchestrator")
    return g.compile()


# =========================================================
# Ejecución
# =========================================================
def run_orchestrated_workflow(task: str, thread_id: str = "electronics_design"):
    workflow_graph = create_workflow_graph()
    intent_id = f"intent-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    initial_intent = _new_intent(intent_id)

    initial_state: WorkflowState = WorkflowState(
        messages=[HumanMessage(content=task)],
        current_task=task,
        workflow_step="spec",
        should_proceed=True,
        agent_feedback="",
        intent_history=[],
        current_intent=initial_intent
    )

    # puedes usar stream si quieres ver progreso; aquí usamos invoke simple
    final_state = workflow_graph.invoke(initial_state, config={"thread_id": thread_id})

    if final_state:
        final_state["intent_history"].append(final_state["current_intent"])

    return {
        "final_state": final_state,
        "intent_summary": {
            "overall_status": final_state["current_intent"]["overall_status"],
            "total_attempts": final_state["current_intent"]["total_attempts"],
        },
        "steps": {
            k: {
                "status": v["status"],
                "attempts": v["attempts"],
                "last_updated": v["last_updated"]
            } for k, v in final_state["current_intent"]["steps"].items()
        },
    }

