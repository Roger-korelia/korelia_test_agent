# How to Execute the Application

## Prerequisites

1. **Python 3.8+** installed
2. **Node.js 18+** installed
3. **OpenAI API Key** (required for AI functionality)
4. **Optional**: KiCad CLI and NGSpice (for full circuit design features)

## Quick Start

### Step 1: Environment Setup

Create a `.env` file in the **root directory** (`Korelia_agent/`):

```bash
# Required
OPENAI_API_KEY=your_openai_api_key_here

# Optional (Windows defaults are already set in code)
# NGSPICE=C:\Program Files\Spice64\bin\ngspice.exe
# KICAD_CLI=C:\Program Files\KiCad\8.0\bin\kicad-cli.exe
```

### Step 2: Install Backend Dependencies

```bash
cd apps/backend
pip install -r requirements.txt
```

### Step 3: Install Frontend Dependencies

```bash
cd apps/frontend
npm install
```

### Step 4: Start the Backend Server

From the project root (`Korelia_agent/`):

```bash
# Option A: Using uvicorn directly (recommended)
cd apps/backend
uvicorn apps.backend.main:app --reload --port 8000

# Option B: Using Python module
cd apps/backend
python -m uvicorn apps.backend.main:app --reload --port 8000
```

The backend will be available at:
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Step 5: Start the Frontend Server

Open a **new terminal** (keep backend running):

```bash
cd apps/frontend
npm run dev
```

The frontend will be available at:
- Web App: http://localhost:3000

### Step 6: Use the Application

1. Open your browser and go to **http://localhost:3000**
2. Click "Start Chat" or navigate to **http://localhost:3000/chat**
3. Enter your electronics design task, e.g.:
   - "Design a 24V/3A isolated power supply with PFC"
   - "Create an LED driver circuit for 3.3V"

---

## Option 2: Docker Compose (All Services)

If you want to run everything including database and storage:

```bash
# From project root
docker-compose up
```

This will start:
- Backend API: http://localhost:8000
- Frontend: http://localhost:3000
- PostgreSQL: localhost:5432
- Redis: localhost:6379
- MinIO: http://localhost:9000

---

## Option 3: Test Backend Only (Python Script)

To test the agent directly without the web interface:

```bash
cd apps/backend
python test_agent.py
```

Or create your own test script:

```python
from apps.backend.agent import run_single_agent_workflow

result = run_single_agent_workflow("Design a 5V/2A power supply")
print(result)
```

---

## Troubleshooting

### Backend Issues

**Problem**: `ModuleNotFoundError: No module named 'apps'`
**Solution**: Run from project root, not from `apps/backend/`:
```bash
# From Korelia_agent/ root
cd apps/backend
uvicorn apps.backend.main:app --reload --port 8000
```

**Problem**: `OPENAI_API_KEY not found`
**Solution**: Create `.env` file in root with your OpenAI API key

**Problem**: Port 8000 already in use
**Solution**: Change port or stop the conflicting service:
```bash
uvicorn apps.backend.main:app --reload --port 8001
```

### Frontend Issues

**Problem**: Cannot connect to backend
**Solution**: 
1. Ensure backend is running on port 8000
2. Check `NEXT_PUBLIC_BACKEND_URL` in frontend environment (defaults to `http://localhost:8000`)

**Problem**: `npm install` fails
**Solution**: 
```bash
cd apps/frontend
rm -rf node_modules package-lock.json
npm install
```

### Environment Variables

If running manually (not Docker), create `.env` in root:

```bash
OPENAI_API_KEY=sk-...
```

The backend will automatically load this via `python-dotenv`.

---

## Expected Behavior

1. **Backend starts**: You should see FastAPI startup logs
2. **Frontend starts**: You should see Next.js dev server on port 3000
3. **API accessible**: Visit http://localhost:8000/docs to see Swagger UI
4. **Chat works**: Send a message and get AI agent response

---

## Development Tips

- Backend auto-reloads on code changes (--reload flag)
- Frontend auto-reloads with Next.js hot reload
- Check backend logs for agent execution details
- Check browser console for frontend errors
- Use http://localhost:8000/docs for API testing

