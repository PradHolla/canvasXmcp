import os
import sys
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# LangChain & MCP Imports
from langchain_aws import ChatBedrockConverse
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.agent.checkpointer import (
    get_checkpointer,
    get_all_conversations,
    get_conversation_title,
    delete_conversation,
    save_conversation_title,
    initialize_metadata_table,
)

# Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("canvas-api")

load_dotenv()

# Pydantic Models
class ChatRequest(BaseModel):
    message: str
    thread_id: str
    model_id: Optional[str] = None

class ThreadResponse(BaseModel):
    thread_id: str
    title: str
    updated_at: Optional[str] = None

# --- Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(" Starting Canvas LMS Agent API...")
    
    # 1. Initialize DB (Synchronous - No await!)
    initialize_metadata_table()
    
    # 2. Connect to MCP Server
    try:
        # Simple path to the server script
        script_path = "app/mcp/canvas_server.py"
        
        logger.info(f"🔌 Connecting to MCP Server at: {script_path}")

        # Use sys.executable to ensure we use the same python environment
        server_params = StdioServerParameters(
            command=sys.executable, 
            args=[script_path], 
            env={**os.environ, "PYTHONUNBUFFERED": "1"}
        )
        
        # Start the stdio client
        app.state.stdio_context = stdio_client(server_params)
        read, write = await app.state.stdio_context.__aenter__()
        
        app.state.mcp_session = ClientSession(read, write)
        await app.state.mcp_session.__aenter__()
        await app.state.mcp_session.initialize()
        
        # 3. Load Tools
        app.state.tools = await load_mcp_tools(app.state.mcp_session)
        logger.info(f" Loaded {len(app.state.tools)} Canvas tools via MCP")
        
    except Exception as e:
        logger.error(f" Failed to initialize MCP server: {e}")
        app.state.tools = [] 

    yield

    # Cleanup
    logger.info(" Shutting down MCP connection...")
    if hasattr(app.state, "mcp_session"):
        await app.state.mcp_session.__aexit__(None, None, None)
    if hasattr(app.state, "stdio_context"):
        await app.state.stdio_context.__aexit__(None, None, None)

# --- App Setup ---
app = FastAPI(title="Canvas LMS Agent API", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def health_check():
    return {"status": "healthy"}

# --- Helper Functions ---

def get_system_prompt() -> str:
    today = datetime.now()
    current_date = today.strftime("%A, %B %d, %Y")
    
    return f"""You are a Canvas LMS assistant that helps students with their coursework.

TODAY'S DATE: {current_date}

RULES:
1. Use tools to get real data
2. Choose the most specific tool
3. Remember context from conversation
4. Format dates as "October 23, 2025"
5. Format scores as "8.5/10"
6. Never show course IDs or technical details
7. Be concise and helpful

CRITICAL COURSE ACCESS RULES:

1. ALWAYS call get_course_id_by_name() when user mentions a course by NAME
2. NEVER guess or invent course IDs
3. NEVER use course IDs from memory without verification

CORRECT WORKFLOW:
User: "Show me CS 559 assignments"
Step 1: get_course_id_by_name("CS 559") → returns course ID
Step 2: get_assignments(course_id=<that ID>)
Step 3: Verify response shows "CS 559"

If tool returns error about course access:
- Call get_courses() to show enrolled courses
- Apologize and ask user to clarify
- NEVER retry with random course IDs

ASSIGNMENT SUBMISSION RULES:

BEFORE submitting any assignment:
1. Call get_course_id_by_name() to get course ID
2. Call get_assignments(course_id) to find correct assignment
3. Show assignment name, due date, and submission status
4. Verify file path is provided (absolute path like /home/user/file.pdf)
5. CONFIRM details with user before calling submit_assignment()

SUBMISSION WORKFLOW:
User: "Submit report.pdf to CS 555 assignment 3"
Step 1: get_course_id_by_name("CS 555") → get course ID
Step 2: get_assignments(course_id) → find assignment 3
Step 3: Show: "Found: Assignment 3 - Midterm Report (due Nov 20, unsubmitted)"
Step 4: Ask: "Please provide the full path to report.pdf"
Step 5: User provides: "/home/pnh/Documents/report.pdf"
Step 6: submit_assignment(course_id, assignment_id, file_path, comment="")
Step 7: Show success: "Successfully submitted report.pdf at [timestamp]"

IMPORTANT SUBMISSION RULES:
- NEVER submit without explicit user intent
- ALWAYS verify file path exists (must be absolute path)
- ALWAYS show assignment details before submission
- NEVER submit to wrong assignment
- Always show confirmation with timestamp after submission

TEMPORAL QUERY HANDLING:

Today is {today.strftime("%A, %B %d, %Y")} (Day {today.day} of {today.strftime("%B")})

When user asks about timeframes, calculate days from TODAY:

"this week" → Days until end of current week (Saturday)
  Example: If today is Sunday Nov 9, Saturday is Nov 15 → use days=6

"this month" → Days until end of current month
  Example: If today is Nov 9, end of month is Nov 30 → use days=21
  
"next 7 days" → Literal 7 days → use days=7

"by Friday" → Days until next Friday
  Example: If today is Sunday Nov 9, Friday is Nov 14 → use days=5

"overdue" → Show only overdue items
  Use: get_upcoming_assignments(days=0, include_overdue=True)

IMPORTANT: 
- Always explain your date calculation in reasoning
- get_upcoming_assignments automatically includes overdue items from past week
- For "only upcoming" (no overdue), use include_overdue=False

Present information cleanly with bullet points. No raw JSON.
"""

async def get_agent_executor(thread_id: str, model_id: str):
    if not hasattr(app.state, "tools") or not app.state.tools:
         raise HTTPException(status_code=503, detail="MCP Tools not initialized")

    checkpointer = await get_checkpointer()
    # Ensure you have your model ID set in environment variables
    final_model_id = model_id or os.getenv("GPT_OSS", "openai.gpt-oss-120b-1:0")
    
    llm = ChatBedrockConverse(
        model=final_model_id,
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        temperature=0.3,
        max_tokens=4096,
    )

    agent = create_react_agent(
        llm,
        app.state.tools,
        checkpointer=checkpointer,
        prompt=get_system_prompt()
    )
    
    return agent

# --- Routes ---

@app.get("/api/health")
async def health_check():
    tools_count = len(app.state.tools) if hasattr(app.state, "tools") else 0
    return {"status": "ok", "mcp_tools": tools_count}

@app.get("/api/threads", response_model=List[ThreadResponse])
async def list_threads():
    try:
        convos = await get_all_conversations()
        results = []
        for c in convos:
            title = await get_conversation_title(c["thread_id"])
            results.append(ThreadResponse(
                thread_id=c["thread_id"],
                title=title,
                updated_at=c.get("updated_at")
            ))
        return results
    except Exception as e:
        logger.error(f"Error listing threads: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/threads/{thread_id}/messages")
async def get_thread_history(thread_id: str):
    try:
        agent = await get_agent_executor(thread_id, "")
        config = {"configurable": {"thread_id": thread_id}}
        state = await agent.aget_state(config)
        
        if not state or "messages" not in state.values:
            return []

        formatted = []
        model_id = os.getenv("GPT_OSS", "openai.gpt-oss-120b-1:0")
        is_gpt_oss = "openai.gpt-oss" in model_id
        
        for msg in state.values["messages"]:
            msg_type = msg.type if hasattr(msg, "type") else None
            
            # Skip tool and tool_call messages
            if msg_type in ["tool", "tool_call"]:
                continue
            
            # For AI messages, skip those with tool_calls (intermediate responses)
            if msg_type == "ai":
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    continue
                    
                content = msg.content
                reasoning = None
                
                # Handle GPT-OSS list-based content
                if isinstance(content, list) and is_gpt_oss:
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "reasoning_content":
                                reasoning = block.get("reasoning_content", {}).get("text", "")
                            elif block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                    content = "\n\n".join(text_parts).strip()
                
                # Handle string content - filter out tool artifacts
                elif isinstance(content, str):
                    lines = content.split("\n")
                    cleaned_lines = [
                        line for line in lines
                        if not (
                            line.strip().startswith('{"name":') or
                            line.strip().startswith('{"id":') or
                            line.strip().startswith('{"course_id":') or
                            line.strip().startswith("[{") or
                            line.strip().startswith("get_") or
                            "function call" in line.lower()
                        )
                    ]
                    content = "\n".join(cleaned_lines).strip()
                
                if content:  # Only add if there's actual content
                    msg_data = {"type": "assistant", "content": content}
                    if reasoning:
                        msg_data["reasoning"] = reasoning
                    formatted.append(msg_data)
                    
            # For human messages, just include as-is
            elif msg_type == "human":
                formatted.append({
                    "type": "user",
                    "content": msg.content if isinstance(msg.content, str) else str(msg.content)
                })
            
        return formatted
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/threads/{thread_id}")
async def remove_thread(thread_id: str):
    try:
        await delete_conversation(thread_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
async def chat_stream(request: ChatRequest):
    agent = await get_agent_executor(request.thread_id, request.model_id)
    model_id = request.model_id or os.getenv("GPT_OSS", "openai.gpt-oss-120b-1:0")
    is_gpt_oss = "openai.gpt-oss" in model_id
    
    async def event_generator():
        try:
            # Run agent to completion
            complete_result = await agent.ainvoke(
                {"messages": [("user", request.message)]},
                config={"configurable": {"thread_id": request.thread_id}, "recursion_limit": 50}
            )
            
            # Find the final assistant message (skip tool-calling messages)
            final_message = None
            reasoning_text = None
            
            for msg in reversed(complete_result["messages"]):
                if hasattr(msg, "__class__") and msg.__class__.__name__ == "AIMessage":
                    # Skip tool-calling messages
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        continue
                    
                    content = msg.content
                    
                    # Handle GPT-OSS list-based content
                    if isinstance(content, list) and is_gpt_oss:
                        text_parts = []
                        
                        for block in content:
                            if isinstance(block, dict):
                                # Extract reasoning
                                if block.get("type") == "reasoning_content":
                                    reasoning_text = block.get("reasoning_content", {}).get("text", "")
                                # Extract answer text
                                elif block.get("type") == "text":
                                    text_parts.append(block.get("text", ""))
                        
                        final_message = "\n\n".join(text_parts).strip()
                    
                    # Handle string content (other models)
                    elif isinstance(content, str):
                        lines = content.split("\n")
                        cleaned_lines = [
                            line for line in lines
                            if not (
                                line.strip().startswith('{"name":') or
                                line.strip().startswith('{"id":') or
                                line.strip().startswith("get_") or
                                "function call" in line.lower()
                            )
                        ]
                        final_message = "\n".join(cleaned_lines).strip()
                    
                    if final_message:
                        break
            
            if not final_message:
                final_message = "Sorry, I couldn't process that request."
            
            # Stream reasoning first (if exists)
            if reasoning_text:
                yield f"data: {json.dumps({'type': 'reasoning', 'text': reasoning_text})}\n\n"
            
            # Stream final message preserving markdown structure
            # Split by lines and send in small batches to maintain formatting
            lines = final_message.split('\n')
            current_chunk = []
            
            for line in lines:
                current_chunk.append(line)
                
                # Send chunk every 3-5 lines, or at markdown boundaries
                if (len(current_chunk) >= 3 or 
                    line.startswith('#') or 
                    line.strip() == '' or
                    line == lines[-1]):  # Last line
                    
                    chunk_text = '\n'.join(current_chunk)
                    yield f"data: {json.dumps({'type': 'content', 'text': chunk_text + '\n'})}\n\n"
                    current_chunk = []
            
            # Send any remaining lines
            if current_chunk:
                chunk_text = '\n'.join(current_chunk)
                yield f"data: {json.dumps({'type': 'content', 'text': chunk_text})}\n\n"
            
            # Save conversation title
            try:
                if len(request.message) > 0:
                     await save_conversation_title(request.thread_id, request.message[:50])
            except Exception:
                pass

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)