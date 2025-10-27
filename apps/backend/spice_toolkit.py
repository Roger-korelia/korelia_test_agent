# spice_toolkit.py
# Módulo unificado: Parser SPICE → Grafo bipartito → Reglas ERC/DRC deterministas → Builder por capas
# Autor: Consolidación de spice_graph.py y spice_builder.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
import re
import json
import time

try:
    import networkx as nx
except ImportError:
    nx = None  # el caller debe manejarlo o instalarlo (pip install networkx)

# --- Config pin-map por tipo SPICE ---
COMP_PINMAP: Dict[str, int] = {
    # Pasivos / fuentes independientes
    'R': 2, 'L': 2, 'C': 2, 'V': 2, 'I': 2, 'D': 2,
    # Activos
    'M': 4,  # MOS: D G S B
    'Q': 3,  # BJT: C B E
    'J': 3,  # JFET: D G S
    # Dependientes / comportamentales
    'E': 4,  # VCVS
    'G': 4,  # VCCS
    'F': 2,  # CCCS: 2 nodos + referencia de control en params
    'H': 2,  # CCVS: 2 nodos + referencia de control en params
    'B': 2,  # Fuente comportamental (al menos 2 nodos de salida)
    # Subcircuitos y acoplos
    'X': -1, # subckt con n pines libre
    'K': 0   # acoplos: no tienen nodos propios
}

# --- Modelos de datos unificados ---
@dataclass
class Pin:
    name: str
    node: str

@dataclass
class Component:
    ref: str
    ctype: str
    pins: List[Pin] = field(default_factory=list)
    params: Dict[str, str] = field(default_factory=dict)
    raw: str = ""   # línea original (debug)

@dataclass
class Layer:
    name: str
    locked: bool = False
    comps: List[Component] = field(default_factory=list)
    notes: str = ""

# --- Utilidades de parsing (del spice_graph.py original) ---
def _norm_node(n: str) -> str:
    s = n.strip()
    return "0" if s.lower() in {"0", "gnd", "gnd!", "earth"} else s

def _tokenize_line(line: str) -> List[str]:
    """
    Tokeniza tolerante:
    - ignora comentarios al inicio con '*'
    - corta comentarios inline después de ';' o '*' (si no están dentro de paréntesis)
    - conserva paréntesis (...) y llaves {...} como un token
    """
    s = line.strip()
    if not s or s.startswith('*'):
        return []
    # elimina comentarios inline (no muy estricto, pero práctico)
    s = re.split(r'(?<!\))\s*;|(?<!\))\s*\*', s)[0]
    # tokens: palabras/num/., operadores simples, paréntesis, llaves
    return re.findall(r'[\w\.\+\-\/!\$]+|\([^\)]*\)|\{[^\}]*\}', s)

def _join_continuations(text: str) -> str:
    """Une líneas SPICE que comienzan con '+' como continuación de la anterior."""
    out: List[str] = []
    acc = ""
    for ln in text.splitlines():
        s = ln.rstrip()
        if s.startswith('+'):
            acc += " " + s[1:].lstrip()
        else:
            if acc:
                out.append(acc)
            acc = s
    if acc:
        out.append(acc)
    return "\n".join(out)

def _is_param_token(t: str) -> bool:
    return ('=' in t) or t.startswith('(') or t.lower().startswith(('model', 'mod', 'type'))

CONTROL_KEYWORDS = {"dc", "ac", "pulse", "sin", "exp", "sffm", "pwl"}

def parse_components(net_text: str) -> List[Component]:
    """Parser SPICE → Lista de componentes (del spice_graph.py original)"""
    lines = _join_continuations(net_text).splitlines()
    
    comps: List[Component] = []
    processed_lines = 0
    skipped_lines = 0
    component_counts = {}
    
    for line_num, ln in enumerate(lines):
        toks = _tokenize_line(ln)
        if not toks:
            skipped_lines += 1
            continue
            
        name = toks[0]
        ctype = name[0].upper()
        if ctype not in COMP_PINMAP:
            # ignoramos directivas (.param/.tran...), includes, o cartas raras
            skipped_lines += 1
            continue
            
        want = COMP_PINMAP[ctype]
        component_counts[ctype] = component_counts.get(ctype, 0) + 1

        if ctype == 'K':  # acoplos: no crean nodos eléctricos
            comps.append(Component(ref=name, ctype=ctype, raw=ln))
            continue

        pins: List[Pin] = []
        params: Dict[str, str] = {}
        rest = toks[1:]

        if want > 0:
            nodetoks = []
            for t in rest:
                if _is_param_token(t):
                    break
                nodetoks.append(t)
                if len(nodetoks) == want:
                    break
            # fallback mínimo de 2 nodos para elementos 2-terminal
            if len(nodetoks) < max(2, min(4, want)):
                nodetoks = rest[:2] if len(rest) >= 2 else rest
            for i, n in enumerate(nodetoks):
                pins.append(Pin(name=str(i+1), node=_norm_node(n)))
            tail = rest[len(nodetoks):]
        else:
            # X-subckt: nodos hasta que aparezcan params
            nodetoks = []
            for t in rest:
                if _is_param_token(t):
                    break
                nodetoks.append(t)
            for i, n in enumerate(nodetoks):
                pins.append(Pin(name=str(i+1), node=_norm_node(n)))
            tail = rest[len(nodetoks):]

        # Captura de valor y formas de onda / control
        i = 0
        if tail:
            t0 = tail[0]
            t0low = t0.lower()
            # Controladas F/H: primer token suele ser fuente de control (nombre de V)
            if ctype in {'F', 'H'} and len(tail) >= 1 and '=' not in t0:
                params['ctrl'] = t0
                i = 1
                if len(tail) > 1 and '=' not in tail[1].lower():
                    params['value'] = tail[1]
                    i = 2
            # Valor puro (R/L/C/D/M etc.)
            elif '=' not in t0 and t0low not in CONTROL_KEYWORDS and not t0.startswith(('(', '{')):
                params['value'] = t0
                i = 1
            # Fuentes independientes: DC/AC/PULSE/SIN/EXP/SFFM/PWL
            if i < len(tail) and tail[i].lower() in CONTROL_KEYWORDS:
                params['waveform'] = tail[i]
                i += 1
                if i < len(tail):
                    params['spec'] = " ".join(tail[i:])
                i = len(tail)
        # resto k=v
        for t in tail[i:]:
            if '=' in t and not t.startswith('='):
                k, v = t.split('=', 1)
                params[k.strip()] = v.strip().strip('()')

        comps.append(Component(ref=name, ctype=ctype, pins=pins, params=params, raw=ln))
        processed_lines += 1
    
    return comps

def build_graph(comps: List[Component]):
    """Constructor de grafo bipartito con MultiGraph para preservar pines y acoplos."""
    if nx is None:
        raise RuntimeError("networkx no instalado. Ejecuta: pip install networkx")
    
    G = nx.MultiGraph()
    
    # Añade componentes como nodos
    for c in comps:
        G.add_node(c.ref, kind="comp", ctype=c.ctype, data=c)
    
    # Añade nodos eléctricos y aristas comp↔nodo
    for c in comps:
        for p in c.pins:
            if p.node not in G.nodes:
                G.add_node(p.node, kind="node")
            G.add_edge(c.ref, p.node, key=f"{c.ref}:{p.name}", pin=p.name, kind="electrical")
        # Añade aristas de acoplo entre inductores para K
        if c.ctype.upper() == 'K' and c.raw:
            toks = _tokenize_line(c.raw)
            if len(toks) >= 3:
                l1, l2 = toks[1], toks[2]
                kval = toks[3] if len(toks) >= 4 else ""
                # Nos aseguramos de que los inductores existan como nodos comp
                if l1 not in G:
                    G.add_node(l1, kind="comp", ctype="L")
                if l2 not in G:
                    G.add_node(l2, kind="comp", ctype="L")
                G.add_edge(l1, l2, kind="coupling", k=kval)
    
    return G

# --- Reglas deterministas ERC/DRC (del spice_graph.py original) ---
def rule_ground_exists(G, ground: str = "0") -> Tuple[List[str], List[str]]:
    nodes = [n for n, d in G.nodes(data=True) if d.get("kind") == "node"]
    if ground not in nodes:
        return (["No existe nodo de referencia '0'."],
                ["Conectar algún punto de retorno a 0 (ground)."])
    return [], []

def rule_min_degree(G, ground: str = "0") -> Tuple[List[str], List[str]]:
    errors, fixes = [], []
    for n, d in G.nodes(data=True):
        if d.get("kind") != "node" or n == ground:
            continue
        if G.degree(n) < 2:
            errors.append(f"Nodo flotante o de grado 1: {n}")
            fixes.append(f"Añadir Rshunt {n} 0 10Meg")
    return errors, fixes

def rule_parallel_voltage_sources(G) -> Tuple[List[str], List[str]]:
    errors, fixes = [], []
    seen = {}
    for c, d in G.nodes(data=True):
        if d.get("kind") != "comp": 
            continue
        if d.get("ctype", "").upper() != "V":
            continue
        nbrs = [nbr for nbr in G.neighbors(c) if G.nodes[nbr].get("kind") == "node"]
        if len(nbrs) == 2:
            key = tuple(sorted(nbrs))
            if key in seen:
                errors.append(f"Fuentes de tensión paralelas: {seen[key]} y {c} en {key}")
                fixes.append(f"Insertar Rserie 10mΩ en {c}")
            else:
                seen[key] = c
    return errors, fixes

def rule_LC_ideal(G) -> Tuple[List[str], List[str]]:
    errors, fixes = [], []
    for comp_ref, d in G.nodes(data=True):
        if d.get("kind") != "comp":
            continue
        ct = d.get("ctype", "").upper()
        if ct not in {"L", "C"}:
            continue
        data = d.get("data")
        raw = getattr(data, "raw", "") if data else ""
        has_rser = bool(re.search(r'(?i)\b(rser|esr|res)\s*=\s*', raw)) or (" Rser=" in raw)
        # Detección estructural: resistencia en serie inmediata
        series_found = False
        for nbr in G.neighbors(comp_ref):
            if G.nodes[nbr].get("kind") != "node":
                continue
            other_comps = [x for x in G.neighbors(nbr) if x != comp_ref and G.nodes[x].get("kind") == "comp"]
            if len(other_comps) == 1 and G.nodes[other_comps[0]].get("ctype", "").upper() == "R":
                series_found = True
                break
        if not has_rser and not series_found:
            errors.append(f"{ct}{comp_ref} sin ESR en serie (param o R en serie).")
            fixes.append(f"Añadir R serie pequeña con {comp_ref} (10m–200mΩ).")
    return errors, fixes

def rule_device_pin_count(G) -> Tuple[List[str], List[str]]:
    errors, fixes = [], []
    for c, d in G.nodes(data=True):
        if d.get("kind") != "comp":
            continue
        ct = d.get("ctype", "").upper()
        want = COMP_PINMAP.get(ct, 2)
        have = len(d["data"].pins)
        # tolerancia: E/G/H/F/B/X no estrictas aquí
        if ct in {"E", "G", "H", "F", "B", "X", "K"}:
            continue
        if want > 0 and have != want:
            errors.append(f"{c} ({ct}) con número de pines inesperado: {have}≠{want}")
            fixes.append(f"Verificar orden de pines y modelo de {c}.")
    return errors, fixes

# --- Clase principal unificada: SpiceToolkit ---
class SpiceToolkit:
    """
    Herramienta unificada que combina:
    - Parser SPICE → Componentes
    - Constructor de grafo bipartito
    - Validación ERC/DRC determinista
    - Builder por capas con validación automática
    """
    
    def __init__(self, ground: str = "0"):
        self.ground = ground
        self.layers: List[Layer] = []
        self.version = 0
        self._graph: Optional[nx.Graph] = None
        self._components: List[Component] = []
        # Feedback tracking for intelligent decision making
        self._feedback_history: List[Dict[str, Any]] = []
        self._validation_history: List[Dict[str, Any]] = []
    
    # === MÉTODOS DE PARSING Y VALIDACIÓN (del spice_graph.py) ===
    
    def parse_netlist(self, net_text: str) -> List[Component]:
        """Parse netlist SPICE text into components"""
        self._components = parse_components(net_text)
        return self._components
    
    def build_graph_from_components(self, comps: Optional[List[Component]] = None) -> nx.Graph:
        """Build bipartite graph from components"""
        if comps is None:
            comps = self._components
        self._graph = build_graph(comps)
        return self._graph
    
    def validate_topology(self, G: Optional[nx.Graph] = None) -> Dict[str, Any]:
        """Run all ERC/DRC rules on the graph"""
        if G is None:
            if self._graph is None:
                raise RuntimeError("No graph available. Build graph first.")
            G = self._graph
        
        start_time = time.time()
        errors: List[str] = []
        fixes: List[str] = []
        
        rules = (rule_ground_exists, rule_min_degree, rule_parallel_voltage_sources, rule_LC_ideal, rule_device_pin_count)
        for rule in rules:
            try:
                if rule.__code__.co_argcount == 2:
                    e, f = rule(G, self.ground)  # type: ignore
                else:
                    e, f = rule(G)          # type: ignore
                errors += e
                fixes  += f
            except Exception as rule_error:
                errors.append(f"Rule {rule.__name__} failed: {rule_error}")
        
        validation_time = time.time() - start_time
        
        return {
            "pass": len(errors) == 0,
            "errors": errors,
            "fixes": fixes,
            "graph_stats": {
                "nodes": G.number_of_nodes(),
                "components": sum(1 for n, d in G.nodes(data=True) if d.get("kind") == "comp"),
                "electrical_nodes": sum(1 for n, d in G.nodes(data=True) if d.get("kind") == "node"),
            },
            "validation_time": validation_time
        }
    
    def run_erc_on_netlist(self, net_text: str) -> Dict[str, Any]:
        """Complete ERC pipeline: parse → graph → validate"""
        # Step 1: Parse components
        parse_start = time.time()
        comps = self.parse_netlist(net_text)
        parse_time = time.time() - parse_start
        
        # Step 2: Build graph
        graph_start = time.time()
        G = self.build_graph_from_components(comps)
        graph_time = time.time() - graph_start
        
        # Step 3: Validate
        validation_result = self.validate_topology(G)
        
        total_time = time.time() - parse_start
        
        return {
            **validation_result,
            "debug_timing": {
                "parse_time": parse_time,
                "graph_time": graph_time,
                "validation_time": validation_result.get("validation_time", 0),
                "total_time": total_time
            }
        }
    
    # === MÉTODOS DE CONSTRUCCIÓN POR CAPAS (del spice_builder.py mejorado) ===
    
    def begin_layer(self, name: str, notes: str = ""):
        """Begin a new layer"""
        if self.layers and not self.layers[-1].locked:
            raise RuntimeError("La capa anterior no está bloqueada. Bloquéala o revierte antes de crear otra.")
        # Evitar duplicados de nombre de capa para mantener historial limpio
        if any(l.name == name for l in self.layers):
            raise RuntimeError(f"La capa '{name}' ya existe. Usa graph_rollback_to('{name}') o crea un nombre distinto.")
        self.layers.append(Layer(name=name, notes=notes))
    
    def lock_layer(self):
        """Lock the current layer"""
        if not self.layers:
            raise RuntimeError("No hay capas.")
        if len(self.layers[-1].comps) == 0:
            raise RuntimeError("No se puede bloquear una capa vacía. Añade componentes primero.")
        self.layers[-1].locked = True
    
    def rollback_to(self, layer_name: str):
        """Rollback to a specific layer"""
        idx = next((i for i,l in enumerate(self.layers) if l.name == layer_name), None)
        if idx is None:
            raise RuntimeError(f"No existe la capa '{layer_name}'.")
        self.layers = self.layers[:idx+1]  # conserva inclusive
        self.layers[-1].locked = False
    
    def add_component(self, ref: str, ctype: str, pins: List[str], params: Optional[Dict[str,str]] = None):
        """Add component to current layer"""
        if not self.layers:
            raise RuntimeError("Primero crea una capa con begin_layer().")
        if self.layers[-1].locked:
            raise RuntimeError("La capa actual está bloqueada. Desbloquéala (rollback) o crea otra capa.")
        
        # Convert pins to Pin objects
        pin_objects = [Pin(name=str(i+1), node=_norm_node(pin)) for i, pin in enumerate(pins)]
        
        # Create component
        comp = Component(ref=ref, ctype=ctype, pins=pin_objects, params=params or {})
        self.layers[-1].comps.append(comp)
        self.version += 1
    
    def edit_component(self, ref: str, **updates):
        """Edit existing component in current layer"""
        if not self.layers:
            raise RuntimeError("No hay capas.")
        if self.layers[-1].locked:
            raise RuntimeError("La capa actual está bloqueada.")
        
        PIN_ALIAS = {
            'D': {'A': '1', 'K': '2'},
            'Q': {'C': '1', 'B': '2', 'E': '3'},
            'J': {'D': '1', 'G': '2', 'S': '3'},
            'M': {'D': '1', 'G': '2', 'S': '3', 'B': '4'},
        }
        
        for c in self.layers[-1].comps:
            if c.ref == ref:
                if "pins" in updates:
                    pins = updates["pins"]
                    # Case 1: dict mapping (supports alias names)
                    if isinstance(pins, dict):
                        mapping: Dict[str, str] = {}
                        # Normalize keys using alias by component type when needed
                        if any(not str(k).isdigit() for k in pins.keys()):
                            alias = PIN_ALIAS.get(c.ctype.upper(), {})
                            for k, v in pins.items():
                                num = alias.get(str(k).upper()) or str(k)
                                mapping[num] = _norm_node(v)
                        else:
                            mapping = {str(k): _norm_node(v) for k, v in pins.items()}
                        # Update existing pins by position name ("1","2",...)
                        for p in c.pins:
                            if p.name in mapping:
                                p.node = mapping[p.name]
                    # Case 2: list of nodes → rebuild pin list in order
                    elif isinstance(pins, list):
                        if pins and isinstance(pins[0], str):
                            c.pins = [Pin(name=str(i+1), node=_norm_node(pin)) for i, pin in enumerate(pins)]
                        else:
                            # Already a list[Pin]
                            c.pins = pins
                    else:
                        raise RuntimeError("Formato de 'pins' no soportado: use lista o diccionario")
                if "params" in updates:
                    c.params.update(updates["params"])
                if "ctype" in updates:
                    c.ctype = updates["ctype"]
                self.version += 1
                return
        raise RuntimeError(f"No existe el componente {ref} en la capa actual.")
    
    def validate_current_layer(self, require_pass: bool = True, construction_phase: str = "in_progress") -> Dict[str, Any]:
        """Validate the current layer's topology with contextual validation"""
        if not self.layers:
            raise RuntimeError("No hay capas para validar.")
        
        # Get all components from all layers
        all_comps = []
        for layer in self.layers:
            all_comps.extend(layer.comps)
        
        if not all_comps:
            # Sin componentes aún: no pasar validación cuando se solicita bloqueo
            return {"pass": False, "errors": ["No hay componentes para validar"], "fixes": ["Añadir componentes a la capa actual"], "message": "Sin componentes"}
        
        # Apply contextual validation based on construction phase
        if construction_phase == "in_progress":
            return self._validate_construction_phase(all_comps)
        elif construction_phase == "layer_complete":
            return self._validate_layer_complete(all_comps)
        elif construction_phase == "final":
            return self._validate_final_design(all_comps)
        else:
            # Default to construction phase
            return self._validate_construction_phase(all_comps)
    
    def _validate_construction_phase(self, all_comps: List[Component]) -> Dict[str, Any]:
        """Validaciones suaves durante construcción incremental"""
        G = build_graph(all_comps)
        critical_errors = []
        warnings = []
        fixes = []
        
        # Solo errores críticos durante construcción
        for rule in [rule_device_pin_count, rule_parallel_voltage_sources]:
            try:
                errors, rule_fixes = rule(G)
                critical_errors.extend(errors)
                fixes.extend(rule_fixes)
            except Exception:
                pass  # Ignorar errores en reglas durante construcción
        
        # Warnings (no errores) para cosas que se pueden resolver después
        try:
            ground_errors, ground_fixes = rule_ground_exists(G, self.ground)
            warnings.extend(ground_errors)
            fixes.extend(ground_fixes)
        except Exception:
            pass
        
        try:
            floating_errors, floating_fixes = rule_min_degree(G, self.ground)
            warnings.extend(floating_errors)
            fixes.extend(floating_fixes)
        except Exception:
            pass
        
        try:
            lc_errors, lc_fixes = rule_LC_ideal(G)
            warnings.extend(lc_errors)
            fixes.extend(lc_fixes)
        except Exception:
            pass
        
        return {
            "pass": len(critical_errors) == 0,
            "errors": critical_errors,
            "warnings": warnings,
            "fixes": fixes,
            "construction_phase": "in_progress",
            "message": f"Construcción en progreso: {len(warnings)} advertencias, {len(critical_errors)} errores críticos"
        }
    
    def _validate_layer_complete(self, all_comps: List[Component]) -> Dict[str, Any]:
        """Validaciones moderadas al completar una capa"""
        G = build_graph(all_comps)
        errors = []
        fixes = []
        
        # Validaciones más estrictas pero no extremas
        for rule in [rule_ground_exists, rule_device_pin_count, rule_parallel_voltage_sources]:
            try:
                if rule.__code__.co_argcount == 2:
                    rule_errors, rule_fixes = rule(G, self.ground)  # type: ignore
                else:
                    rule_errors, rule_fixes = rule(G)  # type: ignore
                errors.extend(rule_errors)
                fixes.extend(rule_fixes)
            except Exception:
                pass
        
        # Para nodos flotantes, solo warning si hay pocos componentes
        if len(all_comps) < 5:  # Capa temprana
            try:
                floating_errors, floating_fixes = rule_min_degree(G, self.ground)
                # Convertir a warnings si es capa temprana
                for error in floating_errors:
                    errors.append(f"ADVERTENCIA: {error}")
                fixes.extend(floating_fixes)
            except Exception:
                pass
        else:  # Capa más avanzada
            try:
                floating_errors, floating_fixes = rule_min_degree(G, self.ground)
                errors.extend(floating_errors)
                fixes.extend(floating_fixes)
            except Exception:
                pass
        
        return {
            "pass": len(errors) == 0,
            "errors": errors,
            "fixes": fixes,
            "construction_phase": "layer_complete",
            "message": f"Capa completada: {len(errors)} problemas encontrados"
        }
    
    def _validate_final_design(self, all_comps: List[Component]) -> Dict[str, Any]:
        """Validación estricta para diseño final"""
        G = build_graph(all_comps)
        result = self.validate_topology(G)
        
        return {
            **result,
            "construction_phase": "final",
            "message": f"Diseño final: {len(result.get('errors', []))} errores, {len(result.get('fixes', []))} sugerencias"
        }
    
    def emit_spice(self, title: str = "Layered Netlist") -> str:
        """Emit SPICE netlist from all layers."""
        lines = [f"* {title}", ""]
        
        for ly in self.layers:
            lines.append(f"* --- layer: {ly.name} (locked={ly.locked}) ---")
            for c in ly.comps:
                pinstr = " ".join([p.node for p in c.pins])
                pitems: List[str] = []
                if c.params:
                    if "value" in c.params:
                        pitems.append(str(c.params["value"]))
                    # Emit waveform(spec) ensuring parentheses for time-domain sources
                    if "waveform" in c.params:
                        wf = str(c.params["waveform"]).strip()
                        spec = str(c.params.get("spec", "")).strip()
                        if spec:
                            # Avoid double parentheses
                            spec_formatted = spec if spec.startswith("(") and spec.endswith(")") else f"({spec})"
                            pitems.append(f"{wf}{spec_formatted}")
                        else:
                            pitems.append(wf)
                    for k, v in c.params.items():
                        if k in {"value", "waveform", "spec"}:
                            continue
                        pitems.append(f"{k}={v}")
                tail = " ".join(pitems).strip()
                line = f"{c.ref} {pinstr} {tail}".strip()
                lines.append(line)
            lines.append("")
        
        return "\n".join(lines).rstrip() + "\n"
    
    def get_layer_summary(self) -> Dict[str, Any]:
        """Get summary of all layers"""
        return {
            "total_layers": len(self.layers),
            "locked_layers": sum(1 for l in self.layers if l.locked),
            "total_components": sum(len(l.comps) for l in self.layers),
            "layers": [
                {
                    "name": l.name,
                    "locked": l.locked,
                    "component_count": len(l.comps),
                    "notes": l.notes
                }
                for l in self.layers
            ]
        }
    
    def get_graph(self) -> Optional[nx.Graph]:
        """Get the current graph"""
        return self._graph
    
    def get_components(self) -> List[Component]:
        """Get all components from all layers"""
        all_comps = []
        for layer in self.layers:
            all_comps.extend(layer.comps)
        return all_comps
    
    def analyze_implementation_progress(self, component_list: str = "") -> Dict[str, Any]:
        """Analyze implementation progress and provide intelligent feedback"""
        all_comps = self.get_components()
        
        # Parse component list if provided
        expected_components = []
        if component_list:
            lines = component_list.split('\n')
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Simple parsing of component list format
                    parts = line.split()
                    if len(parts) >= 2:
                        expected_components.append({
                            'ref': parts[0],
                            'type': parts[1],
                            'description': ' '.join(parts[2:]) if len(parts) > 2 else ''
                        })
        
        # Analyze current implementation
        implemented_types = {}
        implemented_refs = []
        missing_components = []
        extra_components = []
        
        for comp in all_comps:
            implemented_types[comp.ctype] = implemented_types.get(comp.ctype, 0) + 1
            implemented_refs.append(comp.ref)
        
        # Check against expected components
        expected_refs = [comp['ref'] for comp in expected_components]
        missing_components = [comp for comp in expected_components if comp['ref'] not in implemented_refs]
        extra_components = [ref for ref in implemented_refs if ref not in expected_refs]
        
        # Generate intelligent feedback
        feedback = {
            'implementation_status': 'in_progress' if missing_components else 'complete',
            'progress_percentage': len(implemented_refs) / max(len(expected_refs), 1) * 100,
            'implemented_components': len(implemented_refs),
            'expected_components': len(expected_refs),
            'missing_components': missing_components,
            'extra_components': extra_components,
            'component_types': implemented_types,
            'layer_summary': self.get_layer_summary(),
            'recommendations': []
        }
        
        # Generate recommendations
        if missing_components:
            feedback['recommendations'].append(f"Faltan {len(missing_components)} componentes por implementar")
            for missing in missing_components[:3]:  # Show first 3
                feedback['recommendations'].append(f"- {missing['ref']} ({missing['type']}): {missing['description']}")
        
        if extra_components:
            feedback['recommendations'].append(f"Componentes adicionales implementados: {', '.join(extra_components)}")
        
        # Layer-specific recommendations
        if self.layers:
            current_layer = self.layers[-1]
            if not current_layer.locked:
                feedback['recommendations'].append(f"Capas completadas: {len([l for l in self.layers if l.locked])}/{len(self.layers)}")
                feedback['recommendations'].append(f"Capa actual '{current_layer.name}': {len(current_layer.comps)} componentes")
        
        return feedback
    
    def add_feedback(self, operation: str, component_ref: str = "", feedback_data: Dict[str, Any] = None):
        """Add feedback to history for intelligent decision making"""
        if feedback_data is None:
            feedback_data = {}
        
        feedback_entry = {
            "timestamp": time.time(),
            "operation": operation,
            "component_ref": component_ref,
            "layer": self.layers[-1].name if self.layers else "none",
            "data": feedback_data
        }
        
        self._feedback_history.append(feedback_entry)
        
        # Keep only last 50 feedback entries to prevent memory issues
        if len(self._feedback_history) > 50:
            self._feedback_history = self._feedback_history[-50:]
    
    def get_feedback_summary(self) -> Dict[str, Any]:
        """Get summary of feedback history for decision making"""
        if not self._feedback_history:
            return {
                "total_feedback": 0, 
                "recent_operations": 0,
                "operation_counts": {},
                "warning_counts": {},
                "error_counts": {},
                "insights": [],
                "summary": "No feedback available"
            }
        
        # Analyze recent feedback patterns
        recent_feedback = self._feedback_history[-10:]  # Last 10 operations
        
        # Count operations by type
        operation_counts = {}
        warning_counts = {}
        error_counts = {}
        
        for entry in recent_feedback:
            op = entry["operation"]
            operation_counts[op] = operation_counts.get(op, 0) + 1
            
            data = entry.get("data", {})
            if "warnings" in data:
                warning_counts[op] = warning_counts.get(op, 0) + len(data["warnings"])
            if "errors" in data:
                error_counts[op] = error_counts.get(op, 0) + len(data["errors"])
        
        # Generate insights
        insights = []
        if warning_counts:
            total_warnings = sum(warning_counts.values())
            insights.append(f"Total warnings in last operations: {total_warnings}")
        
        if error_counts:
            total_errors = sum(error_counts.values())
            insights.append(f"Total errors in last operations: {total_errors}")
        
        # Most common operations
        if operation_counts:
            most_common = max(operation_counts.items(), key=lambda x: x[1])
            insights.append(f"Most common operation: {most_common[0]} ({most_common[1]} times)")
        
        return {
            "total_feedback": len(self._feedback_history),
            "recent_operations": len(recent_feedback),
            "operation_counts": operation_counts,
            "warning_counts": warning_counts,
            "error_counts": error_counts,
            "insights": insights,
            "summary": "; ".join(insights) if insights else "No significant patterns detected"
        }
    
    def get_decision_recommendations(self) -> List[str]:
        """Get recommendations based on feedback history"""
        recommendations = []
        feedback_summary = self.get_feedback_summary()
        
        # Analyze patterns and provide recommendations
        if feedback_summary["error_counts"]:
            total_errors = sum(feedback_summary["error_counts"].values())
            if total_errors > 3:
                recommendations.append("Multiple errors detected - consider using graph_validate_construction() for detailed analysis")
        
        if feedback_summary["warning_counts"]:
            total_warnings = sum(feedback_summary["warning_counts"].values())
            if total_warnings > 5:
                recommendations.append("Many warnings detected - consider adding missing components or connections")
        
        # Check for repeated operations
        operation_counts = feedback_summary["operation_counts"]
        if "add_component" in operation_counts and operation_counts["add_component"] > 5:
            recommendations.append("Many components added recently - consider using graph_analyze_progress() to check completion")
        
        if not recommendations:
            recommendations.append("Feedback patterns look normal - continue with current approach")
        
        return recommendations

    # === JSON-driven netlist workflow helpers ===
    def apply_netlist_json(self, net_spec: Dict[str, Any], allow_autolock: bool = True) -> Dict[str, Any]:
        """Apply a JSON netlist specification into layered builder state.

        Schema examples accepted:
        {
          "title": "Layered Netlist",
          "layers": [
            {"name": "input", "notes": "", "locked": true,
             "components": [
               {"ref":"V1","type":"V","pins":["AC_L","0"],"params":{"waveform":"SIN","spec":"0 311 50"}}
             ]}
          ]
        }

        Or a flat form (auto-wrapped into a single layer):
        { "components": [ {"ref":"R1","type":"R","pins":["N1","N2"],"params":{"value":"1k"}} ] }
        """
        # Reset layers and rebuild from spec
        self.layers = []

        def _apply_layer(layer_spec: Dict[str, Any], is_last: bool) -> None:
            name = str(layer_spec.get("name") or f"layer-{len(self.layers)+1}")
            notes = str(layer_spec.get("notes") or "")
            # begin layer
            self.begin_layer(name, notes)

            comps = layer_spec.get("components") or []
            for comp in comps:
                ref = str(comp.get("ref") or "")
                ctype = str(comp.get("type") or comp.get("ctype") or "").upper()
                pins_spec = comp.get("pins") or []
                params = comp.get("params") or {}

                # pins may be list [node1,node2,...] or dict {"1":"N1","2":"N2"}
                if isinstance(pins_spec, dict):
                    # order by numeric key when possible
                    try:
                        ordered = [pins_spec[k] for k in sorted(pins_spec.keys(), key=lambda x: int(str(x)))]
                    except Exception:
                        ordered = list(pins_spec.values())
                    pins_list = [str(n) for n in ordered]
                elif isinstance(pins_spec, list):
                    pins_list = [str(n) for n in pins_spec]
                else:
                    pins_list = []

                # Fallback minimal pin list (avoid exceptions)
                if not pins_list:
                    pins_list = ["0", "0"]

                self.add_component(ref=ref, ctype=ctype, pins=pins_list, params=params)

            # Lock policy: if JSON says locked or if autolock and this is not the last layer
            want_locked = bool(layer_spec.get("locked", False)) or (allow_autolock and not is_last)
            if want_locked:
                try:
                    self.lock_layer()
                except Exception:
                    # Ignore locking errors for empty layers
                    pass

        # Normalize to layered form
        if isinstance(net_spec, dict) and "layers" in net_spec:
            layers: List[Dict[str, Any]] = net_spec.get("layers") or []
            for idx, layer in enumerate(layers):
                _apply_layer(layer, is_last=(idx == len(layers) - 1))
        else:
            _apply_layer({
                "name": str(net_spec.get("name") if isinstance(net_spec, dict) else "auto"),
                "notes": str(net_spec.get("notes") if isinstance(net_spec, dict) else ""),
                "components": (net_spec.get("components") if isinstance(net_spec, dict) else [])
            }, is_last=True)

        # Provide summary and initial validation feedback (moderate)
        summary = self.get_layer_summary()
        try:
            validation = self.validate_current_layer(require_pass=False, construction_phase="layer_complete")
        except Exception as e:
            validation = {"pass": False, "errors": [str(e)], "warnings": []}

        return {"summary": summary, "validation": validation}

    def export_netlist_json(self) -> Dict[str, Any]:
        """Export current layered state to JSON schema used by apply_netlist_json."""
        layers_json: List[Dict[str, Any]] = []
        for ly in self.layers:
            comps_json: List[Dict[str, Any]] = []
            for c in ly.comps:
                comps_json.append({
                    "ref": c.ref,
                    "type": c.ctype,
                    "pins": [p.node for p in c.pins],
                    "params": dict(c.params) if c.params else {}
                })
            layers_json.append({
                "name": ly.name,
                "notes": ly.notes,
                "locked": ly.locked,
                "components": comps_json
            })
        return {"title": "Layered Netlist", "layers": layers_json}

    def validate_design(self, construction_phase: str = "layer_complete", require_pass: bool = False) -> Dict[str, Any]:
        """Wrapper around contextual validation for convenience from tools."""
        try:
            return self.validate_current_layer(require_pass=require_pass, construction_phase=construction_phase)
        except Exception as e:
            return {"pass": False, "errors": [str(e)], "warnings": [], "construction_phase": construction_phase}

# === FUNCIONES DE CONVENIENCIA PARA COMPATIBILIDAD ===

def run_erc_on_netlist(net_text: str, ground: str = "0") -> Dict[str, Any]:
    """Función de conveniencia para compatibilidad con código existente"""
    toolkit = SpiceToolkit(ground)
    return toolkit.run_erc_on_netlist(net_text)

# === EXPORTS ===
__all__ = [
    "SpiceToolkit",
    "Component", "Pin", "Layer",
    "parse_components", "build_graph", "run_erc_on_netlist",
    "rule_ground_exists", "rule_min_degree", "rule_parallel_voltage_sources",
    "rule_LC_ideal", "rule_device_pin_count",
    "COMP_PINMAP"
]
