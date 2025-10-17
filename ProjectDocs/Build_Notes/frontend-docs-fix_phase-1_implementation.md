Task Objective

Create/repair the `frontend.mdc` context for the Next.js 15 frontend so it is deploy-ready on Vercel and aligned with Vercel AI SDK UI usage.

Current State Assessment

- Frontend uses App Router under `apps/frontend/app/`.
- `app/api/chat/route.ts` proxies to a backend with `StreamingTextResponse`, edge runtime.
- `app/chat/page.tsx` uses `useChat` from `ai/react`.
- No `ProjectDocs/contexts/frontend.mdc` existed.

Future State Goal

- Ship a stable, concise `frontend.mdc` that documents environment, runtime, streaming, and minimal UI patterns compatible with Vercel.

Implementation Plan

1. Create `ProjectDocs/contexts/frontend.mdc` with verified guidance.
   - [x] Cover Next.js 15, React 19, App Router conventions
   - [x] Document environment variables and Vercel settings
   - [x] Provide minimal chat UI and API route examples
2. Review repo frontend for alignment with the guidance.
   - [x] Verify API route uses edge runtime and streaming
   - [x] Verify `useChat` setup and routes
3. Add Build Notes for traceability and future updates.
   - [x] Create this file with objective, state, plan
4. Implement Tailwind and root layout in `apps/frontend`.
   - [x] Add Tailwind config and PostCSS setup
   - [x] Add `globals.css` and import via `app/layout.tsx`
5. Harden API routes for Vercel Edge compatibility.
   - [x] Set `/api/pipeline/start` to Edge runtime

Notes / Decisions

- Kept proxy approach (Option A) documented since backend returns JSON; added Option B for true streaming if backend supports it.
- Ensured guidance remains provider-agnostic with optional `streamText` via `@ai-sdk/openai`.

Completion Criteria

- `frontend.mdc` added and reflects current code and recommended next steps.
- Build notes exist and document rationale and implementation steps.


