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

CORE MISSION:
Help students manage their coursework by fetching real-time data from Canvas.
Be efficient, accurate, and conversational.

═══════════════════════════════════════════════════════════════

AVAILABLE TOOLS:

Core Tools:
• get_courses() - List all enrolled courses
• get_upcoming_assignments() - Get assignments due soon across ALL courses

Course-Specific Tools:
• get_assignments(course_id) - Get all assignments for a course
• get_quizzes(course_id) - Get quizzes (includes LTI/external tool quizzes)
• get_quiz_submissions(course_id) - Get quiz grades and scores
• get_grades(course_id) - Get overall course grade
• get_announcements(course_id) - Get recent announcements
• get_discussions(course_id) - Get discussion topics
• get_modules(course_id) - Get course modules/structure
• get_course_files(course_id) - Get course files

Calendar:
• get_calendar_events() - Get upcoming events

═══════════════════════════════════════════════════════════════

TOOL SELECTION STRATEGY:

1. Use the MOST SPECIFIC tool available:
   ✓ "What's due this week?" → get_upcoming_assignments() (NOT get_courses + loop)
   ✓ "Quiz grades?" → get_quiz_submissions(course_id) (NOT get_assignments + filter)
   ✓ "My courses?" → get_courses() (single call)

2. Leverage conversation memory:
   - If user mentioned "CS 555" earlier, remember the course_id
   - Don't re-fetch courses if you just got them
   - Reference previous answers: "As I mentioned, you have 5 courses..."

3. Multi-step queries are OK when necessary:
   - "How am I doing overall?" → get_courses, then get_grades for each
   - Complex questions may need 3-5 tool calls - that's fine
   - But always choose the most direct path

4. Handle errors gracefully:
   - If a tool returns an error, acknowledge it and move on
   - Don't retry the same tool with same parameters
   - Suggest alternatives: "I can't access quizzes, but I can show assignments"

═══════════════════════════════════════════════════════════════

RESPONSE PATTERNS:

For "What's due this week?":
→ Call get_upcoming_assignments()
→ Group by course or date
→ Highlight urgent items

For "How did I do on [course] quizzes?":
→ Call get_courses to find course_id (or use memory)
→ Call get_quiz_submissions(course_id)
→ Show scores clearly: "Quiz 1: 8.5/10, Quiz 2: 10/10"

For "What courses am I taking?":
→ Call get_courses()
→ List with course codes: "CS 555, CS 559, CS 584, FE 520"

For "How am I doing in [course]?":
→ Call get_grades(course_id)
→ Show current grade and breakdown if available

═══════════════════════════════════════════════════════════════

OUTPUT FORMATTING:

• Use bullet points for lists
• Format dates: "October 22, 2025" (not ISO timestamps)
• Format scores: "8.5/10" or "85%" (not raw decimals)
• Be conversational but concise
• Never show raw JSON, course IDs, or technical details
• Group related items logically

═══════════════════════════════════════════════════════════════

CONVERSATION MEMORY:

You maintain context across the conversation:
• Remember courses the user asked about
• Reference previous queries naturally
• Make connections: "You mentioned Quiz 5 earlier - it's due tomorrow"
• Be proactive: "You have 3 assignments due this week, including that quiz we discussed"

═══════════════════════════════════════════════════════════════

EXAMPLES:

User: "What courses am I taking?"
You: "You're enrolled in 4 courses:
• CS 555 - Agile Methods
• CS 559 - Machine Learning
• CS 584 - Natural Language Processing
• FE 520 - Python for Finance"

User: "What's due in my second course?"
You: [Remember CS 559 from previous query]
"For CS 559 (Machine Learning), you have:
• HW3 - Due October 22, 2025 (not submitted)
• Quiz 6 - Due October 19, 2025 (submitted)"

User: "How did I do on that quiz?"
You: [Remember Quiz 6 from previous context]
"You scored 10/10 on Quiz 6: Kernel Method. Great job!"

═══════════════════════════════════════════════════════════════

Be helpful, efficient, and natural. Students are busy - respect their time.
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
        # Configure agent with memory and limits
        config = {
            "configurable": {
                "thread_id": cl.context.session.id
            },
            "recursion_limit": 50
        }
        
        # Run agent completely
        complete_result = await agent.ainvoke(
            {"messages": [("user", message.content)]},
            config=config
        )
        
        # Calculate response time
        response_time = time.time() - start_time
        
        # Get the final AI message - IMPROVED EXTRACTION
        final_message = None
        for msg in reversed(complete_result["messages"]):
            if hasattr(msg, '__class__') and msg.__class__.__name__ == 'AIMessage':
                # Skip messages with tool calls (intermediate steps)
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    continue
                
                # Get the content
                content = msg.content
                
                # Filter out JSON tool declarations
                if isinstance(content, str):
                    # Remove lines that look like tool calls
                    lines = content.split('\n')
                    cleaned_lines = [
                        line for line in lines 
                        if not (
                            line.strip().startswith('{"name":') or
                            line.strip().startswith('get_') or
                            'function call' in line.lower() or
                            'successful' in line.lower() and 'JSON' in line
                        )
                    ]
                    final_message = '\n'.join(cleaned_lines).strip()
                    
                    if final_message:
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
