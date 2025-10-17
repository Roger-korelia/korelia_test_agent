"use client";

import { useEffect, useState } from "react";

export function usePipelineEvents(pipelineId: string) {
  const [events, setEvents] = useState<any[]>([]);
  useEffect(() => {
    const es = new EventSource(`/api/pipeline/${pipelineId}/events`);
    es.onmessage = (e) => setEvents((prev) => [...prev, JSON.parse(e.data)]);
    es.onerror = () => es.close();
    return () => es.close();
  }, [pipelineId]);
  return events;
}


