import { NextRequest } from "next/server";

export const runtime = "nodejs";
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
  
  // Stream the response from backend
  const stream = new ReadableStream({
    async start(controller) {
      const reader = resp.body?.getReader();
      const decoder = new TextDecoder();
      
      if (!reader) {
        controller.close();
        return;
      }
      
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          controller.enqueue(new TextEncoder().encode(chunk));
        }
      } catch (error) {
        console.error("[chat-api] stream error", error);
      } finally {
        controller.close();
      }
    },
  });
  
  return new Response(stream, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}


