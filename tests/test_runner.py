import os
import json
import time
import asyncio
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.token_tracker import TokenTracker
from langchain_aws import ChatBedrockConverse
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv
from src.utils.text_sanitizer import TextSanitizer

load_dotenv()


# Prompt from app.py
CANVAS_ASSISTANT_PROMPT = """You are a Canvas LMS assistant that helps students with their coursework.

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
8. NEVER output code (Python, JSON, etc.) - only plain text answers  # ← ADD THIS

IMPORTANT: Canvas APIs need numeric course IDs (like "80546"), not names.
If user mentions a course by name, call get_course_id_by_name() first.

Present information cleanly with bullet points. No raw JSON. No code.  # ← REINFORCE
"""



class ModelTester:
    """Test a single model with proper GPT-OSS reasoning extraction"""

    def __init__(self, model_id: str):
        self.model_id = model_id
        self.tracker = TokenTracker()
        self.mcp_session = None
        self.stdio_context = None
        self.agent = None
        
    async def setup_agent(self):
        """Initialize MCP connection and agent (WITHOUT memory)"""
        print(f"  🔌 Setting up {self.model_id}...")
        
        # MCP server parameters
        server_params = StdioServerParameters(
            command="sh",
            args=["-c", "PYTHONPATH=. uv run src/mcp/canvas_server.py"]
        )
        
        # Connect to MCP server
        self.stdio_context = stdio_client(server_params)
        read, write = await self.stdio_context.__aenter__()
        
        self.mcp_session = ClientSession(read, write)
        await self.mcp_session.__aenter__()
        await self.mcp_session.initialize()
        
        # Load Canvas tools
        tools = await load_mcp_tools(self.mcp_session)
        print(f"    ✓ Loaded {len(tools)} Canvas tools")
        
        # Create Bedrock LLM
        llm = ChatBedrockConverse(
            model=f"{self.model_id}",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            temperature=0.3,
            max_tokens=4096
        )
        
        # Create agent WITHOUT memory (no checkpointer)
        self.agent = create_react_agent(
            llm,
            tools,
            prompt=CANVAS_ASSISTANT_PROMPT
        )
        
        print(f"    ✅ Agent ready (memory disabled)")
    
    async def cleanup(self):
        """Clean up MCP connection (suppress non-fatal errors)"""
        import warnings
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        
        try:
            if self.mcp_session:
                await asyncio.wait_for(
                    self.mcp_session.__aexit__(None, None, None),
                    timeout=2.0
                )
        except (asyncio.TimeoutError, RuntimeError, asyncio.CancelledError):
            pass  # MCP cleanup race conditions are non-fatal
        
        try:
            if self.stdio_context:
                await asyncio.wait_for(
                    self.stdio_context.__aexit__(None, None, None),
                    timeout=2.0
                )
        except (asyncio.TimeoutError, RuntimeError, asyncio.CancelledError):
            pass  # Stdio cleanup issues are non-fatal


    
    async def run_query(self, query: str, query_id: int, category: str) -> Dict[str, Any]:
        """Execute a single query and record results"""
        
        print(f"    Running: {query[:50]}...")
        
        start_time = time.time()
        
        try:
            # Simplified config (no memory)
            config = {
                "recursion_limit": 50
            }
            
            # Run agent with retry logic for ValidationException
            max_retries = 1
            result = None
            last_error = None
            
            for attempt in range(max_retries + 1):
                try:
                    result = await self.agent.ainvoke(
                        {"messages": [("user", query)]},
                        config=config
                    )
                    break  # Success
                
                except Exception as e:
                    last_error = e
                    error_msg = str(e)
                    
                    # Check if it's a Bedrock validation error
                    if "ValidationException" in error_msg and attempt < max_retries:
                        print(f"      ⚠️  Retry {attempt + 1}/{max_retries} due to validation error")
                        await asyncio.sleep(2)
                        continue
                    else:
                        # Out of retries or non-validation error
                        raise
            
            # Extract response and metrics (with GPT-OSS reasoning handling)
            response_data = self._extract_response(result)
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            
            # Extract token usage and tools from LATEST AIMessage ONLY
            total_input = 0
            total_output = 0
            tools_used = []

            # Find the LATEST AIMessage (current query response)
            latest_ai_msg = None
            for msg in reversed(result["messages"]):
                if hasattr(msg, '__class__') and msg.__class__.__name__ == 'AIMessage':
                    latest_ai_msg = msg
                    break

            # Extract tokens from latest message
            if latest_ai_msg:
                if hasattr(latest_ai_msg, 'usage_metadata') and latest_ai_msg.usage_metadata:
                    total_input = latest_ai_msg.usage_metadata.get("input_tokens", 0)
                    total_output = latest_ai_msg.usage_metadata.get("output_tokens", 0)

            # Find where current turn started (should be first message without memory)
            current_turn_start = 0  # Without memory, all messages are current turn

            # Extract tool calls from ALL messages in result (since no memory, all are current)
            for msg in result["messages"]:
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tool_call in msg.tool_calls:
                        tools_used.append({
                            "tool": tool_call.get("name", "unknown"),
                            "args": tool_call.get("args", {})
                        })

            
            # Log to token tracker
            self.tracker.log_usage(
                model_id=self.model_id,
                input_tokens=total_input,
                output_tokens=total_output,
                query=query,
                response_time=elapsed_ms / 1000,
                tools_used=len(tools_used) > 0,
                session_id=f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            
            # Calculate cost
            pricing = self.tracker.PRICING.get(self.model_id, {"input": 0, "output": 0})
            cost_usd = (
                (total_input / 1000) * pricing["input"] +
                (total_output / 1000) * pricing["output"]
            )
            
            # Detect quality issues
            quality_issues = self._detect_quality_issues(response_data)
            
            print(f"      ✅ {elapsed_ms}ms | {total_input + total_output} tokens | ${cost_usd:.6f} | {len(tools_used)} tools{' | ⚠️  ' + ', '.join(quality_issues) if quality_issues else ''}")
            
            return {
                "success": True,
                "query": query,
                "category": category,
                "response": response_data,
                "performance": {
                    "latency_ms": elapsed_ms,
                    "tokens_input": total_input,
                    "tokens_output": total_output,
                    "tokens_total": total_input + total_output,
                    "cost_usd": round(cost_usd, 6)
                },
                "tools_used": tools_used,
                "quality_issues": quality_issues,
                "errors": [],
                "timestamp_start": datetime.fromtimestamp(start_time).isoformat(),
                "timestamp_end": datetime.now().isoformat()
            }
            
        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            
            print(f"      ❌ Error: {str(e)[:80]}")
            
            return {
                "success": False,
                "query": query,
                "category": category,
                "response": {
                    "raw_content": None,
                    "reasoning": None,
                    "final_answer": None,
                    "has_reasoning": False,
                    "reasoning_length": 0
                },
                "performance": {
                    "latency_ms": elapsed_ms,
                    "tokens_input": 0,
                    "tokens_output": 0,
                    "tokens_total": 0,
                    "cost_usd": 0
                },
                "tools_used": [],
                "quality_issues": [],
                "errors": [str(e)],
                "timestamp_start": datetime.fromtimestamp(start_time).isoformat(),
                "timestamp_end": datetime.now().isoformat()
            }
    
    def _extract_response(self, result: Dict) -> Dict[str, Any]:
        """Extract and parse response from agent result (handles GPT-OSS reasoning)"""
                
        for msg in reversed(result["messages"]):
            if hasattr(msg, '__class__') and msg.__class__.__name__ == 'AIMessage':
                # Skip tool-calling messages
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    continue
                
                content = msg.content
                
                # Handle GPT-OSS list-based content with reasoning
                if isinstance(content, list):
                    reasoning = None
                    text_parts = []
                    
                    for block in content:
                        if isinstance(block, dict):
                            if block.get('type') == 'reasoning_content':
                                reasoning = TextSanitizer.sanitize_string(
                                    block.get('reasoning_content', {}).get('text', '')
                                )
                            elif block.get('type') == 'text':
                                text_parts.append(
                                    TextSanitizer.sanitize_string(block.get('text', ''))
                                )
                    
                    final_answer = '\n\n'.join(text_parts).strip()
                    
                    return {
                        "raw_content": content,
                        "reasoning": reasoning,
                        "final_answer": final_answer,
                        "has_reasoning": reasoning is not None,
                        "reasoning_length": len(reasoning) if reasoning else 0
                    }
                
                # Handle Llama string content
                elif isinstance(content, str):
                    # Clean up tool artifacts
                    lines = content.split('\n')
                    cleaned = [
                        line for line in lines 
                        if not (
                            line.strip().startswith('{"name":') or
                            line.strip().startswith('get_') or
                            'function call' in line.lower()
                        )
                    ]
                    final_answer = TextSanitizer.sanitize_string('\n'.join(cleaned).strip())
                    
                    return {
                        "raw_content": content,
                        "reasoning": None,
                        "final_answer": final_answer,
                        "has_reasoning": False,
                        "reasoning_length": 0
                    }
        
        return {
            "raw_content": None,
            "reasoning": None,
            "final_answer": "No response generated",
            "has_reasoning": False,
            "reasoning_length": 0
        }
    
    def _detect_quality_issues(self, response_data: Dict[str, Any]) -> List[str]:
        """Detect quality issues in the response"""
        issues = []
        
        final_answer = response_data.get("final_answer", "")
        
        if not final_answer:
            return issues
        
        # Check for code in response (Llama issue)
        if any(keyword in final_answer for keyword in ["import ", "def ", "```"]):
            issues.append("contains_code")
        
        # Check for raw JSON
        if final_answer.strip().startswith('[{') or final_answer.strip().startswith('{"'):
            issues.append("raw_json")
        
        # Check for tool artifacts
        if 'get_' in final_answer and '(' in final_answer:
            issues.append("tool_artifacts")
        
        # Check for empty or very short response
        if len(final_answer.strip()) < 10:
            issues.append("too_short")
        
        return issues


class TestRunner:
    """Run systematic tests across multiple models"""
    
    def __init__(self, results_dir: str = "tests/results"):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.test_run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    async def run_test_suite(
        self, 
        query_file: str,
        models: List[str]
    ) -> Dict[str, Any]:
        """Run test suite with query-by-query comparison"""
        
        # Load queries
        query_path = Path(__file__).parent / "query_sets" / query_file
        with open(query_path, 'r') as f:
            query_sets = json.load(f)
        
        print("\n" + "="*80)
        print("CANVAS AI ASSISTANT - MODEL TESTING FRAMEWORK")
        print("="*80)
        print(f"Test Run ID: {self.test_run_id}")
        print(f"Query File: {query_file}")
        print(f"Models: {len(models)}")
        for i, model in enumerate(models, 1):
            short = "Llama Maverick 17B" if "llama" in model.lower() else "GPT-OSS 120B"
            print(f"  {i}. {short}")
        print(f"Total Query Categories: {len(query_sets)}")
        print("="*80 + "\n")
        
        all_results = {
            "test_metadata": {
                "test_run_id": self.test_run_id,
                "timestamp": datetime.now().isoformat(),
                "query_file": query_file,
                "models_tested": models,
                "prompt_used": CANVAS_ASSISTANT_PROMPT
            },
            "queries": []  # Query-by-query structure
        }
        
        # Initialize agents for all models ONCE
        print("🚀 Initializing agents...\n")
        testers = {}
        for model_id in models:
            tester = ModelTester(model_id)
            await tester.setup_agent()
            testers[model_id] = tester
            print()
        
        print("="*80)
        print("🧪 Starting Tests")
        print("="*80 + "\n")
        
        # Test each query across all models
        query_counter = 0
        for category, queries in query_sets.items():
            print(f"📋 Category: {category}\n")
            
            for query in queries:
                query_counter += 1
                
                print(f"{'─'*80}")
                print(f"Query {query_counter}/{sum(len(q) for q in query_sets.values())}: {query}")
                print(f"{'─'*80}")
                
                query_result = {
                    "query_id": query_counter,
                    "query_text": query,
                    "category": category,
                    "model_results": {}
                }
                
                # Test with each model
                for model_id in models:
                    model_short = "Llama Maverick" if "llama" in model_id.lower() else "GPT-OSS 120B"
                    print(f"\n  [{model_short}]")
                    
                    result = await testers[model_id].run_query(query, query_counter, category)
                    query_result["model_results"][model_id] = result
                    
                    # Brief pause between models
                    if model_id != models[-1]:
                        await asyncio.sleep(1)
                
                # Add comparison metrics
                if len(models) == 2:
                    llama_result = query_result["model_results"].get(models[0], {})
                    gpt_result = query_result["model_results"].get(models[1], {})
                    
                    query_result["comparison"] = {
                        "both_successful": llama_result.get("success", False) and gpt_result.get("success", False),
                        "latency_delta_ms": round(
                            gpt_result.get("performance", {}).get("latency_ms", 0) - 
                            llama_result.get("performance", {}).get("latency_ms", 0), 2
                        ),
                        "cost_delta_usd": round(
                            gpt_result.get("performance", {}).get("cost_usd", 0) - 
                            llama_result.get("performance", {}).get("cost_usd", 0), 6
                        ),
                        "tokens_delta": (
                            gpt_result.get("performance", {}).get("tokens_total", 0) - 
                            llama_result.get("performance", {}).get("tokens_total", 0)
                        ),
                        "tools_delta": (
                            len(gpt_result.get("tools_used", [])) - 
                            len(llama_result.get("tools_used", []))
                        ),
                        "winner": self._determine_winner(llama_result, gpt_result)
                    }
                
                all_results["queries"].append(query_result)
                
                # Save intermediate
                self._save_results(all_results)
                
                print()  # Blank line between queries
            
            print()  # Blank line between categories
        
        # Cleanup all agents
        print("="*80)
        print("🧹 Cleaning up...")
        print("="*80 + "\n")
        for model_id, tester in testers.items():
            await tester.cleanup()
            short = "Llama Maverick" if "llama" in model_id.lower() else "GPT-OSS 120B"
            print(f"  ✓ {short} cleaned up")
        
        # Generate aggregate comparison
        comparison = self._generate_comparison_from_queries(all_results["queries"], models)
        all_results["aggregate_comparison"] = comparison
        
        # Save final results
        self._save_results(all_results)
        self._print_summary(comparison)
        
        return all_results
    
    def _determine_winner(self, result1: Dict, result2: Dict) -> str:
        """Determine which model performed better for a query"""
        
        # If one failed, the other wins
        if not result1.get("success") and result2.get("success"):
            return "model_2"
        if result1.get("success") and not result2.get("success"):
            return "model_1"
        if not result1.get("success") and not result2.get("success"):
            return "both_failed"
        
        # Compare quality issues
        issues1 = len(result1.get("quality_issues", []))
        issues2 = len(result2.get("quality_issues", []))
        
        if issues1 < issues2:
            return "model_1"
        elif issues2 < issues1:
            return "model_2"
        
        # If tied, faster wins
        lat1 = result1.get("performance", {}).get("latency_ms", float('inf'))
        lat2 = result2.get("performance", {}).get("latency_ms", float('inf'))
        
        if lat1 < lat2:
            return "model_1"
        elif lat2 < lat1:
            return "model_2"
        
        return "tie"
    
    def _generate_comparison_from_queries(self, queries: List[Dict], models: List[str]) -> Dict[str, Any]:
        """Generate comparison statistics from query-by-query results"""
        
        comparison = {"models": {}}
        
        for model_id in models:
            results = [q["model_results"][model_id] for q in queries]
            successful = [r for r in results if r.get("success", False)]
            
            if not successful:
                comparison["models"][model_id] = {
                    "success_rate": 0,
                    "total_queries": len(results),
                    "successful_queries": 0,
                    "failed_queries": len(results),
                    "avg_latency_ms": 0,
                    "avg_tokens_total": 0,
                    "avg_tokens_input": 0,
                    "avg_tokens_output": 0,
                    "total_cost_usd": 0,
                    "avg_cost_per_query": 0,
                    "total_tools_called": 0,
                    "avg_tools_per_query": 0,
                    "quality_issues_count": 0,
                    "reasoning_stats": {
                        "queries_with_reasoning": 0,
                        "reasoning_percentage": 0,
                        "avg_reasoning_length": 0
                    }
                }
                continue
            
            # Calculate metrics
            total_tools = sum(len(r.get("tools_used", [])) for r in successful)
            queries_with_reasoning = sum(
                1 for r in successful 
                if r.get("response", {}).get("has_reasoning", False)
            )
            avg_reasoning_length = (
                sum(r.get("response", {}).get("reasoning_length", 0) for r in successful) / 
                len(successful) if successful else 0
            )
            
            # Count quality issues
            total_quality_issues = sum(
                len(r.get("quality_issues", [])) for r in results
            )
            
            comparison["models"][model_id] = {
                "success_rate": round(len(successful) / len(results), 3),
                "total_queries": len(results),
                "successful_queries": len(successful),
                "failed_queries": len(results) - len(successful),
                "avg_latency_ms": round(
                    sum(r.get("performance", {}).get("latency_ms", 0) for r in successful) / len(successful), 2
                ),
                "avg_tokens_total": round(
                    sum(r.get("performance", {}).get("tokens_total", 0) for r in successful) / len(successful)
                ),
                "avg_tokens_input": round(
                    sum(r.get("performance", {}).get("tokens_input", 0) for r in successful) / len(successful)
                ),
                "avg_tokens_output": round(
                    sum(r.get("performance", {}).get("tokens_output", 0) for r in successful) / len(successful)
                ),
                "total_cost_usd": round(
                    sum(r.get("performance", {}).get("cost_usd", 0) for r in results), 6
                ),
                "avg_cost_per_query": round(
                    sum(r.get("performance", {}).get("cost_usd", 0) for r in results) / len(results), 6
                ),
                "total_tools_called": total_tools,
                "avg_tools_per_query": round(total_tools / len(successful), 2) if successful else 0,
                "quality_issues_count": total_quality_issues,
                "reasoning_stats": {
                    "queries_with_reasoning": queries_with_reasoning,
                    "reasoning_percentage": round(
                        queries_with_reasoning / len(successful) * 100, 1
                    ) if successful else 0,
                    "avg_reasoning_length": round(avg_reasoning_length)
                }
            }
        
        return comparison
    
    def _save_results(self, results: Dict[str, Any]):
        """Save detailed results to JSON"""
        output_file = self.results_dir / f"test_results_ec{self.test_run_id}.json"
        
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
    
    def _print_summary(self, comparison: Dict[str, Any]):
        """Print comparison summary table"""
        
        print("\n" + "="*90)
        print("📊 TEST SUMMARY - MODEL COMPARISON")
        print("="*90)
        
        models = list(comparison["models"].keys())
        
        # Header
        print(f"\n{'Metric':<30} ", end="")
        for model in models:
            short_name = "Llama Maverick" if "llama" in model.lower() else "GPT-OSS 120B"
            print(f"{short_name:<25}", end="")
        print()
        print("-" * 90)
        
        # Success rate
        print(f"{'Success Rate':<30} ", end="")
        for model in models:
            rate = comparison["models"][model]["success_rate"] * 100
            print(f"{rate:.1f}%{' ':<21}", end="")
        print()
        
        # Failed queries
        print(f"{'Failed Queries':<30} ", end="")
        for model in models:
            failed = comparison["models"][model]["failed_queries"]
            print(f"{failed}{' ':<24}", end="")
        print()
        
        # Avg latency
        print(f"{'Avg Latency (ms)':<30} ", end="")
        for model in models:
            lat = comparison["models"][model]["avg_latency_ms"]
            print(f"{lat:.0f}{' ':<22}", end="")
        print()
        
        # Avg tokens
        print(f"{'Avg Tokens (total)':<30} ", end="")
        for model in models:
            tok = comparison["models"][model]["avg_tokens_total"]
            print(f"{tok}{' ':<22}", end="")
        print()
        
        # Avg cost
        print(f"{'Avg Cost per Query':<30} ", end="")
        for model in models:
            cost = comparison["models"][model]["avg_cost_per_query"]
            print(f"${cost:.6f}{' ':<17}", end="")
        print()
        
        # Total cost
        print(f"{'Total Cost':<30} ", end="")
        for model in models:
            cost = comparison["models"][model]["total_cost_usd"]
            print(f"${cost:.6f}{' ':<17}", end="")
        print()
        
        # Tools used
        print(f"{'Avg Tools per Query':<30} ", end="")
        for model in models:
            tools = comparison["models"][model]["avg_tools_per_query"]
            print(f"{tools:.2f}{' ':<21}", end="")
        print()
        
        # Quality issues
        print(f"{'Quality Issues (total)':<30} ", end="")
        for model in models:
            issues = comparison["models"][model]["quality_issues_count"]
            print(f"{issues}{' ':<24}", end="")
        print()
        
        # Reasoning stats (GPT-OSS specific)
        print(f"{'Queries with Reasoning':<30} ", end="")
        for model in models:
            reasoning_pct = comparison["models"][model]["reasoning_stats"]["reasoning_percentage"]
            print(f"{reasoning_pct:.1f}%{' ':<21}", end="")
        print()
        
        print("\n" + "="*90)
        print(f"\n💾 Detailed results saved: tests/results/test_results_ec{self.test_run_id}.json")
        print("="*90 + "\n")


async def main():
    """Main test execution"""
    
    runner = TestRunner()
    
    # Models to test
    models = [
        "us.meta.llama4-maverick-17b-instruct-v1:0",
        "openai.gpt-oss-120b-1:0"
    ]
    
    # Run tests
    results = await runner.run_test_suite(
        query_file="edge_cases_queries.json",
        models=models
    )
    
    print("✅ Testing complete!")
    print(f"🆔 Test Run ID: {runner.test_run_id}")


if __name__ == "__main__":
    asyncio.run(main())
