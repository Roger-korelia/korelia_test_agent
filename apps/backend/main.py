from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal
import logging

# Import multi-agent system
from apps.backend.multi_agent import run_orchestrated_workflow

# Models
class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]

class ChatResponse(BaseModel):
    content: str

# FastAPI app
app = FastAPI(title="Multi-Agent Chat API")

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


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    logger.info("Chat request received: %d messages", len(req.messages))
    
    try:
        # Get the last user message
        user_task = ""
        for m in reversed(req.messages):
            if m.role == "user":
                user_task = m.content
                break
        
        if not user_task:
            user_task = "Please help me with an electronics design task."
        
        logger.info("Running multi-agent workflow for: %s", user_task[:100])
        
        # Run the multi-agent workflow
        result = run_orchestrated_workflow(user_task)
        
        # Extract the final response
        final_state = result.get("final_state", {})
        current_intent = final_state.get("current_intent", {})
        steps = current_intent.get("steps", {})
        
        # Create a simple response
        content_parts = []
        content_parts.append("## Multi-Agent Design Results")
        content_parts.append(f"**Status:** {current_intent.get('overall_status', 'unknown')}")
        content_parts.append(f"**Attempts:** {current_intent.get('total_attempts', 0)}\n")
        
        # Add step results
        for step_name, step_data in steps.items():
            status = step_data.get("status", "unknown")
            content_parts.append(f"**{step_name.title()}:** {status}")
        
        content = "\n".join(content_parts)
        
        if not content.strip():
            content = "Multi-agent workflow completed but no results available."
            
    except Exception as exc:
        logger.exception("Multi-agent workflow failed: %s", exc)
        content = f"Error: {str(exc)}"
    
    return ChatResponse(content=content)
