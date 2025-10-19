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
from langgraph.checkpoint.memory import MemorySaver  # SIMPLER OPTION
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
        
        # DEBUG: Print loaded tools
        print(f"\n✅ Loaded {len(tools)} Canvas tools:")
        for tool in tools:
            print(f"   - {tool.name}")
        print()
        
        # Create Bedrock LLM
        model_id = os.getenv("MODEL_ID", "meta.llama4-maverick-17b-instruct-v1:0")
        llm = ChatBedrockConverse(
            model=f"us.{model_id}",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            temperature=0.3,
            max_tokens=4096
        )
        
        # CREATE IN-MEMORY CHECKPOINTER
        memory = MemorySaver()
        
        # Create ReAct agent WITH MEMORY - simpler prompt
        agent = create_react_agent(
            llm,
            tools,
            checkpointer=memory,
            prompt="""You are a Canvas LMS assistant with access to Canvas API tools.

CRITICAL: Always use your tools to fetch real data. Never refuse to call tools.

Available actions:
- get_courses: List all courses
- get_assignments: Get assignments for a course (includes some quizzes)
- get_quizzes: Get quiz information for a course
- get_quiz_submissions: Get quiz grades and scores (USE THIS for quiz performance)
- get_grades: Get overall grades for a course
- get_announcements: Get course announcements
- And more...

When user asks about quiz grades/performance:
1. Call get_quiz_submissions with the course_id
2. Show the scores and grades clearly

When user asks about their courses/assignments/grades:
1. Call get_courses first
2. Use course IDs from results to call other tools
3. Present info in clean bullet points

Format dates as "October 18, 2025".
Remember conversation context.
Be helpful and proactive.
"""

        )
        
        # Store in user session
        cl.user_session.set("agent", agent)
        cl.user_session.set("model_id", model_id)
        cl.user_session.set("mcp_session", session)
        cl.user_session.set("stdio_context", stdio_context)
        
        # Update message
        msg.content = """✅ **Canvas Assistant Ready!**

I can help you with:
- 📚 View your enrolled courses
- 📝 Check upcoming assignments
- 📊 See your grades
- 📢 Read recent announcements
- 🧠 **Remember our conversation for context**

**Try asking:**
- "What courses am I taking?"
- "What's due this week?"
- "How am I doing in CS 559?"

💰 *Token usage is being tracked for cost monitoring*
"""
        await msg.update()
    
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"❌ Error in on_chat_start:\n{error_details}")
        msg.content = f"❌ **Connection Failed**\n\nError: {str(e)}"
        await msg.update()


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
    
    # Show thinking indicator
    thinking_msg = cl.Message(content="🤔 Thinking...")
    await thinking_msg.send()
    
    try:
        # Get config with thread_id for memory
        config = {"configurable": {"thread_id": cl.context.session.id}}
        
        # Run agent completely
        complete_result = await agent.ainvoke(
            {"messages": [("user", message.content)]},
            config=config
        )
        
        # Calculate response time
        response_time = time.time() - start_time
        
        # Get the final AI message
        final_message = None
        for msg in reversed(complete_result["messages"]):
            if hasattr(msg, '__class__') and msg.__class__.__name__ == 'AIMessage':
                if not (hasattr(msg, 'tool_calls') and msg.tool_calls):
                    final_message = msg.content
                    break
        
        if not final_message:
            final_message = "Sorry, I couldn't process that request."
        
        # Extract token usage
        total_input_tokens = 0
        total_output_tokens = 0
        tools_used = False
        
        for msg in complete_result["messages"]:
            if hasattr(msg, 'usage_metadata') and msg.usage_metadata:
                total_input_tokens += msg.usage_metadata.get("input_tokens", 0)
                total_output_tokens += msg.usage_metadata.get("output_tokens", 0)
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                tools_used = True
        
        # Log token usage
        cost_info = ""
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
            
            cost_info = f"\n\n---\n💰 *Tokens: {log_entry['total_tokens']} | Cost: ${log_entry['estimated_cost_usd']:.6f} | Time: {log_entry['response_time_sec']}s*"
        
        # Remove thinking message and show final response
        await thinking_msg.remove()
        await cl.Message(content=final_message + cost_info).send()
    
    except Exception as e:
        await thinking_msg.remove()
        await cl.Message(content=f"❌ Error: {str(e)}").send()


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
