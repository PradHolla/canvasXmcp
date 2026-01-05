#!/usr/bin/env python3
"""
Simple Streamlit viewer for LLM test results.
Minimal interface optimized for copying query/response text.

Usage:
    streamlit run tests/simple_viewer.py
"""

import streamlit as st
import json
from pathlib import Path

# Page config
st.set_page_config(
    page_title="Simple Test Results Viewer",
    page_icon="📋",
    layout="wide"
)

# Minimal CSS
st.markdown("""
<style>
    .text-box {
        background-color: rgba(128, 128, 128, 0.05);
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 5px;
        padding: 20px;
        margin: 15px 0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        line-height: 1.6;
    }
    .query-text {
        font-size: 1.1em;
        font-weight: 500;
        margin-bottom: 20px;
    }
    @media (prefers-color-scheme: dark) {
        .text-box {
            background-color: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.15);
        }
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data
def load_test_results(file_path):
    """Load and cache test results JSON"""
    with open(file_path, 'r') as f:
        return json.load(f)

def get_model_display_name(model_id):
    """Get shortened display name for model"""
    if "llama4-maverick" in model_id.lower():
        return "Llama 4 Maverick"
    elif "gpt-oss" in model_id.lower():
        return "GPT-OSS"
    elif "claude" in model_id.lower():
        return "Claude 3.5 Sonnet"
    else:
        return model_id.split('.')[-1].split(':')[0].title()

def extract_final_answer(response):
    """Extract final answer from response object"""
    final_answer = response.get('final_answer', response.get('raw_content', 'No response'))
    
    # Handle list format
    if isinstance(final_answer, list):
        for item in final_answer:
            if isinstance(item, dict) and item.get('type') == 'text':
                return item.get('text', '')
    
    return final_answer

def main():
    st.title("📋 Simple Test Results Viewer")
    
    # File selection
    results_dir = Path(__file__).parent / "results"
    if not results_dir.exists():
        st.error(f"Results directory not found: {results_dir}")
        return
    
    json_files = sorted(results_dir.glob("*.json"), reverse=True)
    
    if not json_files:
        st.error("No test result JSON files found in tests/results/")
        return
    
    file_options = {f.name: f for f in json_files}
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        selected_file = st.selectbox(
            "Select test results file:",
            options=list(file_options.keys()),
            format_func=lambda x: f"{x.replace('test_results_', '').replace('.json', '')}"
        )
    
    # Load data
    data = load_test_results(file_options[selected_file])
    queries = data.get('queries', [])
    
    if not queries:
        st.warning("No queries found in this test run")
        return
    
    with col2:
        query_num = st.selectbox(
            "Select query:",
            options=range(1, len(queries) + 1),
            format_func=lambda x: f"Query {x}"
        )
    
    # Get selected query
    selected_query = queries[query_num - 1]
    query_text = selected_query['query_text']
    model_results = selected_query.get('model_results', {})
    
    # Display query
    st.markdown("---")
    st.markdown('<div class="text-box query-text">📝 <strong>Query:</strong></div>', unsafe_allow_html=True)
    st.text_area(
        "Query Text",
        value=query_text,
        height=80,
        label_visibility="collapsed",
        key="query"
    )
    
    # Display model responses
    if len(model_results) >= 2:
        model_ids = list(model_results.keys())
        
        col1, col2 = st.columns(2)
        
        with col1:
            model_name = get_model_display_name(model_ids[0])
            st.markdown(f'<div class="text-box">🤖 <strong>{model_name}</strong></div>', unsafe_allow_html=True)
            
            result = model_results[model_ids[0]]
            response = result.get('response', {})
            answer = extract_final_answer(response)
            
            st.text_area(
                f"{model_name} Response",
                value=answer,
                height=400,
                label_visibility="collapsed",
                key=f"model1_{query_num}"
            )
            
            # Quick stats
            perf = result.get('performance', {})
            st.caption(f"⏱️ {perf.get('latency_ms', 0):.0f}ms | 🪙 {perf.get('tokens_total', 0):,} tokens | 💰 ${perf.get('cost_usd', 0):.4f}")
        
        with col2:
            model_name = get_model_display_name(model_ids[1])
            st.markdown(f'<div class="text-box">🤖 <strong>{model_name}</strong></div>', unsafe_allow_html=True)
            
            result = model_results[model_ids[1]]
            response = result.get('response', {})
            answer = extract_final_answer(response)
            
            st.text_area(
                f"{model_name} Response",
                value=answer,
                height=400,
                label_visibility="collapsed",
                key=f"model2_{query_num}"
            )
            
            # Quick stats
            perf = result.get('performance', {})
            st.caption(f"⏱️ {perf.get('latency_ms', 0):.0f}ms | 🪙 {perf.get('tokens_total', 0):,} tokens | 💰 ${perf.get('cost_usd', 0):.4f}")
    else:
        # Single model
        for model_id, result in model_results.items():
            model_name = get_model_display_name(model_id)
            st.markdown(f'<div class="text-box">🤖 <strong>{model_name}</strong></div>', unsafe_allow_html=True)
            
            response = result.get('response', {})
            answer = extract_final_answer(response)
            
            st.text_area(
                f"{model_name} Response",
                value=answer,
                height=400,
                label_visibility="collapsed",
                key=f"model_{query_num}"
            )
            
            perf = result.get('performance', {})
            st.caption(f"⏱️ {perf.get('latency_ms', 0):.0f}ms | 🪙 {perf.get('tokens_total', 0):,} tokens | 💰 ${perf.get('cost_usd', 0):.4f}")
    
    # Copy-paste ready format
    st.markdown("---")
    with st.expander("📄 Copy-Paste Format (Plain Text)", expanded=False):
        # Generate plain text format
        plain_text = f"QUERY:\n{query_text}\n\n"
        
        for idx, (model_id, result) in enumerate(model_results.items(), 1):
            model_name = get_model_display_name(model_id)
            response = result.get('response', {})
            answer = extract_final_answer(response)
            
            plain_text += f"MODEL {idx}: {model_name}\n"
            plain_text += f"{answer}\n\n"
            plain_text += "---\n\n"
        
        st.text_area(
            "Plain Text Format",
            value=plain_text,
            height=400,
            label_visibility="collapsed"
        )

if __name__ == "__main__":
    main()
