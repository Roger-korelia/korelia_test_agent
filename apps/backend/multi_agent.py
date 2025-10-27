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
from langgraph.graph import StateGraph, END
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy


# --- Esquemas ---
from schema.spec_schema import SpecModel
from schema.topology_schema import TopologyModel
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
StepName = Literal["spec", "topology", "netlist", "simulation", "kicad", "documentation"]

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

def _get_graph_toolkit(thread_id: str) -> Toolkit:
    tk = _GRAPH_THREADS.get(thread_id)
    if tk is None:
        tk = Toolkit()
        _GRAPH_THREADS[thread_id] = tk
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
# Tools de grafo/JSON (spec/topology/netlist)
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
            f"Eres ingeniero de requisitos. Devuelve SOLO JSON válido que cumpla el schema de spec.json"
            "INSTRUCCIONES CRÍTICAS:\n"
            "1. Los objetos en arrays (metrics, constraints, standards) DEBEN ser objetos completos, NO strings.\n"
            "2. Ejemplo CORRECTO: metrics debe ser [{id:'m1', name:'efficiency', target:null, priority:'should', acceptance:'...'}]\n"
            "3. Ejemplo INCORRECTO: metrics=['efficiency', 'voltage']\n"
            "4. Extrae TODOS los parámetros del task. Si no hay target, usa target:null.\n"
            "5. Todos los campos requeridos (id, name, etc.) son obligatorios.\n"
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
            "genera un reporte final."
        ),
        tools=[],
    ),
}


# =========================================================
# Helpers de feedback/decisión
# =========================================================

# Esta función convierte la respuesta JSON de una herramienta en una lista de feedback (errores, advertencias, violaciones).
# También marca como OK si no hay errores/advertencias/violaciones.
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

# Esta función determina si se puede avanzar en el flujo basándose en el resultado de una herramienta y el paso actual.
# Para pasos que requieren validación (spec, topology), verifica que el resultado sea válido.
# Para netlist, verifica violaciones y errores.
# Para pasos que usan 'status' (simulación, KiCad, documentación), verifica que el status sea 'completed' o 'failed'.
def _decide_proceed(data: Dict[str, Any], step: StepName) -> Tuple[bool, str]:
    if step in ("spec","topology"):
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


# Esta función procesa e integra un nuevo intento de ejecución de un paso (step) en el workflow.
# Actualiza el estado del intento, el feedback, el historial y determina si es posible avanzar en el flujo.
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

    if not ok and step in ("spec", "topology", "netlist"):
        intent["overall_status"] = "needs_improvement"
    elif all(intent["steps"][k]["status"] == "completed" for k in intent["steps"]):
        intent["overall_status"] = "completed"


# =========================================================
# Orquestador y routing
# =========================================================
MAX_RETRIES: Dict[StepName, int] = {
    "spec": 3, "topology": 3, "netlist": 4, "simulation": 2, "kicad": 2, "documentation": 1
}


# Esta función determina el siguiente paso en el flujo basándose en el paso actual.
def _next_step(step: StepName) -> StepName:
    order = ["spec","topology","netlist","simulation","kicad","documentation"]
    i = order.index(step)
    return order[min(i+1, len(order)-1)]

# Esta función gestiona el flujo de ejecución del workflow.
# Verifica si se puede avanzar en el flujo, reintenta si es necesario y termina si se agotan los reintentos.
def orchestrator_node(state: WorkflowState) -> WorkflowState:
    step = state.get("workflow_step","spec")
    intent = state["current_intent"]
    s = intent["steps"][step]
    
    # Si el flujo ya está completado, no hacer nada más
    if intent["overall_status"] == "completed":
        return state

    # Verificar si el paso actual está completado antes de avanzar
    if state.get("should_proceed", True) and s["status"] == "completed":
        nxt = _next_step(step)
        
        # Si ya estamos en documentación y está completado, terminar
        if step == "documentation" and s["status"] == "completed":
            state["workflow_step"] = "documentation"
            state["should_proceed"] = False  # Terminar el flujo
            intent["overall_status"] = "completed"  # Marcar como completado
            return state
        
        # Verificar que el siguiente paso no está ya completado
        next_step_data = intent["steps"][nxt]
        if next_step_data["status"] == "completed":
            nxt = _next_step(nxt)
        
        state["workflow_step"] = nxt
        state["should_proceed"] = True  # Reset para el nuevo paso
        return state

    # No procede: reintentar si quedan retries
    if not state.get("should_proceed", True):
        retries_left = MAX_RETRIES[step] - s["attempts"]
        if retries_left > 0:
            state["workflow_step"] = step
            state["should_proceed"] = True  # Reset para reintentar
            return state

    # Si no hay intentos, es primera vez o reintento automático
    if s["attempts"] == 0:
        state["should_proceed"] = True  # Primera ejecución
        return state

    # Fallback si se agotaron intentos
    if step in ("netlist","simulation"):
        state["workflow_step"] = "netlist"
        state["should_proceed"] = False
        state["agent_feedback"] = "Simulación fallida repetidamente; ajusta netlist."
        return state

    # Si se agotaron reintentos, ir a documentación y terminar
    intent["overall_status"] = "failed"
    state["workflow_step"] = "documentation"
    state["should_proceed"] = True
    state["agent_feedback"] = f"Se agotaron reintentos en {step}. Generar informe."
    return state

def route_after_orchestrator(state: WorkflowState) -> str:
    step = state.get("workflow_step","spec")
    intent = state["current_intent"]
    
    # Si el workflow está completado, terminar
    if intent["overall_status"] == "completed":
        return "END"
    
    return {
        "spec": "spec_agent",
        "topology": "topology_agent",
        "netlist": "netlist_agent",
        "simulation": "sim_agent",
        "kicad": "kicad_agent",
        "documentation": "doc_agent",
    }.get(step, "doc_agent")


# ====== CONTEXTO SIMPLE PARA SUBAGENTES ======


StepName = Literal["spec","topology","netlist","simulation","kicad","documentation"]

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
        steps = ["spec","topology","netlist","simulation","kicad","documentation"]

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

    # Creamos el prompt de sistema con TODO el contexto incluido
    system_prompt = subagents["spec_agent"].prompt + "\n\n" + ctx + "\n\nTU TAREA: Genera 'spec.json' basándote en el design_task mostrado arriba. Devuelve SOLO JSON sin texto adicional."
    
    agent = create_agent(
        model=llm_base,
        tools=[ _TOOL_REGISTRY["spec_schema_validator"] ],
        system_prompt=system_prompt,
        response_format=ToolStrategy(SpecModel)
    )
    try:
        # El input ahora es explícito y completo
        result = agent.invoke({
            "messages": [{"role": "user", "content": f"TASK: {task}\n\nGenera spec.json válido siguiendo el esquema. Extrae todos los parámetros posibles del task."}]
        })
         # Obtener la respuesta estructurada
        structured_response = result.get("structured_response")
        if structured_response:
            # Convertir el modelo Pydantic a JSON string para la tool
            spec_json = structured_response.model_dump_json()
            # Llamar manualmente a la tool de validación
            validation_result = _TOOL_REGISTRY["spec_schema_validator"].invoke({
                "spec_json": spec_json,
                "thread_id": "default"
            })
            _push_attempt(state, "spec", payload_in=task, tool_output_str=validation_result)
        else:
            # Fallback si no hay structured_response
            output_str = result.get("output", str(result))
            _push_attempt(state, "spec", payload_in=task, tool_output_str=output_str)
    except Exception as e:
        import traceback
        _push_attempt(state, "spec", payload_in=task, tool_output_str=json.dumps({"ok":False,"errors":[str(e)]}))
    return state

def topology_agent_node(state: WorkflowState) -> WorkflowState:
    task = state.get("current_task","")
    state["current_intent"]["steps"]["topology"]["status"] = "in_progress"

    # Verificar que spec esté completado
    spec_step = state["current_intent"]["steps"]["spec"]
    if spec_step["status"] != "completed":
        _push_attempt(state, "topology", payload_in="waiting_for_spec", tool_output_str=json.dumps({"ok":False,"errors":["Spec no completado"]}))
        return state

    ctx = _brief_workflow_state(state, steps=["spec","topology"], max_history_per_step=2, max_chars=3000)
    system_prompt = subagents["topology_agent"].prompt + "\n\n" + ctx + "\n\nTU TAREA: Genera 'topology.json' coherente con el spec mostrado arriba. Devuelve SOLO JSON sin texto adicional."
    
    agent = create_agent(
        model=llm_base,
        tools=[_TOOL_REGISTRY["topology_schema_validator"]],
        system_prompt=system_prompt,
        response_format=ToolStrategy(TopologyModel)
    )
    
    try:
        result = agent.invoke({
            "messages": [{"role": "user", "content": f"TASK: {task}\n\nGenera topology.json válido basándote en el spec y el design_task. Devuelve SOLO JSON."}]
        })
        
        structured_response = result.get("structured_response")
        if structured_response:
            topology_json = structured_response.model_dump_json()
            validation_result = _TOOL_REGISTRY["topology_schema_validator"].invoke({
                "topology_json": topology_json,
                "thread_id": "default"
            })
            
            _push_attempt(state, "topology", payload_in=task, tool_output_str=validation_result)
        else:
            output_str = result.get("output", str(result))
            _push_attempt(state, "topology", payload_in=task, tool_output_str=output_str)
            
    except Exception as e:
        _push_attempt(state, "topology", payload_in=task, tool_output_str=json.dumps({"ok":False,"errors":[str(e)]}))
    
    return state

def netlist_agent_node(state: WorkflowState) -> WorkflowState:
    task = state.get("current_task","")
    state["current_intent"]["steps"]["netlist"]["status"] = "in_progress"

    ctx = _brief_workflow_state(
        state,
        steps=["spec","topology","netlist"],
        max_history_per_step=3,
        max_chars=4000
    )

    system_prompt = subagents["netlist_agent"].prompt + "\n\n" + ctx + "\n\nTU TAREA: Construye y valida 'netlist.json' basándote en spec ytopology. Si hay violations/errors previos, corrígelos. Devuelve SOLO JSON."

    agent = create_agent(
        model=llm_base,
        tools=[_TOOL_REGISTRY["graph_apply_netlist_json"]],
        system_prompt=system_prompt,
        response_format=ToolStrategy(NetlistModel)
    )
    
    try:
        result = agent.invoke({
            "messages": [{"role": "user", "content": f"TASK: {task}\n\nConstruye y valida netlist.json. Si hay errores previos, corrígelos. Devuelve SOLO JSON."}]
        })
        
        structured_response = result.get("structured_response")
        if structured_response:
            netlist_json = structured_response.model_dump_json()
            validation_result = _TOOL_REGISTRY["graph_apply_netlist_json"].invoke({
                "netlist_json": netlist_json,
                "allow_autolock": "true",
                "thread_id": "default"
            })
            _push_attempt(state, "netlist", payload_in="netlist_build", tool_output_str=validation_result)
        else:
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

    system_prompt = subagents["simulation_agent"].prompt + "\n\n" + ctx + "\n\nTU TAREA: Ejecuta la simulación SPICE usando el netlist aprobado. Devuelve SOLO JSON con el formato {status, kpis?, log?}. Si falla, explica la causa en 'log'."

    sim_agent = create_agent(
        model=llm_base,
        tools=[ _TOOL_REGISTRY["spice_autorun"] ],
        system_prompt=system_prompt
    )

    task = state.get("current_task","")
    try:
        res = sim_agent.invoke({
            "messages": [{"role": "user", "content": f"TASK: {task}\n\nEjecuta la simulación SPICE con el netlist aprobado. Devuelve SOLO JSON."}]
        })
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

    system_prompt = subagents["kicad_agent"].prompt + "\n\n" + ctx + "\n\nTU TAREA: Crea el proyecto en KiCad y ejecuta ERC (y DRC si procede). Devuelve SOLO JSON con {status, artifacts?, log?}. Si falta kicad-cli, informa en 'log' y status='failed'."

    kicad_agent = create_agent(
        model=llm_base,
        tools=[
            _TOOL_REGISTRY["kicad_project_manager"],
            _TOOL_REGISTRY["kicad_cli_exec"],
            _TOOL_REGISTRY["kicad_erc"],
            _TOOL_REGISTRY["kicad_drc"],
            _TOOL_REGISTRY["save_local_file"],
        ],
        system_prompt=system_prompt
    )

    task = state.get("current_task","")
    try:
        res = kicad_agent.invoke({
            "messages": [{"role": "user", "content": f"TASK: {task}\n\nCrea el proyecto en KiCad y ejecuta ERC/DRC. Devuelve SOLO JSON."}]
        })
        output_str = res.get("output", str(res))
        _push_attempt(state, step, payload_in="kicad_flow", tool_output_str=output_str)
    except Exception as e:
        _push_attempt(state, step, payload_in="kicad_flow", tool_output_str=json.dumps({"status":"failed","error":str(e)}))
    return state


def doc_agent_node(state: WorkflowState) -> WorkflowState:
    step = "documentation"
    state["current_intent"]["steps"][step]["status"] = "in_progress"
    # Contexto: netlist + simulation + kicad (para ver artefactos previos/errores)
    ctx = _brief_workflow_state(
        state,
        steps=["spec","topology","netlist","simulation","kicad","documentation"],
        max_history_per_step=2,
        max_chars=3800
    )
    system_prompt = subagents["doc_agent"].prompt + "\n\n" + ctx + "\n\nTU TAREA: Genera un informe final del proyecto."
    doc_agent = create_agent(
        model=llm_base,
        tools=[],
        system_prompt=system_prompt
    )
    task = state.get("current_task","")
    try:
        response = doc_agent.invoke({"messages": [{"role": "user", "content": f"TASK: {task}\n\nGenera un informe final del proyecto."}]})

        # response can be an AIMessage, a dict, or FewShotOutput depending on LangChain version/config.
        # Most modern LC returns a dict with 'output', or an AIMessage with .content
        # Let's try to be robust:

        # Extrae solo el contenido del mensaje AI y lo muestra en un formato claro.
        if isinstance(response, AIMessage):
            output_str = response.content
        elif isinstance(response, dict):
            # LangChain puede devolver 'output' o 'content' según la versión/configuración
            output_str = response.get("output") or response.get("content") or str(response)
        else:
            output_str = getattr(response, "content", str(response))
        print(f"DocAgent AIMessage content:\n{output_str}")

        _push_attempt(state, step, payload_in="doc_flow", tool_output_str=output_str)
    except Exception as e:
        _push_attempt(state, step, payload_in="doc_flow", tool_output_str=json.dumps({"status":"failed","error":str(e)}))
    return state


# =========================================================
# Construcción del grafo
# =========================================================
def create_workflow_graph():
    g = StateGraph(WorkflowState)
    g.add_node("orchestrator", orchestrator_node)
    g.add_node("spec_agent", spec_agent_node)
    g.add_node("topology_agent", topology_agent_node)
    g.add_node("netlist_agent", netlist_agent_node)
    g.add_node("sim_agent", sim_agent_node)
    g.add_node("kicad_agent", kicad_agent_node)
    g.add_node("doc_agent", doc_agent_node)

    g.set_entry_point("orchestrator")
    g.add_conditional_edges("orchestrator", route_after_orchestrator, {
        "spec_agent": "spec_agent",
        "topology_agent": "topology_agent",
        "netlist_agent": "netlist_agent",
        "sim_agent": "sim_agent",
        "kicad_agent": "kicad_agent",
        "doc_agent": "doc_agent",
        "END": END,  # ← AÑADIR ESTA LÍNEA
    })
    # tras cada nodo vuelve al orquestador (que decide avanzar/reintentar)
    for n in ["spec_agent","topology_agent","netlist_agent","sim_agent","kicad_agent","doc_agent"]:
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

