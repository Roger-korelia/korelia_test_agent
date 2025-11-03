from __future__ import annotations
from typing import List, Optional, Dict, Union, Literal
from enum import Enum
from pydantic import BaseModel, Field


# ============================================================
# Hints para el LLM (todo opcional, el runtime puede ignorarlo)
# ============================================================

class AliasKind(str, Enum):
    NODE = "node"      # alias -> nombre de nodo (p.ej., "VOUT")
    BRANCH = "branch"  # alias -> rama (i(Rx), v(n1,n2))
    EXPR = "expr"      # alias -> expresión SPICE completa (p.ej., "v(VINP,VINN)")

class AnalysisKind(str, Enum):
    OP = "op"
    TRAN = "tran"
    AC = "ac"
    DC = "dc"

class DeviceStrategy(str, Enum):
    K_COUPLED = "K_coupled"  # Trafo como Lp/Ls+K
    IDEAL_FCE = "ideal_FCE"  # Trafo ideal con fuentes controladas
    AUTO = "auto"            # El LLM decide

class SpiceDialect(str, Enum):
    NGSPICE = "ngspice"
    Xyce = "xyce"
    PSPICE = "pspice"


class SpiceAlias(BaseModel):
    name: str = Field(..., description="Nombre lógico del alias (p.ej., 'output_dc', 'vbus').")
    value: str = Field(..., description="Nodo o expresión SPICE: 'VOUT' | 'v(VOUT,PGND)' | 'i(RLOAD)'.")
    kind: AliasKind = Field(default=AliasKind.NODE, description="Tipo de alias: node/branch/expr.")
    description: Optional[str] = Field(default=None, description="Pista breve para el LLM (1–2 líneas).")


class SpiceProbe(BaseModel):
    id: str = Field(..., description="Identificador de la medida, p.ej. 'v_out', 'i_load'.")
    expr: str = Field(..., description="Expresión SPICE; permite @alias:name.")
    unit: Optional[str] = Field(default=None, description="Unidad esperada (informativa).")
    required: bool = Field(default=True, description="Si la medida es crítica para considerar la simulación 'ok'.")
    description: Optional[str] = Field(default=None, description="Pista breve para el LLM.")


class SpiceAnalysis(BaseModel):
    kind: AnalysisKind = Field(default=AnalysisKind.OP, description="Tipo de análisis: op/tran/ac/dc.")
    params: Dict[str, str] = Field(
        default_factory=dict,
        description="Parámetros del análisis (tran: {'tstop':'20m','tstep':'50u'}, ac: {'points':'100','f_start':'10','f_stop':'1Meg'}, etc.)"
    )


class SpiceLibrary(BaseModel):
    name: str = Field(..., description="Nombre lógico de la librería.")
    include: Optional[str] = Field(default=None, description="Ruta a .include si aplica.")
    models: Dict[str, str] = Field(
        default_factory=dict,
        description="Modelos inline: {'1N4001': '.model D1N4001 D(Is=...)', ...}"
    )


class SpiceDeviceMap(BaseModel):
    transformer_strategy: DeviceStrategy = Field(
        default=DeviceStrategy.K_COUPLED,
        description="Cómo materializar transformadores abstractos."
    )
    default_diode: Optional[str] = Field(
        default="1N4148",
        description="Modelo por defecto si falta .model para un diodo."
    )
    default_mosfet: Optional[str] = Field(
        default=None,
        description="Modelo por defecto si falta .model para un MOSFET."
    )
    notes: Optional[str] = Field(default=None, description="Notas breves para el LLM.")


class BuildPolicy(BaseModel):
    """Reglas accionables para el LLM (convenciones y defaults)."""
    naming: Dict[str, str] = Field(default_factory=dict, description="Convenciones: {'ground':'PGND','vout':'VOUT'}")
    node_aliases: Dict[str, str] = Field(default_factory=dict, description="Alias simples de nodo: {'output_dc':'VOUT'}")
    preferred_models: Dict[str, str] = Field(default_factory=dict, description="Preferencias: {'Diode':'1N4001'}")
    fallback_models: Dict[str, str] = Field(default_factory=dict, description="Fallbacks: {'Diode':'1N4148'}")
    transformer_strategy: DeviceStrategy = Field(default=DeviceStrategy.K_COUPLED)
    defaults: Dict[str, str] = Field(default_factory=dict, description="Defaults p.ej. {'Lp':'1m','k':'0.999','ratio':'5'}")
    analyses_default: List[Dict[str, str]] = Field(default_factory=list, description="Analyses por defecto si faltan.")
    options_default: Dict[str, str] = Field(default_factory=dict, description="Opciones por defecto (.options).")
    controls_default: List[str] = Field(default_factory=list, description="Controles por defecto (.control lines).")
    strictness: Literal["strict","lenient"] = Field(default="strict", description="Rigor ante errores de naming/modelos.")


class AuthoringHint(BaseModel):
    key: str = Field(..., description="Clave breve, p.ej. 'probe.vout'.")
    value: str = Field(..., description="Pista corta (1 línea) p.ej. 'usar v(VOUT,PGND) para DC'.")


class DesignContext(BaseModel):
    """Bloque de contexto solo para el LLM (no usado por el runtime)."""
    intent: Optional[str] = Field(default=None, description="Objetivo corto, p.ej. 'PSU 24V/3A con PFC aislada'.")
    assumptions: List[str] = Field(default_factory=list, description="Supuestos (Vin, fsw, etc.).")
    invariants: List[str] = Field(default_factory=list, description="Restricciones que no se deben violar.")
    conventions: List[str] = Field(default_factory=list, description="Normas de nombres, dominios, etc.")
    glossary: Dict[str, str] = Field(default_factory=dict, description="Glosario técnico breve.")
    build_policy: Optional[BuildPolicy] = Field(default=None, description="Reglas accionables.")
    hints: List[AuthoringHint] = Field(default_factory=list, description="Micro-pistas para el LLM.")


class TransformerHint(BaseModel):
    """Pistas por diseño/instancia para materializar un trafo si aparece abstracto en el netlist."""
    strategy: DeviceStrategy = Field(default=DeviceStrategy.K_COUPLED)
    ratio: Optional[float] = Field(default=None, description="Np/Ns si se conoce.")
    Lp: Optional[str] = Field(default=None, description="Inductancia primaria (H, p.ej. '1m').")
    k: Optional[float] = Field(default=None, description="Acoplamiento (0..1).")
    primary_nodes: Optional[List[str]] = Field(default=None, description="['PRI1','PRI2'] si aplica.")
    secondary_nodes: Optional[List[str]] = Field(default=None, description="['SEC1','SEC2'] si aplica.")
    notes: Optional[str] = Field(default=None)


class ComponentHint(BaseModel):
    """Pistas por referencia de componente concreto (R1, D3, M1, ...)."""
    ref: str = Field(..., description="Referencia exacta del componente ('D1','M3',...).")
    spice_model_name: Optional[str] = Field(default=None, description="Nombre de modelo SPICE preferido (p.ej. '1N4001').")
    spice_subckt: Optional[str] = Field(default=None, description="Nombre de subcircuito si aplica.")
    spice_params: Dict[str, Union[str, float, int]] = Field(default_factory=dict, description="Parámetros para el modelo/subckt.")
    roles: Dict[str, str] = Field(default_factory=dict, description="Roles de pines si aportan contexto (A/K, D/G/S...).")
    transformer: Optional[TransformerHint] = Field(default=None, description="Si este ref es un trafo abstracto.")
    notes: Optional[str] = Field(default=None)


# ============================================================
# CONTRATOS EXPLÍCITOS (añadidos) PARA QUE EL AGENTE “LO HAGA BIEN”
# ============================================================

class LibraryResolutionContract(BaseModel):
    """
    Contrato de resolución de librerías. Evita includes relativos rotos.
    El LLM DEBE cumplirlo al construir el netlist final.
    """
    mode: Literal["absolute_only", "inline_only", "mixed"] = Field(
        default="absolute_only",
        description="Cómo deben resolverse los modelos."
    )
    base_dir: Optional[str] = Field(
        default=None,
        description="Si mode='absolute_only' y se proveen rutas relativas en libraries.include, el LLM DEBE resolverlas contra este base_dir."
    )
    require_models_for: List[str] = Field(
        default_factory=list,
        description="Clases/tipos que DEBEN tener modelo explícito ('Diode','MOSFET','Transformer')."
    )


class ControlBlockContract(BaseModel):
    """
    Contrato para el bloque .control: propiedad y unicidad.
    El LLM decide si inyectar o no en función de este contrato.
    """
    ownership: Literal["agent_injects", "user_provided", "auto"] = Field(
        default="auto",
        description="'agent_injects': el agente DEBE crear el bloque; 'user_provided': no debe crearlo; 'auto': decidir según contenido."
    )
    must_be_singleton: bool = Field(
        default=True,
        description="Nunca debe haber más de un bloque .control en el netlist final."
    )
    minimal_lines: List[str] = Field(
        default_factory=lambda: ["set noaskquit", "set filetype=ascii", "set wr_singlescale"],
        description="Líneas mínimas que el bloque debe contener si lo inyecta el agente."
    )
    wrdata_from_probes: bool = Field(
        default=True,
        description="Si el agente inyecta control, debe generar WRDATA/.print a partir de 'probes'."
    )


class SourceIntent(BaseModel):
    """
    Intención de fuentes de entrada para que el LLM elija correctamente
    (p.ej., SINE en .tran en vez de 'AC 220V').
    """
    line_frequency_hz: Optional[float] = Field(default=50.0, description="Frecuencia de red si aplica.")
    vin_rms: Optional[float] = Field(default=None, description="Tensión RMS de línea, p.ej. 230 (V).")
    vin_kind: Literal["sine_mains", "dc", "pwl", "ac_small_signal", "custom"] = Field(
        default="sine_mains",
        description="Tipo de estímulo deseado."
    )
    custom: Optional[str] = Field(default=None, description="Forma de onda textual si vin_kind='custom'.")


class ProbeContract(BaseModel):
    """
    Contrato de medidas: nombres válidos y convenciones de expresión.
    Evita iRload / v(Vsrc) ambiguos.
    """
    allow_vsource_names: bool = Field(
        default=False,
        description="Si False, el LLM NO debe usar v(Vsrc) y debe resolver a v(n+,n-)."
    )
    require_i_parentheses: bool = Field(
        default=True,
        description="Si True, las corrientes SIEMPRE con paréntesis: i(Rload)."
    )
    required_nodes_exist: List[str] = Field(
        default_factory=list,
        description="Nombres de nodos que deben existir en el netlist final (p.ej., ['VOUT','PGND'])."
    )
    alias_policy: Dict[str, str] = Field(
        default_factory=dict,
        description="Alias a resolver antes de construir probes: {'output_dc':'VOUT'}."
    )


class KPIContract(BaseModel):
    """
    (Opcional) Qué KPIs medirá y cómo interpretarlos. El agente lo usa para
    escoger probes y análisis coherentes.
    """
    targets: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description="{'v_out': {'min':23.9,'max':24.1}, 'i_out': {'min':2.95,'max':3.05}}"
    )
    pass_criteria: Literal["all", "any"] = Field(default="all")


# ============================================================
# SCHEMA DE ENTRADA PARA LA TOOL (compatibilidad + contexto LLM)
# ============================================================

class SpiceAutorunInput(BaseModel):
    """Input schema para spice_autorun tool.

    El runtime sólo necesita: input_text, mode, probes, node_expr, from_fraction, timeout_s.
    Todo lo demás son CONTRATOS/HINTS para el LLM: debe usarlos para construir un netlist SPICE correcto
    ANTES de invocar la tool real.
    """

    # ------- Campos consumidos por el runtime (ya existentes) -------
    input_text: str = Field(
        ...,
        description="Netlist SPICE como texto, ruta a archivo .sp/.cir, o código Python para ejecutar"
    )
    mode: Literal["auto", "netlist", "python"] = Field(
        default="auto",
        description="Modo de ejecución: 'auto' detecta automáticamente, 'netlist' para SPICE, 'python' para código Python"
    )
    probes: List[str] = Field(
        default_factory=lambda: ["v(VOUT)"],
        description="Lista de expresiones SPICE a exportar (ej: ['v(VOUT)', 'i(R1)'])"
    )
    node_expr: Optional[str] = Field(
        default="v(VOUT)",
        description="Expresión de nodo por defecto si probes está vacío (fallback)"
    )
    from_fraction: float = Field(
        default=0.5,
        ge=0.0,
        lt=1.0,
        description="Fracción del tiempo de simulación desde la cual calcular métricas (0.0-1.0)"
    )
    timeout_s: int = Field(
        default=120,
        ge=1,
        description="Timeout en segundos para la ejecución"
    )

    # ------- Hints SOLO para el LLM (no los usa directamente el runtime) -------
    dialect: SpiceDialect = Field(
        default=SpiceDialect.NGSPICE,
        description="Dialecto SPICE objetivo para construir el netlist final (ngspice/xyce/pspice)."
    )
    aliases: List[SpiceAlias] = Field(
        default_factory=list,
        description="Alias de nodos/expresiones para resolver probes sin ambigüedad."
    )
    analyses: List[SpiceAnalysis] = Field(
        default_factory=list,
        description="Análisis deseados (.op/.tran/.ac/.dc) con parámetros."
    )
    libraries: List[SpiceLibrary] = Field(
        default_factory=list,
        description="Librerías y modelos SPICE a inyectar (.include/.model)."
    )
    device_map: SpiceDeviceMap = Field(
        default_factory=SpiceDeviceMap,
        description="Estrategias de materialización de dispositivos abstractos (trafo, fallbacks)."
    )
    options: Dict[str, str] = Field(
        default_factory=dict,
        description="Opciones SPICE a incluir (equivalente a .options)."
    )
    controls: List[str] = Field(
        default_factory=list,
        description="Líneas dentro de bloque .control (p.ej., 'set wr_singlescale', 'set filetype=ascii')."
    )
    build_policy: Optional[BuildPolicy] = Field(
        default=None,
        description="Convenciones y defaults para que el LLM resuelva nombres, modelos y estrategias."
    )
    component_hints: List[ComponentHint] = Field(
        default_factory=list,
        description="Pistas por referencia para mapear modelos/subcircuitos, roles o trafos concretos."
    )
    net_name_map: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapeo lógico→real de nodos (p.ej., {'output_dc':'VOUT','gnd':'PGND'})."
    )
    expression_hints: List[str] = Field(
        default_factory=list,
        description="Reglas/ejemplos de cómo expresar medidas válidas (i(RLOAD), v(n+,n-), etc.)."
    )
    retry_policy: Dict[str, Union[int, str]] = Field(
        default_factory=lambda: {"max_attempts": 3, "on_error": "normalize_probes_then_rebuild"},
        description="Pautas para el LLM ante errores de simulación (reintentos, normalización de probes, etc.)."
    )
    description: Optional[str] = Field(
        default=None,
        description="Resumen breve para el LLM sobre qué se espera de la simulación."
    )

    # ------- NUEVO: contratos explícitos para evitar tus fallos típicos -------
    library_resolution: LibraryResolutionContract = Field(
        default_factory=LibraryResolutionContract,
        description="Contrato de includes/modelos (absolutas, inline o mixto)."
    )
    control_contract: ControlBlockContract = Field(
        default_factory=ControlBlockContract,
        description="Contrato para el bloque .control (propiedad y unicidad)."
    )
    source_intent: Optional[SourceIntent] = Field(
        default=None,
        description="Intención de fuente de red/estímulo para elegir SINE/DC/PWL correctamente."
    )
    probe_contract: ProbeContract = Field(
        default_factory=ProbeContract,
        description="Contrato de medidas (nombres válidos y convenciones de expresión)."
    )
    kpi_contract: Optional[KPIContract] = Field(
        default=None,
        description="(Opcional) KPIs objetivo para guiar construcción de probes/análisis."
    )
