from __future__ import annotations

from typing import Iterator, List, Literal
import os
import logging
from uuid import UUID

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from apps.backend.agent import agent, AGENT_ACTIVE, _AGENT_IMPORT_ERROR
from langchain_core.runnables import RunnableLambda


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]


class ChatResponse(BaseModel):
    content: str


# ---- Minimal pipeline models and stubs to enable the API to run ----
class PipelineStart(BaseModel):
    prompt: str | None = None


class TaskStatus(BaseModel):
    status: Literal["queued", "running", "completed", "failed"]
    current_node: str | None = None
    progress: float = 0.0


def start_pipeline(_p: PipelineStart) -> TaskStatus:
    # Minimal stub: immediately report running with 0 progress
    return TaskStatus(status="running", current_node="start", progress=0.0)


def get_status(_pipeline_id: str) -> TaskStatus:
    # Minimal stub: return a static status
    return TaskStatus(status="running", current_node="processing", progress=0.5)


def stream_events(_pipeline_id: str) -> Iterator[str]:
    # Server-Sent Events minimal stream simulating progress updates
    import json
    import time

    steps = [
        ("queued", "queue", 0.0),
        ("running", "prepare", 0.2),
        ("running", "analyze", 0.5),
        ("running", "finalize", 0.8),
        ("completed", "done", 1.0),
    ]
    for status, node, prog in steps:
        event = {"status": status, "current_node": node, "progress": prog}
        yield f"data: {json.dumps(event)}\n\n"
        time.sleep(0.5)


app = FastAPI(title="Engineering Agents API")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend")


@app.post("/pipeline/start", response_model=TaskStatus)
def start(p: PipelineStart):
    return start_pipeline(p)


@app.get("/pipeline/{pipeline_id}/status", response_model=TaskStatus)
def status(pipeline_id: str):
    return get_status(pipeline_id)


@app.get("/pipeline/{pipeline_id}/events")
def events(pipeline_id: str):
    return StreamingResponse(stream_events(pipeline_id), media_type="text/event-stream")



@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    logger.info("/chat request received: %d messages", len(req.messages))
    logger.info("/chat request messages: %s", [
        {"role": m.role, "content": m.content[:100]} for m in req.messages
    ])
    logger.info("/chat agent active: %s", AGENT_ACTIVE)
    if not AGENT_ACTIVE:
        logger.warning("/chat agent inactive due to import error: %s", _AGENT_IMPORT_ERROR)

    def try_llm_fallback() -> str:
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

            if not os.environ.get("OPENAI_API_KEY"):
                logger.warning("/chat llm_fallback skipped: OPENAI_API_KEY not set")
                return ""

            model_name = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            logger.info("/chat model: %s", model_name)
            llm = ChatOpenAI(model=model_name, temperature=0)
            lc_messages = []
            for m in req.messages:
                if m.role == "system":
                    lc_messages.append(SystemMessage(content=m.content))
                elif m.role == "assistant":
                    lc_messages.append(AIMessage(content=m.content))
                else:
                    lc_messages.append(HumanMessage(content=m.content))
            # Traced automatically when LANGCHAIN_TRACING_V2 is enabled
            resp = llm.invoke(lc_messages, config={"run_name": "llm_fallback"})
            return str(getattr(resp, "content", resp))
        except Exception as exc:
            logger.exception("/chat llm_fallback error: %s", exc)
            return ""

    try:
        def _agent_call(payload: dict):
            return agent.invoke(payload)

        agent_runnable = RunnableLambda(_agent_call)
        result = agent_runnable.invoke({
            "messages": [{"role": m.role, "content": m.content} for m in req.messages]
        }, config={"run_name": "deep_agent_invoke"})
        logger.info("/chat agent result type: %s", type(result).__name__)
        if isinstance(result, str):
            content = result
        elif isinstance(result, dict):
            content = str(result.get("output", result))
        else:
            content = str(result)
        logger.info("/chat agent content preview: %s", content[:200])
        if not content or (not AGENT_ACTIVE) or content.startswith("[fallback-agent]"):
            content = try_llm_fallback() or "[fallback] No content returned by agent."
    except Exception as exc:
        logger.exception("Agent invocation failed: %s", exc)
        # If agent fails, attempt LLM fallback; otherwise echo last user message with error
        content = try_llm_fallback()
        if not content:
            user_last = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
            content = f"[fallback] You said: {user_last}. Error: {exc}"
    logger.info("/chat response bytes: %d", len(content.encode("utf-8")))
    return ChatResponse(content=content)
