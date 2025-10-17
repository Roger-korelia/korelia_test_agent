# Korelia Agent

A full-stack AI agent application built with Next.js 15, React 19, and Python FastAPI. This project provides a modern chat interface with real-time pipeline management and AI-powered interactions.

## 🚀 Features

- **Modern Frontend**: Next.js 15 with React 19 and App Router
- **AI Chat Interface**: Real-time chat with AI agents
- **Pipeline Management**: Visual pipeline creation and monitoring
- **Real-time Events**: WebSocket-based event streaming
- **Modern UI**: Tailwind CSS with Shadcn UI components
- **Type Safety**: Full TypeScript implementation
- **Docker Support**: Containerized development and deployment

## 📁 Project Structure

```
Korelia_agent/
├── apps/
│   ├── frontend/          # Next.js 15 application
│   │   ├── app/           # App Router pages and API routes
│   │   ├── types/         # TypeScript type definitions
│   │   └── package.json   # Frontend dependencies
│   └── backend/           # Python FastAPI backend
│       ├── main.py        # FastAPI application
│       ├── deep_agent2.py # AI agent implementation
│       ├── tools.py       # Agent tools and utilities
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
- **AI Integration**: Custom agent implementation
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
   git clone https://github.com/YOUR_USERNAME/korelia-agent.git
   cd korelia-agent
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
python main.py
```

## 📖 Usage

### Chat Interface
- Navigate to `/chat` to access the AI chat interface
- Real-time conversation with AI agents
- Support for multi-step interactions

### Pipeline Management
- Visit `/projects/[id]` to view pipeline details
- Real-time pipeline event monitoring
- Visual pipeline representation

### API Endpoints
- `POST /api/chat` - Chat with AI agents
- `POST /api/pipeline/start` - Start new pipeline
- `GET /api/pipeline/[id]/events` - Stream pipeline events

## 🔧 Development

### Project Structure Guidelines
- **Frontend**: Follow Next.js 15 App Router patterns
- **Backend**: FastAPI with async/await patterns
- **Documentation**: Maintain build notes in `ProjectDocs/Build_Notes/`
- **Code Quality**: TypeScript strict mode, ESLint, Prettier

### Key Development Principles
- **Server Components First**: Use RSC where possible
- **Minimal Client Components**: Only use `'use client'` when necessary
- **Type Safety**: Comprehensive TypeScript coverage
- **Performance**: Optimize for Core Web Vitals
- **Accessibility**: WCAG 2.1 compliance

## 📚 Documentation

- **Build Notes**: Track development progress in `ProjectDocs/Build_Notes/`
- **Context Files**: Project requirements in `ProjectDocs/contexts/`
- **API Documentation**: Available at `/docs` when backend is running

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

1. Check the [Issues](https://github.com/YOUR_USERNAME/korelia-agent/issues) page
2. Review the build notes in `ProjectDocs/Build_Notes/`
3. Create a new issue with detailed information

## 🔄 Recent Updates

- ✅ Initial project setup with Next.js 15 and React 19
- ✅ FastAPI backend with AI agent integration
- ✅ Real-time chat interface
- ✅ Pipeline management system
- ✅ Docker containerization
- ✅ TypeScript implementation
- ✅ Modern UI with Tailwind CSS and Shadcn UI

---

Built with ❤️ using Next.js 15, React 19, and FastAPI
