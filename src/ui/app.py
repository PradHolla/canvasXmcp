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

            CRITICAL OUTPUT RULES:
            1. NEVER show raw JSON to users - always format data in natural language
            2. NEVER show technical fields like IDs, raw timestamps, or URLs unless specifically asked
            3. Present information in clean bullet points or numbered lists
            4. Use readable date formats like "October 13, 2025" not "2025-10-13T03:59:59Z"

            COURSE ID RESOLUTION:
            When a user mentions a course by name/code:
            - Step 1: Call get_courses first
            - Step 2: Find matching course and extract numeric "id"
            - Step 3: Use ONLY that numeric ID in subsequent tool calls
            - NEVER pass course names where course_id is expected

            Example:
            User: "Show modules for CS 584"
            You: Call get_courses() → find id:82456 → Call get_modules(course_id="82456")

            ASSIGNMENT LOOKUPS:
            - First call get_assignments to find the assignment by name
            - Then use get_assignment_submission with the assignment name

            RESPONSE FORMATTING:
            Good example:
            "You have 3 assignments due this week:
            • Assignment 1 - Due October 15, 2025 (Submitted, Grade: 100/100)
            • Quiz 2 - Due October 20, 2025 (Not submitted)
            • Homework 3 - Due October 22, 2025 (Submitted, Pending grade)"

            Bad example:
            "[{'id':123,'name':'hw1','due_at':'2025-10-15T03:59:59Z','submitted':true}]"

            Remember: Users are students, not developers. Show human-readable information only.
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


# Replace the on_message function in src/ui/app.py

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
    
    # Create response message
    response_message = cl.Message(content="")
    
    try:
        # Get config
        config = {"configurable": {"thread_id": cl.context.session.id}}
        
        # Run agent and collect ONLY the final AI response
        final_ai_message = None
        
        async for msg, metadata in agent.astream(
            {"messages": [("user", message.content)]},
            stream_mode="messages",
            config=config
        ):
            # Only stream content from AIMessage, skip ToolMessages
            if hasattr(msg, '__class__') and msg.__class__.__name__ == 'AIMessage':
                # Check if it has tool_calls (intermediate step) or just content (final answer)
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    # This is an intermediate tool-calling message, skip it
                    continue
                
                # This is the final response
                if hasattr(msg, "content") and isinstance(msg.content, str):
                    await response_message.stream_token(msg.content)
                    final_ai_message = msg
                elif hasattr(msg, "content") and isinstance(msg.content, list):
                    for item in msg.content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text = item.get("text", "")
                            await response_message.stream_token(text)
        
        # Calculate response time
        response_time = time.time() - start_time
        
        # Get complete result for token tracking
        complete_result = await agent.ainvoke(
            {"messages": [("user", message.content)]},
            config=config
        )
        
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

