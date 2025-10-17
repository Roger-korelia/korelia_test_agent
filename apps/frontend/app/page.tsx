import React from "react";
export default function Home() {
  return (
    <main className="p-6">
      <h1 className="text-2xl font-semibold">Agents Platform</h1>
      <div className="space-x-4 mt-4">
        <a className="text-blue-600 underline" href="/projects/demo">Ir a proyecto demo</a>
        <a className="text-blue-600 underline" href="/chat">Chat</a>
      </div>
    </main>
  );
}
