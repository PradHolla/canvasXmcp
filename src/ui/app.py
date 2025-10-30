import chainlit as cl
import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from langchain_aws import ChatBedrockConverse
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Add parent directory to path
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from src.utils.token_tracker import TokenTracker

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
        logger.info(f"Loaded {len(tools)} Canvas tools")
        
        # Create Bedrock LLM
        model_id = os.getenv("GPT_OS", "us.meta.llama4-maverick-17b-instruct-v1:0")
        llm = ChatBedrockConverse(
            model=f"{model_id}",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            temperature=0.3,
            max_tokens=4096
        )
        
        # Create memory
        memory = MemorySaver()
        
        # Create ReAct agent with memory
        agent = create_react_agent(
            llm,
            tools,
            checkpointer=memory,
            prompt="""You are a Canvas LMS assistant that helps students with their coursework.

TOOLS:
- get_courses() - enrolled courses
- get_upcoming_assignments(days=7) - assignments due soon
- get_assignments(course_id) - all course assignments
- get_quizzes(course_id) - course quizzes with grades
- get_grades(course_id) - course grade
- get_all_grades() - all course grades at once
- get_course_summary(course_id) - complete course overview
- get_announcements(days=7) - recent announcements
- get_course_id_by_name(name) - find course ID by name

RULES:
1. Use tools to get real data
2. Choose the most specific tool
3. Remember context from conversation
4. Format dates as "October 23, 2025"
5. Format scores as "8.5/10"
6. Never show course IDs or technical details
7. Be concise and helpful

IMPORTANT: Canvas APIs need numeric course IDs (like "80546"), not names.
If user mentions a course by name, call get_course_id_by_name() first.

Present information cleanly with bullet points. No raw JSON.
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
- 🧠 Remember our conversation

**Try asking:**
- "What courses am I taking?"
- "What's due this week?"
- "How am I doing in CS 559?"

💰 *Token usage is being tracked*
"""
        await msg.update()
    
    except Exception as e:
        logger.error(f"Error in on_chat_start: {e}", exc_info=True)
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
        # Configure agent with memory and limits
        config = {
            "configurable": {"thread_id": cl.context.session.id},
            "recursion_limit": 50
        }
        
        # Run agent
        complete_result = await agent.ainvoke(
            {"messages": [("user", message.content)]},
            config=config
        )
        
        # Calculate response time
        response_time = time.time() - start_time
        
        # Detect if using GPT-OSS model
        is_gpt_oss = "openai.gpt-oss" in model_id
        
        # Extract final AI message with model-specific handling
        final_message = None
        reasoning_text = None
        elements = []
        
        for msg in reversed(complete_result["messages"]):
            if hasattr(msg, '__class__') and msg.__class__.__name__ == 'AIMessage':
                # Skip tool-calling messages
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    continue
                
                content = msg.content
                
                # Handle GPT-OSS list-based content
                if isinstance(content, list) and is_gpt_oss:
                    text_parts = []
                    
                    for block in content:
                        if isinstance(block, dict):
                            # Extract reasoning
                            if block.get('type') == 'reasoning_content':
                                reasoning_text = block.get('reasoning_content', {}).get('text', '')
                            
                            # Extract answer text
                            elif block.get('type') == 'text':
                                text_parts.append(block.get('text', ''))
                    
                    final_message = '\n\n'.join(text_parts).strip()
                    
                    # Create reasoning accordion if reasoning exists
                    if reasoning_text:
                        reasoning_element = cl.CustomElement(
                            name="ReasoningAccordion",
                            props={"reasoning": reasoning_text},
                            display="inline"
                        )
                        elements.append(reasoning_element)
                
                # Handle Llama Maverick string content
                elif isinstance(content, str):
                    lines = content.split('\n')
                    cleaned_lines = [
                        line for line in lines 
                        if not (
                            line.strip().startswith('{"name":') or
                            line.strip().startswith('get_') or
                            'function call' in line.lower()
                        )
                    ]
                    final_message = '\n'.join(cleaned_lines).strip()
                
                if final_message:
                    break
        
        if not final_message:
            final_message = "Sorry, I couldn't process that request."
        
        # Extract token usage (same as before)
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
        
        # Send final response with reasoning accordion (if exists)
        await thinking_msg.remove()
        await cl.Message(
            content=final_message + cost_info,
            elements=elements  # Attach reasoning accordion
        ).send()
    
    except Exception as e:
        logger.error(f"Error in on_message: {e}", exc_info=True)
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
    try:
        if session:
            await session.__aexit__(None, None, None)
        if stdio_context:
            await stdio_context.__aexit__(None, None, None)
    except Exception as e:
        logger.error(f"Error cleaning up connections: {e}")
