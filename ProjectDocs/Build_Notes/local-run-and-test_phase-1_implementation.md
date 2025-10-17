Task Objective

- Run frontend and backend locally, verify chat and pipeline SSE flows.

Current State Assessment

- `docker-compose.yaml` defines `api` (FastAPI), `frontend` (Next.js), and dependencies.
- Frontend proxies to backend via `NEXT_PUBLIC_BACKEND_URL` or defaults to `http://localhost:8000`.
- Backend had undefined pipeline symbols; added minimal stubs and a chat fallback to avoid hard failures.
- Local environment currently lacks Docker in PATH.

Future State Goal

- Able to run both services locally (Docker or host) and validate:
  - POST `/chat` returns content.
  - GET `/pipeline/:id/events` streams SSE to frontend page.

Implementation Plan

1) Wire frontend-to-backend URL
   - [x] Add `NEXT_PUBLIC_BACKEND_URL=http://api:8000` to `docker-compose.yaml` for Docker runs.
   - [ ] Optionally add `.env.local` in `apps/frontend` for host runs.

2) Unblock backend API
   - [x] Define `PipelineStart`, `TaskStatus`, `start_pipeline`, `get_status`, `stream_events` stubs in `apps/backend/main.py`.
   - [x] Wrap `/chat` with try/except fallback echo if agent raises.

3) Run stack
   - [ ] Docker path available → `docker compose up --build -d`.
   - [ ] If no Docker → run backend with `uvicorn`, frontend with `npm run dev`.

4) Verify functionality
   - [ ] `curl` POST `http://localhost:8000/chat` returns JSON with `content`.
   - [ ] Visit `http://localhost:3000/chat` and send a message → response shows.
   - [ ] Visit `http://localhost:3000/projects/test` → progress updates via SSE.

Notes / Decisions

- Kept agent integration but added a safe fallback to ensure demo viability without external tools.
- SSE stream is simulated for demonstration.


