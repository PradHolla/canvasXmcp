# Canvas LMS AI Agent with MCP

An intelligent AI agent that interfaces with Canvas LMS through the Model Context Protocol (MCP), powered by AWS Bedrock and LangGraph. This agent provides students with a conversational interface to access their Canvas data including courses, assignments, grades, quizzes, and announcements.

## 🎯 Overview

This project combines several cutting-edge technologies to create a seamless educational assistant:

- **Canvas LMS API Integration** - Direct access to course data, assignments, submissions, and grades
- **Model Context Protocol (MCP)** - Standardized server exposing Canvas functionality as tools
- **AWS Bedrock** - Enterprise-grade LLM inference (GPT-OSS, Claude 3.5 Sonnet, etc.)
- **LangGraph ReAct Agent** - Autonomous agent with reasoning and tool-calling capabilities
- **React Frontend** - Modern dark-themed chat interface with streaming responses
- **FastAPI Backend** - High-performance async API server
- **Token Tracking** - Built-in cost monitoring and usage analytics

## 🏗️ Architecture

```
┌─────────────────┐
│  React Frontend │  ← User Interface (Vite + Tailwind)
│    (Port 5173)  │     • Dark mode chat UI
└────────┬────────┘     • Streaming responses
         │              • Conversation history
┌────────▼────────┐
│  FastAPI Server │  ← REST API Backend
│    (Port 8000)  │     • SSE streaming
└────────┬────────┘     • Thread management
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
- Dark-themed React interface
- Real-time SSE streaming responses
- Markdown rendering with syntax highlighting
- Persistent conversation history
- Collapsible reasoning accordion
- Mobile-friendly responsive design

## 📁 Project Structure

```
canvasXmcp/
├── frontend/                     # React Frontend (Vite)
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatArea.jsx     # Main chat interface
│   │   │   ├── Sidebar.jsx      # Conversation history
│   │   │   └── ReasoningAccordion.jsx
│   │   ├── lib/
│   │   │   └── api.js           # API client
│   │   ├── App.jsx              # Root component
│   │   └── index.css            # Tailwind styles
│   ├── package.json
│   └── vite.config.js
├── src/
│   ├── agent/
│   │   ├── canvas_agent.py      # LangGraph ReAct agent
│   │   └── checkpointer.py      # Conversation memory
│   ├── canvas/
│   │   ├── client.py            # Canvas API HTTP client
│   │   └── models.py            # Data models
│   ├── mcp/
│   │   └── canvas_server.py     # FastMCP server with 15+ tools
│   ├── ui/
│   │   └── app.py               # Legacy Chainlit interface
│   └── utils/
│       └── token_tracker.py     # Token usage and cost tracking
├── main.py                       # FastAPI backend server
├── tests/
│   └── ...                       # Test files
├── pyproject.toml                # Python dependencies (uv)
└── .env                          # Configuration (not in repo)
```

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+ and npm
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- Canvas LMS access token
- AWS account with Bedrock access

### 1. Clone and Install

```bash
git clone https://github.com/PradHolla/canvasXmcp.git
cd canvasXmcp

# Install Python dependencies with uv
uv sync

# Install frontend dependencies
cd frontend
npm install
cd ..
```

### 2. Configure Environment

Create a `.env` file in the project root:

```bash
# Canvas LMS Configuration
CANVAS_URL=https://canvas.your-institution.edu
CANVAS_TOKEN=your_canvas_access_token_here

# AWS Bedrock Configuration
AWS_REGION=us-east-1
GPT_OSS=openai.gpt-oss-120b-1:0

# Optional: Use different models
# GPT_OSS=anthropic.claude-3-5-sonnet-20241022-v2:0
# GPT_OSS=meta.llama4-maverick-17b-instruct-v1:0
```

**Getting your Canvas token:**
1. Log into Canvas
2. Go to Account → Settings
3. Scroll to "Approved Integrations"
4. Click "+ New Access Token"
5. Copy the token to your `.env` file

### 3. Run the Application

You need to run both the backend and frontend:

**Terminal 1: Start the FastAPI Backend**
```bash
uv run uvicorn main:app --reload --port 8000
```
The API server will start at http://localhost:8000

**Terminal 2: Start the React Frontend**
```bash
cd frontend
npm run dev
```
The frontend will start at http://localhost:5173

Open http://localhost:5173 in your browser to use the application.

## 🛠️ Usage Examples

### Web Interface

Once both servers are running, try these queries in the chat:

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

### API Endpoints

The FastAPI backend exposes the following endpoints:

```bash
# Health check
GET /api/health

# List conversation threads
GET /api/threads

# Get messages for a thread
GET /api/threads/{thread_id}/messages

# Delete a thread
DELETE /api/threads/{thread_id}

# Chat with streaming response (SSE)
POST /api/chat
Body: { "message": "What's due?", "thread_id": "uuid" }
```

### Legacy Chainlit Interface

The original Chainlit UI is still available:

```bash
export PYTHONPATH=.
chainlit run src/ui/app.py -w
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

Change models by updating `GPT_OSS` in `.env`:

```bash
# GPT-OSS (default - with reasoning)
GPT_OSS=openai.gpt-oss-120b-1:0

# Claude 3.5 Sonnet
CLAUDE=anthropic.claude-3-5-sonnet-20241022-v2:0

# Llama 4 Maverick
MAVERICK=meta.llama4-maverick-17b-instruct-v1:0
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

Built with:
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP server framework
- [LangGraph](https://github.com/langchain-ai/langgraph) - Agent orchestration
- [LangChain](https://github.com/langchain-ai/langchain) - LLM framework
- [FastAPI](https://fastapi.tiangolo.com/) - Backend API framework
- [React](https://react.dev/) + [Vite](https://vitejs.dev/) - Frontend framework
- [Tailwind CSS](https://tailwindcss.com/) - Styling
- [AWS Bedrock](https://aws.amazon.com/bedrock/) - LLM inference

---

**Note**: This is an educational project. Always ensure compliance with your institution's Canvas API usage policies and AWS usage terms.
