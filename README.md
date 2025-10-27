# Korelia Agent

A full-stack AI agent application for circuit design and analysis, built with Next.js 15, React 19, and Python FastAPI. This project provides a multi-agent system with SPICE netlist parsing, graph-based validation, and real-time pipeline management.

## 🚀 Features

- **Multi-Agent System**: Specialized AI agents for circuit design (spec, topology, netlist, analytical sizing)
- **SPICE Toolkit**: Advanced parser with graph-based validation and ERC/DRC rules
- **Graph-Based Validation**: Automatic topology checking with deterministric ERC/DRC rules
- **Layered Netlist Builder**: Incremental circuit construction with validation
- **Modern Frontend**: Next.js 15 with React 19 and App Router
- **Real-time Pipeline**: Visual pipeline creation and monitoring with WebSocket streaming
- **Modern UI**: Tailwind CSS with Shadcn UI components
- **Type Safety**: Full TypeScript implementation
- **Docker Support**: Containerized development and deployment

## 📁 Project Structure

```
Korelia_agent/
├── apps/
│   ├── frontend/          # Next.js 15 application
│   │   ├── app/           # App Router pages and API routes
│   │   │   ├── api/       # API routes (chat, pipeline)
│   │   │   ├── chat/      # Chat interface
│   │   │   └── projects/  # Project management
│   │   ├── types/         # TypeScript type definitions
│   │   └── package.json   # Frontend dependencies
│   └── backend/           # Python FastAPI backend
│       ├── main.py        # FastAPI application entry
│       ├── multi_agent.py # Multi-agent orchestration
│       ├── spice_toolkit.py # SPICE parser & validation
│       ├── agents/        # Specialized AI agents
│       │   ├── spec_agent.py
│       │   ├── topology_agent.py
│       │   ├── netlist_agent.py
│       │   └── analytical_sizer_agent.py
│       ├── graph/         # Graph-based validation
│       │   ├── context.py
│       │   ├── patcher.py
│       │   ├── validators.py
│       │   ├── rulesets.py
│       │   └── store.py
│       ├── rules/         # Circuit validation rules
│       │   ├── engine.py
│       │   ├── base.py
│       │   └── power_base.py
│       ├── schema/        # Schema definitions
│       │   ├── netlist_schema.py
│       │   ├── topology_schema.py
│       │   ├── sizing_schema.py
│       │   └── violations_schema.py
│       ├── tools/         # Agent tools
│       │   ├── run_tools.py
│       │   └── tools_graph.py
│       └── requirements.txt
├── ProjectDocs/           # Project documentation
│   ├── Build_Notes/       # Development progress tracking
│   └── contexts/          # Project context files
├── docker-compose.yaml   # Multi-service orchestration
└── README.md
```

## 🛠️ Tech Stack

### Frontend
- **Framework**: Next.js 15 with App Router
- **React**: React 19 with Server Components
- **Styling**: Tailwind CSS + Shadcn UI
- **TypeScript**: Full type safety
- **State Management**: Zustand (when needed)

### Backend
- **Framework**: FastAPI
- **Python**: 3.8+
- **AI Integration**: Custom multi-agent system with LangGraph
- **Circuit Processing**: NetworkX for graph-based analysis
- **Validation**: Deterministic ERC/DRC rules engine
- **Real-time**: WebSocket support

### DevOps
- **Containerization**: Docker + Docker Compose
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

### Pipeline Management
- Visit `/projects/[id]` to view pipeline details
- Real-time pipeline event monitoring
- Visual pipeline representation

### SPICE Toolkit
The SPICE toolkit provides:
- **Parser**: Converts SPICE netlists to structured components
- **Graph Builder**: Creates bipartite graphs for topology analysis
- **Validation**: ERC/DRC rules checking (floating nodes, parallel sources, etc.)
- **Layered Builder**: Incremental circuit construction with automatic validation

### API Endpoints
- `POST /api/chat` - Chat with AI agents
- `POST /api/pipeline/start` - Start new pipeline
- `GET /api/pipeline/[id]/events` - Stream pipeline events

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

- ✅ Multi-agent system with specialized circuit design agents
- ✅ SPICE toolkit with graph-based validation and ERC/DRC rules
- ✅ Layered netlist builder with incremental construction
- ✅ Graph-based topology validation engine
- ✅ Schema-based circuit representation and patching
- ✅ FastAPI backend with LangGraph integration
- ✅ Real-time chat interface with multi-step interactions
- ✅ Pipeline management with WebSocket streaming
- ✅ Docker containerization
- ✅ TypeScript implementation
- ✅ Modern UI with Tailwind CSS and Shadcn UI

---

Built with ❤️ using Next.js 15, React 19, FastAPI, and NetworkX
