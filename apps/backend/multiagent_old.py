import os
import json
import re
import sys
import time
import threading
import tempfile
import csv
import base64
import datetime as dt
from pathlib import Path
from typing import Literal, Dict, Any, List, Optional, Annotated, TypedDict
from subprocess import run, PIPE, TimeoutExpired
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from spice_toolkit import SpiceToolkit, run_erc_on_netlist

# Enhanced state with workflow control
class WorkflowState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    current_task: str
    plan: Optional[str]
    component_list: Optional[str]
    netlist_proposal: Optional[str]
    netlist_results: Optional[Dict[str, Any]]
    sim_results: Optional[Dict[str, Any]]
    kicad_results: Optional[Dict[str, Any]]
    doc_results: Optional[str]
    workflow_step: str  # "planning", "netlist", "simulation", "kicad", "documentation", "completed"
    quality_check: Optional[str]
    should_proceed: bool
    decision_history: Optional[List[str]]
    sim_attempts: Optional[int]  # Track simulation retry attempts
    netlist_attempts: Optional[int]  # Track netlist retry attempts


load_dotenv()

# Environment variables setup
os.environ.setdefault("NGSPICE", r"C:\Program Files\Spice64\bin\ngspice.exe")
os.environ.setdefault("KICAD_CLI", r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe")
# =========================
# BINARIES RESOLVERS (NGSPICE / KICAD_CLI)
# =========================
def _resolve_ngspice():
    """Prefiere ngspice_con.exe en Windows; cae a env NGSPICE o PATH."""
    import shutil
    cand = os.getenv("NGSPICE")
    if cand:
        return cand.strip('"')
    for name in ("ngspice_con.exe", "ngspice_con", "ngspice.exe", "ngspice"):
        p = shutil.which(name)
        if p:
            return p
    return None

def _resolve_kicad_cli():
    """Devuelve la ruta al binario de kicad-cli. Prioriza env var KICAD_CLI y si no, busca en PATH."""
    import shutil, platform
    
    # 1. Variable de entorno
    cand = os.getenv("KICAD_CLI")
    if cand:
        cand = cand.strip('"')
        if os.path.exists(cand):
            return cand
    
    # 2. Buscar en PATH
    for cmd in ["kicad-cli", "kicad-cli.exe"]:
        result = shutil.which(cmd)
        if result:
            return result
    
    # 3. Buscar en ubicaciones comunes de Windows (solo si es Windows)
    if platform.system() == "Windows":
        common_paths = [
            r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe",
            r"C:\Program Files\KiCad\7.0\bin\kicad-cli.exe",
            r"C:\Program Files (x86)\KiCad\8.0\bin\kicad-cli.exe",
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                return path
    
    return None

# =========================
# 1) MODEL CONFIGURATION
# =========================
llm_base = ChatOpenAI(model="gpt-4.1-nano", temperature=0.1)
# Helper to read layer counts from toolkit summary stored in state
def _get_layer_counts_from_state(state: Dict[str, Any]) -> tuple[int, int]:
    lp = state.get("layer_progress", {}) or {}
    total = 0
    locked = 0
    try:
        if isinstance(lp, dict):
            total = int(lp.get("total_layers", 0) or 0)
            locked = int(lp.get("locked_layers", 0) or 0)
            if (total == 0 or locked == 0) and isinstance(lp.get("layers"), list):
                layers = lp.get("layers", [])
                total = total or len(layers)
                locked = locked or sum(1 for l in layers if l.get("locked"))
    except Exception:
        total, locked = 0, 0
    return total, locked


# =========================
# 2) STATE DEFINITION (Deep Agents Style - Using TypedDict)
# =========================
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    files: Dict[str, str]  # Virtual file system
    plan: Optional[str]
    current_task: Optional[str]
    subagent_context: Dict[str, Any]


# =========================
# 4) BUILT-IN TOOLS (Deep Agents Style)
# =========================

@tool("write_todos")
def write_todos(plan: str) -> str:
    """Create a detailed plan/todo list for the current task. This helps organize complex work into manageable steps."""
    return f"Plan created successfully. Here's your plan:\n{plan}"

@tool("write_file")
def write_file(filename: str, content: str) -> str:
    """Write content to a file in the virtual file system."""
    # In a real implementation, this would update the state's files dictionary
    return f"File '{filename}' written successfully with {len(content)} characters."

@tool("read_file")
def read_file(filename: str) -> str:
    """Read content from a file in the virtual file system."""
    # In a real implementation, this would read from the state's files dictionary
    return f"Reading file '{filename}': [File content would be retrieved from virtual file system]"

@tool("list_files")
def list_files() -> str:
    """List all files in the virtual file system."""
    return "Files in virtual file system: [File list would be retrieved from state]"

@tool("edit_file")
def edit_file(filename: str, new_content: str) -> str:
    """Edit/update content in an existing file."""
    return f"File '{filename}' updated successfully."

# =========================
# 5) ELECTRONICS TOOLS (Your Existing Tools)
# =========================


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

@tool("generate_spec_markdown")
def generate_spec_markdown(project_name: str, requirements_json: str = "[]", test_results_json: str = "[]") -> str:
    """Genera Markdown de especificación+verificación a partir de JSON de requisitos y resultados."""
    try:
        requirements = json.loads(requirements_json) if requirements_json else []
        tests = json.loads(test_results_json) if test_results_json else []
    except Exception as e:
        return f"ERROR JSON: {e}"

    lines = [f"# Especificación y Verificación — {project_name}", "",
             f"_Fecha:_ {dt.date.today().isoformat()}",
             "\n## Requisitos"]
    for r in requirements:
        must = "(MUST)" if r.get("must_have", True) else "(NICE)"
        rid = r.get("id") or "?"
        rtype = r.get("type") or ""
        text = r.get("text") or ""
        lines.append(f"- [{rid}] {must} {text} — tipo: {rtype}")
    lines.append("\n## Resultados de ensayo")
    for t in tests:
        ok = "✅" if t.get("pass") else "❌"
        name = t.get("name", "test")
        summary = t.get("summary", "")
        data = t.get("data", "")
        lines.append(f"- {ok} {name} — {summary}\n  - datos: {data}")

    return "\n".join(lines)

@tool("document_reasoning")
def document_reasoning(decision: str, reasoning: str, feedback_analysis: str = "", phase: str = "") -> str:
    """Documenta el razonamiento y decisiones del agente para mantener trazabilidad en la metodología reflexiva."""
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    reasoning_entry = f"""
[REASONING LOG - {timestamp}]
PHASE: {phase if phase else "Unknown"}
DECISION: {decision}
REASONING: {reasoning}
FEEDBACK ANALYSIS: {feedback_analysis if feedback_analysis else "No feedback analysis provided"}
---
"""
    return f"Reasoning documented successfully.\n{reasoning_entry}"

# load_initial_netlist tool removed - netlist initial is now passed in instructions



# =========================
# UNIFIED TOOL
# =========================

# --------- ENV helper para PySpice/libngspice ----------
def _augment_env_for_ngspice(env: dict):
    """Añade la carpeta de ngspice al PATH del subproceso (necesario para DLL en Windows)."""
    import os
    exe = _resolve_ngspice()
    if not exe:
        return env
    bindir = os.path.dirname(exe)
    env = dict(env)
    env["PATH"] = bindir + os.pathsep + env.get("PATH", "")
    return env

# --------- Autoparchado de netlists SPICE ----------

def _ensure_end(code: str) -> str:
    return code if re.search(r"(?im)^\s*\.end\s*$", code) else (code.rstrip() + "\n.end\n")

def _has_control(code: str) -> bool:
    return bool(re.search(r"(?is)^\s*\.control\b.*?\.endc\b", code))

def _has_any_analysis(code: str) -> bool:
    return bool(re.search(r"(?im)^\s*\.(tran|ac|dc|op)\b", code))

def _fix_tran_lines(code: str) -> str:
    """Asegura .tran con TSTEP>0. Si solo hay TSTOP → TSTEP=TSTOP/1000."""
    def repl(m):
        line = m.group(0)
        args = m.group(1).strip()
        args = re.split(r"\s*\*", args)[0].strip()
        toks = re.split(r"\s+", args) if args else []
        nums = []
        for t in toks:
            try:
                nums.append(float(eval(t, {"__builtins__": {}}, {})))
            except Exception:
                nums.append(None)
        
        # .tran TSTOP
        if len(nums) == 1 and nums[0] and nums[0] > 0:
            tstop = nums[0]; tstep = max(tstop/1000.0, 1e-12)
            return f".tran {tstep:g} {tstop:g}"
        
        # .tran TSTEP TSTOP ...
        if len(nums) >= 2 and nums[1] and nums[1] > 0:
            tstep = nums[0] if nums[0] and nums[0] > 0 else max(nums[1]/1000.0, 1e-12)
            tail = " ".join(toks[2:]) if len(toks) > 2 else ""
            tail = (" " + tail) if tail else ""
            return f".tran {tstep:g} {nums[1]:g}{tail}"
        
        # CORRECCIÓN ESPECÍFICA: .tran 0 TSTOP TSTEP es inválido
        if len(nums) >= 2 and nums[0] == 0 and nums[1] > 0:
            tstop = nums[1]
            tstep = nums[2] if len(nums) > 2 and nums[2] and nums[2] > 0 else max(tstop/1000.0, 1e-12)
            return f".tran {tstep:g} {tstop:g}"
        
        return line
    return re.sub(r"(?im)^\s*\.tran\b(.*)$", repl, code)

def _inject_default_tran_if_missing(code: str) -> str:
    if _has_any_analysis(code):
        return code
    return code.rstrip() + "\n.tran 1u 1m\n"

def _autopatch_netlist_min(code: str) -> str:
    """Sanea netlist para batch: unidades, switch SW, DC en .tran, .end, .tran válido."""
    c = code
    c = _sanitize_units(c)
    c = _fix_switch_models(c)
    c = _fix_waveform_parentheses(c)
    c = _force_dc_for_tran(c)
    c = _ensure_end(c)
    c = _fix_tran_lines(c)
    c = _inject_default_tran_if_missing(c)
    return c

def _inject_wrdata_control(code: str, wr_lines: list[str]) -> str:
    """Inserta .control con run + wrdata (o añade wrdata antes de .endc si ya hay control)."""
    if _has_control(code):
        return re.sub(r"(?is)\.endc", "\n" + "\n".join(wr_lines) + "\n.endc", code)
    code_wo_end = re.sub(r"(?im)^\s*\.end\s*$", "", code).rstrip()
    return code_wo_end + "\n.control\nset noaskquit\nrun\n" + "\n".join(wr_lines) + "\n.endc\n.end\n"

# --------- Heurísticas para modo auto ----------
def _guess_is_python(snippet: str) -> bool:
    s = snippet.strip()
    if s.startswith("#!") or s.startswith("import ") or s.startswith("from "):
        return True
    return any(tok in s for tok in ("PySpice", "pyngspice", "NgSpiceShared", "def run("))

def _guess_is_file_path(s: str) -> bool:
    return os.path.exists(s) and os.path.isfile(s)

def _sanitize_units(code: str) -> str:
    """
    Normaliza unidades para ngspice:
    - 'µ' -> 'u'
    - 100uF -> 100u, 10mH -> 10m, '8 ohm'/'8Ω' -> '8'
    - Evita sufijos de unidad (F, H, V, A, Ω) tras un número con prefijo SI.
    """
    c = code.replace("µ", "u").replace("μ", "u")  # micro
    # 100uF / 47UF -> 100u / 47u
    c = re.sub(r'(?i)\b([+-]?\d*\.?\d+(?:e[+-]?\d+)?)[ \t]*uF\b', r'\1u', c)
    # 10mH / 100MH -> 10m / 100m
    c = re.sub(r'(?i)\b([+-]?\d*\.?\d+(?:e[+-]?\d+)?)[ \t]*mH\b', r'\1m', c)
    # Quita unidades textuales comunes tras valor con prefijo SI o número
    c = re.sub(r'(?i)\b([+-]?\d*\.?\d+(?:e[+-]?\d+)?[munpfkgt]?)\s*(ohms?|Ω|volt(s)?|amp(s)?|[FfHhVvAa])\b', r'\1', c)
    return c

def _force_dc_for_tran(code: str) -> str:
    """
    Si hay .tran, convierte fuentes 'AC <val>' a 'DC <val>' para evitar:
    'v1: has no value, DC 0 assumed'.
    """
    if not re.search(r'(?im)^\s*\.tran\b', code):
        return code
    # En líneas de fuentes de tensión (Vxxx ...), AC -> DC conservando valor
    def repl(line: str) -> str:
        return re.sub(r'(?i)\bAC\b', 'DC', line)
    lines = []
    for ln in code.splitlines():
        if re.match(r'(?im)^\s*V\w+\s', ln) and re.search(r'(?i)\bAC\b', ln):
            lines.append(repl(ln))
        else:
            lines.append(ln)
    return "\n".join(lines)

def _fix_switch_models(code: str) -> str:
    """
    - Cambia '.model NAME VSW...' o 'VSWITCH' -> '.model NAME SW(...)'
    - Si hay instancias Sxxx sin modelo, añade ' SDEF'
    - Si hay algún Sxxx y no existe '.model ... SW', inserta modelo por defecto:
      .model SDEF SW(Ron=0.01 Roff=1e9 Vt=5 Vh=0)
    """
    c = re.sub(r'(?im)^\s*\.model\s+(\w+)\s+VS?W(?:ITCH)?\b', r'.model \1 SW', code)
    # Detecta instancias Sxxx
    s_lines = re.findall(r'(?im)^\s*S\w+\s+.*$', c)
    if s_lines:
        # Asegura que cada Sxxx tenga modelo (6º token)
        def ensure_model(m):
            line = m.group(0)
            toks = line.split()
            if len(toks) < 6:  # Sname n+ n- nc+ nc-
                return line + " SDEF"
            return line
        c = re.sub(r'(?im)^\s*S\w+\s+.*$', ensure_model, c)

        # Si no hay ningún modelo SW, insertar uno
        has_sw_model = bool(re.search(r'(?im)^\s*\.model\s+\w+\s+SW\b', c))
        if not has_sw_model:
            c_wo_end = re.sub(r'(?im)^\s*\.end\s*$', '', c)
            c = (c_wo_end.rstrip() +
                 "\n* default switch model for Sxxx\n.model SDEF SW(Ron=0.01 Roff=1e9 Vt=5 Vh=0)\n.end\n")
    return c

# --------- Waveform normalization ----------
def _fix_waveform_parentheses(code: str) -> str:
    """
    Asegura paréntesis en especificaciones de formas de onda para fuentes independientes:
    V/I ... SIN 0 311 50 -> SIN(0 311 50)
    V/I ... PULSE 0 5 1u 10n 10n 100u 200u -> PULSE(0 5 1u 10n 10n 100u 200u)
    Solo aplica cuando el token de forma de onda no va seguido de '(' ya.
    """
    def fix_line(ln: str) -> str:
        # Solo líneas de V/I
        if not re.match(r"(?im)^\s*[VI]\\w+\s+", ln):
            return ln
        # Reemplazar SIN sin '('
        ln2 = re.sub(r"(?i)\b(SIN)\s+(?!\()([^\n]*)", lambda m: f"{m.group(1).upper()}(" + m.group(2).strip() + ")", ln)
        # Reemplazar PULSE sin '('
        ln2 = re.sub(r"(?i)\b(PULSE)\s+(?!\()([^\n]*)", lambda m: f"{m.group(1).upper()}(" + m.group(2).strip() + ")", ln2)
        return ln2
    return "\n".join(fix_line(l) for l in code.splitlines())

# --------- Simulation log classifier ----------
def _classify_ngspice_failure(log_tail: str, netlist_text: str) -> dict:
    """
    Clasifica el fallo de ngspice entre problema de netlist o del simulador/wrapper.
    Devuelve dict: {scope: 'netlist'|'simulator'|'unknown', reason, suggestions: [..]}
    """
    lt = (log_tail or "").lower()
    scope = "unknown"
    reason = ""
    suggestions: list[str] = []

    # 1) Modelo no definido -> a menudo netlist (A-Device mal usado o falta .model)
    if "unable to find definition of model" in lt or "no such model" in lt or "mif-error" in lt:
        # Revisar si hay una fuente Axxx con SIN
        if re.search(r"(?im)^\s*A\w+\s+\S+\s+\S+\s+SIN\b", netlist_text):
            scope = "netlist"
            reason = "Fuente arbitraria Axxx con SIN: se espera modelo; debía ser fuente de tensión Vxxx."
            # Intentar construir sugerencia basándonos en la primera coincidencia
            m = re.search(r"(?im)^(\s*)A\w+\s+(\S+)\s+(\S+)\s+SIN\s+([^\n]*)", netlist_text)
            if m:
                indent, nplus, nminus, spec = m.groups()
                spec = spec.strip()
                spec_paren = spec if spec.startswith("(") else f"({spec})"
                suggestions.append(f"Cambiar prefijo a 'V' y usar SIN{spec_paren}: V1 {nplus} {nminus} SIN{spec_paren}")
            else:
                suggestions.append("Renombra la fuente 'A...' a 'V...' y usa formato SIN(VOFF VAMP FREQ ...)")
        else:
            scope = "netlist"
            reason = "Modelo no definido en el netlist (faltan .model/.include o tipo de dispositivo incorrecto)."
            suggestions.append("Añade/ajusta la tarjeta .model adecuada o corrige el tipo de dispositivo.")

    # 2) Errores de sintaxis de forma de onda comunes sin paréntesis -> simulador (autoparche)
    elif re.search(r"(?i)error.*sin", lt) and not re.search(r"\(", netlist_text):
        scope = "simulator"
        reason = "Especificación SIN sin paréntesis; el wrapper puede normalizarlo."
        suggestions.append("Normalizar a SIN(VOFF VAMP FREQ ...); reintentar simulación.")

    # 3) Matriz singular / nodos flotantes -> netlist
    elif "singular matrix" in lt or "node .* is floating" in lt:
        scope = "netlist"
        reason = "Topología inválida (nodo flotante o lazo ideal)."
        suggestions.append("Añade resistencias parásitas pequeñas o conecta nodos a 0.")

    # 4) Por defecto: desconocido
    else:
        scope = "unknown"
        reason = "No se pudo clasificar automáticamente el error."

    return {"scope": scope, "reason": reason, "suggestions": suggestions}

def _analyze_spice_syntax_errors(netlist_text: str) -> dict:
    """
    Analiza el netlist SPICE para detectar errores de sintaxis comunes.
    Devuelve dict con errores encontrados y sugerencias de corrección.
    """
    errors = []
    warnings = []
    suggestions = []
    
    lines = netlist_text.splitlines()
    
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith('*') or line.startswith('.'):
            continue
            
        # 1) Diodos sin modelo: Dname anode cathode [model]
        if re.match(r'^\s*D\w+\s+\S+\s+\S+\s*$', line):
            # Diodo sin modelo - verificar si hay .model definido
            has_diode_model = any('.model' in l and 'D(' in l for l in lines)
            if not has_diode_model:
                errors.append({
                    "line": i,
                    "type": "missing_diode_model",
                    "message": f"Línea {i}: Diodo sin modelo definido",
                    "suggestion": "Añadir .model para diodos o especificar modelo en el componente"
                })
        
        # 2) BJT con sintaxis incorrecta: model=param
        if re.search(r'model=\w+', line):
            errors.append({
                "line": i,
                "type": "invalid_bjt_syntax",
                "message": f"Línea {i}: Sintaxis BJT incorrecta (model= no válido)",
                "suggestion": "Usar formato: Qname C B E [S] modelname (sin model=)"
            })
        
        # 3) Fuente con prefijo U (no válido)
        if re.match(r'^\s*U\w+', line):
            errors.append({
                "line": i,
                "type": "invalid_source_prefix",
                "message": f"Línea {i}: Prefijo 'U' no válido para fuentes",
                "suggestion": "Usar V para fuente de tensión o I para fuente de corriente"
            })
        
        # 4) Parámetros undefined
        if "undefined parameter" in line.lower():
            errors.append({
                "line": i,
                "type": "undefined_parameter",
                "message": f"Línea {i}: Parámetro no definido",
                "suggestion": "Revisar sintaxis de parámetros del componente"
            })
    
    # 5) Verificar análisis ausente
    has_analysis = any(re.match(r'^\s*\.(op|tran|ac|dc)', line) for line in lines)
    if not has_analysis:
        warnings.append({
            "type": "missing_analysis",
            "message": "No se encontró análisis (.op, .tran, .ac, .dc)",
            "suggestion": "Añadir análisis apropiado (ej: .tran 1u 1m)"
        })
    
    # 6) Verificar .end
    has_end = any(re.match(r'^\s*\.end\s*$', line) for line in lines)
    if not has_end:
        warnings.append({
            "type": "missing_end",
            "message": "Falta .end al final del netlist",
            "suggestion": "Añadir .end al final del archivo"
        })
    
    return {
        "errors": errors,
        "warnings": warnings,
        "has_critical_errors": len(errors) > 0,
        "suggestions": suggestions
    }

# === Spice Toolkit tools ===

_TOOLKIT_SESSIONS = {}  # {thread_id: SpiceToolkit}

def _get_toolkit(thread_id: str) -> SpiceToolkit:
    toolkit = _TOOLKIT_SESSIONS.get(thread_id)
    if toolkit is None:
        toolkit = SpiceToolkit(ground="0")
        _TOOLKIT_SESSIONS[thread_id] = toolkit
    return toolkit

def _reset_toolkit(thread_id: str) -> None:
    """Reset toolkit session - use when starting fresh netlist build."""
    if thread_id in _TOOLKIT_SESSIONS:
        del _TOOLKIT_SESSIONS[thread_id]


@tool("graph_emit_spice")
def graph_emit_spice(title: str = "Layered Netlist", thread_id: str = "default") -> str:
    """Emit the current spice toolkit as a SPICE netlist."""
    toolkit = _get_toolkit(thread_id)
    return toolkit.emit_spice(title)

@tool("graph_assert_invariants")
def graph_assert_invariants(require_pass: str = "true", thread_id: str = "default") -> str:
    """Assert that the current spice toolkit meets all topological invariants."""
    toolkit = _get_toolkit(thread_id)
    res = toolkit.validate_current_layer(require_pass.lower() == "true")
    return json.dumps(res, ensure_ascii=False)

# spice_graph_validate tool removed - validation is now integrated into graph_* tools

@tool("graph_validate_construction")
def graph_validate_construction(thread_id: str = "default") -> str:
    """Valida el estado actual considerando que es construcción en progreso."""
    toolkit = _get_toolkit(thread_id)
    
    try:
        result = toolkit.validate_current_layer(require_pass=False, construction_phase="in_progress")
        
        # Create structured feedback for agent reflection
        feedback_info = {
            "action": "construction_validation",
            "validation_passed": result.get("pass", False),
            "warnings": result.get("warnings", []),
            "errors": result.get("errors", []),
            "suggestion": ""
        }
        
        if result.get("pass"):
            warnings = result.get("warnings", [])
            if warnings:
                feedback_info["suggestion"] = "Advertencias normales durante construcción - continuar añadiendo componentes"
                return f"✅ Construcción en progreso - Sin errores críticos\n⚠️ Advertencias (normales durante construcción):\n" + "\n".join([f"- {w}" for w in warnings[:3]]) + f"\n\nFEEDBACK: {json.dumps(feedback_info, ensure_ascii=False)}"
            else:
                feedback_info["suggestion"] = "Construcción correcta - continuar con componentes"
                return f"✅ Construcción en progreso - Todo correcto\n\nFEEDBACK: {json.dumps(feedback_info, ensure_ascii=False)}"
        else:
            errors = result.get("errors", [])
            feedback_info["suggestion"] = "Errores críticos requieren corrección inmediata"
            return f"❌ Errores críticos que requieren corrección:\n" + "\n".join([f"- {e}" for e in errors[:3]]) + f"\n\nFEEDBACK: {json.dumps(feedback_info, ensure_ascii=False)}"
    except Exception as e:
        feedback_info = {
            "action": "construction_validation_error",
            "error": str(e),
            "suggestion": "Error en validación - revisar estado del toolkit"
        }
        return f"❌ Error en validación: {str(e)}\n\nFEEDBACK: {json.dumps(feedback_info, ensure_ascii=False)}"

@tool("graph_validate_final")
def graph_validate_final(thread_id: str = "default") -> str:
    """Valida el diseño completo con todas las reglas estrictas."""
    toolkit = _get_toolkit(thread_id)
    
    try:
        result = toolkit.validate_current_layer(require_pass=True, construction_phase="final")
        return "✅ Diseño final validado correctamente"
    except Exception as e:
        return f"❌ Diseño final tiene errores: {str(e)}"


@tool("graph_validate_layer_complete")
def graph_validate_layer_complete(thread_id: str = "default") -> str:
    """Valida la capa actual considerando que está completa."""
    toolkit = _get_toolkit(thread_id)
    
    try:
        result = toolkit.validate_current_layer(require_pass=False, construction_phase="layer_complete")
        
        if result.get("pass"):
            return "✅ Capa completada correctamente"
        else:
            errors = result.get("errors", [])
            warnings = [e for e in errors if e.startswith("ADVERTENCIA:")]
            critical_errors = [e for e in errors if not e.startswith("ADVERTENCIA:")]
            
            response = ""
            if critical_errors:
                response += f"❌ Errores críticos:\n" + "\n".join([f"- {e}" for e in critical_errors[:3]])
            if warnings:
                response += f"\n⚠️ Advertencias:\n" + "\n".join([f"- {w}" for w in warnings[:3]])
            
            return response
    except Exception as e:
        return f"❌ Error en validación: {str(e)}"

@tool("graph_apply_netlist_json")
def graph_apply_netlist_json(netlist_json: str, allow_autolock: str = "true", thread_id: str = "default") -> str:
    """Aplica una netlist propuesta en JSON al builder por capas del toolkit.

    - netlist_json: especificación JSON de la netlist (layers/components)
    - allow_autolock: 'true'|'false' para bloquear capas automáticamente según la política
    Devuelve resumen y validación (JSON).
    """
    toolkit = _get_toolkit(thread_id)
    try:
        spec = json.loads(netlist_json)
    except Exception as e:
        return json.dumps({"error": f"JSON inválido: {e}"}, ensure_ascii=False)
    try:
        result = toolkit.apply_netlist_json(spec, allow_autolock=str(allow_autolock).lower() == "true")
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

@tool("graph_export_netlist_json")
def graph_export_netlist_json(thread_id: str = "default") -> str:
    """Exporta el estado actual del builder por capas a JSON."""
    toolkit = _get_toolkit(thread_id)
    try:
        data = toolkit.export_netlist_json()
        return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

@tool("graph_validate_design")
def graph_validate_design(construction_phase: str = "layer_complete", require_pass: str = "false", thread_id: str = "default") -> str:
    """Valida el diseño actual con validación contextual ('in_progress'|'layer_complete'|'final')."""
    toolkit = _get_toolkit(thread_id)
    try:
        res = toolkit.validate_design(construction_phase=construction_phase, require_pass=require_pass.lower() == "true")
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

@tool("spice_analyze_syntax")
def spice_analyze_syntax(netlist_text: str) -> str:
    """
    Analiza un netlist SPICE para detectar errores de sintaxis comunes.
    Devuelve JSON con errores, warnings y sugerencias de corrección.
    """
    try:
        analysis = _analyze_spice_syntax_errors(netlist_text)
        return json.dumps(analysis, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Análisis falló: {str(e)}"}, ensure_ascii=False)

@tool("spice_autorun")
def spice_autorun(input_text: str,
                  mode: str = "auto",
                  probes_json: str = '["v(VOUT)"]',
                  node_expr: str = "v(VOUT)",
                  from_fraction: str = "0.5",
                  timeout_s: str = "120") -> str:
    """
    Una única tool para:
    - Ejecutar código Python (PySpice/pyngspice) que recibes como string (modo 'python')
    - Ejecutar netlist SPICE (texto o ruta) en batch con ngspice_con, autoparcheando .tran/.control/.end (modo 'netlist')
    - 'auto': detecta por heurística

    Devuelve JSON con:
      - method: 'python' | 'ngspice_wrdata'
      - paths (workdir, netlist_path, log_path, script_path)
      - probes[expr,csv,metrics{avg,rms,p2p}]
      - measures (si hay .meas en el log)
      - result (si run() devolvió dict en python)
      - stdout_tail / stderr_tail
    """

    # Parse inputs
    try:
        probes = json.loads(probes_json)
        if not isinstance(probes, list) or not probes:
            probes = [node_expr]
    except Exception:
        probes = [node_expr]
    try:
        frac = float(from_fraction);  assert 0.0 <= frac < 1.0
    except Exception:
        frac = 0.5

    # --- MODE DECISION ---
    chosen = mode.lower().strip()
    if chosen not in ("auto", "python", "netlist"):
        chosen = "auto"
    if chosen == "auto":
        if _guess_is_file_path(input_text):
            chosen = "netlist"
        elif _guess_is_python(input_text):
            chosen = "python"
        else:
            chosen = "netlist"  # por defecto, tratamos como netlist SPICE

    # --- PYTHON (PySpice/pyngspice) ---
    if chosen == "python":
        workdir = tempfile.mkdtemp(prefix="pyng_")
        script_path = os.path.join(workdir, "snippet.py")
        wrapper = r"""
import json, sys, traceback
if "run" in globals() and callable(globals()["run"]):
    try:
        _res = globals()["run"]()
        try:
            print("RESULT_JSON:" + json.dumps(_res, ensure_ascii=False, separators=(",",":")))
        except Exception as _ejson:
            print("RESULT_ERROR: JSON serialization failed:", repr(_ejson))
    except Exception as _erun:
        print("RESULT_ERROR: run() raised:", repr(_erun))
        traceback.print_exc()
"""
        code = (input_text or "").rstrip() + "\n" + wrapper
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        env = _augment_env_for_ngspice(os.environ.copy())
        try:
            r = run([sys.executable, "-u", script_path], stdout=PIPE, stderr=PIPE, text=True, env=env, timeout=int(timeout_s))
            stdout, stderr = r.stdout or "", r.stderr or ""
        except TimeoutExpired:
            return json.dumps({"error": f"Timeout after {timeout_s}s", "workdir": workdir, "script_path": script_path}, ensure_ascii=False)

        result_obj = None
        m = re.search(r"^RESULT_JSON:(\{.*\})\s*$", stdout, flags=re.M|re.S)
        if m:
            try: result_obj = json.loads(m.group(1))
            except Exception: result_obj = None

        return json.dumps({
            "method": "python",
            "returncode": r.returncode,
            "workdir": workdir,
            "script_path": script_path,
            "stdout_tail": stdout[-10000:],
            "stderr_tail": stderr[-10000:],
            "result": result_obj
        }, ensure_ascii=False)

    # --- NETLIST (texto o archivo) ---
    # Resolve ngspice
    cmd_ngspice = _resolve_ngspice()
    if not cmd_ngspice:
        return json.dumps({"error": "ngspice no encontrado (define NGSPICE o añade a PATH)"}, ensure_ascii=False)

    # Build workdir & paths
    workdir = tempfile.mkdtemp(prefix="spice_")
    netlist_path = os.path.join(workdir, "circuit.sp")
    log_path = os.path.join(workdir, "ngspice.log")

    # Get netlist text: if 'input_text' is a file path, read it; else assume it's netlist code
    if _guess_is_file_path(input_text):
        with open(input_text, "r", encoding="utf-8", errors="ignore") as f:
            net_txt = f.read()
    else:
        net_txt = input_text

    # Sanear .tran/.end (no añadimos control aquí; lo insertamos con WRDATA)
    base = _autopatch_netlist_min(net_txt)

    # Prepare WRDATA exports for probes
    wr_lines, csv_paths = [], []
    for expr in probes:
        safe = re.sub(r"[^A-Za-z0-9_]+", "_", expr).strip("_").lower() or "sig"
        csv_path = os.path.join(workdir, f"{safe}.csv")
        csv_path_sp = csv_path.replace("\\", "/")  # ngspice tolera mejor slashes
        wr_lines.append(f'wrdata "{csv_path_sp}" {expr}')
        csv_paths.append((expr, csv_path))

    code = _inject_wrdata_control(base, wr_lines)

    # Write patched netlist
    with open(netlist_path, "w", encoding="utf-8") as f:
        f.write(code)

    # Run ngspice in batch, logging to file
    r = run([cmd_ngspice, "-b", "-o", log_path, netlist_path], stdout=PIPE, stderr=PIPE, text=True)
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as lf:
            log_txt = lf.read()
    except Exception:
        log_txt = (r.stdout or "") + "\n" + (r.stderr or "")

    # Parse .meas lines (si las hubiera)
    FLOAT_RE = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
    meas_pairs = re.findall(r"(?mi)^\s*([A-Za-z_]\w*)\s*=\s*({})\s*$".format(FLOAT_RE), log_txt)
    measures = {k: float(v) for k, v in meas_pairs}

    # Read CSVs and compute metrics
    def _metrics_from_csv(path):
        xs, ys = [], []
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                # WRDATA suele separar por TAB; usamos split() genérico para tolerar espacios
                for line in f:
                    parts = line.strip().split()
                    if len(parts) < 2: 
                        continue
                    try:
                        xs.append(float(parts[0])); ys.append(float(parts[1]))
                    except Exception:
                        continue
        except Exception:
            return None
        if not ys:
            return None
        n0 = int(len(ys) * frac)
        yw = ys[n0:] if n0 > 0 else ys
        # avg/rms/p2p sin numpy
        n = len(yw)
        avg = sum(yw)/n
        rms = (sum(v*v for v in yw)/n) ** 0.5
        p2p = (max(yw) - min(yw)) if yw else 0.0
        return {"avg": float(avg), "rms": float(rms), "p2p": float(p2p), "samples": len(ys), "window_samples": len(yw)}

    probes_out = []
    for expr, path in csv_paths:
        probes_out.append({"expr": expr, "csv": path, "metrics": _metrics_from_csv(path)})

    return json.dumps({
        "method": "ngspice_wrdata",
        "returncode": r.returncode,
        "workdir": workdir,
        "netlist_path": netlist_path,
        "log_path": log_path,
        "probes": probes_out,
        "measures": measures,
        "log_tail": log_txt[-10000:]
    }, ensure_ascii=False)

@tool("kicad_cli_exec")
def kicad_cli_exec(args_json: str) -> str:
    """Ejecuta kicad-cli con una lista de argumentos en JSON. Resuelve binario via KICAD_CLI o PATH."""

    cmd_kicad = _resolve_kicad_cli()
    if not cmd_kicad:
        return json.dumps({"error": "kicad-cli no encontrado (define KICAD_CLI o añade a PATH)"}, ensure_ascii=False)

    try:
        args = json.loads(args_json)
        if not isinstance(args, list):
            return json.dumps({"error": "args_json debe ser una lista JSON"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"JSON inválido: {e}"}, ensure_ascii=False)

    res = run([cmd_kicad] + args, stdout=PIPE, stderr=PIPE, text=True)
    return json.dumps({
        "returncode": res.returncode,
        "stdout": (res.stdout or "")[-10000:],
        "stderr": (res.stderr or "")[-10000:],
        "cmd": [cmd_kicad] + args
    }, ensure_ascii=False)

@tool("kicad_project_manager")
def kicad_project_manager(action: str, project_name: str = "Switched_PSU_24V_3A", content: str = "") -> str:
    """
    Manages KiCad project files in a consistent directory structure.
    
    Actions:
    - "create_project": Creates a new KiCad project structure
    - "save_schematic": Saves schematic content to .kicad_sch file
    - "save_board": Saves board content to .kicad_pcb file
    - "get_project_path": Returns the absolute path to the project file
    - "get_board_path": Returns the absolute path to the board file
    - "list_files": Lists all project files
    
    All files are saved in a consistent backend directory structure.
    """
    
    # Define the backend directory structure
    backend_dir = Path(__file__).parent  # This will be apps/backend
    project_dir = backend_dir / project_name
    project_file = project_dir / f"{project_name}.kicad_pro"
    schematic_file = project_dir / f"{project_name}.kicad_sch"
    board_file = project_dir / f"{project_name}.kicad_pcb"
    
    try:
        if action == "create_project":
            # Create project directory
            project_dir.mkdir(exist_ok=True)
            
            # Create basic project file if it doesn't exist
            if not project_file.exists():
                with open(project_file, 'w') as f:
                    f.write("(kicad_project\n")
                    f.write(f'  (version 8)\n')
                    f.write(f'  (generator kicad-cli)\n')
                    f.write(f')\n')
            
            return json.dumps({
                "status": "success",
                "action": "create_project",
                "project_path": str(project_file),
                "schematic_path": str(schematic_file),
                "board_path": str(board_file),
                "project_dir": str(project_dir)
            }, ensure_ascii=False)
            
        elif action == "save_schematic":
            project_dir.mkdir(exist_ok=True)
            with open(schematic_file, 'w', encoding='utf-8') as f:
                f.write(content)
            return json.dumps({
                "status": "success",
                "action": "save_schematic",
                "schematic_path": str(schematic_file),
                "content_length": len(content)
            }, ensure_ascii=False)
            
        elif action == "save_board":
            project_dir.mkdir(exist_ok=True)
            with open(board_file, 'w', encoding='utf-8') as f:
                f.write(content)
            return json.dumps({
                "status": "success",
                "action": "save_board", 
                "board_path": str(board_file),
                "content_length": len(content)
            }, ensure_ascii=False)
            
        elif action == "get_project_path":
            return json.dumps({
                "status": "success",
                "project_path": str(project_file),
                "exists": project_file.exists()
            }, ensure_ascii=False)
            
        elif action == "get_board_path":
            return json.dumps({
                "status": "success",
                "board_path": str(board_file),
                "exists": board_file.exists()
            }, ensure_ascii=False)
            
        elif action == "list_files":
            files = []
            if project_dir.exists():
                for file_path in project_dir.iterdir():
                    if file_path.is_file():
                        files.append({
                            "name": file_path.name,
                            "path": str(file_path),
                            "size": file_path.stat().st_size
                        })
            return json.dumps({
                "status": "success",
                "project_dir": str(project_dir),
                "files": files
            }, ensure_ascii=False)
            
        else:
            return json.dumps({
                "status": "error",
                "message": f"Unknown action: {action}. Valid actions: create_project, save_schematic, save_board, get_project_path, get_board_path, list_files"
            }, ensure_ascii=False)
            
    except Exception as e:
        return json.dumps({
            "status": "error",
            "action": action,
            "error": str(e)
        }, ensure_ascii=False)

@tool("kicad_erc")
def kicad_erc(project_path: str, timeout_s: str = "120") -> str:
    """Run KiCad ERC on a .kicad_pro/.kicad_sch project (resuelve kicad-cli por env/PATH)."""

    cmd_kicad = _resolve_kicad_cli()
    if not cmd_kicad:
        return json.dumps({
            "error": "kicad-cli no encontrado. Instala KiCad desde https://www.kicad.org/download/ o define KICAD_CLI.",
            "suggestion": "Descarga e instala KiCad, luego define la variable de entorno KICAD_CLI con la ruta al ejecutable."
        }, ensure_ascii=False)

    # Resolve project path - buscar en ubicaciones genéricas
    resolved_path = project_path
    if not os.path.isabs(project_path):
        # Buscar en directorio actual y subdirectorios
        backend_dir = Path(__file__).parent
        possible_paths = [
            project_path,  # Directorio actual
            backend_dir / project_path,  # Directorio backend
            # Buscar recursivamente en subdirectorios del backend
        ]
        
        # Añadir búsqueda recursiva en subdirectorios
        for subdir in backend_dir.iterdir():
            if subdir.is_dir():
                possible_paths.append(subdir / project_path)
        
        for path in possible_paths:
            if os.path.exists(path):
                resolved_path = os.path.abspath(path)
                break
        else:
            return json.dumps({
                "error": f"Project file not found: {project_path}",
                "searched_paths": [str(p) for p in possible_paths[:5]]  # Solo mostrar los primeros 5
            }, ensure_ascii=False)

    try:
        res = run([cmd_kicad, "sch", "erc", "--project", resolved_path],
                  stdout=PIPE, stderr=PIPE, text=True, timeout=int(timeout_s))
        return json.dumps({
            "returncode": res.returncode,
            "stdout": (res.stdout or "")[-10000:],
            "stderr": (res.stderr or "")[-10000:],
            "project_path": resolved_path,
            "original_path": project_path
        }, ensure_ascii=False)
    except FileNotFoundError:
        return json.dumps({
            "error": f"kicad-cli no se puede ejecutar: {cmd_kicad}",
            "suggestion": "Verifica que KiCad esté instalado correctamente y la ruta sea válida."
        }, ensure_ascii=False)
    except TimeoutExpired:
        return json.dumps({"error": f"ERC timeout > {timeout_s}s"}, ensure_ascii=False)


@tool("kicad_drc")
def kicad_drc(board_path: str, timeout_s: str = "120") -> str:
    """Run KiCad DRC list on a .kicad_pcb board (resuelve kicad-cli por env/PATH)."""

    cmd_kicad = _resolve_kicad_cli()
    if not cmd_kicad:
        return json.dumps({
            "error": "kicad-cli no encontrado. Instala KiCad desde https://www.kicad.org/download/ o define KICAD_CLI.",
            "suggestion": "Descarga e instala KiCad, luego define la variable de entorno KICAD_CLI con la ruta al ejecutable."
        }, ensure_ascii=False)

    # Resolve board path - buscar en ubicaciones genéricas
    resolved_path = board_path
    if not os.path.isabs(board_path):
        # Buscar en directorio actual y subdirectorios
        backend_dir = Path(__file__).parent
        possible_paths = [
            board_path,  # Directorio actual
            backend_dir / board_path,  # Directorio backend
            # Buscar recursivamente en subdirectorios del backend
        ]
        
        # Añadir búsqueda recursiva en subdirectorios
        for subdir in backend_dir.iterdir():
            if subdir.is_dir():
                possible_paths.append(subdir / board_path)
        
        for path in possible_paths:
            if os.path.exists(path):
                resolved_path = os.path.abspath(path)
                break
        else:
            return json.dumps({
                "error": f"Board file not found: {board_path}",
                "searched_paths": [str(p) for p in possible_paths[:5]]  # Solo mostrar los primeros 5
            }, ensure_ascii=False)

    try:
        res = run([cmd_kicad, "pcb", "drclist", "--board", resolved_path],
                  stdout=PIPE, stderr=PIPE, text=True, timeout=int(timeout_s))
        return json.dumps({
            "returncode": res.returncode,
            "stdout": (res.stdout or "")[-10000:],
            "stderr": (res.stderr or "")[-10000:],
            "board_path": resolved_path,
            "original_path": board_path
        }, ensure_ascii=False)
    except FileNotFoundError:
        return json.dumps({
            "error": f"kicad-cli no se puede ejecutar: {cmd_kicad}",
            "suggestion": "Verifica que KiCad esté instalado correctamente y la ruta sea válida."
        }, ensure_ascii=False)
    except TimeoutExpired:
        return json.dumps({"error": f"DRC timeout > {timeout_s}s"}, ensure_ascii=False)

# =========================
# 6) SUB-AGENT DEFINITIONS
# =========================

class SubAgent:
    def __init__(self, name: str, description: str, prompt: str, tools: List[str]):
        self.name = name
        self.description = description
        self.prompt = prompt
        self.tools = tools

subagents = {
    "netlist_agent": SubAgent(
        name="netlist-agent",
        description="Genera una netlist propuesta en JSON, la aplica al builder y itera con feedback hasta validarla, manteniendo trazabilidad reflexiva.",
        prompt=(
            "Eres NetlistAgent. Trabaja de forma REFLEXIVA (propuesta → plan → implementación → reflexión → iteración) usando un flujo basado en JSON.\n\n"
            "FLUJO JSON OBLIGATORIO:\n"
            "1) Propón arquitectura y nodos clave. Documenta con document_reasoning().\n"
            "2) Construye un netlist JSON con esquema: {title,layers[{name,notes,locked,components[{ref,type,pins[],params{}}]}]} o forma plana {components:[...]}.\n"
            "3) Llama a graph_apply_netlist_json con el JSON. Analiza validation.errors/warnings.\n"
            "4) Ajusta el JSON para corregir errores críticos (pines, fuentes paralelas, ground, ESR). Documenta el porqué.\n"
            "5) Itera hasta que la validación pase razonablemente.\n"
            "6) Emite SPICE con graph_emit_spice.\n\n"
            "REGLAS: No pegues SPICE directo, usa JSON y herramientas. Asegura nodo '0', evita lazos ideales añadiendo ESR/Rser, usa nombres de nodos descriptivos, y registra decisiones con document_reasoning."
        ),
        tools=['graph_apply_netlist_json', 'graph_export_netlist_json', 'graph_validate_design', 'graph_emit_spice', 'document_reasoning', 'save_local_file']
    ),

    "simulation_agent": SubAgent(
        name="simulation-agent", 
        description="Ejecuta simulaciones SPICE y analiza resultados.",
        prompt=(
            "Eres SimulationAgent. Tu única función es ejecutar simulaciones SPICE y analizar resultados.\n"
            "\n"
            "PROCESO OBLIGATORIO:\n"
            "1. Recibir netlist del netlist_agent\n"
            "2. SIEMPRE usar spice_analyze_syntax ANTES de simular para detectar errores\n"
            "3. Si hay errores críticos, corregir el netlist y reintentar\n"
            "4. Ejecutar spice_autorun con el netlist corregido\n"
            "5. Analizar resultados y extraer KPIs\n"
            "6. Reportar métricas con unidades\n"
            "\n"
            "REGLAS SPICE CRÍTICAS:\n"
            "- Diodos: Dname anode cathode [model] (si no hay modelo, añadir .model)\n"
            "- BJT: Qname C B E [S] modelname (NUNCA usar model=)\n"
            "- Fuentes: Vname/Iname node1 node2 [DC/AC/PULSE/SIN] value (NUNCA usar prefijo U)\n"
            "- Análisis: Siempre incluir .op/.tran/.ac y .end\n"
            "- Valores: usar 10u, 1k, 1m (sin F, H, V, A)\n"
            "- Paréntesis: SIN(VOFF VAMP FREQ) no SIN VOFF VAMP FREQ\n"
            "\n"
            "MANEJO DE ERRORES COMUNES:\n"
            "- 'unable to find definition of model': añadir .model o corregir tipo de componente\n"
            "- 'undefined parameter': revisar sintaxis de parámetros\n"
            "- 'singular matrix': añadir resistencias parásitas\n"
            "- 'floating nodes': conectar nodos a GND\n"
            "- 'no such function as i': verificar sintaxis de sondas\n"
            "\n"
            "CONFIGURACIÓN DE SONDAS:\n"
            "- Siempre incluir al menos 'v(VOUT)' en probes_json\n"
            "- Si hay resistor de carga, añadir '@Rload[i]' o 'i(Rload)'\n"
            "- Si hay inductores, añadir 'i(L1)' o 'i(Lp1)'\n"
            "- Usar mode='netlist' o mode='auto'\n"
            "- NUNCA usar nombres de medidas .meas como sondas\n"
            "\n"
            "ANÁLISIS DE RESULTADOS:\n"
            "- Extraer métricas: avg, rms, p2p de las sondas\n"
            "- Verificar medidas .meas si están disponibles\n"
            "- Reportar KPIs con unidades (V, A, %, etc.)\n"
            "- Comparar con criterios de aceptación\n"
            "\n"
            "MANEJO DE ERRORES:\n"
            "- Si spice_autorun falla, leer log_tail\n"
            "- Identificar causa específica del error\n"
            "- Corregir UNA vez y re-ejecutar\n"
            "- Si falla dos veces, reportar error y detener\n"
        ),
        tools=["spice_autorun", "spice_analyze_syntax", "save_local_file"]
    ),

    "kicad_agent": SubAgent(
        name="kicad-agent",
        description="Crea proyecto KiCad y ejecuta ERC/DRC.",
        prompt=(
            "Eres KiCadAgent. Crea y gestiona proyectos KiCad de forma estructurada.\n"
            "PROCESO OBLIGATORIO:\n"
            "1. Usa 'kicad_project_manager' con action='create_project' para crear la estructura del proyecto\n"
            "2. Usa 'kicad_project_manager' con action='get_project_path' para obtener la ruta del proyecto\n"
            "3. Ejecuta 'kicad_erc' con la ruta del proyecto obtenida\n"
            "4. Si kicad_erc devuelve error sobre kicad-cli no encontrado, informa que KiCad debe instalarse\n"
            "5. Si es necesario, crea archivos .kicad_pcb y ejecuta 'kicad_drc'\n"
            "6. Siempre usa las rutas devueltas por kicad_project_manager\n"
            "\n"
            "MANEJO DE ERRORES:\n"
            "- Si kicad-cli no está instalado, informa al usuario que debe instalar KiCad desde https://www.kicad.org/download/\n"
            "- Si hay errores de archivos no encontrados, verifica las rutas\n"
            "- Siempre reporta errores claramente\n"
            "\n"
            "IMPORTANTE: NUNCA uses rutas hardcodeadas. Siempre obtén las rutas de kicad_project_manager."
        ),
        tools=["kicad_project_manager", "kicad_cli_exec", "kicad_erc", "kicad_drc", "save_local_file"]
    ),

    "doc_agent": SubAgent(
        name="doc-agent",
        description="Genera informe de especificación y verificación.",
        prompt=(
            "Eres DocAgent. Con requisitos y resultados (SPICE y/o ERC/DRC), "
            "genera un markdown de especificación y verificación con generate_spec_markdown."
        ),
        tools=["generate_spec_markdown"]
    )
}

# =========================
# ORCHESTRATOR AGENT
# =========================

def orchestrator_node(state: WorkflowState) -> WorkflowState:
    """Main orchestrator that manages the workflow and creates plans directly."""
    
    current_step = state.get("workflow_step", "planning")
    messages = state["messages"]
    
    # Get the last human message as the task
    task = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            task = msg.content
            break
    
    print(f"🎯 ORQUESTRADOR: Step={current_step}, Task={task[:50]}...")
    
    # DIRECT ORCHESTRATOR LOGIC - No LLM needed for simple decisions
    decision_history = state.get("decision_history", [])
    recent_decisions = decision_history[-5:] if len(decision_history) >= 5 else decision_history
    
    # Check for loops
    if len(recent_decisions) >= 3 and all(d == current_step for d in recent_decisions[-3:]):
        print(f"🔄 LOOP DETECTED: {current_step} repeated 3 times, forcing progression")
        if current_step == "planning":
            current_step = "netlist"
        # Do not auto-progress from netlist or simulation; allow iterative fixes
        elif current_step == "kicad":
            current_step = "documentation"
        elif current_step == "documentation":
            current_step = "completed"
    
    # DIRECT DECISION LOGIC
    if current_step == "planning":
        # Create plan directly if it doesn't exist
        if not state.get("plan"):
            print("📋 CREANDO PLAN GENERAL DINÁMICAMENTE")
            
            # Use LLM to create dynamic plan based on task
            planning_prompt = f"""
Analiza la siguiente tarea de diseño electrónico y crea un plan general detallado:

TAREA: {task}

Crea un plan que incluya:
1. ANÁLISIS DE REQUISITOS: Extrae todos los requisitos técnicos (voltajes, corrientes, eficiencia, ripple, protecciones, normas, etc.)
2. TOPOLOGÍA SELECCIONADA: Propón la topología más adecuada (flyback, buck, boost, etc.) con justificación
3. COMPONENTES PRINCIPALES: Lista los componentes necesarios con especificaciones
4. FASES DE IMPLEMENTACIÓN: Define las fases del diseño (netlist, simulación, PCB, documentación)

Responde en formato estructurado y técnico.
"""
            
            try:
                planning_response = llm_base.invoke([HumanMessage(content=planning_prompt)])
                plan = planning_response.content
                state["plan"] = plan
                print(f"📋 PLAN CREADO: {len(plan)} caracteres")
            except Exception as e:
                # Fallback plan if LLM fails
                plan = f"Plan general para: {task}\n1. Análisis de requisitos\n2. Selección de topología\n3. Componentes principales\n4. Implementación por fases"
                state["plan"] = plan
                print(f"📋 PLAN FALLBACK: {str(e)}")
            
            # Create component list dynamically
            component_prompt = f"""
Basándote en la tarea: {task}

Crea una lista detallada de componentes necesarios con especificaciones técnicas:
- Identifica cada componente necesario
- Especifica valores, voltajes, corrientes, potencias
- Incluye protecciones, filtros, conectores
- Formato: Componente: Ref (Especificaciones)

Responde solo con la lista de componentes, sin explicaciones adicionales.
"""
            
            try:
                component_response = llm_base.invoke([HumanMessage(content=component_prompt)])
                component_list = component_response.content
                state["component_list"] = component_list
                print(f"🔧 COMPONENTES CREADOS: {len(component_list)} caracteres")
            except Exception as e:
                # Fallback component list
                component_list = f"Componentes para: {task}\n- Componentes principales\n- Protecciones\n- Filtros\n- Conectores"
                state["component_list"] = component_list
                print(f"🔧 COMPONENTES FALLBACK: {str(e)}")
            
            # Create initial netlist proposal
            netlist_prompt = f"""
Basándote en la tarea: {task}

Crea un netlist SPICE inicial que sirva como punto de partida:
- Incluye la topología básica propuesta
- Usa componentes realistas con valores típicos
- Añade análisis básico (.tran, .op)
- Incluye comentarios explicativos
- Formato SPICE estándar

Responde solo con el netlist SPICE, sin explicaciones adicionales.
"""
            
            try:
                netlist_response = llm_base.invoke([HumanMessage(content=netlist_prompt)])
                initial_netlist = netlist_response.content
                
                # Store initial netlist proposal for netlist agent
                state["netlist_proposal"] = initial_netlist
                print(f"🔌 NETLIST INICIAL CREADO: {len(initial_netlist)} caracteres")
                
            except Exception as e:
                # Fallback netlist
                initial_netlist = f"* Netlist inicial para: {task}\nV1 1 0 12V\nR1 1 0 1k\n.tran 1u 1m\n.end"
                state["netlist_proposal"] = initial_netlist
                print(f"🔌 NETLIST FALLBACK: {str(e)}")
            
            next_step = "netlist"
            should_proceed = True
            quality_check = "Pass"
            feedback = "Plan general, componentes y netlist inicial creados dinámicamente por el orquestrador"
        else:
            next_step = "netlist"
            should_proceed = True
            quality_check = "Pass"
            feedback = "Plan ya existe, procediendo a netlist"
    
    elif current_step == "netlist":
        # Check if we have a netlist ready for simulation
        netlist_results = state.get("netlist_results", {})
        net_status = netlist_results.get("status") if isinstance(netlist_results, dict) else None
        net_content = netlist_results.get("content", "") if isinstance(netlist_results, dict) else ""
        net_erc = netlist_results.get("erc", {}) if isinstance(netlist_results, dict) else {}
        
        # Contar componentes reales en el netlist
        component_count = 0
        if net_content:
            lines = net_content.splitlines()
            component_count = sum(1 for line in lines if line.strip() and not line.strip().startswith('*') 
                                and line.strip()[0].upper() in "RLCVDMQXBEFGH")
        
        # Extraer errores críticos de ERC (no advertencias)
        erc_errors = net_erc.get("errors", []) if isinstance(net_erc, dict) else []
        critical_errors = [e for e in erc_errors if not str(e).startswith("ADVERTENCIA:")]
        
        # Límite de intentos
        netlist_attempts = state.get("netlist_attempts", 0)
        
        # 1) Si el netlist no tiene componentes, iterar
        if component_count == 0:
            state["netlist_attempts"] = netlist_attempts + 1
            next_step = "netlist"
            should_proceed = True
            quality_check = "Needs_improvement"
            feedback = "Netlist sin componentes - añade componentes y revalida"
        # 2) Si hay errores críticos, iterar corrigiendo
        elif critical_errors:
            if netlist_attempts >= 5:
                next_step = "completed"
                should_proceed = False
                quality_check = "Failed"
                feedback = f"Errores críticos sin resolver tras 5 iteraciones: {critical_errors[:2]}"
            else:
                state["netlist_attempts"] = netlist_attempts + 1
                next_step = "netlist"
                should_proceed = True
                quality_check = "Needs_improvement"
                feedback = f"Corregir errores críticos: {critical_errors[0]}"
        # 3) Si está listo y sin críticos, avanzar
        elif net_status == "ready":
            state["netlist_attempts"] = 0
            next_step = "simulation"
            should_proceed = True
            quality_check = "Pass"
            feedback = f"Netlist OK ({component_count} comp.) → simulación"
        # 4) Caso intermedio, seguir mejorando
        else:
            state["netlist_attempts"] = netlist_attempts + 1
            next_step = "netlist"
            should_proceed = True
            quality_check = "Pass"
            feedback = f"Mejorando netlist (iteración {state['netlist_attempts']})"
    
    elif current_step == "simulation":
        sim_results = state.get("sim_results", {})
        sim_status = sim_results.get("status") if isinstance(sim_results, dict) else None
        sim_returncode = sim_results.get("returncode") if isinstance(sim_results, dict) else None
        
        # Si la simulación falló (returncode != 0), clasificar y decidir routing
        if sim_status == "failed" or (sim_returncode is not None and sim_returncode != 0):
            # Clasificar fallo para dirigir feedback
            try:
                log_tail = sim_results.get("log_tail", "") if isinstance(sim_results, dict) else ""
                # Obtener netlist actual para contexto de clasificación
                netlist_text = ""
                try:
                    if isinstance(state.get("netlist_results"), dict):
                        netlist_text = str(state["netlist_results"].get("content", ""))
                    if not netlist_text:
                        tk = _get_toolkit("default")
                        netlist_text = tk.emit_spice("Layered Netlist").strip()
                except Exception:
                    netlist_text = ""
                classification = _classify_ngspice_failure(log_tail or "", netlist_text or "")
            except Exception:
                classification = {"scope": "unknown", "reason": "classification failed", "suggestions": []}

            # Persist netlist issue feedback for the netlist agent prompt
            state["netlist_issue"] = classification

            # Check if we've already tried simulation multiple times
            sim_attempts = state.get("sim_attempts", 0)
            if sim_attempts >= 2:
                # Too many attempts, report and stop
                next_step = "completed"
                should_proceed = False
                quality_check = "Failed"
                feedback = "Simulación falló múltiples veces - detener workflow"
            else:
                # Dirigir según clasificación
                state["sim_attempts"] = sim_attempts + 1
                if classification.get("scope") == "netlist":
                    next_step = "netlist"
                    should_proceed = True
                    quality_check = "Needs_improvement"
                    sug = "; ".join(classification.get("suggestions", [])[:2])
                    feedback = f"Simulación falló (returncode={sim_returncode}) → problema de netlist: {classification.get('reason','')}. Sugerencias: {sug}"
                elif classification.get("scope") == "simulator":
                    # Reintentar simulación dejando que el wrapper normalice el netlist
                    next_step = "simulation"
                    should_proceed = True
                    quality_check = "Pass"
                    feedback = "Simulación falló por sintaxis corregible por el wrapper; reintentar simulación"
                else:
                    next_step = "netlist"
                    should_proceed = True
                    quality_check = "Needs_improvement"
                    feedback = f"Simulación falló (returncode={sim_returncode}) - reenviar a netlist para inspección general"
        elif not sim_results:
            next_step = "simulation"
            should_proceed = True
            quality_check = "Pass"
            feedback = "Ejecutando simulación SPICE"
        elif sim_status == "completed":
            # Reset sim attempts counter on success
            state["sim_attempts"] = 0
            next_step = "kicad"
            should_proceed = True
            quality_check = "Pass"
            feedback = "Simulación completada exitosamente, procediendo a KiCad"
        else:
            next_step = "simulation"
            should_proceed = True
            quality_check = "Pass"
            feedback = "Completando simulación SPICE"
    
    elif current_step == "kicad":
        if not state.get("kicad_results"):
            next_step = "kicad"
            should_proceed = True
            quality_check = "Pass"
            feedback = "Creando proyecto KiCad"
        else:
            next_step = "documentation"
            should_proceed = True
            quality_check = "Pass"
            feedback = "KiCad completado, procediendo a documentación"
    
    elif current_step == "documentation":
        if not state.get("doc_results"):
            next_step = "documentation"
            should_proceed = True
            quality_check = "Pass"
            feedback = "Generando documentación final"
        else:
            next_step = "completed"
            should_proceed = False
            quality_check = "Pass"
            feedback = "Workflow completado exitosamente"
    
    else:
        next_step = "planning"
        should_proceed = True
        quality_check = "Needs_improvement"
        feedback = f"Paso desconocido {current_step}, reiniciando desde planning"
    
    # Update decision history
    decision_history.append(next_step)
    state["decision_history"] = decision_history[-10:]  # Keep last 10 decisions
    
    # Update state
    state["workflow_step"] = next_step
    state["should_proceed"] = should_proceed
    state["quality_check"] = quality_check
    
    # Add orchestrator message
    orchestrator_msg = AIMessage(content=f"Orchestrator Decision: {feedback}\nNext Step: {next_step}\nQuality: {quality_check}")
    state["messages"].append(orchestrator_msg)
    
    print(f"🎯 DECISIÓN ORQUESTRADOR: {next_step} - {feedback[:100]}...")
    
    
    return state
# =========================
# SIMPLIFIED GRAPH (No orchestrator node needed)
# =========================

def run_orchestrated_pipeline(task: str, thread_id: str = "electronics_design"):
    """Updated pipeline using the new workflow graph."""
    return run_orchestrated_workflow(task, thread_id)
# =========================
# 6) SUB-AGENT DEFINITIONS (SIMPLIFIED 4-AGENT PIPELINE)
# =========================

# Planner node removed - orchestrator handles planning directly

def netlist_agent_node(state: WorkflowState) -> WorkflowState:
    """Netlist agent node: construye netlist por capas usando graph_* tools y luego valida."""
    task = state.get("current_task", "")
    plan = state.get("plan", "")
    component_list = state.get("component_list", "")
    messages = state["messages"]
    
    # Si es la primera vez o si hay capas duplicadas/bloqueadas, reset toolkit
    try:
        tk = _get_toolkit("default")
        summary = tk.get_layer_summary()
        total_layers = summary.get("total_layers", 0)
        locked_layers = summary.get("locked_layers", 0)
        # Reset si: hay muchas capas bloqueadas (>5), o si todas están bloqueadas
        # (Deshabilitado para preservar el trabajo en curso)
        # if locked_layers > 5 or (total_layers > 0 and locked_layers == total_layers):
        #     print(f"🔄 RESETTING TOOLKIT: {locked_layers}/{total_layers} capas bloqueadas - empezar de cero")
        #     _reset_toolkit("default")
    except Exception:
        pass
    
    print(f"🔧 NETLIST AGENT: Starting with {len(state.get('layer_progress', {}))} layers, phase={state.get('netlist_current_phase', 'proposal')}")


    # 1) Prompt + agente con herramientas de construcción por capas
    # Inyecta guía de errores si viene de un fallo de simulación clasificado
    sim_issue = state.get("netlist_issue", {}) if isinstance(state, dict) else {}
    issue_hint = ""
    if isinstance(sim_issue, dict) and sim_issue.get("scope") == "netlist":
        sug = "; ".join(sim_issue.get("suggestions", [])[:2])
        issue_hint = f"\n\nPROBLEMA DETECTADO POR SIMULACIÓN (dirigido al netlist): {sim_issue.get('reason','')}.\nSugerencias: {sug}\nAjusta el JSON para corregir esto antes de validar.\n"
    netlist_prompt = SystemMessage(content=subagents["netlist_agent"].prompt + issue_hint)
    # Get initial netlist and components from orchestrator
    initial_netlist = state.get("netlist_proposal", "")
    
    # Create clean, focused user message with initial netlist and components
    # Analizar feedback previo para dar contexto específico
    prev_feedback = state.get('netlist_feedback_history', [])
    latest_feedback_summary = ""
    if prev_feedback:
        latest = prev_feedback[-1]
        latest_feedback_summary = f"""
📊 FEEDBACK DE LA ITERACIÓN ANTERIOR:
- Estado validación: {latest.get('validation_status', 'unknown')}
- Capas completadas: {latest.get('layers_completed', 0)}
- Vista previa netlist: {latest.get('netlist_preview', 'No disponible')}
"""
    
    # Obtener errores críticos del toolkit actual
    critical_errors_context = ""
    current_components = 0
    current_layers = 0
    layer_lines = []
    comps_lines = []
    reflections_lines = []
    feedback_summary_text = ""
    try:
        tk = _get_toolkit("default")
        summary = tk.get_layer_summary()
        current_layers = summary.get("total_layers", 0)
        current_components = summary.get("total_components", 0)
        # Layers snapshot (máx 6)
        for ly in summary.get("layers", [])[:6]:
            layer_lines.append(f"- {ly.get('name','?')} (locked={ly.get('locked', False)}, comps={ly.get('component_count', 0)})")
        
        # Components snapshot (máx 10)
        try:
            comps = tk.get_components()
            for c in comps[:10]:
                pins_str = ", ".join([f"{p.name}={p.node}" for p in c.pins])
                val = c.params.get("value") if isinstance(c.params, dict) else None
                wv = c.params.get("waveform") if isinstance(c.params, dict) else None
                extra = f", value={val}" if val else (f", wf={wv}" if wv else "")
                comps_lines.append(f"- {c.ref} ({c.ctype}): {pins_str}{extra}")
        except Exception:
            pass
        
        # Toolkit feedback summary
        try:
            fsum = tk.get_feedback_summary()
            feedback_summary_text = f"{fsum.get('summary','')} (ops={fsum.get('total_feedback',0)})"
        except Exception:
            pass
        
        val_result = tk.validate_current_layer(require_pass=False, construction_phase="layer_complete")
        errors = val_result.get("errors", [])
        critical = [e for e in errors if not str(e).startswith("ADVERTENCIA:")]
        if critical:
            critical_errors_context = f"""
⚠️ ERRORES CRÍTICOS A CORREGIR:
{chr(10).join([f"- {e}" for e in critical[:3]])}
"""
    except Exception:
        pass
    
    # Recent reflections (máx 2)
    try:
        refls = state.get('netlist_reflections', []) or []
        for r in refls[-2:]:
            reflections_lines.append(f"- {str(r)[:180]}...")
    except Exception:
        pass
    
    # Schema guidance and examples extracted to plain strings to avoid f-string brace parsing
    schema_guidelines = """
Esquema JSON esperado (genérico):
- Raíz: objeto con opcionales "title", "notes" y obligatorio "layers" (array)
- Capa: { "name": string, "notes"?: string, "locked"?: boolean, "components": Component[] }
- Componente: { "ref": string, "type": string, "pins": string[] | { "1": node, "2": node, ... }, "params"?: object }
- Forma plana: { "components": Component[] } (se auto-envuelve en una única capa)
- Campos desconocidos se ignoran sin fallar
Reglas:
- Incluye nodo de referencia "0" donde aplique
- "type" usa letras SPICE (R, L, C, V, I, D, M, Q, X, K, ...)
"""

    json_schema_example = """
```
{
  "title": "Layered Netlist",
  "layers": [
    {"name": "input", "notes": "...", "locked": true,
     "components": [
       {"ref":"V1","type":"V","pins":["AC_L","0"],"params":{"waveform":"SIN","spec":"0 311 50"}}
     ]}
  ]
}
```
"""

    flat_schema_example = """
```
{
  "components": [
    {"ref":"R1","type":"R","pins":["N1","N2"],"params":{"value":"1k"}}
  ]
}
```
"""

    netlist_context = f"""
🎯 TAREA: {task[:200]}...

📊 ESTADO ACTUAL:
- Componentes añadidos: {current_components}
- Capas creadas: {current_layers}
{critical_errors_context}

📚 CAPAS (resumen):
{chr(10).join(layer_lines) if layer_lines else '(sin capas)'}

🔎 COMPONENTES (muestra):
{chr(10).join(comps_lines) if comps_lines else '(sin componentes)'}

🧠 REFLEXIONES RECIENTES:
{chr(10).join(reflections_lines) if reflections_lines else '(sin reflexiones registradas)'}

📈 FEEDBACK DE HERRAMIENTAS:
{feedback_summary_text if feedback_summary_text else '(sin feedback)'}

🔧 TU TRABAJO (FLUJO JSON):
1) Propón y construye un JSON de netlist con el siguiente esquema:
{schema_guidelines}

Ejemplo:
{json_schema_example}

Alternativa plana:
{flat_schema_example}

2) Llama a graph_apply_netlist_json(netlist_json) y analiza el resultado (validation.errors/warnings).
3) Ajusta el JSON para corregir errores críticos (pines, fuentes paralelas, ground, ESR) y documenta la decisión con document_reasoning.
4) Repite hasta que la validación sea aceptable, luego usa graph_emit_spice para emitir SPICE.

REGLAS:
- No pegues SPICE directo; trabaja en JSON y usa las tools.
- Asegura el nodo "0", añade ESR/Rser cuando sea necesario, y usa nodos descriptivos.

EMPIEZA AHORA:
"""
    
    netlist_message = HumanMessage(content=netlist_context)

    netlist_tools = [tool for name, tool in _TOOL_REGISTRY.items() if name in subagents["netlist_agent"].tools]
    
    netlist_agent = create_react_agent(llm_base, netlist_tools)

    try:
        # 2) Ejecuta el agente siguiendo la metodología reflexiva
        print(f"🔧 EJECUTANDO NETLIST AGENT: {len([netlist_prompt, netlist_message])} messages")
        netlist_response = netlist_agent.invoke({"messages": [netlist_prompt, netlist_message]})
        netlist_msgs = netlist_response.get("messages", []) if isinstance(netlist_response, dict) else []
        print(f"🔧 NETLIST AGENT RESPONSE: {len(netlist_msgs)} messages received")
        
        # 3) Analiza la respuesta del agente para determinar qué fase completó
        current_phase = state.get('netlist_current_phase', 'proposal')
        phase_completed = None
        
        # Buscar indicadores de fase completada en los mensajes
        for msg in netlist_msgs:
            if hasattr(msg, 'content'):
                content = str(msg.content)
                if 'PROPUESTA:' in content and not state.get('netlist_proposal'):
                    phase_completed = 'proposal'
                elif 'PLANIFICACIÓN:' in content and not state.get('netlist_implementation_plan'):
                    phase_completed = 'planning'
                elif 'graph_apply_netlist_json' in content:
                    phase_completed = 'implementation'
                elif 'graph_emit_spice' in content:
                    phase_completed = 'reflection'
        
        # 3) Obtener el netlist final desde el toolkit (estado real)
        netlist_text = ""
        try:
            tk = _get_toolkit("default")
            emitted = tk.emit_spice("Layered Netlist")
            if emitted and len(emitted.strip()) > 10:
                netlist_text = emitted.strip()
                print(f"🔧 NETLIST DESDE TOOLKIT: {len(netlist_text)} chars")
        except Exception as e:
            print(f"⚠️ ERROR AL EMITIR TOOLKIT: {str(e)}")
        if not netlist_text:
            netlist_text = f"* Netlist generado para: {task}\n.end"

        # 6) Validar estado real del diseño con el toolkit (evitar avanzar con errores críticos)
        try:
            tk = _get_toolkit("default")
            val = tk.validate_current_layer(require_pass=False, construction_phase="layer_complete")
        except Exception:
            val = {"pass": False, "errors": ["Validación no disponible"], "warnings": []}

        # Determinar estado basado en errores críticos (no 'ADVERTENCIA:')
        errors_list = val.get("errors", []) or []
        critical_errors = [e for e in errors_list if not str(e).startswith("ADVERTENCIA:")]
        status = "ready" if len(critical_errors) == 0 else "needs_fixes"

        # 7) Actualiza estado con el netlist y el resultado de ERC
        state["netlist_results"] = {
            "content": netlist_text,
            "erc": val,
            "status": status,
            "layers_completed": state.get("layer_progress", {}),
            "timestamp": dt.datetime.now().isoformat()
        }

        # 8) Actualiza el progreso de capas con resumen del toolkit
        try:
            tk = _get_toolkit("default")
            state["layer_progress"] = tk.get_layer_summary()
        except Exception:
            if "layer_progress" not in state:
                state["layer_progress"] = {}
        
        # 9) Captura y almacena feedback del netlist agent
        netlist_feedback = {
            "timestamp": dt.datetime.now().isoformat(),
            "netlist_length": len(netlist_text),
            "layers_completed": len(state.get('layer_progress', {})),
            "validation_status": "passed" if val.get('pass') else "failed",
            "netlist_preview": netlist_text[:200] + "..." if len(netlist_text) > 200 else netlist_text
        }
        
        # Actualiza historial de feedback
        if "netlist_feedback_history" not in state:
            state["netlist_feedback_history"] = []
        state["netlist_feedback_history"].append(netlist_feedback)
        
        # 10) Extrae reflexiones del agente y feedback estructurado de las tool outputs
        agent_reflections = []
        feedback_analysis = []
        
        # Recorre todos los mensajes; parsea bloques FEEDBACK JSON y añade al historial del toolkit
        for msg in netlist_response.get("messages", []):
            if hasattr(msg, 'content'):
                content = str(msg.content)
                
                # Buscar reflexiones en document_reasoning (método principal)
                if 'document_reasoning' in content and 'REASONING:' in content:
                    reasoning_start = content.find('REASONING:') + len('REASONING:')
                    reasoning_end = content.find('---', reasoning_start)
                    if reasoning_end == -1:
                        reasoning_end = content.find('\n\n', reasoning_start)
                    if reasoning_end == -1:
                        reasoning_end = reasoning_start + 200
                    reflection = content[reasoning_start:reasoning_end].strip()
                    if reflection and len(reflection) > 20:
                        agent_reflections.append(reflection)
                        print(f"🧠 REFLEXIÓN CAPTURADA: {reflection[:100]}...")
                
                # Buscar análisis de feedback estructurado JSON
                if 'FEEDBACK:' in content and '{' in content:
                    feedback_start = content.find('FEEDBACK:') + len('FEEDBACK:')
                    feedback_end = content.find('\n\n', feedback_start)
                    if feedback_end == -1:
                        feedback_end = feedback_start + 500
                    feedback_json = content[feedback_start:feedback_end].strip()
                    if feedback_json and '{' in feedback_json:
                        try:
                            import json
                            feedback_data = json.loads(feedback_json)
                            feedback_analysis.append(feedback_data)
                            print(f"📊 FEEDBACK ANALIZADO: {feedback_data.get('action', 'unknown')} - {feedback_data.get('suggestion', 'no suggestion')}")
                            # Persistir feedback en el toolkit para decisiones futuras
                            try:
                                tk = _get_toolkit("default")
                                tk.add_feedback(
                                    operation=feedback_data.get("action", "unknown"),
                                    component_ref=feedback_data.get("component", ""),
                                    feedback_data=feedback_data,
                                )
                            except Exception:
                                pass
                        except:
                            pass
        
        # Actualiza reflexiones
        if "netlist_reflections" not in state:
            state["netlist_reflections"] = []
        state["netlist_reflections"].extend(agent_reflections)
        
        # 11) Actualiza plan específico del netlist agent basado en feedback y progreso
        current_plan = state.get("netlist_current_plan", "")
        layers_completed = len(state.get('layer_progress', {}))
        current_phase = state.get('netlist_current_phase', 'proposal')
        
        # Analizar feedback para actualizar plan
        if feedback_analysis:
            latest_feedback = feedback_analysis[-1]
            action = latest_feedback.get('action', '')
            suggestion = latest_feedback.get('suggestion', '')
            validation_passed = latest_feedback.get('validation_passed', False)
            
            # Crear plan dinámico basado en feedback
            if 'component_added' in action:
                if validation_passed:
                    state["netlist_current_plan"] = f"✅ Componente añadido correctamente. Continuar con siguiente componente. Capas: {layers_completed}"
                else:
                    state["netlist_current_plan"] = f"⚠️ Error en componente: {suggestion}. Revisar conexiones. Capas: {layers_completed}"
            elif 'layer_lock_attempt' in action:
                if validation_passed:
                    state["netlist_current_plan"] = f"✅ Capa bloqueada. Proceder con siguiente capa. Capas: {layers_completed + 1}"
                else:
                    # Inserta acciones concretas si falta la referencia a '0'
                    crits = latest_feedback.get('critical_errors') or latest_feedback.get('errors') or []
                    if any("nodo de referencia '0'" in str(e).lower() for e in crits):
                        state["netlist_current_plan"] = (
                            "❌ Falta referencia a '0'. Acción: añadir conexión a 0 en la capa actual "
                            "(p.ej., resistor de shunt o referencia de retorno). Capas: "
                            f"{layers_completed}"
                        )
                    else:
                        state["netlist_current_plan"] = f"❌ Capa no se puede bloquear: {suggestion}. Corregir errores. Capas: {layers_completed}"
            elif 'construction_validation' in action:
                if validation_passed:
                    state["netlist_current_plan"] = f"✅ Construcción validada. Continuar añadiendo componentes. Capas: {layers_completed}"
                else:
                    state["netlist_current_plan"] = f"❌ Errores críticos: {suggestion}. Corregir antes de continuar. Capas: {layers_completed}"
            else:
                state["netlist_current_plan"] = f"🔄 {action}: {suggestion}. Capas: {layers_completed}"
        else:
            # Plan basado en fase actual y progreso
            if current_phase == "proposal":
                state["netlist_current_plan"] = f"📋 FASE PROPUESTA: Analizar requisitos y proponer arquitectura flyback. Capas: {layers_completed}"
            elif current_phase == "planning":
                state["netlist_current_plan"] = f"📋 FASE PLANIFICACIÓN: Crear plan detallado por capas. Capas: {layers_completed}"
            elif current_phase == "implementation":
                state["netlist_current_plan"] = f"📋 FASE IMPLEMENTACIÓN: Ejecutar plan por capas. Capas: {layers_completed}"
            elif current_phase == "reflection":
                state["netlist_current_plan"] = f"📋 FASE REFLEXIÓN: Analizar feedback y documentar decisiones. Capas: {layers_completed}"
            elif current_phase == "iteration":
                state["netlist_current_plan"] = f"📋 FASE ITERACIÓN: Actualizar plan basado en reflexiones. Capas: {layers_completed}"
            else:
                state["netlist_current_plan"] = f"Implementar netlist por capas: input → primary → magsec → control → analysis. Estado: {layers_completed} capas completadas."
        
        print(f"📋 PLAN ACTUALIZADO: {state.get('netlist_current_plan', 'No plan')}")
        print(f"📊 ESTADO: Fase={current_phase}, Capas={layers_completed}, Feedback={len(feedback_analysis)}")
        
        # 12) Actualiza metodología reflexiva
        if not state.get("netlist_current_phase"):
            state["netlist_current_phase"] = "proposal"
        
        if not state.get("netlist_iteration_count"):
            state["netlist_iteration_count"] = 0
        
        # Extrae propuesta y plan de implementación de los mensajes del agente
        # Buscar en document_reasoning calls para propuestas y planes reales
        for msg in netlist_msgs:
            if hasattr(msg, 'content'):
                content = str(msg.content)
                
                # Buscar propuesta real en document_reasoning calls
                if not state.get("netlist_proposal") and 'document_reasoning' in content and 'DECISION:' in content:
                    # Extraer la decisión que contiene la propuesta real
                    decision_start = content.find('DECISION:') + len('DECISION:')
                    decision_end = content.find('REASONING:', decision_start)
                    if decision_end == -1:
                        decision_end = content.find('---', decision_start)
                    if decision_end == -1:
                        decision_end = decision_start + 200
                    decision_text = content[decision_start:decision_end].strip()
                    if len(decision_text) > 20 and 'propuesta' in decision_text.lower():
                        state["netlist_proposal"] = decision_text
                        print(f"🔍 PROPUESTA EXTRAÍDA: {decision_text[:100]}...")
                
                # Buscar plan real en document_reasoning calls
                if not state.get("netlist_implementation_plan") and 'document_reasoning' in content and 'REASONING:' in content:
                    reasoning_start = content.find('REASONING:') + len('REASONING:')
                    reasoning_end = content.find('---', reasoning_start)
                    if reasoning_end == -1:
                        reasoning_end = content.find('\n\n', reasoning_start)
                    if reasoning_end == -1:
                        reasoning_end = reasoning_start + 300
                    reasoning_text = content[reasoning_start:reasoning_end].strip()
                    if len(reasoning_text) > 50 and ('plan' in reasoning_text.lower() or 'implementación' in reasoning_text.lower()):
                        state["netlist_implementation_plan"] = reasoning_text
                        print(f"🔍 PLAN EXTRAÍDO: {reasoning_text[:100]}...")
        
        # Actualiza fase actual basada en progreso y fase completada
        if phase_completed:
            # Si se completó una fase, avanzar a la siguiente
            if phase_completed == 'proposal':
                state["netlist_current_phase"] = "planning"
            elif phase_completed == 'planning':
                state["netlist_current_phase"] = "implementation"
            elif phase_completed == 'implementation':
                state["netlist_current_phase"] = "reflection"
            elif phase_completed == 'reflection':
                state["netlist_current_phase"] = "iteration"
        else:
            # Lógica de fallback basada en estado actual
            if not state.get("netlist_proposal"):
                state["netlist_current_phase"] = "proposal"
            elif not state.get("netlist_implementation_plan"):
                state["netlist_current_phase"] = "planning"
            elif len(state.get('layer_progress', {})) == 0:
                state["netlist_current_phase"] = "implementation"
            elif len(state.get('layer_progress', {})) < 5:
                state["netlist_current_phase"] = "implementation"
            else:
                state["netlist_current_phase"] = "reflection"
        
        # Incrementa contador de iteraciones
        state["netlist_iteration_count"] = state.get("netlist_iteration_count", 0) + 1
        
        # 12) Feedback en el chat para el operador/historial (solo mensajes relevantes)
        relevant_msgs = []
        for m in netlist_response.get("messages", []):
            try:
                c = str(getattr(m, "content", ""))
                # Evita reenviar el plan entero; conserva sólo tool calls y resúmenes
                if any(k in c for k in ("graph_", "FEEDBACK:", "document_reasoning")):
                    relevant_msgs.append(m)
            except Exception:
                continue
        state["messages"].extend(relevant_msgs)
        
        # 13) Crear mensaje de feedback estructurado con análisis de feedback
        feedback_summary = ""
        if feedback_analysis:
            latest_feedback = feedback_analysis[-1]
            feedback_summary = f"Último feedback: {latest_feedback.get('action', 'unknown')} - {latest_feedback.get('suggestion', 'no suggestion')}"
        
        feedback_msg = AIMessage(content=f"""✅ Netlist Agent completado

ESTADO ACTUAL:
- Netlist generado: {len(netlist_text)} caracteres
- Capas implementadas: {len(state.get('layer_progress', {}))}
- Validación: {'✅ Passed' if val.get('pass') else '❌ Failed'}
- Reflexiones capturadas: {len(agent_reflections)}
- Feedback analizado: {len(feedback_analysis)} entradas

MI METODOLOGÍA REFLEXIVA:
- Fase actual: {state.get('netlist_current_phase', 'proposal')}
- Fase completada: {phase_completed if phase_completed else 'Ninguna'}
- Iteración: {state.get('netlist_iteration_count', 0)}
- Propuesta: {'✅ Completada' if state.get('netlist_proposal') else '❌ Pendiente'}
- Plan de implementación: {'✅ Completado' if state.get('netlist_implementation_plan') else '❌ Pendiente'}

MI PLAN ACTUALIZADO:
- {state.get('netlist_current_plan', 'No plan')}

ANÁLISIS DE FEEDBACK:
- {feedback_summary if feedback_summary else 'No feedback analysis available'}

PRÓXIMOS PASOS:
- {'Continuar con siguiente fase' if phase_completed else 'Completar fase actual'}
- {'Proceder a simulación' if state.get('netlist_current_phase') == 'reflection' else 'Continuar implementación'}

FEEDBACK PARA ORQUESTRADOR:
- Metodología reflexiva funcionando correctamente
- Fase completada: {phase_completed if phase_completed else 'En progreso'}
- {'Listo para simulación' if state.get('netlist_current_phase') == 'reflection' else 'Continuar con netlist agent'}""")
        
        state["messages"].append(feedback_msg)
        print(f"📝 FEEDBACK MSG CREADO: {len(feedback_analysis)} feedback entries, {len(agent_reflections)} reflections")

    except Exception as e:
        state["messages"].append(AIMessage(content=f"Netlist error: {str(e)}"))
        state["netlist_results"] = {"status": "failed", "error": str(e)}

    return state


def sim_agent_node(state: WorkflowState) -> WorkflowState:
    """Simulation agent node."""
    
    task = state.get("current_task", "")
    plan = state.get("plan", "")
    netlist_results = state.get("netlist_results", {})
    messages = state["messages"]
    
    
    # Select netlist content from state
    netlist_text = ""
    if isinstance(netlist_results, dict):
        netlist_text = str(netlist_results.get("content", ""))
    if not netlist_text:
        # Fallback to toolkit emission
        try:
            tk = _get_toolkit("default")
            netlist_text = tk.emit_spice("Layered Netlist").strip()
        except Exception:
            netlist_text = ""

    # If still empty, report and stop early
    if not netlist_text:
        error_msg = AIMessage(content="Simulation error: No netlist available from netlist agent")
        state["messages"].append(error_msg)
        state["sim_results"] = {"status": "failed", "error": "No netlist available"}
        return state

    # Build a compact instruction for the simulation agent (tool-only)
    sim_prompt = SystemMessage(content=subagents["simulation_agent"].prompt)
    sim_message = HumanMessage(content=f"""⚠️ INSTRUCCIONES CRÍTICAS:

1. Ejecuta SOLO este netlist con spice_autorun
2. NO modifiques el netlist - usa mode='netlist'
3. Analiza SOLO resultados (log_tail, probes, measures)
4. Si returncode != 0, reporta error y detener

NETLIST A SIMULAR:
```spice
{netlist_text}
```

CONFIGURACIÓN:
- mode='netlist'
- probes_json='["v(VOUT)"]' (o nodos que detectes en el netlist)

Ejecuta spice_autorun AHORA:
""")
    
    # Get sim tools
    sim_tools = [tool for name, tool in _TOOL_REGISTRY.items() if name in subagents["simulation_agent"].tools]
    
    # Create and run sim agent
    sim_agent = create_react_agent(llm_base, sim_tools)
    
    try:
        # Run sim agent
        sim_response = sim_agent.invoke({"messages": [sim_prompt, sim_message]})
        
        # Extract last message and parse for spice_autorun result
        sim_msgs = sim_response.get("messages", []) if isinstance(sim_response, dict) else []
        sim_content = sim_msgs[-1].content if sim_msgs else ""

        # Try to parse JSON result from spice_autorun
        returncode = None
        log_tail = ""
        for msg in sim_msgs:
            if hasattr(msg, 'content'):
                content = str(msg.content)
                # Look for JSON blocks with returncode
                try:
                    import json
                    if '{' in content and 'returncode' in content:
                        # Extract JSON from content
                        json_start = content.find('{')
                        json_end = content.rfind('}') + 1
                        if json_start >= 0 and json_end > json_start:
                            result_json = json.loads(content[json_start:json_end])
                            returncode = result_json.get('returncode')
                            log_tail = result_json.get('log_tail', '')
                            break
                except:
                    pass

        # Determine status based on returncode
        if returncode is not None and returncode != 0:
            status = "failed"
            sim_results = {
                "content": sim_content,
                "status": status,
                "returncode": returncode,
                "log_tail": log_tail,
                "timestamp": dt.datetime.now().isoformat()
            }
            print(f"⚠️ SIMULACIÓN FALLÓ: returncode={returncode}")
        else:
            status = "completed"
            sim_results = {
                "content": sim_content,
                "status": status,
                "timestamp": dt.datetime.now().isoformat()
            }
        
        # Update state
        state["sim_results"] = sim_results
        state["messages"].extend(sim_response.get("messages", []))
        
        
    except Exception as e:
        error_msg = AIMessage(content=f"Simulation error: {str(e)}")
        state["messages"].append(error_msg)
        state["sim_results"] = {"status": "failed", "error": str(e)}
    
    return state

def kicad_agent_node(state: WorkflowState) -> WorkflowState:
    """KiCad agent node."""
    
    task = state.get("current_task", "")
    sim_results = state.get("sim_results", {})
    messages = state["messages"]
    
    
    # Create kicad agent prompt
    kicad_prompt = SystemMessage(content=subagents["kicad_agent"].prompt)
    kicad_message = HumanMessage(content=f"""Task: {task}
Simulation Results: {sim_results}

Create KiCad project and run ERC/DRC.""")
    
    # Get kicad tools
    kicad_tools = [tool for name, tool in _TOOL_REGISTRY.items() if name in subagents["kicad_agent"].tools]
    
    # Create and run kicad agent
    kicad_agent = create_react_agent(llm_base, kicad_tools)
    
    try:
        # Run kicad agent
        kicad_response = kicad_agent.invoke({"messages": [kicad_prompt, kicad_message]})
        
        # Extract kicad results
        kicad_msgs = kicad_response.get("messages", []) if isinstance(kicad_response, dict) else []
        kicad_content = kicad_msgs[-1].content if kicad_msgs else ""
        
        kicad_results = {
            "content": kicad_content,
            "status": "completed",
            "timestamp": "now"
        }
        
        # Update state
        state["kicad_results"] = kicad_results
        state["messages"].extend(kicad_response.get("messages", []))
        
        
    except Exception as e:
        error_msg = AIMessage(content=f"KiCad error: {str(e)}")
        state["messages"].append(error_msg)
        state["kicad_results"] = {"status": "failed", "error": str(e)}
    
    return state

def doc_agent_node(state: WorkflowState) -> WorkflowState:
    """Documentation agent node."""
    
    task = state.get("current_task", "")
    plan = state.get("plan", "")
    sim_results = state.get("sim_results", {})
    kicad_results = state.get("kicad_results", {})
    messages = state["messages"]
    
    
    # Create doc agent prompt
    doc_prompt = SystemMessage(content=subagents["doc_agent"].prompt)
    doc_message = HumanMessage(content=f"""Task: {task}
Plan: {plan}
Simulation Results: {sim_results}
KiCad Results: {kicad_results}

Generate final specification and verification report.""")
    
    # Get doc tools
    doc_tools = [tool for name, tool in _TOOL_REGISTRY.items() if name in subagents["doc_agent"].tools]
    
    # Create and run doc agent
    doc_agent = create_react_agent(llm_base, doc_tools)
    
    try:
        # Run doc agent
        doc_response = doc_agent.invoke({"messages": [doc_prompt, doc_message]})
        
        # Extract documentation results
        doc_msgs = doc_response.get("messages", []) if isinstance(doc_response, dict) else []
        doc_content = doc_msgs[-1].content if doc_msgs else ""
        
        # Update state
        state["doc_results"] = doc_content
        state["messages"].extend(doc_response.get("messages", []))
        
        
    except Exception as e:
        error_msg = AIMessage(content=f"Documentation error: {str(e)}")
        state["messages"].append(error_msg)
        state["doc_results"] = f"Documentation failed: {str(e)}"
    
    return state


# Mapa tool-name -> callable real (reutiliza tus definiciones existentes)
_TOOL_REGISTRY = {
    "write_todos": write_todos,
    "write_file": write_file,
    "read_file": read_file,
    "list_files": list_files,
    "edit_file": edit_file,
    "spice_autorun": spice_autorun,
    "spice_analyze_syntax": spice_analyze_syntax,
    "save_local_file": save_local_file,
    "kicad_project_manager": kicad_project_manager,  # NEW TOOL
    "kicad_cli_exec": kicad_cli_exec,
    "kicad_erc": kicad_erc,
    "kicad_drc": kicad_drc,
    "generate_spec_markdown": generate_spec_markdown,
    # spice_graph_validate removed - validation now integrated into graph_* tools
    # Graph builder tools (deprecated or minimal) and JSON-driven tools
    # Still used
    "graph_emit_spice": graph_emit_spice,
    "graph_assert_invariants": graph_assert_invariants,
    "graph_validate_construction": graph_validate_construction,
    "graph_validate_layer_complete": graph_validate_layer_complete,
    "graph_validate_final": graph_validate_final,
    # JSON-driven netlist tools
    "graph_apply_netlist_json": graph_apply_netlist_json,
    "graph_export_netlist_json": graph_export_netlist_json,
    "graph_validate_design": graph_validate_design,
    # Component list tool
    # Reasoning documentation tool
    "document_reasoning": document_reasoning,
}



# =========================
# ROUTING FUNCTIONS
# =========================

def route_after_orchestrator(state: WorkflowState) -> str:
    """Route to appropriate agent based on orchestrator decision."""
    workflow_step = state.get("workflow_step", "planning")
    should_proceed = state.get("should_proceed", True)
    
    if not should_proceed:
        return "end"
    
    # No more planner agent - orchestrator handles planning directly
    if workflow_step == "planning":
        return "end"  # Planning is done directly by orchestrator
    elif workflow_step == "netlist":
        return "netlist_agent"
    elif workflow_step == "simulation":
        return "sim_agent"
    elif workflow_step == "kicad":
        return "kicad_agent"
    elif workflow_step == "documentation":
        return "doc_agent"
    elif workflow_step == "completed":
        return "end"
    else:
        return "end"

def should_continue(state: WorkflowState) -> str:
    """Check if workflow should continue."""
    workflow_step = state.get("workflow_step", "completed")
    
    if workflow_step == "completed":
        return "end"
    else:
        return "orchestrator"

# =========================
# GRAPH CONSTRUCTION
# =========================

def create_workflow_graph():
    """Create the main workflow graph."""
    
    # Create the graph
    workflow = StateGraph(WorkflowState)
    
    # Add nodes (no more planner - orchestrator handles planning directly)
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("netlist_agent", netlist_agent_node)
    workflow.add_node("sim_agent", sim_agent_node)
    workflow.add_node("kicad_agent", kicad_agent_node)
    workflow.add_node("doc_agent", doc_agent_node)
    
    # Set entry point
    workflow.set_entry_point("orchestrator")
    
    # Add edges
    workflow.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {
            "netlist_agent": "netlist_agent",
            "sim_agent": "sim_agent", 
            "kicad_agent": "kicad_agent",
            "doc_agent": "doc_agent",
            "end": END
        }
    )
    
    # After each agent, go back to orchestrator for evaluation
    workflow.add_edge("netlist_agent", "orchestrator")
    workflow.add_edge("sim_agent", "orchestrator")
    workflow.add_edge("kicad_agent", "orchestrator")
    workflow.add_edge("doc_agent", "orchestrator")
    
    # Compile the graph
    return workflow.compile()

# =========================
# 9) MAIN EXECUTION
# =========================

# =========================
# MAIN EXECUTION FUNCTION
# =========================

def run_orchestrated_workflow(task: str, thread_id: str = "electronics_design"):
    """Run the complete orchestrated workflow with timeout protection."""
    
    # Create the graph
    workflow_graph = create_workflow_graph()
    
    # Initialize state
    initial_state = WorkflowState(
        messages=[HumanMessage(content=task)],
        current_task=task,
        plan=None,
        component_list=None,
        netlist_proposal=None,
        netlist_results=None,
        sim_results=None,
        kicad_results=None,
        doc_results=None,
        workflow_step="planning",
        quality_check=None,
        should_proceed=True,
        decision_history=[],
        sim_attempts=0,
        netlist_attempts=0,
    )
    
    # Run the workflow with timeout protection
    
    try:
        # Use stream with timeout to prevent hanging
        max_iterations = 20  # Limit iterations to prevent infinite loops
        iteration_count = 0
        
        for chunk in workflow_graph.stream(initial_state, config={"thread_id": thread_id}):
            iteration_count += 1
            
            if iteration_count >= max_iterations:
                break
                
            # Check if workflow should continue
            if "orchestrator" in chunk:
                orchestrator_state = chunk["orchestrator"]
                if orchestrator_state and orchestrator_state.get("workflow_step") == "completed":
                    break
                if orchestrator_state and not orchestrator_state.get("should_proceed", True):
                    break
        
        # Get final state
        final_state = workflow_graph.invoke(initial_state, config={"sizeof": thread_id})
        
        # Ensure final_state is not None
        if final_state is None:
            final_state = initial_state
        
        return {
            "final_state": final_state,
            "plan": final_state.get("plan") if final_state else None,
            "netlist_results": final_state.get("netlist_results") if final_state else None,
            "sim_results": final_state.get("sim_results") if final_state else None,
            "kicad_results": final_state.get("kicad_results") if final_state else None,
            "doc_results": final_state.get("doc_results") if final_state else None
        }
        
    except KeyboardInterrupt:
        return {"error": "Workflow interrupted by user"}
    except Exception as e:
        return {"error": str(e)}



# Example usage
if __name__ == "__main__":
    import sys

   
    task = (
        "Diseñar una fuente conmutada de 24V/3A desde 220VAC, eficiencia >88%, "
        "ripple <50mVpp, protección OCP/OTP, cumplimiento IEC 62368-1 e IEC 61000-6-1/2/3/4, "
        "entorno -10..+60°C."
    )
    result = run_orchestrated_workflow(task)
    print(f"Task completed with result keys: {list(result.keys())}")
    