# Canvas LMS AI Agent with MCP

An intelligent AI agent that interfaces with Canvas LMS through the Model Context Protocol (MCP), powered by AWS Bedrock and LangGraph. This agent provides students with a conversational interface to access their Canvas data including courses, assignments, grades, quizzes, and announcements.

## 🎯 Overview

This project combines several cutting-edge technologies to create a seamless educational assistant:

- **Canvas LMS API Integration** - Direct access to course data, assignments, submissions, and grades
- **Model Context Protocol (MCP)** - Standardized server exposing Canvas functionality as tools
- **AWS Bedrock** - Enterprise-grade LLM inference (Llama 4 Maverick, Claude 3.5 Sonnet, etc.)
- **LangGraph ReAct Agent** - Autonomous agent with reasoning and tool-calling capabilities
- **Chainlit UI** - Beautiful web interface with conversation memory
- **Token Tracking** - Built-in cost monitoring and usage analytics

## 🏗️ Architecture

```
┌─────────────────┐
│   Chainlit UI   │  ← User Interface (Web-based chat)
└────────┬────────┘
         │
┌────────▼────────┐
│  Canvas Agent   │  ← LangGraph ReAct Agent
│  (Bedrock LLM)  │     • Reasoning & Planning
└────────┬────────┘     • Tool Selection
         │              • Memory & Context
┌────────▼────────┐
│   MCP Server    │  ← FastMCP Server
│  Canvas Tools   │     • 15+ Canvas API Tools
└────────┬────────┘     • Standardized Interface
         │
┌────────▼────────┐
│  Canvas Client  │  ← HTTP API Wrapper
│   (REST API)    │     • Authentication
└────────┬────────┘     • Request Handling
         │
┌────────▼────────┐
│   Canvas LMS    │  ← Institution's Canvas Instance
└─────────────────┘
```

## ✨ Features

### 🤖 AI-Powered Conversational Interface
- Natural language queries ("What's due this week?")
- Context-aware responses with conversation memory
- Autonomous tool selection and multi-step reasoning

### 📚 Comprehensive Canvas Access
- **Courses** - Enrolled courses with grades and terms
- **Assignments** - Due dates, submissions, scores, feedback
- **Quizzes** - Quiz submissions and detailed grades
- **Grades** - Current grades and score breakdowns
- **Announcements** - Recent course announcements
- **Calendar** - Upcoming events across all courses
- **Discussions** - Forum topics and replies
- **Files** - Course documents and materials
- **Modules** - Course structure and content organization

### 💰 Cost Monitoring
- Real-time token usage tracking
- Per-query cost estimation
- Session summaries with total costs
- Support for multiple Bedrock models

### 🎨 Modern UI
- Responsive Chainlit interface
- Real-time streaming responses
- Persistent conversation history
- Mobile-friendly design

## 📁 Project Structure

```
canvasXmcp/
├── src/
│   ├── agent/
│   │   └── canvas_agent.py      # LangGraph ReAct agent with Bedrock
│   ├── canvas/
│   │   ├── client.py            # Canvas API HTTP client
│   │   └── models.py            # Data models
│   ├── mcp/
│   │   └── canvas_server.py     # FastMCP server with 15+ tools
│   ├── ui/
│   │   └── app.py               # Chainlit web interface
│   └── utils/
│       └── token_tracker.py     # Token usage and cost tracking
├── tests/
│   ├── test_agent.py            # Agent integration tests
│   └── test_canvas.py           # Canvas client tests
├── test.py                       # Quick CLI test script
├── view_costs.py                 # Cost analysis tool
├── pyproject.toml                # Dependencies (uv/pip)
└── .env                          # Configuration (not in repo)
```

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- Canvas LMS access token
- AWS account with Bedrock access

### 1. Clone and Install

```bash
git clone https://github.com/PradHolla/canvasXmcp.git
cd canvasXmcp

# Install dependencies with uv (recommended)
uv sync
```

### 2. Configure Environment

Create a `.env` file in the project root:

```bash
# Canvas LMS Configuration
CANVAS_URL=https://canvas.your-institution.edu
CANVAS_TOKEN=your_canvas_access_token_here

# AWS Bedrock Configuration
AWS_REGION=us-east-1
MODEL_ID=meta.llama4-maverick-17b-instruct-v1:0

# Optional: Use different models
# MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
# MODEL_ID=meta.llama4-scout-17b-instruct-v1:0
```

**Getting your Canvas token:**
1. Log into Canvas
2. Go to Account → Settings
3. Scroll to "Approved Integrations"
4. Click "+ New Access Token"
5. Copy the token to your `.env` file

### 3. Run the Application

**Option A: Web Interface (Chainlit)**
```bash
# Make sure PYTHONPATH is set for imports
export PYTHONPATH=.
chainlit run src/ui/app.py -w
```

Open http://localhost:8000 in your browser.

**Option B: CLI Test Script**
```bash
export PYTHONPATH=.
uv run test.py
```

## 🛠️ Usage Examples

### Web Interface (Chainlit)

Once the Chainlit app is running, try these queries:

```
"What courses am I taking?"
"What's due this week?"
"How did I do on quizzes in CS 559?"
"Show me recent announcements"
"What's my grade in Machine Learning?"
"What assignments haven't I submitted yet?"
```

The agent maintains conversation memory, so you can ask follow-up questions:

```
You: "What courses am I taking?"
Agent: "You're enrolled in CS 555, CS 559, CS 584, and FE 520."

You: "What's due in my second course?"
Agent: [Remembers CS 559] "For CS 559, you have HW3 due tomorrow..."
```

### Programmatic Access

```python
import asyncio
from src.agent.canvas_agent import CanvasAgent

async def main():
    agent = CanvasAgent()
    await agent.initialize()
    
    response = await agent.query("What assignments are due soon?")
    print(response)
    
    await agent.cleanup()

asyncio.run(main())
```

## 📊 Cost Tracking

Token usage is automatically tracked to `token_usage.jsonl`. View costs with:

```bash
python view_costs.py
```

Output:
```
💰 COST SUMMARY
─────────────────────────────────
Total queries: 12
Total tokens: 45,332
Average tokens/query: 3,778
Total cost: $0.1234
─────────────────────────────────
```

Cost estimates are based on current AWS Bedrock pricing:
- Llama 4 Maverick: $0.24/$0.97 per 1M input/output tokens
- Claude 3.5 Sonnet: $3/$15 per 1M tokens
- Llama 4 Scout: $0.17/$0.66 per 1M tokens

## 🧪 Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_agent.py

# Run with verbose output
pytest -v
```

## 🔧 Configuration

### Model Selection

Change models by updating `MODEL_ID` in `.env`:

```bash
# Fast and cost-effective
MODEL_ID=meta.llama4-scout-17b-instruct-v1:0

# Balanced (default)
MODEL_ID=meta.llama4-maverick-17b-instruct-v1:0

# Most capable
MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
```

### Agent Parameters

Edit `src/agent/canvas_agent.py`:

```python
self.llm = ChatBedrockConverse(
    model=f"us.{self.model_id}",
    region_name=self.region,
    temperature=0.3,      # Lower = more deterministic
    max_tokens=4096       # Maximum response length
)
```

### MCP Server Tools

Add custom Canvas tools in `src/mcp/canvas_server.py`:

```python
@mcp.tool()
async def my_custom_tool(
    param: str = Field(description="Description")
) -> Dict[str, Any]:
    """Tool description for the LLM"""
    return canvas.my_custom_method(param)
```

## 🐛 Troubleshooting

### PYTHONPATH Issues

If you see `ModuleNotFoundError: No module named 'src'`:

```bash
# Set PYTHONPATH before running
export PYTHONPATH=.

# OR install in editable mode
pip install -e .
```

### Canvas Authentication Errors

```bash
# Verify your token works
curl -H "Authorization: Bearer YOUR_TOKEN" \
     https://canvas.your-institution.edu/api/v1/users/self
```

### AWS Bedrock Access

Ensure your AWS credentials have Bedrock permissions:

```bash
aws bedrock-runtime invoke-model \
  --model-id us.meta.llama4-maverick-17b-instruct-v1:0 \
  --body '{"prompt":"test"}' \
  --region us-east-1 \
  output.txt
```

### MCP Connection Issues

Check that the server starts correctly:

```bash
export PYTHONPATH=.
uv run src/mcp/canvas_server.py
# Should show: Server running...
```

## 🙏 Acknowledgments

Built with:
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP server framework
- [LangGraph](https://github.com/langchain-ai/langgraph) - Agent orchestration
- [LangChain](https://github.com/langchain-ai/langchain) - LLM framework
- [Chainlit](https://github.com/Chainlit/chainlit) - Chat UI
- [AWS Bedrock](https://aws.amazon.com/bedrock/) - LLM inference

---

**Note**: This is an educational project. Always ensure compliance with your institution's Canvas API usage policies and AWS usage terms.