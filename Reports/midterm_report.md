# CanvasXMCP Midterm Report

*Generated: October 30, 2025*

## 1. Repository Snapshot

- **Root**: `canvasXmcp`
- **Primary entry points**:
  - `src/agent/canvas_agent.py` – async LangGraph + Bedrock agent orchestrator
  - `src/mcp/canvas_server.py` – FastMCP tool server exposing Canvas LMS API
  - `src/ui/app.py` – Chainlit interface for conversational access
- **Support utilities**: `src/canvas/client.py` (Canvas REST wrapper), `src/utils/token_tracker.py`
- **Auxiliary scripts**: `test.py`, `view_costs.py`, `aws.py`, `debug.py`
- **Tests**: `tests/test_agent.py`, `tests/test_canvas.py`

## 2. Application Architecture

```
User (Chainlit UI)
    │
    ▼
CanvasAgent (LangGraph ReAct agent + AWS Bedrock LLM)
    │  -- tool calls -->
    ▼
FastMCP Canvas Server (Stdio transport)
    │
    ▼
CanvasClient (HTTP requests + caching)
    │
    ▼
Canvas LMS REST API
```

- **LLM Layer**: AWS Bedrock via `langchain_aws.ChatBedrockConverse`; model id sourced from `GPT_OSS`/`SCOUT` env vars. Supports GPT-OSS reasoning blocks and Meta Llama 4.
- **Tooling Layer**: `langgraph.prebuilt.create_react_agent` integrates MCP tools fetched via `langchain_mcp_adapters`.
- **State & Memory**:
  - Conversation memory: `langgraph.checkpoint.memory.MemorySaver` in UI.
  - Token/cost tracking: `TokenTracker` logging to `token_usage.jsonl` with model-specific pricing.
- **Execution Flow**:
  1. Chainlit session starts → spawns MCP server (`uv run src/mcp/canvas_server.py`).
  2. MCP server registers 15+ Canvas tools (courses, assignments, grades, discussions, quizzes, files, modules, calendar, etc.).
  3. Agent queries run through LangGraph; MCP tool responses shape final answer.
  4. Token usage logged per message; end-of-session cost summary displayed.

## 3. Key Components

### 3.1 Canvas Agent (`src/agent/canvas_agent.py`)
- Async lifecycle (`initialize`, `query`, `cleanup`).
- Configures Bedrock LLM (temperature 0.3, 4K max tokens).
- Launches MCP server over stdio with `PYTHONPATH=.` assumption.
- Loads tools dynamically; constructs ReAct prompt emphasizing real data usage and formatting.
- Collects token usage metadata and response time, persists via `TokenTracker`.

### 3.2 MCP Server (`src/mcp/canvas_server.py`)
- Uses `fastmcp.FastMCP` to register Canvas-focused tools.
- Tools wrap `CanvasClient` methods, returning curated dictionaries for LLM consumption.
- Includes rich set: `get_courses`, `get_assignments`, `get_upcoming_assignments`, `get_grades`, `get_announcements`, `get_discussions`, `get_course_files`, `get_calendar_events`, `get_modules` (with file fallback), `get_quizzes`, `get_assignment_submission`, `get_quiz_submissions`, etc.
- Loads Canvas URL/token from environment; server entry point `main()` executes `mcp.run()`.

### 3.3 Canvas Client (`src/canvas/client.py`)
- Full-featured REST wrapper using `requests`, environment-based configuration.
- Implements caching (simple in-memory with 5-minute TTL) for courses and assignments.
- Extensive helpers: courses, assignments, upcoming deadlines, grades, announcements, discussions (HTML stripping), files, calendar, modules (with fallback), quizzes, submissions, course summaries, course lookup by name.
- Formats dates to local timezone, handles Canvas-specific nuances (quiz detection, partial matches, fallback when modules absent).

### 3.4 UI Layer (`src/ui/app.py`)
- Chainlit `on_chat_start`/`on_message`/`on_chat_end` hooks.
- Bootstraps MCP server via shell command, sets up session storage for agent, tracker, LLM id.
- Handles GPT-OSS reasoning content vs plain text differently; injects custom Chainlit element `ReasoningAccordion` when present.
- Enforces recursion limit, memory thread id per Chainlit session.
- Provides user guidance, token-cost overlays, graceful error handling/logging.

### 3.5 Utilities
- `TokenTracker`: logs JSONL entries with cost estimation based on per-model pricing map, computes summaries.
- `view_costs.py`: pretty-prints aggregated token usage summary.
- `aws.py`: sample CloudWatch metric fetcher for Bedrock token counts (manual usage).
- `debug.py`: manual Bedrock LLM invocation for debugging GPT-OSS integration.

## 4. Configuration & Dependencies

- **Python**: 3.12 (via `.python-version` & `pyproject.toml`).
- **Package Manager**: `uv` lockfile present; `pyproject.toml` declares dependencies:
  - Core: `langchain`, `langgraph`, `langchain-aws`, `langchain-mcp-adapters`, `fastmcp`, `mcp`, `chainlit`, `requests`, `python-dotenv`, `boto3`, `aiosqlite` (for LangGraph checkpoints).
- **Environment Variables** (expected in `.env`):
  - `CANVAS_URL`, `CANVAS_TOKEN`
  - `AWS_REGION`, `MODEL_ID`/`SCOUT`/`GPT_OSS`
  - Chainlit relies on `PYTHONPATH=.` or editable install to import `src`.

## 5. Testing & Quality

- Tests located in `tests/`:
  - `test_agent.py` (unit tests for `BedrockAgent`) – **currently broken**:
    - Imports `src.agent.bedrock_agent.BedrockAgent`, but file does not exist; indicates stale test or missing implementation.
  - `test_canvas.py` – assumes simple `CanvasClient.get_course`, but live client now requires real Canvas credentials and raises `ValueError` when env vars missing; likely fails without mock.
- `pytest` not listed under dev dependencies in `pyproject.toml` (previous minimal scaffold added separate file; ensure alignment).
- No CI configuration detected.
- Manual script `test.py` performs end-to-end async test but requires valid Canvas + AWS credentials.

## 6. Observations & Risks

| Area | Status | Notes |
|------|--------|-------|
| Package imports | ⚠️ | Requires `PYTHONPATH=.` or `pip install -e .`; otherwise MCP server fails to import `src` modules. |
| Tests | ❌ | Both existing tests fail due to missing modules and external dependencies; no automated coverage. |
| Credentials | 🔒 | Project depends heavily on `.env` secrets; ensure secure handling. |
| Error handling | ⚠️ | Canvas client often returns broad `{"error": ...}` strings; surface-specific errors to the UI for better UX. |
| External dependencies | ⚠️ | Live Canvas + AWS Bedrock services required for end-to-end runs; no offline/fixture mode yet. |
| Logging & monitoring | ⚠️ | Basic logging via `logging` + token tracker; no centralized observability or alerts.

## 7. Tooling & Scripts

- `test.py`: Async smoke test exercising agent initialization, three sample queries, cleanup, and cost summary. Requires valid credentials and network.
- `view_costs.py`: Reads `token_usage.jsonl` and prints aggregate usage metrics.
- `debug.py`: Manual Bedrock prompt test aimed at GPT-OSS model variants.
- `aws.py`: CloudWatch metrics fetcher for Bedrock token counts (example script, not integrated).
- `chainlit.md`: Presumably Chainlit-specific notes/instructions (not analyzed in detail).

## 8. Recent Activity & State

- Repository currently on `main`; no Git status information captured during analysis (workspace may contain uncommitted changes from this report).
- `token_usage.jsonl` suggests prior session logging is active (contents not inspected).
- `uv.lock` present indicating dependency versions resolved via `uv`; ensure lockfile remains updated after dependency changes.

## 9. Recommendations & Next Steps

1. **Stabilize automated testing**
  - Implement mocks or fixtures for Canvas API to allow local pytest runs without live credentials.
  - Restore/implement `BedrockAgent` or update tests to target `CanvasAgent` API instead.
  - Add `pytest` (and possibly `pytest-asyncio`) to dependencies/dev-dependencies; consider wiring into CI.

2. **Improve resiliency & observability**
  - Harden error handling in `CanvasClient` and surface user-friendly messages upstream.
  - Add structured logging (JSON or key-value) for MCP server and agent to support production monitoring.
  - Consider integrating metrics (prometheus / CloudWatch) for tool latency and error counts.

3. **Developer Experience**
  - Provide shell scripts or `Makefile`/`taskfile` wrappers for common operations (`uv sync`, `chainlit run`, `pytest`).
  - Document credential setup and sample `.env` template in `README` (partially present—ensure kept current).
  - Package project as installable module (`pip install -e .`) to eliminate PYTHONPATH issues.

4. **Feature Enhancements**
  - Expand MCP toolset with instructor-specific operations (gradebook exports, announcements posting).
  - Introduce caching layer persistence (Redis/sqlite) to reduce Canvas API load for shared deployments.
  - Capture conversation transcripts for analytics (with privacy safeguards).

## 10. Appendix

- **Setup Summary**
  - Python 3.12, `uv`-managed dependencies.
  - Requires `.env` with Canvas + AWS credentials.
  - Chainlit UI launched via `chainlit run src/ui/app.py -w` (ensure `PYTHONPATH=.`).

- **Manual Test Commands** *(not executed during this report)*
  - `uv run test.py` – end-to-end agent exercise.
  - `uv run python view_costs.py` – token usage summary.

- **Notable Files**
  - `public/elements/ReasoningAccordion.jsx` – custom Chainlit element used when GPT-OSS returns reasoning traces.
  - `Reports/Proposal/main.tex` – LaTeX artifacts (outside scope of code analysis).

---

*Tests were not executed as part of this report; quality findings are based on static analysis and inspection.*