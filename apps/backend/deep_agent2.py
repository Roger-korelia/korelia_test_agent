import os
import json
from typing import Literal, Dict, Any, List, Optional, Annotated, TypedDict
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

load_dotenv()

# =========================
# 1) MODEL CONFIGURATION
# =========================
llm_base = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)

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
# 3) DEEP AGENTS SYSTEM PROMPT
# =========================
DEEP_AGENTS_SYSTEM_PROMPT = """You are an expert AI assistant with access to powerful tools for planning, file management, and task execution.

## Core Capabilities:
- **Planning**: Create detailed plans for complex tasks
- **File Management**: Read, write, and manage files in a virtual file system
- **Tool Usage**: Execute various specialized tools for calculations and analysis
- **Sub-Agent Coordination**: Delegate tasks to specialized sub-agents when needed

## Workflow Guidelines:
1. **PLAN FIRST**: Always start by creating a plan using the planning tool
2. **EXECUTE SYSTEMATICALLY**: Follow your plan step by step
3. **USE TOOLS APPROPRIATELY**: Leverage available tools for calculations, file operations, and analysis
4. **MAINTAIN CONTEXT**: Keep track of progress and update your plan as needed
5. **VALIDATE RESULTS**: Check your work and ensure quality

## Tool Usage Rules:
- Use `write_todos` to create and track your plan
- Use file system tools (`write_file`, `read_file`, `list_files`, `edit_file`) to manage documents
- Use specialized tools (`reg_check`, `ee_calc`, `component_suggest`, `sim_estimator`) for technical tasks
- Always explain what you're doing and why

## Response Format:
- Be clear and structured in your responses
- Reference your plan and progress
- Explain technical decisions and calculations
- Provide actionable next steps

Remember: You are working on complex engineering tasks that require careful planning and systematic execution."""

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

@tool("reg_check")
def reg_check(requirements: str) -> str:
    """Valida (heurísticamente) mapeo de requisitos a normativas típicas: IEC 62368-1, IEC 61000-x, IPC-2221, UL94, ISO 9001, etc.
    Devuelve un breve dict-like en texto con 'normas_sugeridas' y 'observaciones'."""
    norms = []
    if "EMC" in requirements or "emc" in requirements or "ruido" in requirements:
        norms += ["IEC 61000-6-1/2/3/4"]
    if "seguridad" in requirements or "ac" in requirements.lower():
        norms += ["IEC 62368-1", "IEC 60664"]
    if "pcb" in requirements.lower() or "placa" in requirements.lower():
        norms += ["IPC-2221", "IPC-7351"]
    if "material" in requirements.lower():
        norms += ["UL 94"]
    if "calidad" in requirements.lower():
        norms += ["ISO 9001"]
    if not norms:
        norms = ["Revisar IEEE/IEC aplicables según dominio."]
    return str({"normas_sugeridas": norms, "observaciones": "Revisar límites, ensayos y marcado CE si aplica."})

@tool("ee_calc")
def ee_calc(expression: str) -> str:
    """Calculadora eléctrica simple: acepta expresiones Python seguras (por ejemplo '24*3', '(5e-3)**2 * 4.7e3'). Devuelve el resultado como str."""
    try:
        allowed_names = {"__builtins__": {}}
        result = eval(expression, allowed_names, {})
        return str(result)
    except Exception as e:
        return f"ERROR: {e}"

@tool("component_suggest")
def component_suggest(hint: str) -> str:
    """Sugiere tipos de componentes en base a una pista (p.ej., 'MOSFET 150V 10A, LDO 3.3V 1A, optoacoplador'), sin marcas específicas."""
    if "flyback" in hint.lower():
        return "Topología flyback: controlador PWM aislado, MOSFET >600V, diodo rápido, trafo EE, optoacoplador, TL431."
    if "buck" in hint.lower():
        return "Topología buck: controlador síncrono, MOSFETs de canal N, inductor de potencia, diodo/rectificación síncrona, condensadores de baja ESR."
    return "Componentes genéricos: MCU, ADC, LDO, regulador conmutado, MOSFET, BJT, op-amp, TVS, NTC, optoacoplador, conector, sensor."

@tool("sim_estimator")
def sim_estimator(setup: str) -> str:
    """Estimador de simulación conceptual: produce métricas esperadas (ripple, eficiencia, margen de fase) de forma razonada (no experimental)."""
    out = {
        "supuestos": ["Valores nominales, cargas típicas, condiciones ambientales estándar"],
        "métricas": {"eficiencia(%)": "87-92", "ripple_mVpp": "20-60", "margen_fase_deg": "45-60"},
        "limitaciones": "Estimación conceptual; validar con SPICE/LTspice."
    }
    return str(out)

# =========================
# 6) SUB-AGENT DEFINITIONS
# =========================

class SubAgent:
    def __init__(self, name: str, description: str, prompt: str, tools: List[str]):
        self.name = name
        self.description = description
        self.prompt = prompt
        self.tools = tools

# Define sub-agents similar to your deep_agent.py
subagents = {
    "reg_check_agent": SubAgent(
        name="reg-check-agent",
        description="Used to check electronic component requirements and provide recommendations",
        prompt="""You are an expert in electronic components and circuit design.
        When given requirements or hints about a circuit design, provide appropriate component recommendations.
        Focus on power electronics, analog circuits, and digital interfaces.""",
        tools=["reg_check"]
    ),
    "design_agent": SubAgent(
        name="design-agent", 
        description="Used to propose and elaborate electronic circuit designs according to given specifications",
        prompt="""You are an expert electronics design engineer.
        Given requirements and specifications, you propose and elaborate detailed circuit designs.
        You take into account constraints, safety, and use clear schematics and rationales.
        Focus on power electronics, analog circuits, and digital interfaces.""",
        tools=["component_suggest", "ee_calc"]
    ),
    "sim_agent": SubAgent(
        name="sim-agent",
        description="Used to estimate simulation parameters and requirements", 
        prompt="""You are an expert in circuit simulation and modeling.
        When given circuit specifications, estimate appropriate simulation parameters and requirements.
        Consider factors like time steps, convergence, and component models.
        Focus on power electronics, analog circuits, and digital interfaces.""",
        tools=["sim_estimator"]
    )
}

# =========================
# 7) GRAPH CONSTRUCTION (Using LangGraph's Built-in ReAct Agent)
# =========================

def create_deep_agent_graph():
    """Create the Deep Agent graph using LangGraph's built-in ReAct agent."""
    from langgraph.prebuilt import create_react_agent
    
    # Get all available tools
    all_tools = [
        write_todos, write_file, read_file, list_files, edit_file,
        reg_check, ee_calc, component_suggest, sim_estimator
    ]
    
    # Create the ReAct agent with our system prompt and tools
    agent = create_react_agent(
        llm_base,
        all_tools,
        state_modifier=DEEP_AGENTS_SYSTEM_PROMPT
    )
    
    # The agent is already compiled, just add memory
    memory = MemorySaver()
    agent.checkpointer = memory
    return agent

# =========================
# 9) MAIN EXECUTION
# =========================

def create_electronics_deep_agent():
    """Create and return the electronics deep agent."""
    return create_deep_agent_graph()

# Create the agent
agent = create_electronics_deep_agent()

# Example usage
if __name__ == "__main__":
    import sys
    
    # Choose task based on command line argument or default
    if len(sys.argv) > 1 and sys.argv[1] == "simple":
        task = "What is the capital of France?"
    else:
        task = "Diseñar una fuente conmutada de 24V/3A desde 220VAC, eficiencia >88%, ripple <50mVpp, protección OCP/OTP, cumplimiento IEC 62368-1 e IEC 61000-6-1/2/3/4, entorno -10..+60°C."
    
    # Test with chosen task - ReAct agent expects messages format
    initial_state = {
        "messages": [
            HumanMessage(content=task)
        ]
    }
    
    config = {"configurable": {"thread_id": "electronics_design"}}
    
    print("Starting Deep Agent execution...")
    print("=" * 50)
    
    # Stream the execution with clean output
    print("🤖 Deep Agent is working on your electronics design task...")
    print("=" * 60)
    
    for chunk in agent.stream(initial_state, config=config, stream_mode="values"):
        if "messages" in chunk and chunk["messages"]:
            last_message = chunk["messages"][-1]
            
            if isinstance(last_message, AIMessage):
                if last_message.content and last_message.content.strip():
                    print(f"\n🧠 Agent Response:")
                    print(f"{last_message.content}")
                    print("-" * 40)
                
                if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
                    for tool_call in last_message.tool_calls:
                        print(f"🔧 Using tool: {tool_call['name']}")
                        
            elif isinstance(last_message, ToolMessage):
                print(f"📋 Tool Result: {last_message.content}")
                print("-" * 40)
    
    print("=" * 50)
    print("Deep Agent execution completed!")