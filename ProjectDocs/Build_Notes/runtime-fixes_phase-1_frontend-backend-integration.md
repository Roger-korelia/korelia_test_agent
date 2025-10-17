Task Objective
Fix runtime errors across frontend and backend: Next.js dynamic params, AI SDK streaming response, and backend pipeline ID type mismatches.

Current State Assessment
- Project page used a client component accessing sync `params.id` (invalid in Next.js 15).
- API route `/api/pipeline/[pipeline_id]/events` accessed sync `params`.
- Chat API used `StreamingTextResponse` which is not exported by installed `ai` package.
- Backend FastAPI endpoints expected `UUID` causing 422 for non-UUID IDs like `demo`.

Future State Goal
- Stable navigation to `/projects/[id]` with proper param awaiting.
- SSE pipeline events proxied correctly.
- Chat API streams text via standard Response.
- Backend accepts string pipeline IDs.

Implementation Plan
1. Project page conversion
   - [x] Convert `app/projects/[id]/page.tsx` to server component awaiting `params`.
   - [x] Add `PipelineViewer.tsx` client component using `usePipelineEvents`.
2. Pipeline events route params
   - [x] Await `params` in `app/api/pipeline/[pipeline_id]/events/route.ts`.
3. Chat API streaming
   - [x] Remove `StreamingTextResponse`; return `new Response(ReadableStream)` with headers.
4. Backend pipeline IDs
   - [x] Change `UUID` to `str` for status/events functions and endpoints in `apps/backend/main.py`.
5. Verification
   - [ ] Run frontend, open `/projects/demo`, verify live updates.
   - [ ] Chat at `/chat`, verify streamed text.
   - [ ] Confirm no 422 from backend endpoints.


