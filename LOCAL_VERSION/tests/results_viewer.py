#!/usr/bin/env python3
"""
Streamlit app for viewing and comparing LLM test results.
Handles large JSON files with query/response comparisons.

Usage:
    streamlit run tests/results_viewer.py
"""

import streamlit as st
import json
from pathlib import Path
from datetime import datetime

# Page config
st.set_page_config(
    page_title="LLM Test Results Viewer",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better readability (dark theme compatible)
st.markdown("""
<style>
    .metric-card {
        background-color: rgba(240, 242, 246, 0.1);
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
        border: 1px solid rgba(128, 128, 128, 0.3);
    }
    .winner-badge {
        background-color: #28a745;
        color: white;
        padding: 5px 10px;
        border-radius: 5px;
        font-weight: bold;
    }
    .loser-badge {
        background-color: #6c757d;
        color: white;
        padding: 5px 10px;
        border-radius: 5px;
    }
    .response-box {
        background-color: rgba(128, 128, 128, 0.1);
        border: 1px solid rgba(128, 128, 128, 0.3);
        border-radius: 5px;
        padding: 15px;
        margin: 10px 0;
    }
    .reasoning-box {
        background-color: rgba(255, 193, 7, 0.15);
        border-left: 4px solid #ffc107;
        padding: 10px;
        margin: 10px 0;
        border-radius: 3px;
    }
    .tools-used {
        background-color: rgba(23, 162, 184, 0.15);
        border-left: 4px solid #17a2b8;
        padding: 10px;
        margin: 10px 0;
        border-radius: 3px;
    }
    /* Dark theme specific fixes */
    @media (prefers-color-scheme: dark) {
        .response-box {
            background-color: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        .reasoning-box {
            background-color: rgba(255, 193, 7, 0.2);
        }
        .tools-used {
            background-color: rgba(23, 162, 184, 0.2);
        }
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data
def load_test_results(file_path):
    """Load and cache test results JSON"""
    with open(file_path, 'r') as f:
        return json.load(f)

def format_timestamp(ts_string):
    """Format ISO timestamp to readable format"""
    try:
        dt = datetime.fromisoformat(ts_string)
        return dt.strftime("%B %d, %Y at %I:%M:%S %p")
    except Exception:
        return ts_string

def format_metric(value, unit="", decimals=2):
    """Format metric with appropriate precision"""
    if isinstance(value, float):
        return f"{value:.{decimals}f}{unit}"
    return f"{value}{unit}"

def get_model_display_name(model_id):
    """Get shortened display name for model"""
    if "llama4-maverick" in model_id.lower():
        return "Llama 4 Maverick"
    elif "gpt-oss" in model_id.lower():
        return "GPT-OSS"
    elif "claude" in model_id.lower():
        return "Claude 3.5 Sonnet"
    else:
        # Extract last part after last dot or colon
        return model_id.split('.')[-1].split(':')[0].title()

def display_comparison_metrics(comparison):
    """Display comparison metrics with visual indicators"""
    cols = st.columns(4)
    
    with cols[0]:
        delta = comparison.get('latency_delta_ms', 0)
        if delta < 0:
            st.metric("Latency Δ", f"{abs(delta):.0f}ms", delta="Model 2 slower", delta_color="inverse")
        else:
            st.metric("Latency Δ", f"{delta:.0f}ms", delta="Model 1 slower", delta_color="inverse")
    
    with cols[1]:
        delta = comparison.get('cost_delta_usd', 0)
        if delta < 0:
            st.metric("Cost Δ", f"${abs(delta):.4f}", delta="Model 2 costlier", delta_color="inverse")
        else:
            st.metric("Cost Δ", f"${delta:.4f}", delta="Model 1 costlier", delta_color="inverse")
    
    with cols[2]:
        delta = comparison.get('tokens_delta', 0)
        st.metric("Tokens Δ", f"{abs(delta)}", delta=f"Model {'2' if delta < 0 else '1'} used more")
    
    with cols[3]:
        winner = comparison.get('winner', 'N/A')
        if winner == 'model_1':
            st.markdown("🏆 **Winner: Model 1**")
        elif winner == 'model_2':
            st.markdown("🏆 **Winner: Model 2**")
        else:
            st.markdown("🤝 **Tie**")

def display_model_response(model_name, result, is_winner=False):
    """Display a single model's response with metrics"""
    
    # Header with winner badge
    header_html = f"<h3>{model_name}"
    if is_winner:
        header_html += ' <span class="winner-badge">✓ WINNER</span>'
    header_html += "</h3>"
    st.markdown(header_html, unsafe_allow_html=True)
    
    # Performance metrics
    perf = result.get('performance', {})
    cols = st.columns(5)
    cols[0].metric("Latency", f"{perf.get('latency_ms', 0):.0f}ms")
    cols[1].metric("Input Tokens", f"{perf.get('tokens_input', 0):,}")
    cols[2].metric("Output Tokens", f"{perf.get('tokens_output', 0):,}")
    cols[3].metric("Total Tokens", f"{perf.get('tokens_total', 0):,}")
    cols[4].metric("Cost", f"${perf.get('cost_usd', 0):.4f}")
    
    # Tools used
    tools = result.get('tools_used', [])
    if tools:
        tools_html = '<div class="tools-used"><strong>🔧 Tools Called:</strong><br>'
        for i, tool in enumerate(tools, 1):
            tool_name = tool.get('tool', 'unknown')
            args = tool.get('args', {})
            args_str = ', '.join(f"{k}={v}" for k, v in args.items() if v) if args else 'no args'
            tools_html += f"{i}. <code>{tool_name}({args_str})</code><br>"
        tools_html += '</div>'
        st.markdown(tools_html, unsafe_allow_html=True)
    
    # Reasoning (if present)
    response = result.get('response', {})
    if response.get('has_reasoning', False):
        reasoning = response.get('reasoning', '')
        if reasoning:
            with st.expander("🧠 Model Reasoning", expanded=False):
                st.markdown(f'<div class="reasoning-box">{reasoning}</div>', unsafe_allow_html=True)
    
    # Final answer
    st.markdown("**Response:**")
    final_answer = response.get('final_answer', response.get('raw_content', 'No response'))
    
    # Handle list format for raw_content (e.g., GPT-OSS with reasoning)
    if isinstance(final_answer, list):
        for item in final_answer:
            if isinstance(item, dict) and item.get('type') == 'text':
                final_answer = item.get('text', '')
                break
    
    st.markdown(f'<div class="response-box">{final_answer}</div>', unsafe_allow_html=True)
    
    # Errors and quality issues
    if result.get('errors'):
        st.error(f"⚠️ Errors: {', '.join(result['errors'])}")
    
    if result.get('quality_issues'):
        st.warning(f"⚠️ Quality Issues: {', '.join(result['quality_issues'])}")

def main():
    st.title("🤖 LLM Test Results Viewer")
    st.markdown("Compare model responses and performance metrics from test runs")
    
    # Sidebar - File selection
    st.sidebar.header("📁 Select Test Results")
    
    results_dir = Path(__file__).parent / "results"
    if not results_dir.exists():
        st.error(f"Results directory not found: {results_dir}")
        return
    
    json_files = sorted(results_dir.glob("*.json"), reverse=True)
    
    if not json_files:
        st.error("No test result JSON files found in tests/results/")
        return
    
    file_options = {f.name: f for f in json_files}
    selected_file = st.sidebar.selectbox(
        "Choose a test run:",
        options=list(file_options.keys()),
        format_func=lambda x: f"{x.replace('test_results_', '').replace('.json', '')}"
    )
    
    # Load selected file
    data = load_test_results(file_options[selected_file])
    
    # Display metadata
    st.sidebar.header("📊 Test Metadata")
    metadata = data.get('test_metadata', {})
    st.sidebar.markdown(f"**Test Run ID:** `{metadata.get('test_run_id', 'N/A')}`")
    st.sidebar.markdown(f"**Timestamp:** {format_timestamp(metadata.get('timestamp', 'N/A'))}")
    st.sidebar.markdown(f"**Query File:** {metadata.get('query_file', 'N/A')}")
    
    models = metadata.get('models_tested', [])
    if models:
        st.sidebar.markdown("**Models Tested:**")
        for i, model in enumerate(models, 1):
            st.sidebar.markdown(f"{i}. `{get_model_display_name(model)}`")
    
    # Aggregate statistics
    st.header("📈 Aggregate Statistics")
    
    aggregate = data.get('aggregate_comparison', {}).get('models', {})
    if aggregate:
        cols = st.columns(len(aggregate))
        for idx, (model_id, stats) in enumerate(aggregate.items()):
            with cols[idx]:
                st.subheader(get_model_display_name(model_id))
                st.metric("Success Rate", f"{stats.get('success_rate', 0) * 100:.1f}%")
                st.metric("Avg Latency", f"{stats.get('avg_latency_ms', 0):.0f}ms")
                st.metric("Avg Cost", f"${stats.get('avg_cost_per_query', 0):.4f}")
                st.metric("Avg Tokens", f"{stats.get('avg_tokens_total', 0):.0f}")
                st.metric("Total Cost", f"${stats.get('total_cost_usd', 0):.4f}")
                
                reasoning_stats = stats.get('reasoning_stats', {})
                if reasoning_stats.get('reasoning_percentage', 0) > 0:
                    st.metric("Reasoning Usage", f"{reasoning_stats.get('reasoning_percentage', 0):.0f}%")
    
    # Query browser
    st.header("🔍 Query Details")
    
    queries = data.get('queries', [])
    if not queries:
        st.warning("No queries found in this test run")
        return
    
    # Query selector
    query_options = {
        f"Q{q['query_id']}: {q['query_text'][:60]}{'...' if len(q['query_text']) > 60 else ''}": q 
        for q in queries
    }
    
    selected_query_key = st.selectbox(
        "Select a query to view:",
        options=list(query_options.keys())
    )
    
    selected_query = query_options[selected_query_key]
    
    # Display query info
    st.subheader(f"Query {selected_query['query_id']}: {selected_query['query_text']}")
    st.markdown(f"**Category:** `{selected_query.get('category', 'N/A')}`")
    
    # Comparison metrics
    if 'comparison' in selected_query:
        st.markdown("---")
        st.subheader("📊 Head-to-Head Comparison")
        display_comparison_metrics(selected_query['comparison'])
    
    # Model responses
    st.markdown("---")
    model_results = selected_query.get('model_results', {})
    
    if len(model_results) >= 2:
        # Side-by-side comparison
        model_ids = list(model_results.keys())
        comparison = selected_query.get('comparison', {})
        winner = comparison.get('winner', None)
        
        col1, col2 = st.columns(2)
        
        with col1:
            is_winner = winner == 'model_1'
            display_model_response(
                get_model_display_name(model_ids[0]),
                model_results[model_ids[0]],
                is_winner
            )
        
        with col2:
            is_winner = winner == 'model_2'
            display_model_response(
                get_model_display_name(model_ids[1]),
                model_results[model_ids[1]],
                is_winner
            )
    else:
        # Single model display
        for model_id, result in model_results.items():
            display_model_response(get_model_display_name(model_id), result)
    
    # Raw JSON viewer (collapsible)
    with st.expander("🔧 View Raw JSON", expanded=False):
        st.json(selected_query)

if __name__ == "__main__":
    main()
