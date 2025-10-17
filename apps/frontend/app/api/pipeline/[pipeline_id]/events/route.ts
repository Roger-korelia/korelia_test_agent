import type { NextRequest } from "next/server";

export const runtime = "edge";

export async function GET(_req: NextRequest, ctx: { params: Promise<{ pipeline_id: string }> }) {
  const params = await ctx.params;
  const backend = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
  const resp = await fetch(`${backend}/pipeline/${params.pipeline_id}/events`, {
    headers: { Accept: "text/event-stream" },
  });
  return new Response(resp.body, {
    headers: { "Content-Type": "text/event-stream" },
  });
}


