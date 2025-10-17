"use client";

import React from "react";
import { useCompletion } from "@ai-sdk/react";

export default function ChatPage() {
  const { completion, input, handleInputChange, handleSubmit, isLoading } = useCompletion({
    api: "/api/chat",
    onFinish: (_prompt, comp) => {
      console.log("[chat-ui] onFinish", { comp });
      if (comp) setHistory((h) => [...h, `AI: ${comp}`]);
    },
    onError: (err) => {
      console.error("[chat-ui] onError", err);
      setHistory((h) => [...h, `Error: ${err.message}`]);
    },
  });

  const [history, setHistory] = React.useState<string[]>([]);

  const onSubmit = React.useCallback(
    (e: any) => {
      console.log("[chat-ui] onSubmit", { input });
      if (input?.trim()) {
        setHistory((h) => [...h, `You: ${input}`]);
      }
      handleSubmit(e);
    },
    [input, handleSubmit]
  );

  React.useEffect(() => {
    if (completion) {
      // Also reflect intermediate/streamed updates if provided
      setHistory((h) => {
        const last = h[h.length - 1] ?? "";
        if (last.startsWith("AI: ")) {
          const base = h.slice(0, -1);
          return [...base, `AI: ${completion}`];
        }
        return [...h, `AI: ${completion}`];
      });
    }
  }, [completion]);

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-4">
      <h1 className="text-2xl font-semibold">Chat</h1>
      <div className="space-y-2">
        {history.map((line, idx) => (
          <div key={idx} className="rounded border p-2 whitespace-pre-wrap">{line}</div>
        ))}
      </div>
      <form onSubmit={onSubmit} className="flex gap-2">
        <input
          className="flex-1 border rounded px-3 py-2"
          value={input}
          onChange={handleInputChange}
          placeholder="Say something..."
        />
        <button disabled={isLoading} className="border rounded px-3 py-2">{isLoading ? "Sending..." : "Send"}</button>
      </form>
    </div>
  );
}


