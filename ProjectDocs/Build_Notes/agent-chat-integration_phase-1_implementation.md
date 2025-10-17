Task Objective
Integrate a chat UI using the Vercel AI SDK that converses with the Python engineering agent, including necessary backend APIs.

Current State Assessment
- Frontend already has a chat page and a Vercel AI SDK route streaming from OpenAI.
- Backend exposes pipeline endpoints; Python agent exists in `apps/backend/agent.py` but no chat endpoint.
- Minor bug in `report_markdown_export` indentation in `apps/backend/tools.py` prevents import reliability.

Future State Goal
- Chat page streams via Vercel AI SDK and delegates answering to the Python agent.
- Backend provides `/chat` endpoint to invoke the agent with chat messages.

Implementation Plan
1) Backend API
   - [x] Add Pydantic models `ChatMessage`, `ChatRequest`, `ChatResponse` in `apps/backend/main.py`.
   - [x] Implement `POST /chat` calling `apps.backend.agent.agent.invoke` with provided messages.
   - [x] Return `{ content }` as JSON.
2) Fix backend tooling import issue
   - [x] Correct indentation in `report_markdown_export` writer block.
3) Frontend API
   - [x] Update `apps/frontend/app/api/chat/route.ts` to use `streamText` with a tool `backendAgent` that calls backend `/chat`.
   - [x] Add `zod` dependency for tool parameters.
4) UI
   - [x] Reuse existing `apps/frontend/app/chat/page.tsx` with `useChat`.
5) Validation
   - [x] Basic lint check and compile type sanity.

Notes / Decisions
- Chose tool-based delegation in the Next.js route so the Vercel AI SDK continues to stream while deferring final content to the Python agent.
- Kept runtime as `edge` for the chat API route; backend is accessed server-side so no CORS issues.

Completion Summary
- New backend `/chat` endpoint implemented and wired.
- Frontend route now delegates to backend agent through Vercel AI SDK tool.
- `tools.py` indentation bug fixed to ensure backend imports succeed.

