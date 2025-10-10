# src/agent/canvas_agent.py
import os
import time
from dotenv import load_dotenv
from langchain_aws import ChatBedrockConverse
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from datetime import datetime
from src.utils.token_tracker import TokenTracker

load_dotenv()


class CanvasAgent:
    """Agent that uses Canvas MCP tools with Bedrock LLM"""

    def __init__(self):
        self.model_id = os.getenv("SCOUT", "meta.llama4-maverick-17b-instruct-v1:0")
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.agent = None
        self.session = None
        self.server_params = None
        self.stdio_context = None
        self.tracker = TokenTracker()
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    async def initialize(self):
        """Initialize the agent with MCP tools and Bedrock LLM"""

        print("🤖 Initializing Canvas Agent...")

        # 1. Create Bedrock LLM
        print("   ↳ Connecting to Bedrock...")
        self.llm = ChatBedrockConverse(
            model=f"us.{self.model_id}",
            region_name=self.region,
            temperature=0.3,
            max_tokens=4096,
        )

        # 2. Set up MCP server parameters
        self.server_params = StdioServerParameters(
            command="sh", args=["-c", "PYTHONPATH=. uv run src/mcp/canvas_server.py"]
        )

        # 3. Connect to Canvas MCP server and load tools
        print("   ↳ Connecting to Canvas MCP server...")
        self.stdio_context = stdio_client(self.server_params)
        read, write = await self.stdio_context.__aenter__()

        self.session = ClientSession(read, write)
        await self.session.__aenter__()
        await self.session.initialize()

        # 4. Load MCP tools
        print("   ↳ Loading Canvas tools...")
        tools = await load_mcp_tools(self.session)
        print(f"   ↳ Loaded {len(tools)} tools")

        # 5. Create ReAct agent
        print("   ↳ Creating agent...")
        self.agent = create_react_agent(
            self.llm,
            tools,
            prompt="""You are a helpful Canvas LMS assistant for students.

            Your job is to help students with:
            - Finding information about their courses
            - Checking assignments and deadlines
            - Viewing grades and submission status
            - Reading recent announcements
            - Managing their academic workload

            Guidelines:
            - Always use the available tools to fetch real data from Canvas
            - Be concise but informative
            - Format dates in a readable way (e.g., "October 9, 2025")
            - If you need a course ID, first call get_courses to list available courses
            - When showing assignments, highlight which ones are submitted vs not submitted
            - Present information in a clear, organized format

            Remember: You have access to real Canvas data through the tools. Use them!
            """,
        )

        print("✅ Agent ready!\n")

    async def query(self, user_input: str) -> str:
        """
        Process a user query with token tracking
        
        Args:
            user_input: User's question or request
            
        Returns:
            Agent's response
        """
        if not self.agent:
            raise ValueError("Agent not initialized. Call initialize() first.")
        
        # Track start time
        start_time = time.time()
        
        # Run agent
        result = await self.agent.ainvoke(
            {"messages": [("user", user_input)]}
        )
        
        # Calculate response time
        response_time = time.time() - start_time
        
        # Extract response (last message)
        response = result["messages"][-1].content
        
        # Sum up token usage from all AI messages
        total_input_tokens = 0
        total_output_tokens = 0
        
        for msg in result["messages"]:
            if hasattr(msg, 'usage_metadata') and msg.usage_metadata:
                total_input_tokens += msg.usage_metadata.get("input_tokens", 0)
                total_output_tokens += msg.usage_metadata.get("output_tokens", 0)
        
        # Check if tools were used
        tools_used = any(
            hasattr(msg, 'tool_calls') and msg.tool_calls
            for msg in result["messages"]
        )
        
        # Log token usage
        log_entry = self.tracker.log_usage(
            model_id=self.model_id,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            query=user_input,
            response_time=response_time,
            tools_used=tools_used,
            session_id=self.session_id
        )
        
        # Print cost info
        print(f"💰 Tokens: {log_entry['total_tokens']} | Cost: ${log_entry['estimated_cost_usd']:.6f} | Time: {log_entry['response_time_sec']}s")
        
        return response



    async def cleanup(self):
        """Clean up resources"""
        if self.session:
            await self.session.__aexit__(None, None, None)
        if self.stdio_context:
            await self.stdio_context.__aexit__(None, None, None)
