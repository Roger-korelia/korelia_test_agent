import os
import json
import re
import sys
import tempfile
import base64
import datetime as dt
from pathlib import Path
from typing import Literal, Dict, Any, List, Optional, Annotated, TypedDict
from subprocess import run, PIPE, TimeoutExpired
from dotenv import load_dotenv
from langchain_core.tools import tool

load_dotenv()

# Environment variables setup
os.environ.setdefault("NGSPICE", r"C:\Program Files\Spice64\bin\ngspice.exe")
os.environ.setdefault("KICAD_CLI", r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe")

# =========================
# BINARIES RESOLVERS
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
# HELPER FUNCTIONS
# =========================

def _guess_is_file_path(text: str) -> bool:
    """Heurística para detectar si el texto es una ruta de archivo."""
    if not text or len(text.strip()) == 0:
        return False
    
    # Si contiene caracteres de ruta típicos
    if any(c in text for c in ['\\', '/', '.']):
        # Si termina en extensión común de netlist
        if any(text.strip().endswith(ext) for ext in ['.sp', '.cir', '.net', '.spice']):
            return True
        # Si parece una ruta absoluta o relativa
        if text.strip().startswith(('.', '\\', '/', 'C:', 'D:', 'E:')):
            return True
    
    return False

def _guess_is_python(text: str) -> bool:
    """Heurística para detectar si el texto es código Python."""
    if not text or len(text.strip()) == 0:
        return False
    
    # Palabras clave de Python/SPICE
    python_keywords = ['import', 'from', 'def', 'class', 'if', 'for', 'while', 'try', 'except']
    spice_keywords = ['.model', '.subckt', '.ends', '.lib', '.include', '.param']
    
    text_lower = text.lower()
    
    # Si contiene palabras clave de Python
    if any(keyword in text_lower for keyword in python_keywords):
        return True
    
    # Si contiene palabras clave de SPICE, probablemente no es Python
    if any(keyword in text_lower for keyword in spice_keywords):
        return False
    
    return False

def _augment_env_for_ngspice(env: dict) -> dict:
    """Añade variables de entorno necesarias para ngspice."""
    env_copy = env.copy()
    
    # Añadir directorio de ngspice al PATH si existe
    ngspice_path = _resolve_ngspice()
    if ngspice_path:
        ngspice_dir = os.path.dirname(ngspice_path)
        if ngspice_dir not in env_copy.get("PATH", ""):
            env_copy["PATH"] = f"{ngspice_dir};{env_copy.get('PATH', '')}"
    
    return env_copy

def _autopatch_netlist_min(netlist_text: str) -> str:
    """Parchea netlist SPICE básico añadiendo .tran/.end si faltan."""
    lines = netlist_text.strip().split('\n')
    
    # Buscar si ya tiene .tran
    has_tran = any('.tran' in line.upper() for line in lines)
    has_end = any(line.strip().upper() == '.END' for line in lines)
    
    # Si no tiene .tran, añadir uno básico
    if not has_tran:
        lines.append('.tran 1u 1m')
    
    # Si no tiene .end, añadirlo
    if not has_end:
        lines.append('.end')
    
    return '\n'.join(lines)

def _inject_wrdata_control(netlist_text: str, wr_lines: List[str]) -> str:
    """Inyecta líneas WRDATA en el netlist."""
    lines = netlist_text.strip().split('\n')
    
    # Buscar la última línea .tran para insertar después
    tran_idx = -1
    for i, line in enumerate(lines):
        if '.tran' in line.upper():
            tran_idx = i
    
    # Si encontramos .tran, insertar después
    if tran_idx >= 0:
        lines.insert(tran_idx + 1, '')
        lines.insert(tran_idx + 2, '.control')
        for wr_line in wr_lines:
            lines.insert(tran_idx + 3, wr_line)
        lines.insert(tran_idx + 3 + len(wr_lines), '.endc')
    else:
        # Si no hay .tran, añadir al final antes de .end
        end_idx = len(lines)
        for i, line in enumerate(lines):
            if line.strip().upper() == '.END':
                end_idx = i
                break
        
        lines.insert(end_idx, '')
        lines.insert(end_idx + 1, '.control')
        for wr_line in wr_lines:
            lines.insert(end_idx + 2, wr_line)
        lines.insert(end_idx + 2 + len(wr_lines), '.endc')
    
    return '\n'.join(lines)

# =========================
# SPICE TOOLS
# =========================

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
    
    All files are saved in a consistent backend directory structure.
    """
    
    # Define the backend directory structure
    backend_dir = Path(__file__).parent.parent  # This will be apps/backend
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
        backend_dir = Path(__file__).parent.parent
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
        backend_dir = Path(__file__).parent.parent
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
# EXPORT TOOLS FOR USE IN OTHER MODULES
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
