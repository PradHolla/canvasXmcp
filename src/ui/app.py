# src/ui/app.py

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
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from datetime import datetime
from langchain_core.messages import HumanMessage

# Add parent directory to path
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from src.utils.token_tracker import TokenTracker
from src.agent.checkpointer import (
    get_checkpointer,
    close_checkpointer,
    get_all_conversations,
    get_conversation_title,
    delete_conversation,
    initialize_metadata_table,
)

load_dotenv()
initialize_metadata_table()
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get current date for context
today = datetime.now()
current_date = today.strftime("%A, %B %d, %Y")  # "Sunday, November 09, 2025"


@cl.action_callback("new_chat")
async def on_new_chat(action):
    """Create a new conversation"""
    import uuid

    new_thread_id = str(uuid.uuid4())

    cl.user_session.set("thread_id", new_thread_id)

    await cl.Message(
        content="🆕 **New conversation started!**\n\nWhat would you like to know?"
    ).send()


@cl.action_callback("load_conversation")
async def on_load_conversation(action):
    """Load a previous conversation"""
    thread_id = action.payload["thread_id"]

    cl.user_session.set("thread_id", thread_id)

    agent = cl.user_session.get("agent")
    config = {"configurable": {"thread_id": thread_id}}

    try:
        state = await agent.aget_state(config)

        if state and "messages" in state.values:
            messages = state.values["messages"]

            # Filter to show only user and assistant messages
            display_messages = []
            for msg in messages:
                if hasattr(msg, "type"):
                    if msg.type == "user":
                        content = (
                            msg.content
                            if isinstance(msg.content, str)
                            else str(msg.content)
                        )
                        display_messages.append(f"**👤 You:** {content[:150]}")
                    elif msg.type == "assistant":
                        # Handle different content formats
                        if isinstance(msg.content, str):
                            display_messages.append(
                                f"**🤖 Assistant:** {msg.content[:150]}"
                            )
                        elif isinstance(msg.content, list):
                            # GPT-OSS format - extract text blocks
                            text_parts = [
                                block.get("text", "")
                                for block in msg.content
                                if isinstance(block, dict)
                                and block.get("type") == "text"
                            ]
                            if text_parts:
                                display_messages.append(
                                    f"**🤖 Assistant:** {text_parts[0][:150]}"
                                )

            # Show last 5 messages
            preview = "📜 **Conversation Loaded!**\n\n"
            preview += f"Total messages: {len(messages)} | Showing last 5:\n\n"
            preview += "\n\n".join(display_messages[-5:])
            preview += "\n\n---\n✅ **You can now continue this conversation!**"

            await cl.Message(content=preview).send()
        else:
            await cl.Message(content="⚠️ No messages found in this conversation.").send()

    except Exception as e:
        logger.error(f"Error loading conversation: {e}")
        await cl.Message(content=f"❌ Error loading conversation: {str(e)}").send()


@cl.action_callback("delete_conversation")
async def on_delete_conversation(action):
    """Delete a conversation"""
    thread_id = action.payload["thread_id"]  # ✅ Extract from dict

    try:
        await delete_conversation(thread_id)
        await cl.Message(content="🗑️ Conversation deleted!").send()
    except Exception as e:
        await cl.Message(content=f"❌ Error deleting: {str(e)}").send()


@cl.on_chat_start
async def on_chat_start():
    """Initialize the chat session with Canvas MCP connection"""

    # Initialize token tracker
    tracker = TokenTracker()
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    cl.user_session.set("tracker", tracker)
    cl.user_session.set("session_id", session_id)

    thread_id = cl.user_session.get("id")  # Chainlit's session ID
    cl.user_session.set("thread_id", thread_id)
    logger.info(f"Starting conversation with thread_id: {thread_id}")

    # Show loading message
    msg = cl.Message(content="🔌 Connecting to Canvas...")
    await msg.send()

    try:
        # MCP server parameters
        server_params = StdioServerParameters(
            command="sh", args=["-c", "PYTHONPATH=. uv run src/mcp/canvas_server.py"]
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
        model_id = os.getenv("GPT_OSS", "openai.gpt-oss-120b-1:0")
        llm = ChatBedrockConverse(
            model=f"{model_id}",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            temperature=0.3,
            max_tokens=4096,
        )

        # Create memory
        memory = await get_checkpointer()

        # Create ReAct agent with memory
        agent = create_react_agent(
            llm,
            tools,
            checkpointer=memory,
            prompt=f"""You are a Canvas LMS assistant that helps students with their coursework.

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
""",
        )

        # Store in user session
        cl.user_session.set("agent", agent)
        cl.user_session.set("model_id", model_id)
        cl.user_session.set("mcp_session", session)
        cl.user_session.set("stdio_context", stdio_context)

        conversations = await get_all_conversations()

        actions = [
            cl.Action(
                name="new_chat",
                payload={"action": "new"},  # ✅ Dictionary, not string
                label="🆕 New Chat",
            )
        ]

        for conv in conversations[:10]:
            title = await get_conversation_title(conv["thread_id"])

            actions.append(
                cl.Action(
                    name="load_conversation",
                    payload={"thread_id": conv["thread_id"]},  # ✅ Dictionary
                    label=f"💬 {title}",
                )
            )

        # Update welcome message with actions
        msg.content = f"""✅ **Canvas Assistant Ready!**

I can help you with:
- 📚 View your enrolled courses
- 📝 Check upcoming assignments
- 📊 See your grades
- 📢 Read recent announcements
- 🧠 Remember our conversation

**Previous Conversations:** {len(conversations)}

💰 *Token usage is being tracked*
"""

        msg.actions = actions  # Add action buttons
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
    thread_id = cl.user_session.get("thread_id")

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
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}

        # Run agent
        complete_result = await agent.ainvoke(
            {"messages": [("user", message.content)]}, config=config
        )

        state = await agent.aget_state(config)
        all_messages = state.values.get("messages", [])

        # Filter for HumanMessage instances
        human_messages = [m for m in all_messages if isinstance(m, HumanMessage)]

        # Save title if first message
        if len(human_messages) == 1:
            from src.agent.checkpointer import save_conversation_title

            title = message.content[:50]
            await save_conversation_title(thread_id, title)
            logger.info(f"SAVED TITLE: '{title}'")

        # Calculate response time
        response_time = time.time() - start_time

        # Detect if using GPT-OSS model
        is_gpt_oss = "openai.gpt-oss" in model_id

        # Extract final AI message with model-specific handling
        final_message = None
        reasoning_text = None
        elements = []

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
                                reasoning_text = block.get("reasoning_content", {}).get(
                                    "text", ""
                                )

                            # Extract answer text
                            elif block.get("type") == "text":
                                text_parts.append(block.get("text", ""))

                    final_message = "\n\n".join(text_parts).strip()

                    # Create reasoning accordion if reasoning exists
                    if reasoning_text:
                        reasoning_element = cl.CustomElement(
                            name="ReasoningAccordion",
                            props={"reasoning": reasoning_text},
                            display="inline",
                        )
                        elements.append(reasoning_element)

                # Handle Llama Maverick string content
                elif isinstance(content, str):
                    lines = content.split("\n")
                    cleaned_lines = [
                        line
                        for line in lines
                        if not (
                            line.strip().startswith('{"name":')
                            or line.strip().startswith("get_")
                            or "function call" in line.lower()
                        )
                    ]
                    final_message = "\n".join(cleaned_lines).strip()

                if final_message:
                    break

        if not final_message:
            final_message = "Sorry, I couldn't process that request."

        # Extract token usage (same as before)
        total_input_tokens = 0
        total_output_tokens = 0
        tools_used = False

        for msg in complete_result["messages"]:
            if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                total_input_tokens += msg.usage_metadata.get("input_tokens", 0)
                total_output_tokens += msg.usage_metadata.get("output_tokens", 0)
            if hasattr(msg, "tool_calls") and msg.tool_calls:
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
                session_id=session_id,
            )

            cost_info = f"\n\n---\n💰 *Tokens: {log_entry['total_tokens']} | Cost: ${log_entry['estimated_cost_usd']:.6f} | Time: {log_entry['response_time_sec']}s*"

        # Send final response with reasoning accordion (if exists)
        await thinking_msg.remove()
        await cl.Message(
            content=final_message + cost_info,
            elements=elements,  # Attach reasoning accordion
        ).send()

    except Exception as e:
        logger.error(f"Error in on_message: {e}", exc_info=True)
        await thinking_msg.remove()
        await cl.Message(content=f"❌ Error: {str(e)}").send()


@cl.on_chat_end
async def on_chat_end():
    """Clean up MCP connection and show cost summary"""
    tracker = cl.user_session.get("tracker")

    # Show session summary
    if tracker:
        summary = tracker.get_summary()
        await cl.Message(
            content=f"""📊 **Session Summary**

    Total queries: {summary["total_queries"]}
    Total tokens: {summary["total_tokens"]:,}
    Total cost: ${summary["total_cost_usd"]:.4f}
    """
        ).send()

    await close_checkpointer()
