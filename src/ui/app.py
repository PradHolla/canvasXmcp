import chainlit as cl
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from langchain_aws import ChatBedrockConverse
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Add parent directory to path
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from src.utils.token_tracker import TokenTracker

load_dotenv()


@cl.on_chat_start
async def on_chat_start():
    """Initialize the chat session with Canvas MCP connection"""
    
    # Initialize token tracker
    tracker = TokenTracker()
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    cl.user_session.set("tracker", tracker)
    cl.user_session.set("session_id", session_id)
    
    # Show loading message
    msg = cl.Message(content="🔌 Connecting to Canvas...")
    await msg.send()
    
    try:
        # MCP server parameters
        server_params = StdioServerParameters(
            command="sh",
            args=["-c", "PYTHONPATH=. uv run src/mcp/canvas_server.py"]
        )
        
        # Connect to MCP server
        stdio_context = stdio_client(server_params)
        read, write = await stdio_context.__aenter__()
        
        session = ClientSession(read, write)
        await session.__aenter__()
        await session.initialize()
        
        # Load Canvas tools
        tools = await load_mcp_tools(session)
        
        # Create Bedrock LLM
        model_id = os.getenv("MODEL_ID", "meta.llama4-maverick-17b-instruct-v1:0")
        llm = ChatBedrockConverse(
            model=f"us.{model_id}",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            temperature=0.3,
            max_tokens=4096
        )
        
        # Create ReAct agent
        agent = create_react_agent(
            llm,
            tools,
            prompt="""You are a helpful Canvas LMS assistant for students.

Your job is to help students with:
- Finding information about their courses
- Checking assignments and deadlines
- Viewing grades and submission status
- Reading recent announcements
- Managing their academic workload

IMPORTANT GUIDELINES:
1. Use tools to fetch data, but DO NOT show raw JSON output to users
2. Format information in a clean, readable way
3. For dates, use format like "October 10, 2025" not ISO timestamps
4. When finding a course by name/code:
   - Call get_courses first
   - CAREFULLY match the course code (e.g., "CS 555" matches "2025F CS 555-A")
   - Look at BOTH the "name" field (like "2025F CS 555-A") AND "course_code" field (like "Agile Methods...")
   - Use the EXACT course_id from the matching course
   - Double-check you're using the right course before calling other tools
5. Only call each tool ONCE per query - don't retry unless there's an error
6. When listing items (assignments, files), use bullet points or numbered lists
7. Summarize information concisely - users don't need to see every field

Example good responses:
- "You have 3 upcoming assignments: Assignment 1 (due Oct 15), Quiz 2 (due Oct 20)..."
- "Your NLP course has 10 files including: syllabus.pdf, lecture1.pdf..."

Example bad responses:
- Showing raw JSON like [{"id":123,"name":"hw1"...}]
- Repeating the same tool call multiple times
- Including technical field names like "course_id", "folder_id"
"""

            )
        
        # Store in user session
        cl.user_session.set("agent", agent)
        cl.user_session.set("mcp_session", session)
        cl.user_session.set("stdio_context", stdio_context)
        cl.user_session.set("model_id", model_id)
        
        # Update message
        msg.content = """✅ **Canvas Assistant Ready!**

I can help you with:
- 📚 View your enrolled courses
- 📝 Check upcoming assignments
- 📊 See your grades
- 📢 Read recent announcements

**Try asking:**
- "What courses am I enrolled in?"
- "What assignments are due this week?"
- "Show me my grades for CS 559"

💰 *Token usage is being tracked for cost monitoring*
"""
        await msg.update()
    
    except Exception as e:
        msg.content = f"❌ **Connection Failed**\n\nError: {str(e)}"
        await msg.update()


@cl.on_chat_end
async def on_chat_end():
    """Clean up MCP connection and show cost summary"""
    session = cl.user_session.get("mcp_session")
    stdio_context = cl.user_session.get("stdio_context")
    tracker = cl.user_session.get("tracker")
    
    # Show session summary
    if tracker:
        summary = tracker.get_summary()
        await cl.Message(
            content=f"""📊 **Session Summary**

Total queries: {summary['total_queries']}
Total tokens: {summary['total_tokens']:,}
Total cost: ${summary['total_cost_usd']:.4f}
"""
        ).send()
    
    # Clean up connections
    if session:
        await session.__aexit__(None, None, None)
    if stdio_context:
        await stdio_context.__aexit__(None, None, None)


@cl.on_message
async def on_message(message: cl.Message):
    """Process user messages with token tracking"""
    
    agent = cl.user_session.get("agent")
    tracker = cl.user_session.get("tracker")
    model_id = cl.user_session.get("model_id")
    session_id = cl.user_session.get("session_id")
    
    if not agent:
        await cl.Message(
            content="⚠️ Canvas connection not ready. Please refresh the page."
        ).send()
        return
    
    # Track start time
    start_time = time.time()
    
    # Create callback handler for streaming
    cb = cl.AsyncLangchainCallbackHandler()
    
    # Create response message
    response_message = cl.Message(content="")
    
    try:
        # Stream the agent response
        config = {
            "callbacks": [cb],
            "configurable": {"thread_id": cl.context.session.id}
        }
        
        result = None
        async for msg, metadata in agent.astream(
            {"messages": [("user", message.content)]},
            stream_mode="messages",
            config=config
        ):
            # Store the full result for token tracking
            if metadata:
                result = metadata
            
            # Stream text content
            if hasattr(msg, "content") and isinstance(msg.content, str):
                await response_message.stream_token(msg.content)
            elif hasattr(msg, "content") and isinstance(msg.content, list):
                for item in msg.content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        await response_message.stream_token(item.get("text", ""))
        
        # Calculate response time
        response_time = time.time() - start_time
        
        # Get the final result by invoking once more (to capture metadata)
        final_result = await agent.ainvoke(
            {"messages": [("user", message.content)]},
            config=config
        )
        
        # Extract token usage
        total_input_tokens = 0
        total_output_tokens = 0
        
        for msg in final_result["messages"]:
            if hasattr(msg, 'usage_metadata') and msg.usage_metadata:
                total_input_tokens += msg.usage_metadata.get("input_tokens", 0)
                total_output_tokens += msg.usage_metadata.get("output_tokens", 0)
        
        # Check if tools were used
        tools_used = any(
            hasattr(msg, 'tool_calls') and msg.tool_calls
            for msg in final_result["messages"]
        )
        
        # Log token usage
        if tracker and (total_input_tokens > 0 or total_output_tokens > 0):
            log_entry = tracker.log_usage(
                model_id=model_id,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                query=message.content,
                response_time=response_time,
                tools_used=tools_used,
                session_id=session_id
            )
            
            # Add cost info to response
            cost_info = f"\n\n---\n💰 *Tokens: {log_entry['total_tokens']} | Cost: ${log_entry['estimated_cost_usd']:.6f} | Time: {log_entry['response_time_sec']}s*"
            response_message.content += cost_info
        
        # Send complete message
        await response_message.update()
    
    except Exception as e:
        await cl.Message(content=f"❌ Error: {str(e)}").send()
