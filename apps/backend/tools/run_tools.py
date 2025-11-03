import os
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Literal, Dict, Any, List, Optional
from subprocess import run, PIPE, TimeoutExpired
from dotenv import load_dotenv
from langchain_core.tools import tool
from ..schema.spice_schema import SpiceAutorunInput

load_dotenv()

# Environment variables setup
os.environ.setdefault("NGSPICE", r"C:\Program Files\Spice64\bin\ngspice.exe")
os.environ.setdefault("KICAD_CLI", r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe")


# =========================
# BINARIES RESOLVERS
# =========================

def _resolve_ngspice():
    """Resolve ngspice binary path - works in both local and Docker."""
    import shutil
    env_path = os.getenv("NGSPICE")
    if env_path and os.path.exists(env_path):
        return env_path
    for path in ["/usr/local/bin/ngspice", "/usr/bin/ngspice", "/opt/ngspice/bin/ngspice"]:
        if os.path.exists(path):
            return path
    for path in [
        r"C:\Program Files\Spice64\bin\ngspice.exe",
        r"C:\Program Files (x86)\Spice64\bin\ngspice.exe",
    ]:
        if os.path.exists(path):
            return path
    return shutil.which("ngspice") or shutil.which("ngspice.exe")


def _resolve_kicad_cli():
    """Resolve kicad-cli binary path - works in both local and Docker."""
    import shutil
    env_path = os.getenv("KICAD_CLI")
    if env_path and os.path.exists(env_path):
        return env_path
    for path in ["/usr/bin/kicad-cli", "/snap/bin/kicad-cli", "/usr/local/bin/kicad-cli"]:
        if os.path.exists(path):
            return path
    for path in [
        r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe",
        r"C:\Program Files\KiCad\7.0\bin\kicad-cli.exe",
        r"C:\Program Files (x86)\KiCad\8.0\bin\kicad-cli.exe",
    ]:
        if os.path.exists(path):
            return path
    return shutil.which("kicad-cli") or shutil.which("kicad-cli.exe")


# =========================
# HELPER FUNCTIONS
# =========================

_SPICE_ANALYSIS_RE = re.compile(r"^\s*\.(op|tran|ac|dc)\b", re.I | re.M)

def _guess_is_file_path(text: str) -> bool:
    """Heurística mínima para detectar si el texto es una ruta existente."""
    if not text or '\n' in text:
        return False
    t = text.strip()
    if not t:
        return False
    if any(t.endswith(ext) for ext in (".sp", ".cir", ".net", ".spice")) and os.path.exists(t):
        return True
    if (t.startswith(("\\", "/", "C:", "D:", "E:")) and os.path.exists(t)):
        return True
    return False


def _guess_is_python(text: str) -> bool:
    """Heurística mínima para detectar si es código Python (sin confundir con SPICE)."""
    if not text:
        return False
    tl = text.lower()
    if any(k in tl for k in ("import ", " from ", "def ", "class ", " try:", " except:", " while ", " for ")):
        # Evita falsos positivos cuando claramente hay directivas SPICE
        if any(k in tl for k in (".model", ".subckt", ".include", ".tran", ".ac", ".op", ".dc", ".control")):
            return False
        return True
    return False


def _augment_env_for_ngspice(env: dict) -> dict:
    """Añade path de ngspice al PATH si hace falta."""
    env_copy = env.copy()
    ngspice_path = _resolve_ngspice()
    if ngspice_path:
        ngspice_dir = os.path.dirname(ngspice_path)
        if ngspice_dir and ngspice_dir not in env_copy.get("PATH", ""):
            env_copy["PATH"] = f"{ngspice_dir};{env_copy.get('PATH', '')}"
    return env_copy


def _has_control_block(lines: List[str]) -> Optional[Dict[str, int]]:
    """
    Devuelve índices del bloque .control si existe: {'start': i, 'end': j}
    Acepta espacios y mayúsculas/minúsculas.
    """
    start = end = None
    for i, ln in enumerate(lines):
        if start is None and ln.strip().lower().startswith(".control"):
            start = i
        elif start is not None and ln.strip().lower().startswith(".endc"):
            end = i
            break
    if start is not None and end is not None and end > start:
        return {"start": start, "end": end}
    return None


def _ensure_one_control_with_wrdata(netlist_text: str, wr_lines: List[str]) -> str:
    """
    Garantiza un único bloque .control … .endc.
    - Si ya existe: inserta WRDATA antes de .endc (evita anidar).
    - Si no existe: crea bloque mínimo con WRDATA en posición segura (tras el último análisis si hay, si no, antes de .end).
    """
    lines = netlist_text.splitlines()
    ctrl = _has_control_block(lines)

    # Normaliza .end al final
    has_end = any(ln.strip().lower() == ".end" for ln in lines)
    if not has_end:
        lines.append(".end")

    if ctrl:
        # Inserta wrdata antes de .endc, evitando duplicados exactos
        insert_at = ctrl["end"]
        existing = set([ln.strip() for ln in lines[ctrl["start"]:ctrl["end"]+1]])
        new_wr = [w for w in wr_lines if w.strip() not in existing]
        for idx, w in enumerate(new_wr):
            lines.insert(insert_at + idx, w)
        return "\n".join(lines)

    # No existe control → crear uno único
    # Buscamos último análisis para colocarlo justo después (si existe)
    last_ana_idx = -1
    for i, ln in enumerate(lines):
        if _SPICE_ANALYSIS_RE.match(ln):
            last_ana_idx = i

    ctrl_block = [".control", "set noaskquit", "set filetype=ascii", "set wr_singlescale"] + wr_lines + [".endc"]

    if last_ana_idx >= 0:
        insert_pos = last_ana_idx + 1
        for ln in reversed(ctrl_block):
            lines.insert(insert_pos, ln)
    else:
        # Inserta antes de .end final
        end_idx = next((i for i, ln in enumerate(lines) if ln.strip().lower() == ".end"), len(lines))
        for ln in reversed(ctrl_block):
            lines.insert(end_idx, ln)

    return "\n".join(lines)


def _autopatch_minimal(netlist_text: str) -> str:
    """
    Ajuste mínimo, no intrusivo:
    - Garantiza que exista .end
    - Si NO hay ningún análisis (.op/.tran/.ac/.dc), añade un .op (neutral)
    No toca fuentes ni añade .tran si ya hay análisis.
    """
    lines = [ln.rstrip() for ln in netlist_text.strip().splitlines() if ln.strip() != ""]
    has_end = any(ln.strip().lower() == ".end" for ln in lines)
    has_analysis = any(_SPICE_ANALYSIS_RE.match(ln) for ln in lines)

    if not has_analysis:
        lines.append(".op")
    if not has_end:
        lines.append(".end")
    return "\n".join(lines)


# =========================
# SPICE TOOLS
# =========================

@tool("spice_autorun")
def spice_autorun(input_data: SpiceAutorunInput) -> str:
    """
    Ejecuta simulaciones SPICE (ngspice batch) o código Python (PySpice/pyngspice).
    **Contrato para el LLM (construcción, no saneado):**
      1) El netlist final debe ser **autocontenido** y válido para ngspice:
         - Incluir modelos como `.model` inline o `.include` con **rutas absolutas** (no relativas).
         - Terminar en `.end`.
         - Si necesitas comandos de batch, usa **un único** bloque:
             .control
               set noaskquit
               set filetype=ascii
               set wr_singlescale
               [tus wrdata/.print]
               run
             .endc
      2) Si el análisis es transitorio, evita `AC <Vrms>` en fuentes: usa `SINE(0 Vp f)`.
      3) Probes deben ser expresiones SPICE válidas para ngspice:
         - Voltajes: `v(n)`, `v(n1,n2)` (no `v(Vsrc)` salvo que lo resuelvas a nodos).
         - Corrientes: `i(Elemento)` **con paréntesis** (p.ej. `i(Rload)`).
      4) Debe existir nodo de referencia `0` (tierra).
      5) Este runner **no** repara netlists rotos. Solo:
         - Garantiza `.end` y, si faltan análisis, añade `.op` (neutral).
         - Inserta WRDATA de probes en un único bloque `.control ... .endc` (si ya existe, reusa; si no, crea uno mínimo).

    Parámetros (SpiceAutorunInput):
      - input_text: Netlist, ruta .sp/.cir/.net, o código Python.
      - mode: 'auto' | 'netlist' | 'python'
      - probes: Lista de expresiones SPICE ['v(VOUT)', 'i(R1)']
      - from_fraction: Fracción 0.0-1.0 para métricas en CSVs.
      - timeout_s: Timeout (s).

    Devuelve JSON con method, paths, probes, measures, y log.
    """
    input_text = input_data.input_text
    mode = input_data.mode
    probes = input_data.probes if input_data.probes else [input_data.node_expr or "v(VOUT)"]
    frac = input_data.from_fraction
    timeout_s = str(input_data.timeout_s)

    # --- PYTHON MODE ---
    if mode == "python" or (mode == "auto" and _guess_is_python(input_text)):
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
            try:
                result_obj = json.loads(m.group(1))
            except Exception:
                result_obj = None

        return json.dumps({
            "method": "python",
            "returncode": r.returncode,
            "workdir": workdir,
            "script_path": script_path,
            "stdout_tail": stdout[-10000:],
            "stderr_tail": stderr[-10000:],
            "result": result_obj
        }, ensure_ascii=False)

    # --- NETLIST MODE ---
    cmd_ngspice = _resolve_ngspice()
    if not cmd_ngspice:
        return json.dumps({"error": "ngspice no encontrado (define NGSPICE o añade a PATH)"}, ensure_ascii=False)

    workdir = tempfile.mkdtemp(prefix="spice_")
    netlist_path = os.path.join(workdir, "circuit.sp")
    log_path = os.path.join(workdir, "ngspice.log")

    # Obtener netlist
    if _guess_is_file_path(input_text):
        with open(input_text, "r", encoding="utf-8", errors="ignore") as f:
            net_txt = f.read()
    else:
        net_txt = input_text

    # Ajuste mínimo (no intrusivo)
    base = _autopatch_minimal(net_txt)

    # Preparar WRDATA para probes (no normalizamos: exigimos que el agente ya pase expresiones válidas)
    wr_lines, csv_paths = [], []
    for expr in probes:
        expr = str(expr)
        safe = re.sub(r"[^A-Za-z0-9_]+", "_", expr).strip("_").lower() or "sig"
        csv_path = os.path.join(workdir, f"{safe}.csv").replace("\\", "/")
        wr_lines.append(f'wrdata "{csv_path}" {expr}')
        csv_paths.append((expr, csv_path))

    # Un único .control .endc con wrdata (si existe, reusamos; si no, creamos)
    code = _ensure_one_control_with_wrdata(base, wr_lines)

    # Escribir netlist final
    with open(netlist_path, "w", encoding="utf-8") as f:
        f.write(code)

    # Ejecutar ngspice batch
    r = run([cmd_ngspice, "-b", "-o", log_path, netlist_path], stdout=PIPE, stderr=PIPE, text=True)
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as lf:
            log_txt = lf.read()
    except Exception:
        log_txt = (r.stdout or "") + "\n" + (r.stderr or "")

    # Parseo de medidas por .meas (si existen)
    FLOAT_RE = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
    meas_pairs = re.findall(r"(?mi)^\s*([A-Za-z_]\w*)\s*=\s*({})\s*$".format(FLOAT_RE), log_txt)
    measures = {k: float(v) for k, v in meas_pairs}

    # Métricas simples desde WRDATA
    def _metrics_from_csv(path: str):
        xs, ys = [], []
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        try:
                            xs.append(float(parts[0]))
                            ys.append(float(parts[1]))
                        except Exception:
                            continue
        except Exception:
            return None
        if not ys:
            return None
        n0 = int(len(ys) * (frac if 0.0 <= frac < 1.0 else 0.0))
        yw = ys[n0:] if n0 > 0 else ys
        n = len(yw)
        if n == 0:
            return None
        avg = sum(yw) / n
        rms = (sum(v*v for v in yw) / n) ** 0.5
        p2p = (max(yw) - min(yw))
        return {"avg": float(avg), "rms": float(rms), "p2p": float(p2p), "samples": len(ys), "window_samples": len(yw)}

    probes_out = []
    for expr, csv_path in csv_paths:
        probes_out.append({"expr": expr, "csv": csv_path, "metrics": _metrics_from_csv(csv_path)})

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


# =========================
# KICAD TOOLS
# =========================

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
    """
    backend_dir = Path(__file__).parent.parent  # apps/backend
    project_dir = backend_dir / project_name
    project_file = project_dir / f"{project_name}.kicad_pro"
    schematic_file = project_dir / f"{project_name}.kicad_sch"
    board_file = project_dir / f"{project_name}.kicad_pcb"

    try:
        if action == "create_project":
            project_dir.mkdir(exist_ok=True)
            if not project_file.exists():
                with open(project_file, 'w', encoding="utf-8") as f:
                    f.write("(kicad_project\n  (version 8)\n  (generator kicad-cli)\n)\n")
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
                "message": "Unknown action. Valid: create_project, save_schematic, save_board, get_project_path, get_board_path, list_files"
            }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"status": "error", "action": action, "error": str(e)}, ensure_ascii=False)


@tool("kicad_erc")
def kicad_erc(project_path: str, timeout_s: str = "120") -> str:
    """Run KiCad ERC on a .kicad_pro/.kicad_sch project (resuelve kicad-cli por env/PATH)."""
    cmd_kicad = _resolve_kicad_cli()
    if not cmd_kicad:
        return json.dumps({
            "error": "kicad-cli no encontrado. Instala KiCad o define KICAD_CLI.",
            "suggestion": "Descarga e instala KiCad y define KICAD_CLI con la ruta del ejecutable."
        }, ensure_ascii=False)

    resolved_path = project_path
    if not os.path.isabs(project_path):
        backend_dir = Path(__file__).parent.parent
        candidates = [project_path, backend_dir / project_path]
        for sub in backend_dir.iterdir():
            if sub.is_dir():
                candidates.append(sub / project_path)
        for p in candidates:
            if os.path.exists(p):
                resolved_path = os.path.abspath(p)
                break
        else:
            return json.dumps({"error": f"Project file not found: {project_path}"}, ensure_ascii=False)

    try:
        res = run([cmd_kicad, "sch", "erc", "--project", resolved_path], stdout=PIPE, stderr=PIPE, text=True, timeout=int(timeout_s))
        return json.dumps({
            "returncode": res.returncode,
            "stdout": (res.stdout or "")[-10000:],
            "stderr": (res.stderr or "")[-10000:],
            "project_path": resolved_path,
            "original_path": project_path
        }, ensure_ascii=False)
    except FileNotFoundError:
        return json.dumps({"error": f"kicad-cli no se puede ejecutar: {cmd_kicad}"}, ensure_ascii=False)
    except TimeoutExpired:
        return json.dumps({"error": f"ERC timeout > {timeout_s}s"}, ensure_ascii=False)


@tool("kicad_drc")
def kicad_drc(board_path: str, timeout_s: str = "120") -> str:
    """Run KiCad DRC list on a .kicad_pcb board (resuelve kicad-cli por env/PATH)."""
    cmd_kicad = _resolve_kicad_cli()
    if not cmd_kicad:
        return json.dumps({
            "error": "kicad-cli no encontrado. Instala KiCad o define KICAD_CLI.",
            "suggestion": "Descarga e instala KiCad y define KICAD_CLI con la ruta del ejecutable."
        }, ensure_ascii=False)

    resolved_path = board_path
    if not os.path.isabs(board_path):
        backend_dir = Path(__file__).parent.parent
        candidates = [board_path, backend_dir / board_path]
        for sub in backend_dir.iterdir():
            if sub.is_dir():
                candidates.append(sub / board_path)
        for p in candidates:
            if os.path.exists(p):
                resolved_path = os.path.abspath(p)
                break
        else:
            return json.dumps({"error": f"Board file not found: {board_path}"}, ensure_ascii=False)

    try:
        res = run([cmd_kicad, "pcb", "drclist", "--board", resolved_path], stdout=PIPE, stderr=PIPE, text=True, timeout=int(timeout_s))
        return json.dumps({
            "returncode": res.returncode,
            "stdout": (res.stdout or "")[-10000:],
            "stderr": (res.stderr or "")[-10000:],
            "board_path": resolved_path,
            "original_path": board_path
        }, ensure_ascii=False)
    except FileNotFoundError:
        return json.dumps({"error": f"kicad-cli no se puede ejecutar: {cmd_kicad}"}, ensure_ascii=False)
    except TimeoutExpired:
        return json.dumps({"error": f"DRC timeout > {timeout_s}s"}, ensure_ascii=False)


# =========================
# EXPORT TOOLS
# =========================

__all__ = [
    'spice_autorun',
    'kicad_cli_exec',
    'kicad_project_manager',
    'kicad_erc',
    'kicad_drc',
    '_resolve_ngspice',
    '_resolve_kicad_cli'
]
