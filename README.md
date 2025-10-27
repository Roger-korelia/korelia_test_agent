# Korelia Agent

A full-stack AI agent application for circuit design and analysis, built with Next.js 15, React 19, and Python FastAPI. This project provides a multi-agent system with graph-based validation, real-time pipeline management, and comprehensive circuit design tools.

## 🚀 Features

- **Multi-Agent System**: Specialized AI agents for circuit design (spec, topology, netlist)
- **Graph-Based Validation**: Automatic topology checking with deterministic ERC/DRC rules
- **Circuit Design Pipeline**: Complete workflow from specifications to KiCad integration
- **Modern Frontend**: Next.js 15 with React 19 and App Router
- **Real-time Pipeline**: Visual pipeline creation and monitoring with WebSocket streaming
- **Modern UI**: Tailwind CSS with Shadcn UI components
- **Type Safety**: Full TypeScript implementation
- **Docker Support**: Containerized development and deployment
- **KiCad Integration**: Direct integration with KiCad CLI tools
- **SPICE Simulation**: NGSpice integration for circuit simulation

## 📁 Project Structure

```
Korelia_agent/
├── apps/
│   ├── frontend/                    # Next.js 15 application
│   │   ├── app/                     # App Router pages and API routes
│   │   │   ├── api/                 # API routes
│   │   │   │   ├── chat/            # Chat API endpoint
│   │   │   │   └── pipeline/        # Pipeline management API
│   │   │   ├── chat/                # Chat interface page
│   │   │   ├── projects/            # Project management pages
│   │   │   │   └── [id]/            # Dynamic project pages
│   │   │   ├── globals.css          # Global styles
│   │   │   ├── layout.tsx           # Root layout
│   │   │   └── page.tsx             # Home page
│   │   ├── types/                   # TypeScript type definitions
│   │   ├── package.json             # Frontend dependencies
│   │   ├── tailwind.config.ts       # Tailwind configuration
│   │   └── tsconfig.json            # TypeScript configuration
│   └── backend/                     # Python FastAPI backend
│       ├── main.py                  # FastAPI application entry point
│       ├── multi_agent.py           # Multi-agent orchestration system
│       ├── agents/                  # Specialized AI agents
│       │   ├── spec_agent.py        # Specification analysis agent
│       │   ├── topology_agent.py    # Circuit topology design agent
│       │   └── netlist_agent.py     # Netlist generation agent
│       ├── graph/                   # Graph-based validation system
│       │   ├── context.py           # Graph context management
│       │   ├── patcher.py           # Graph patching operations
│       │   ├── validators.py        # Validation logic
│       │   ├── rulesets.py          # Rule set definitions
│       │   └── store.py             # Graph storage
│       ├── rules/                   # Circuit validation rules
│       │   ├── engine.py            # Rules engine
│       │   ├── base.py              # Base rule classes
│       │   └── power_base.py        # Power-specific rules
│       ├── schema/                  # Pydantic schema definitions
│       │   ├── graph_patch_schema.py # Graph patch operations
│       │   ├── netlist_schema.py    # Netlist data models
│       │   ├── spec_schema.py       # Specification data models
│       │   ├── topology_schema.py   # Topology data models
│       │   └── violations_schema.py # Validation violation models
│       ├── toolkit/                 # Core toolkit functionality
│       │   └── toolkit.py           # Main toolkit class
│       ├── tools/                   # External tool integrations
│       │   └── run_tools.py         # KiCad and SPICE tool runners
│       ├── PSU_24V_3A_PFC/          # Example KiCad project
│       ├── requirements.txt         # Python dependencies
│       └── Dockerfile               # Backend container definition
├── docker-compose.yaml              # Multi-service orchestration
├── package.json                     # Root package configuration
└── README.md                        # This file
```

## 🛠️ Tech Stack

### Frontend
- **Framework**: Next.js 15 with App Router
- **React**: React 19 with Server Components
- **Styling**: Tailwind CSS + Shadcn UI
- **TypeScript**: Full type safety
- **AI Integration**: Vercel AI SDK for chat functionality
- **State Management**: React hooks and context

### Backend
- **Framework**: FastAPI with async/await
- **Python**: 3.8+
- **AI Integration**: LangGraph for multi-agent orchestration
- **Circuit Processing**: NetworkX for graph-based analysis
- **Validation**: Deterministic ERC/DRC rules engine
- **Real-time**: WebSocket support for pipeline events
- **External Tools**: KiCad CLI, NGSpice integration

### DevOps
- **Containerization**: Docker + Docker Compose
- **Database**: PostgreSQL for data persistence
- **Cache**: Redis for session management
- **Storage**: MinIO for file storage
- **Development**: Hot reload for both frontend and backend

## 🚀 Getting Started

### Prerequisites

- **Node.js**: 18+ (for frontend)
- **Python**: 3.8+ (for backend)
- **Docker**: Latest version (optional but recommended)
- **Git**: For version control
- **OpenAI API Key**: Required for AI functionality
- **KiCad**: Optional, for PCB design integration
- **NGSpice**: Optional, for circuit simulation

### Environment Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/Roger-korelia/korelia_test_agent.git
   cd Korelia_agent
   ```

2. **Create environment file**
   ```bash
   # Create .env file in the root directory
   echo "OPENAI_API_KEY=your_openai_api_key_here" > .env
   echo "NGSPICE=C:\\Program Files\\Spice64\\bin\\ngspice.exe" >> .env
   echo "KICAD_CLI=C:\\Program Files\\KiCad\\8.0\\bin\\kicad-cli.exe" >> .env
   ```

### Quick Start with Docker

1. **Start all services**
   ```bash
   docker-compose up
   ```

2. **Access the application**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs

### Manual Development Setup

#### Backend Setup
```bash
cd apps/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

#### Frontend Setup
```bash
cd apps/frontend
npm install
npm run dev
```

### Direct Backend Usage

#### Using test_agent.py
```bash
cd apps/backend
python test_agent.py
```

This will run a simple test with the prompt: "Diseña una PSU 24V/3A aislada con PFC"

#### Using multi_agent.py directly
```python
from multi_agent import run_orchestrated_workflow

# Run a custom design task
result = run_orchestrated_workflow("Diseña un LED driver 3.3V con control PWM")
print(result)
```

#### Using individual agents
```python
from agents.spec_agent import SpecAgent
from agents.topology_agent import TopologyAgent
from agents.netlist_agent import NetlistAgent

# Initialize agents
spec_agent = SpecAgent()
topology_agent = TopologyAgent()
netlist_agent = NetlistAgent()

# Use agents individually
spec_result = spec_agent.run("Design a 12V power supply")
topology_result = topology_agent.run(spec_result)
netlist_result = netlist_agent.run(topology_result)
```

## 📖 Usage

### Frontend Usage

#### Chat Interface
- Navigate to `http://localhost:3000/chat` to access the AI chat interface
- Real-time conversation with specialized circuit design agents
- Support for multi-step interactions and circuit analysis
- Integration with Vercel AI SDK for streaming responses
- Modern UI with Tailwind CSS and responsive design

#### Home Page
- Visit `http://localhost:3000` for the main dashboard
- Overview of available features and quick access to chat
- Project information and system status

### Backend Usage

#### API Endpoints
- `POST /chat` - Chat with AI agents
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - Alternative API documentation

#### Direct Python Usage

**1. Simple Test Execution**
```bash
cd apps/backend
python test_agent.py
```

**2. Custom Workflow Execution**
```python
from multi_agent import run_orchestrated_workflow

# Example: Design a power supply
result = run_orchestrated_workflow("Diseña una fuente de alimentación 5V/2A con regulación")
print(result)
```

**3. Individual Agent Usage**
```python
from agents.spec_agent import SpecAgent
from agents.topology_agent import TopologyAgent
from agents.netlist_agent import NetlistAgent

# Initialize and use agents


### Multi-Agent System

The system includes specialized agents:

- **Spec Agent** (`agents/spec_agent.py`): Analyzes circuit specifications and requirements
- **Topology Agent** (`agents/topology_agent.py`): Designs circuit topology based on specifications
- **Netlist Agent** (`agents/netlist_agent.py`): Generates SPICE netlists from topology designs
- **Graph Validation**: Automatic ERC/DRC rules checking with NetworkX

### Circuit Design Pipeline

1. **Specification Analysis**: Parse and validate circuit requirements using Pydantic schemas
2. **Topology Design**: Create circuit topology based on specifications
3. **Netlist Generation**: Generate SPICE-compatible netlists
4. **Graph Validation**: Run ERC/DRC rules using NetworkX graph analysis
5. **Simulation**: Run NGSpice simulations for validation (optional)
6. **KiCad Integration**: Export to KiCad for PCB design (optional)

### External Tool Integration

#### KiCad Integration
```python
from tools.run_tools import kicad_cli_exec, kicad_erc, kicad_drc

# Run KiCad CLI commands
result = kicad_cli_exec("project_path", "command")
erc_result = kicad_erc("project_path")
drc_result = kicad_drc("project_path")
```

#### SPICE Simulation
```python
from tools.run_tools import spice_autorun

# Run SPICE simulation
result = spice_autorun("netlist_file.cir")
```

### Example Projects

The repository includes example KiCad projects:
- `PSU_24V_3A_PFC/` - 24V/3A Power Supply with PFC
- `LED_Driver_3.3V/` - 3.3V LED Driver

### Configuration

#### Environment Variables
```bash
# Required
OPENAI_API_KEY=your_openai_api_key_here

# Optional (for external tools)
NGSPICE=C:\Program Files\Spice64\bin\ngspice.exe
KICAD_CLI=C:\Program Files\KiCad\8.0\bin\kicad-cli.exe
```

#### Dependencies
- **Backend**: See `apps/backend/requirements.txt`
- **Frontend**: See `apps/frontend/package.json`

## 🔧 Development

### Code Explanation

#### Backend Architecture

**Multi-Agent System** (`multi_agent.py`)
- **LangGraph Integration**: Uses LangGraph for agent orchestration and workflow management
- **State Management**: Implements a state-based system with step tracking and history
- **Agent Coordination**: Coordinates between spec, topology, and netlist agents
- **Error Handling**: Comprehensive error handling and retry mechanisms

**Agent Implementation**
```python
# Each agent follows a consistent pattern:
class SpecAgent:
    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4.1-nano", temperature=0.1)
    
    def run(self, input_data):
        # Agent-specific logic
        return result
```

**Graph-Based Validation** (`graph/`)
- **GraphStore**: Manages circuit graph state using NetworkX
- **Patcher**: Applies incremental changes to circuit graphs
- **Validators**: Implements ERC/DRC validation rules
- **Rules Engine**: Executes validation rule sets

**Schema System** (`schema/`)
- **Pydantic Models**: Type-safe data validation
- **Graph Patch Schema**: Defines graph operation structure
- **Circuit Models**: Spec, topology, and netlist data models

**Toolkit** (`toolkit/toolkit.py`)
- **Graph Operations**: Applies specifications, topologies, and netlists to graphs
- **Validation Integration**: Runs validation rules after each operation
- **Error Handling**: Comprehensive error reporting and validation

#### Frontend Architecture

**Next.js 15 App Router**
- **Server Components**: Default rendering on the server for performance
- **Client Components**: Minimal client-side interactivity with `'use client'`
- **API Routes**: RESTful endpoints for backend communication
- **TypeScript**: Full type safety throughout the application

**Chat Interface** (`app/chat/page.tsx`)
- **Vercel AI SDK**: Integration for streaming chat responses
- **Real-time Updates**: WebSocket-like functionality for live updates
- **Modern UI**: Tailwind CSS with responsive design

**API Integration** (`app/api/`)
- **Chat Endpoint**: Handles multi-agent chat requests
- **Pipeline Management**: Manages design pipeline workflows
- **Error Handling**: Comprehensive error handling and user feedback

#### External Tool Integration

**KiCad Integration** (`tools/run_tools.py`)
- **CLI Execution**: Direct integration with KiCad command-line tools
- **ERC/DRC**: Electrical and Design Rule Checking
- **Project Management**: KiCad project file management

**SPICE Simulation**
- **NGSpice Integration**: Circuit simulation using NGSpice
- **Netlist Processing**: Converts circuit designs to SPICE netlists
- **Result Analysis**: Parses and analyzes simulation results

### Project Structure Guidelines
- **Frontend**: Follow Next.js 15 App Router patterns
- **Backend**: FastAPI with async/await patterns
- **Agents**: Modular, single-responsibility agents
- **Validation**: Graph-based topology checking with deterministic rules
- **Documentation**: Maintain build notes in `ProjectDocs/Build_Notes/`
- **Code Quality**: TypeScript strict mode, ESLint, Prettier

### Key Development Principles
- **Server Components First**: Use RSC where possible
- **Minimal Client Components**: Only use `'use client'` when necessary
- **Type Safety**: Comprehensive TypeScript coverage
- **Validation**: Deterministic, graph-based circuit validation
- **Performance**: Optimize for Core Web Vitals
- **Accessibility**: WCAG 2.1 compliance

### Testing and Validation

#### Backend Testing
```bash
# Run individual agent tests
cd apps/backend
python test_agent.py

# Test specific functionality
python -c "from multi_agent import run_orchestrated_workflow; print(run_orchestrated_workflow('test'))"
```

#### Frontend Testing
```bash
# Run development server
cd apps/frontend
npm run dev

# Build for production
npm run build
```

#### Integration Testing
```bash
# Test full stack with Docker
docker-compose up
# Test API endpoints at http://localhost:8000/docs
# Test frontend at http://localhost:3000
```

## 📚 Documentation

- **Build Notes**: Track development progress in `ProjectDocs/Build_Notes/`
- **Context Files**: Project requirements in `ProjectDocs/contexts/`
- **API Documentation**: Available at `/docs` when backend is running
- **SPICE Toolkit**: Full documentation in `apps/backend/spice_toolkit.py`

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support & Troubleshooting

### Common Issues

#### Backend Issues
```bash
# OpenAI API Key not set
Error: OpenAI API key not found
Solution: Set OPENAI_API_KEY in .env file

# Module import errors
Error: ModuleNotFoundError: No module named 'multi_agent'
Solution: Run from correct directory: cd apps/backend

# KiCad/NGSpice not found
Error: External tool not found
Solution: Install tools and set environment variables
```

#### Frontend Issues
```bash
# Build errors
Error: Module not found
Solution: Run npm install in apps/frontend

# API connection issues
Error: Failed to fetch
Solution: Ensure backend is running on port 8000
```

#### Docker Issues
```bash
# Container startup issues
Error: Port already in use
Solution: Stop conflicting services or change ports

# Environment variables not loaded
Error: Environment variable not found
Solution: Check .env file and docker-compose.yaml
```

### Debugging

#### Backend Debugging
```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Test individual components
from multi_agent import run_orchestrated_workflow
result = run_orchestrated_workflow("test prompt", debug=True)
```

#### Frontend Debugging
```bash
# Run with debug mode
cd apps/frontend
npm run dev -- --debug

# Check browser console for errors
# Use React Developer Tools extension
```

### Performance Optimization

#### Backend Optimization
- Use async/await patterns
- Implement caching for repeated operations
- Optimize graph operations for large circuits
- Use connection pooling for database operations

#### Frontend Optimization
- Minimize client-side JavaScript
- Use Server Components where possible
- Implement proper loading states
- Optimize bundle size

### Examples and Use Cases

#### Example 1: Power Supply Design
```python
# Design a 5V/2A power supply
result = run_orchestrated_workflow("""
Diseña una fuente de alimentación 5V/2A con las siguientes especificaciones:
- Voltaje de entrada: 12V DC
- Eficiencia: >85%
- Regulación de línea: <1%
- Ripple: <50mV
""")
```

#### Example 2: LED Driver Design
```python
# Design an LED driver
result = run_orchestrated_workflow("""
Diseña un LED driver 3.3V con control PWM:
- Corriente máxima: 1A
- Frecuencia PWM: 1kHz
- Eficiencia: >90%
- Protección contra cortocircuito
""")
```

#### Example 3: Using Individual Agents
```python
from agents.spec_agent import SpecAgent
from agents.topology_agent import TopologyAgent

# Step-by-step design process
spec_agent = SpecAgent()
spec_result = spec_agent.run("Design requirements for buck converter")

topology_agent = TopologyAgent()
topology_result = topology_agent.run(spec_result)
```

### Getting Help

If you encounter any issues or have questions:

1. **Check the Issues**: [GitHub Issues](https://github.com/Roger-korelia/korelia_test_agent/issues)
2. **Review Documentation**: Check this README and code comments
3. **Debug Mode**: Use debug flags and logging
4. **Community**: Create a new issue with detailed information
5. **Examples**: Review the example projects in the repository

## 🔄 Recent Updates

- ✅ Multi-agent system with specialized circuit design agents (spec, topology, netlist)
- ✅ Graph-based validation engine with deterministic ERC/DRC rules
- ✅ LangGraph integration for agent orchestration
- ✅ FastAPI backend with async/await patterns
- ✅ Real-time chat interface with Vercel AI SDK integration
- ✅ Pipeline management with WebSocket streaming
- ✅ KiCad CLI integration for PCB design workflow
- ✅ NGSpice integration for circuit simulation
- ✅ Docker containerization with multi-service support
- ✅ TypeScript implementation with full type safety
- ✅ Modern UI with Tailwind CSS and responsive design
- ✅ Pydantic schema validation for data integrity
- ✅ Graph-based circuit representation and patching
- ✅ Example KiCad project included (PSU_24V_3A_PFC)

---

## 🏗️ Architecture Overview

### Multi-Agent System
The backend implements a sophisticated multi-agent system using LangGraph for orchestration:

- **Spec Agent** (`agents/spec_agent.py`): Analyzes circuit specifications and requirements
- **Topology Agent** (`agents/topology_agent.py`): Designs circuit topology based on specifications  
- **Netlist Agent** (`agents/netlist_agent.py`): Generates SPICE netlists from topology designs

### Graph-Based Validation
The system uses NetworkX for graph-based circuit analysis:

- **Graph Store** (`graph/store.py`): Manages circuit graph state
- **Graph Patcher** (`graph/patcher.py`): Applies incremental changes to circuit graphs
- **Validators** (`graph/validators.py`): Implements ERC/DRC validation rules
- **Rules Engine** (`rules/engine.py`): Executes validation rule sets

### Data Models
Pydantic schemas ensure data integrity throughout the pipeline:

- **Spec Schema** (`schema/spec_schema.py`): Circuit specification models
- **Topology Schema** (`schema/topology_schema.py`): Circuit topology models
- **Netlist Schema** (`schema/netlist_schema.py`): SPICE netlist models
- **Graph Patch Schema** (`schema/graph_patch_schema.py`): Graph operation models

### Frontend Architecture
Next.js 15 App Router with modern React patterns:

- **Server Components**: Default rendering on the server for performance
- **Client Components**: Minimal client-side interactivity
- **API Routes**: RESTful endpoints for backend communication
- **WebSocket Integration**: Real-time pipeline event streaming

### External Integrations
- **KiCad CLI**: Direct integration for PCB design workflow
- **NGSpice**: Circuit simulation and validation
- **PostgreSQL**: Data persistence and session management
- **Redis**: Caching and real-time data
- **MinIO**: File storage for circuit designs

---

Built with ❤️ using Next.js 15, React 19, FastAPI, and NetworkX
