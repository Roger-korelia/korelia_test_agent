import { NextRequest } from "next/server";

export const runtime = "edge";
export const maxDuration = 30;

export async function POST(req: NextRequest) {
  const body = await req.json();
  console.log("[chat-api] incoming body", body);
  const messages = Array.isArray(body?.messages)
    ? body.messages
    : body?.prompt
    ? [{ role: "user", content: String(body.prompt) }]
    : [];
  const backend = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
  console.log("[chat-api] forwarding to backend", backend, { messagesCount: messages.length });
  const resp = await fetch(`${backend}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  console.log("[chat-api] backend status", resp.status);
  if (!resp.ok) {
    return new Response(await resp.text(), { status: resp.status });
  }
  const data = await resp.json();
  console.log("[chat-api] backend data", data);
  return new Response(String(data.content ?? ""), {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}


