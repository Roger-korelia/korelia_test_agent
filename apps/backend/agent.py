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
from apps.backend.schema.spec_schema import SpecModel
from apps.backend.schema.topology_schema import TopologyModel
from apps.backend.schema.netlist_schema import NetlistModel
# --- Toolkit (grafo) y herramientas externas
#   Asegúrate de que estos módulos existen en tu repo
from apps.backend.toolkit.toolkit import Toolkit  # tu clase Toolkit (apply_*_json)
from apps.backend.tools.run_tools import (
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
def spec_schema_validator(spec_json: SpecModel, thread_id: str = "default") -> str:
    """Valida y aplica spec.json (DIG). Devuelve {ok, errors[], graph_patch}."""
    tk = _get_graph_toolkit(thread_id)
    try:
        payload = spec_json.model_dump(exclude_none=True)
    except Exception as e:
        return json.dumps({"ok": False, "errors": [f"JSON inválido: {e}"]}, ensure_ascii=False)
    return json.dumps(tk.apply_spec_json(payload), ensure_ascii=False)

@tool("topology_schema_validator")
def topology_schema_validator(topology_json: TopologyModel, thread_id: str = "default") -> str:
    """Valida y aplica topology.json (FTG). Devuelve {ok, errors[], graph_patch}."""
    tk = _get_graph_toolkit(thread_id)
    try:
        payload = topology_json.model_dump(exclude_none=True)
    except Exception as e:
        return json.dumps({"ok": False, "errors": [f"JSON inválido: {e}"]}, ensure_ascii=False)
    result_str = json.dumps(tk.apply_topology_json(payload), ensure_ascii=False)
    return result_str

@tool("graph_apply_netlist_json")
def graph_apply_netlist_json(netlist_json: NetlistModel, allow_autolock: str = "true", thread_id: str = "default") -> str:
    """Aplica netlist.json → CIG y ejecuta validaciones. Devuelve {ok,warnings,errors,violations,applied_patch}."""
    tk = _get_graph_toolkit(thread_id)
    try:
        payload = netlist_json.model_dump(exclude_none=True)
    except Exception as e:
        return json.dumps({"error": f"JSON inválido: {e}"}, ensure_ascii=False)
    try:
        res = tk.apply_netlist_json(payload)  # allow_autolock no-op aquí
        result_str = json.dumps(res, ensure_ascii=False)
        return result_str
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


PROCESS_PROMPT = (
    "Eres un agente EDA graph-first. Trabaja por pasos y NO avances si hay errores/violations bloqueantes.\n\n"
    "Flujo: 1) spec_schema_validator  2) topology_schema_validator  3) graph_apply_netlist_json  4) spice_autorun  5) kicad_*.\n"
    "En cada paso: llama tool, parsea JSON; si hay errores severos corrige y reintenta (≤3); si persisten, retrocede un paso.\n\n"
    "TopologyModel (contrato breve):\n"
    "- 'connections' conecta IDs de 'blocks' o 'ports' (sin jerarquías). Si necesitas un port global, decláralo en 'ports' y conéctalo.\n\n"
    "NetlistModel (contrato breve):\n"
    "- Conexiones SOLO en 'connections' {component_ref,pin_id,net}. Enum de 'class' permitido (no inventes clases).\n"
    "- 'nets' debe contener TODAS las nets usadas y una GROUND si aplica (is_reference_ground=true).\n\n"
    "Construcción SPICE (antes de spice_autorun):\n"
    "- Usa SpiceAutorunInput como CONTRATO de construcción, no para parchear.\n"
    "- Respeta: library_resolution (includes absolutos o modelos inline según 'mode'); control_contract (un solo .control, con líneas mínimas y WRDATA/.print a partir de 'probes' si ownership=agent_injects o auto lo requiere);\n"
    "- source_intent (si hay .tran y red CA: SINE(0 Vrms*√2, f) en la fuente de línea; evita 'AC' en .tran).\n"
    "- probe_contract (i(Rx) con paréntesis, evita v(Vsrc) si allow_vsource_names=false: usa v(n+,n-); todos los nodos de probes deben existir y respetar alias_policy/net_name_map).\n"
    "- device_map/component_hints para materializar transformadores (estrategia, Lp/Ls/K/ratio) y modelos (preferred/fallback).\n"
    "- analyses: emite .op/.tran/.ac/.dc según 'analyses' o 'build_policy.analyses_default'. Añade '.options' desde 'options' o defaults.\n"
    "- Netlist final autocontenido: único '.control ... .endc', termina en '.end' y coherente con 'dialect'.\n\n"
    "Auto-check previo (sin ejecutar):\n"
    "- Existe y es único el bloque .control; '.endc' antes de '.end'.\n"
    "- Probes correctas y resolubles (aliases y nombres de nodo válidos); si se referencia una fuente, resuélvela a v(n+,n-).\n"
    "- Si library_resolution exige inline/absolutas, cúmplelo. Si faltan modelos requeridos, inclúyelos explícitamente.\n"
    "- Si kpi_contract existe, selecciona probes/análisis que permitan evaluar esos KPIs.\n\n"
    "Simulación y reintentos:\n"
    "- Llama 'spice_autorun' con input_text autocontenido y probes ya resueltas. Si falla por vectores inexistentes, control inválido o modelos ausentes, considera incumplido el CONTRATO y RECONSTRUYE (≤3). Si persiste, retrocede a 'graph_apply_netlist_json'.\n\n"
    "Tras cada tool: emite mini-resumen JSON {step, attempt, decision:'retry'|'backtrack'|'proceed', fix_plan?}.\n"
)


def run_single_agent_workflow_stream(task: str):
    """Stream agent workflow events, yielding text chunks and step information."""
    print(f"[AGENT] Function called with task: {task[:100]}...")
    tools = [
        _TOOL_REGISTRY["spec_schema_validator"],
        _TOOL_REGISTRY["topology_schema_validator"],
        _TOOL_REGISTRY["graph_apply_netlist_json"],
        _TOOL_REGISTRY["spice_autorun"],
        _TOOL_REGISTRY["kicad_project_manager"],
        _TOOL_REGISTRY["kicad_cli_exec"],
        _TOOL_REGISTRY["kicad_erc"],
        _TOOL_REGISTRY["kicad_drc"],
        _TOOL_REGISTRY["save_local_file"],
    ]

    agent = create_agent(
        model="gpt-5-mini",
        tools=tools,
        system_prompt=PROCESS_PROMPT,
    )

    # Stream with updates mode to see agent steps
    for chunk in agent.stream(
        {"messages": [{"role": "user", "content": task}]},
        stream_mode="updates"
    ):
        # chunk is a dict with step name as key
        for step, data in chunk.items():
            print(f"step: {step}")
            print(f"content: {data['messages'][-1].content}")
            yield f"[{step}] {data['messages'][-1].content}\n"


def create_agent_graph():
    """Create a LangGraph-compatible agent graph from create_agent."""
    tools = [
        _TOOL_REGISTRY["spec_schema_validator"],
        _TOOL_REGISTRY["topology_schema_validator"],
        _TOOL_REGISTRY["graph_apply_netlist_json"],
        _TOOL_REGISTRY["spice_autorun"],
        _TOOL_REGISTRY["kicad_project_manager"],
        _TOOL_REGISTRY["kicad_cli_exec"],
        _TOOL_REGISTRY["kicad_erc"],
        _TOOL_REGISTRY["kicad_drc"],
        _TOOL_REGISTRY["save_local_file"],
    ]

    # Create agent using create_agent (this is what Agent Chat UI expects)
    agent = create_agent(
        #model="gpt-5-mini",
        model="gpt-4o-mini",
        tools=tools,
        system_prompt=PROCESS_PROMPT,
    )
    
    # Return the agent runnable (create_agent returns a Runnable)
    return agent