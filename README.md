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

### Quick Start with Docker

1. **Clone the repository**
   ```bash
   git clone https://github.com/Roger-korelia/korelia_test_agent.git
   cd Korelia_agent
   ```

2. **Start all services**
   ```bash
   docker-compose up
   ```

3. **Access the application**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000

### Manual Development Setup

#### Frontend Setup
```bash
cd apps/frontend
npm install
npm run dev
```

#### Backend Setup
```bash
cd apps/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## 📖 Usage

### Chat Interface
- Navigate to `/chat` to access the AI chat interface
- Real-time conversation with specialized circuit design agents
- Support for multi-step interactions and circuit analysis
- Integration with Vercel AI SDK for streaming responses

### Pipeline Management
- Visit `/projects/[id]` to view pipeline details
- Real-time pipeline event monitoring via WebSocket
- Visual pipeline representation with step-by-step progress
- Support for circuit design workflows from spec to KiCad

### Multi-Agent System
The system includes specialized agents:
- **Spec Agent**: Analyzes circuit specifications and requirements
- **Topology Agent**: Designs circuit topology based on specifications
- **Netlist Agent**: Generates SPICE netlists from topology designs
- **Graph Validation**: Automatic ERC/DRC rules checking

### Circuit Design Pipeline
1. **Specification Analysis**: Parse and validate circuit requirements
2. **Topology Design**: Create circuit topology based on specifications
3. **Netlist Generation**: Generate SPICE-compatible netlists
4. **Simulation**: Run NGSpice simulations for validation
5. **KiCad Integration**: Export to KiCad for PCB design
6. **Documentation**: Generate design documentation

### API Endpoints
- `POST /api/chat` - Chat with AI agents
- `POST /api/pipeline/start` - Start new design pipeline
- `GET /api/pipeline/[id]/events` - Stream pipeline events via WebSocket

## 🔧 Development

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

## 🆘 Support

If you encounter any issues or have questions:

1. Check the [Issues](https://github.com/Roger-korelia/korelia_test_agent/issues) page
2. Review the build notes in `ProjectDocs/Build_Notes/`
3. Create a new issue with detailed information

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
