from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Literal
import logging
import json

# Import single-agent workflow
from apps.backend.agent import run_single_agent_workflow_stream

# Models
class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]

class ChatResponse(BaseModel):
    content: str

# FastAPI app
app = FastAPI(title="Single-Agent Chat API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend")


@app.post("/chat")
def chat(req: ChatRequest):
    logger.info("Chat request received: %d messages", len(req.messages))
    
    # Get the last user message
    user_task = ""
    for m in reversed(req.messages):
        if m.role == "user":
            user_task = m.content
            break
    
    if not user_task:
        user_task = "Please help me with an electronics design task."
    
    logger.info("Running single-agent workflow (streaming) for: %s", user_task[:100])

    def generate():
        try:
            for chunk in run_single_agent_workflow_stream(user_task):
                yield chunk
        except Exception as exc:
            logger.exception("Single-agent workflow failed: %s", exc)
            yield f"\n\nError: {str(exc)}\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-store"}
    )
