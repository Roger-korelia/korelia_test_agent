"use client";

import React from "react";
import { useCompletion } from "@ai-sdk/react";

export default function ChatPage() {
  const { completion, input, handleInputChange, handleSubmit, isLoading } = useCompletion({
    api: "/api/chat",
  });

  const [messages, setMessages] = React.useState<Array<{role: string, content: string}>>([]);

  React.useEffect(() => {
    if (completion) {
      setMessages(prev => [...prev, { role: "assistant", content: completion }]);
    }
  }, [completion]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input?.trim()) {
      setMessages(prev => [...prev, { role: "user", content: input }]);
    }
    handleSubmit(e);
  };

  return (
    <div className="min-h-screen bg-gray-100">
      <div className="max-w-2xl mx-auto p-4">
        <div className="bg-white rounded-lg shadow-lg h-screen flex flex-col">
          <div className="p-4 border-b">
            <h1 className="text-xl font-bold">Multi-Agent Chat</h1>
          </div>
          
          <div className="flex-1 p-4 overflow-y-auto space-y-4">
            {messages.length === 0 && (
              <div className="text-center text-gray-500 py-8">
                <p>Describe your electronics design task</p>
                <p className="text-sm mt-2">Try: "Design a LED driver circuit"</p>
              </div>
            )}
            
            {messages.map((message, idx) => (
              <div key={idx} className={`p-3 rounded-lg ${
                message.role === "user" 
                  ? "bg-blue-100 ml-8" 
                  : "bg-gray-100 mr-8"
              }`}>
                <div className="font-semibold text-sm mb-1">
                  {message.role === "user" ? "You" : "Assistant"}
                </div>
                <div className="whitespace-pre-wrap">{message.content}</div>
              </div>
            ))}
            
            {isLoading && (
              <div className="bg-yellow-100 p-3 rounded-lg mr-8">
                <div className="font-semibold text-sm mb-1">Assistant</div>
                <div className="flex items-center space-x-2">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                  <span>Processing...</span>
                </div>
              </div>
            )}
          </div>
          
          <div className="p-4 border-t">
            <form onSubmit={onSubmit} className="flex gap-2">
              <input
                className="flex-1 border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={input}
                onChange={handleInputChange}
                placeholder="Enter your message..."
                disabled={isLoading}
              />
              <button 
                disabled={isLoading || !input?.trim()} 
                className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:bg-gray-400"
              >
                Send
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}


