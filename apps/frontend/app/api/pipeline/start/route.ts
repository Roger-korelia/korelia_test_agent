import type { NextRequest } from "next/server";

export const runtime = "edge";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const backend = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
  const resp = await fetch(`${backend}/pipeline/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return new Response(await resp.text(), { status: resp.status, headers: { "Content-Type": resp.headers.get("Content-Type") || "application/json" } });
}


