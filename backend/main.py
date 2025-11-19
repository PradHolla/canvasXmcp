import os
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# LangChain & MCP Imports
from langchain_aws import ChatBedrockConverse
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# Import your existing modules
# Ensure your PYTHONPATH includes the root directory so these work
from src.utils.token_tracker import TokenTracker
from src.agent.checkpointer import (
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
    """
    Manages the lifecycle of the application.
    Starts the MCP server connection once and keeps it alive.
    """
    logger.info("🚀 Starting Canvas LMS Agent API...")
    
    # 1. Initialize Metadata Table for History
    await initialize_metadata_table()
    
    # 2. Connect to MCP Server
    # We use a single global connection for the backend to avoid 
    # spawning a new subprocess for every request.
    try:
        server_params = StdioServerParameters(
            command="sh", 
            args=["-c", "PYTHONPATH=. uv run src/mcp/canvas_server.py"]
        )
        
        # Start the stdio client
        app.state.stdio_context = stdio_client(server_params)
        read, write = await app.state.stdio_context.__aenter__()
        
        app.state.mcp_session = ClientSession(read, write)
        await app.state.mcp_session.__aenter__()
        await app.state.mcp_session.initialize()
        
        # 3. Load Tools
        app.state.tools = await load_mcp_tools(app.state.mcp_session)
        logger.info(f"✅ Loaded {len(app.state.tools)} Canvas tools via MCP")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize MCP server: {e}")
        raise e

    yield

    # Cleanup
    logger.info("🛑 Shutting down MCP connection...")
    if hasattr(app.state, "mcp_session"):
        await app.state.mcp_session.__aexit__(None, None, None)
    if hasattr(app.state, "stdio_context"):
        await app.state.stdio_context.__aexit__(None, None, None)

# --- App Setup ---
app = FastAPI(title="Canvas LMS Agent API", lifespan=lifespan)

# CORS - Allow your React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"], # Adjust for your frontend port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Helper Functions ---

def get_system_prompt() -> str:
    """Generate the system prompt with dynamic date"""
    today = datetime.now()
    current_date = today.strftime("%A, %B %d, %Y")
    
    return f"""You are a Canvas LMS assistant that helps students with their coursework.

TODAY'S DATE: {current_date}

TOOLS:
- get_courses() - enrolled courses
- get_upcoming_assignments(days=7, include_overdue=True) - assignments due in next N days
- get_assignments(course_id) - all assignments for a specific course
- get_quizzes(course_id) - course quizzes with grades
- get_grades(course_id) - grade for a specific course
- get_all_grades() - all course grades at once
- get_course_summary(course_id) - complete course overview
- get_announcements(days=7) - recent announcements
- get_course_id_by_name(name) - find course ID by name
- submit_assignment(course_id, assignment_id, file_path, comment) - submit file to assignment

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

Examples:
User: "What's due this week?"
Reasoning: Today is Sunday Nov 9. End of week is Saturday Nov 15. That's 6 days ahead.
Call: get_upcoming_assignments(days=6)

User: "What's due this month?"
Reasoning: Today is Nov 9. End of November is Nov 30. That's 21 days ahead.
Call: get_upcoming_assignments(days=21)

User: "What's overdue?"
Reasoning: User wants only overdue items. Use 0 days with include_overdue=True.
Call: get_upcoming_assignments(days=0, include_overdue=True)

Present information cleanly with bullet points. No raw JSON.
"""

async def get_agent_executor(thread_id: str, model_id: str):
    """
    Reconstructs the agent for a specific request.
    This is lightweight because tools are already loaded in app.state.
    """
    # Checkpointer (Memory)
    checkpointer = await get_checkpointer()
    
    # LLM
    # Default to GPT-OSS if not specified, or env variable
    final_model_id = model_id or os.getenv("GPT_OSS", "openai.gpt-oss-120b-1:0")
    
    llm = ChatBedrockConverse(
        model=final_model_id,
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        temperature=0.3,
        max_tokens=4096,
    )

    # Create Agent
    agent = create_react_agent(
        llm,
        app.state.tools,
        checkpointer=checkpointer,
        state_modifier=get_system_prompt() # Dynamic prompt injection
    )
    
    return agent

# --- Routes ---

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "mcp_tools": len(app.state.tools)}

@app.get("/api/threads", response_model=List[ThreadResponse])
async def list_threads():
    """Get all conversation threads"""
    try:
        convos = await get_all_conversations()
        results = []
        for c in convos:
            title = await get_conversation_title(c["thread_id"])
            results.append(ThreadResponse(
                thread_id=c["thread_id"],
                title=title,
                updated_at=c.get("updated_at") # Assuming your DB has this, or None
            ))
        return results
    except Exception as e:
        logger.error(f"Error listing threads: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/threads/{thread_id}/messages")
async def get_thread_history(thread_id: str):
    """Get full message history for a thread"""
    try:
        agent = await get_agent_executor(thread_id, "")
        config = {"configurable": {"thread_id": thread_id}}
        state = await agent.aget_state(config)
        
        if not state or "messages" not in state.values:
            return []

        # Format messages for frontend
        formatted = []
        for msg in state.values["messages"]:
            msg_type = msg.type
            content = msg.content
            
            # Clean up GPT-OSS list format if present
            if isinstance(content, list):
                text_parts = [b["text"] for b in content if b.get("type") == "text"]
                content = "\n".join(text_parts)
            
            formatted.append({
                "type": msg_type,
                "content": content,
                # Add tool calls if needed for UI debugging
                "tool_calls": getattr(msg, "tool_calls", [])
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
    """
    Streaming chat endpoint.
    Returns Server-Sent Events (SSE) with tokens, tool updates, and reasoning.
    """
    agent = await get_agent_executor(request.thread_id, request.model_id)
    tracker = TokenTracker()
    
    async def event_generator():
        start_time = time.time()
        input_tokens = 0
        output_tokens = 0
        tools_used = False
        
        # Check if this is a new thread (no history) to generate a title
        # (Logic simplified: usually frontend handles 'New Chat' state)
        
        try:
            async for event in agent.astream_events(
                {"messages": [("user", request.message)]},
                config={"configurable": {"thread_id": request.thread_id}, "recursion_limit": 50},
                version="v1"
            ):
                kind = event["event"]
                
                # 1. Stream LLM Tokens (Content)
                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if chunk.content:
                        # Normalize content (handle list vs str)
                        text = chunk.content
                        if isinstance(text, list):
                            # Handle GPT-OSS specialized blocks
                            for block in text:
                                if block.get("type") == "text":
                                    yield f"data: {json.dumps({'type': 'content', 'text': block['text']})}\n\n"
                                elif block.get("type") == "reasoning_content":
                                    yield f"data: {json.dumps({'type': 'reasoning', 'text': block['reasoning_content']['text']})}\n\n"
                        else:
                            # Standard Llama/Claude string
                            yield f"data: {json.dumps({'type': 'content', 'text': text})}\n\n"
                            
                    # Track tokens roughly (Bedrock provides exact counts in usage_metadata at end)
                    if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                         input_tokens += chunk.usage_metadata.get("input_tokens", 0)
                         output_tokens += chunk.usage_metadata.get("output_tokens", 0)

                # 2. Stream Tool Usage Indicators
                elif kind == "on_tool_start":
                    tool_name = event["name"]
                    yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name})}\n\n"
                    tools_used = True
                    
                elif kind == "on_tool_end":
                    tool_name = event["name"]
                    yield f"data: {json.dumps({'type': 'tool_end', 'tool': tool_name})}\n\n"

            # 3. Post-Processing: Title Generation & Cost Logging
            response_time = time.time() - start_time
            
            # Log tokens
            if input_tokens > 0 or output_tokens > 0:
                log = tracker.log_usage(
                    model_id=request.model_id or "default",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    query=request.message,
                    response_time=response_time,
                    tools_used=tools_used,
                    session_id=request.thread_id
                )
                yield f"data: {json.dumps({'type': 'usage', 'cost': log['estimated_cost_usd'], 'tokens': log['total_tokens']})}\n\n"

            # Generate Title for new threads (simple heuristic)
            # In a real app, you might check if thread history len == 2
            if len(request.message) < 50: # Simplistic check
                await save_conversation_title(request.thread_id, request.message[:50])

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)