"use client";

import React from "react";
import { usePipelineEvents } from "./usePipelineEvents";

export default function PipelineViewer({ id }: { id: string }) {
  const events = usePipelineEvents(id);
  const last = events.at(-1);
  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-semibold">Pipeline</h1>
      <div className="rounded border p-4">
        <div>Estado: {last?.status ?? "waiting"}</div>
        <div>Nodo: {last?.current_node ?? "-"}</div>
        <progress value={last?.progress ?? 0} max={1} />
      </div>
    </div>
  );
}


