import streamlit as st
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# Page config
st.set_page_config(
    page_title="Canvas AI Response Evaluator",
    page_icon="📊",
    layout="wide"
)

# Failure type enum
FAILURE_TYPES = [
    None,  # Pass - no failure
    "wrong_data_returned",
    "incomplete_answer",
    "poor_formatting",
    "hallucination",
    "error_not_handled",
    "ambiguous_response",
    "extra_noise"
]

# Initialize session state
if 'current_query_idx' not in st.session_state:
    st.session_state.current_query_idx = 0
if 'evaluations' not in st.session_state:
    st.session_state.evaluations = []
if 'test_results' not in st.session_state:
    st.session_state.test_results = None

# Load test results
@st.cache_resource
def load_test_results(file_path: str):
    """Load test results from JSON"""
    with open(file_path, 'r') as f:
        return json.load(f)

# Get all queries from test results
def get_all_queries(test_results: Dict) -> List[Dict]:
    """Extract all queries from test results"""
    queries = []
    for query_data in test_results.get('queries', []):
        queries.append({
            'query_id': query_data['query_id'],
            'query_text': query_data['query_text'],
            'category': query_data['category'],
            'test_run_id': test_results['test_metadata']['test_run_id'],
            'model_results': query_data['model_results']
        })
    return queries

# Calculate overall score
def calculate_overall_score(correctness: int, completeness: int, clarity: int) -> float:
    """Calculate average score"""
    return round((correctness + completeness + clarity) / 3, 2)

# Save evaluation
def save_evaluation(eval_data: Dict):
    """Save or update evaluation in session state"""
    query_id = eval_data['query_id']
    
    # Check if this query already has an evaluation
    existing_idx = None
    for idx, existing_eval in enumerate(st.session_state.evaluations):
        if existing_eval['query_id'] == query_id:
            existing_idx = idx
            break
    
    if existing_idx is not None:
        # Update existing evaluation
        st.session_state.evaluations[existing_idx] = eval_data
    else:
        # Add new evaluation
        st.session_state.evaluations.append(eval_data)

# Get evaluation for query
def get_evaluation_for_query(query_id: int) -> Dict:
    """Get existing evaluation for a query, if any"""
    for eval_data in st.session_state.evaluations:
        if eval_data['query_id'] == query_id:
            return eval_data
    return None

# Export evaluations
def export_evaluations(queries: List[Dict], evaluations: List[Dict]) -> Dict:
    """Generate comprehensive evaluation JSON"""
    
    # Group evaluations by model and category
    by_category = {}
    for query in queries:
        category = query['category']
        if category not in by_category:
            by_category[category] = {
                'total_queries': 0,
                'llama': {'scores': [], 'failures': {}},
                'gpt_oss': {'scores': [], 'failures': {}}
            }
        by_category[category]['total_queries'] += 1
    
    # Process evaluations
    overall_llama_scores = []
    overall_gpt_scores = []
    overall_llama_failures = {}
    overall_gpt_failures = {}
    
    evaluation_entries = []
    
    for eval_data in evaluations:
        query_id = eval_data['query_id']
        query = next(q for q in queries if q['query_id'] == query_id)
        category = query['category']
        
        # Llama evaluation
        llama_eval = eval_data['llama']
        llama_overall = calculate_overall_score(
            llama_eval['correctness'],
            llama_eval['completeness'],
            llama_eval['clarity']
        )
        overall_llama_scores.append(llama_overall)
        
        if llama_eval['failure_type']:
            by_category[category]['llama']['failures'][llama_eval['failure_type']] = \
                by_category[category]['llama']['failures'].get(llama_eval['failure_type'], 0) + 1
            overall_llama_failures[llama_eval['failure_type']] = \
                overall_llama_failures.get(llama_eval['failure_type'], 0) + 1
        
        by_category[category]['llama']['scores'].append(llama_overall)
        
        # GPT-OSS evaluation
        gpt_eval = eval_data['gpt_oss']
        gpt_overall = calculate_overall_score(
            gpt_eval['correctness'],
            gpt_eval['completeness'],
            gpt_eval['clarity']
        )
        overall_gpt_scores.append(gpt_overall)
        
        if gpt_eval['failure_type']:
            by_category[category]['gpt_oss']['failures'][gpt_eval['failure_type']] = \
                by_category[category]['gpt_oss']['failures'].get(gpt_eval['failure_type'], 0) + 1
            overall_gpt_failures[gpt_eval['failure_type']] = \
                overall_gpt_failures.get(gpt_eval['failure_type'], 0) + 1
        
        by_category[category]['gpt_oss']['scores'].append(gpt_overall)
        
        # Build evaluation entry
        evaluation_entries.append({
            "query_id": query_id,
            "query_text": query['query_text'],
            "category": category,
            "test_run_id": query['test_run_id'],
            "model_evaluations": {
                "us.meta.llama4-maverick-17b-instruct-v1:0": {
                    "model_name": "Llama Maverick 17B",
                    "response": query['model_results']['us.meta.llama4-maverick-17b-instruct-v1:0']['response']['final_answer'],
                    "ratings": {
                        "correctness": llama_eval['correctness'],
                        "completeness": llama_eval['completeness'],
                        "clarity": llama_eval['clarity']
                    },
                    "overall_score": llama_overall,
                    "pass": llama_overall >= 6,
                    "failure_type": llama_eval['failure_type'],
                    "notes": llama_eval['notes']
                },
                "openai.gpt-oss-120b-1:0": {
                    "model_name": "GPT-OSS 120B",
                    "response": query['model_results']['openai.gpt-oss-120b-1:0']['response']['final_answer'],
                    "ratings": {
                        "correctness": gpt_eval['correctness'],
                        "completeness": gpt_eval['completeness'],
                        "clarity": gpt_eval['clarity']
                    },
                    "overall_score": gpt_overall,
                    "pass": gpt_overall >= 6,
                    "failure_type": gpt_eval['failure_type'],
                    "notes": gpt_eval['notes']
                }
            }
        })
    
    # Build aggregate stats by category
    category_stats = {}
    for category, data in by_category.items():
        llama_scores = data['llama']['scores']
        gpt_scores = data['gpt_oss']['scores']
        
        category_stats[category] = {
            "total_queries": data['total_queries'],
            "total_evaluations": data['total_queries'] * 2,
            "llama": {
                "avg_correctness": round(sum([eval_data['llama']['correctness'] 
                                             for eval_data in evaluations 
                                             if next(q for q in queries if q['query_id'] == eval_data['query_id'])['category'] == category]) / len(llama_scores) if llama_scores else 0, 2),
                "avg_completeness": round(sum([eval_data['llama']['completeness'] 
                                              for eval_data in evaluations 
                                              if next(q for q in queries if q['query_id'] == eval_data['query_id'])['category'] == category]) / len(llama_scores) if llama_scores else 0, 2),
                "avg_clarity": round(sum([eval_data['llama']['clarity'] 
                                         for eval_data in evaluations 
                                         if next(q for q in queries if q['query_id'] == eval_data['query_id'])['category'] == category]) / len(llama_scores) if llama_scores else 0, 2),
                "overall_avg": round(sum(llama_scores) / len(llama_scores), 2) if llama_scores else 0,
                "pass_rate": round(sum(1 for score in llama_scores if score >= 6) / len(llama_scores), 3) if llama_scores else 0,
                "failure_breakdown": data['llama']['failures']
            },
            "gpt_oss": {
                "avg_correctness": round(sum([eval_data['gpt_oss']['correctness'] 
                                             for eval_data in evaluations 
                                             if next(q for q in queries if q['query_id'] == eval_data['query_id'])['category'] == category]) / len(gpt_scores) if gpt_scores else 0, 2),
                "avg_completeness": round(sum([eval_data['gpt_oss']['completeness'] 
                                              for eval_data in evaluations 
                                              if next(q for q in queries if q['query_id'] == eval_data['query_id'])['category'] == category]) / len(gpt_scores) if gpt_scores else 0, 2),
                "avg_clarity": round(sum([eval_data['gpt_oss']['clarity'] 
                                         for eval_data in evaluations 
                                         if next(q for q in queries if q['query_id'] == eval_data['query_id'])['category'] == category]) / len(gpt_scores) if gpt_scores else 0, 2),
                "overall_avg": round(sum(gpt_scores) / len(gpt_scores), 2) if gpt_scores else 0,
                "pass_rate": round(sum(1 for score in gpt_scores if score >= 6) / len(gpt_scores), 3) if gpt_scores else 0,
                "failure_breakdown": data['gpt_oss']['failures']
            }
        }
    
    # Build overall stats
    overall_stats = {
        "total_queries": len(queries),
        "total_evaluations": len(evaluations) * 2,
        "llama": {
            "avg_correctness": round(sum([eval_data['llama']['correctness'] for eval_data in evaluations]) / len(evaluations), 2),
            "avg_completeness": round(sum([eval_data['llama']['completeness'] for eval_data in evaluations]) / len(evaluations), 2),
            "avg_clarity": round(sum([eval_data['llama']['clarity'] for eval_data in evaluations]) / len(evaluations), 2),
            "overall_avg": round(sum(overall_llama_scores) / len(overall_llama_scores), 2) if overall_llama_scores else 0,
            "pass_rate": round(sum(1 for score in overall_llama_scores if score >= 6) / len(overall_llama_scores), 3) if overall_llama_scores else 0,
            "failure_breakdown": overall_llama_failures
        },
        "gpt_oss": {
            "avg_correctness": round(sum([eval_data['gpt_oss']['correctness'] for eval_data in evaluations]) / len(evaluations), 2),
            "avg_completeness": round(sum([eval_data['gpt_oss']['completeness'] for eval_data in evaluations]) / len(evaluations), 2),
            "avg_clarity": round(sum([eval_data['gpt_oss']['clarity'] for eval_data in evaluations]) / len(evaluations), 2),
            "overall_avg": round(sum(overall_gpt_scores) / len(overall_gpt_scores), 2) if overall_gpt_scores else 0,
            "pass_rate": round(sum(1 for score in overall_gpt_scores if score >= 6) / len(overall_gpt_scores), 3) if overall_gpt_scores else 0,
            "failure_breakdown": overall_gpt_failures
        }
    }
    
    return {
        "evaluation_metadata": {
            "evaluation_run_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "timestamp": datetime.now().isoformat(),
            "evaluator": "your_name",
            "total_queries_evaluated": len(evaluations),
            "evaluation_timestamp": datetime.now().isoformat()
        },
        "evaluations": evaluation_entries,
        "aggregate_stats": {
            "by_category": category_stats,
            "overall": overall_stats
        }
    }

# Main app
def main():
    st.title("🎓 Canvas AI Response Evaluator")
    
    # Sidebar: File selection & stats
    with st.sidebar:
        st.header("📁 Select Test Results")
        
        # Get results directory
        results_dir = Path(__file__).parent / "results"
        if not results_dir.exists():
            st.error(f"Results directory not found: {results_dir}")
            return
        
        # Get all JSON files
        json_files = sorted(results_dir.glob("*.json"), reverse=True)
        
        if not json_files:
            st.error("No test result JSON files found in tests/results/")
            return
        
        # File selection dropdown
        file_options = {f.name: f for f in json_files}
        selected_file = st.selectbox(
            "Choose a test run:",
            options=list(file_options.keys()),
            format_func=lambda x: f"{x.replace('test_results_', '').replace('.json', '')}"
        )
        
        if selected_file:
            # Load the selected file
            test_data = load_test_results(file_options[selected_file])
            st.session_state.test_results = test_data
            queries = get_all_queries(test_data)
            
            st.success(f"✅ Loaded {len(queries)} queries")
            
            # Progress
            st.header("📊 Progress")
            progress = st.session_state.current_query_idx / len(queries)
            st.progress(progress)
            st.write(f"**{st.session_state.current_query_idx}/{len(queries)}** evaluated")
            
            # Quick stats
            if st.session_state.evaluations:
                st.header("📈 Current Stats")
                llama_scores = [calculate_overall_score(e['llama']['correctness'], 
                                                       e['llama']['completeness'],
                                                       e['llama']['clarity'])
                               for e in st.session_state.evaluations]
                gpt_scores = [calculate_overall_score(e['gpt_oss']['correctness'],
                                                     e['gpt_oss']['completeness'],
                                                     e['gpt_oss']['clarity'])
                             for e in st.session_state.evaluations]
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Llama Avg", f"{sum(llama_scores)/len(llama_scores):.2f}/10")
                with col2:
                    st.metric("GPT-OSS Avg", f"{sum(gpt_scores)/len(gpt_scores):.2f}/10")
    
    # Main content
    if not st.session_state.test_results:
        st.info("👈 Upload a test_results JSON file to get started")
        return
    
    queries = get_all_queries(st.session_state.test_results)
    
    if st.session_state.current_query_idx >= len(queries):
        st.success("✅ All queries evaluated!")
        
        # Export button
        if st.button("💾 Export Evaluation Report"):
            report = export_evaluations(queries, st.session_state.evaluations)
            st.json(report)
            
            # Download button
            report_json = json.dumps(report, indent=2)
            st.download_button(
                label="📥 Download JSON",
                data=report_json,
                file_name=f"evaluations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )
        return
    
    current_query = queries[st.session_state.current_query_idx]
    llama_result = current_query['model_results']['us.meta.llama4-maverick-17b-instruct-v1:0']
    gpt_result = current_query['model_results']['openai.gpt-oss-120b-1:0']
    
    # Header
    st.header(f"Query {st.session_state.current_query_idx + 1}/{len(queries)}")
    st.subheader(f"📍 Category: `{current_query['category']}`")
    st.write(f"**Query:** {current_query['query_text']}")
    
    # Side by side responses
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🦙 Llama Maverick 17B")
        st.info(llama_result['response']['final_answer'])
        st.caption(f"⏱️ {llama_result['performance']['latency_ms']}ms | 💰 ${llama_result['performance']['cost_usd']:.6f} | 🔧 {len(llama_result['tools_used'])} tools")
    
    with col2:
        st.markdown("### 🤖 GPT-OSS 120B")
        st.warning(gpt_result['response']['final_answer'])
        st.caption(f"⏱️ {gpt_result['performance']['latency_ms']}ms | 💰 ${gpt_result['performance']['cost_usd']:.6f} | 🔧 {len(gpt_result['tools_used'])} tools")
    
    st.divider()
    
    # Rating form
    st.header("⭐ Rate Responses")
    
    # Check if this query already has an evaluation
    existing_eval = get_evaluation_for_query(current_query['query_id'])
    
    # Set default values
    if existing_eval:
        llama_default_correctness = existing_eval['llama']['correctness']
        llama_default_completeness = existing_eval['llama']['completeness']
        llama_default_clarity = existing_eval['llama']['clarity']
        llama_default_failure = existing_eval['llama']['failure_type']
        llama_default_notes = existing_eval['llama']['notes']
        
        gpt_default_correctness = existing_eval['gpt_oss']['correctness']
        gpt_default_completeness = existing_eval['gpt_oss']['completeness']
        gpt_default_clarity = existing_eval['gpt_oss']['clarity']
        gpt_default_failure = existing_eval['gpt_oss']['failure_type']
        gpt_default_notes = existing_eval['gpt_oss']['notes']
        
        st.info("ℹ️ Editing existing evaluation for this query")
    else:
        llama_default_correctness = 7
        llama_default_completeness = 7
        llama_default_clarity = 7
        llama_default_failure = None
        llama_default_notes = ""
        
        gpt_default_correctness = 7
        gpt_default_completeness = 7
        gpt_default_clarity = 7
        gpt_default_failure = None
        gpt_default_notes = ""
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Llama")
        llama_correctness = st.slider("Correctness", 1, 10, llama_default_correctness, key="llama_correctness")
        llama_completeness = st.slider("Completeness", 1, 10, llama_default_completeness, key="llama_completeness")
        llama_clarity = st.slider("Clarity", 1, 10, llama_default_clarity, key="llama_clarity")
        llama_overall = calculate_overall_score(llama_correctness, llama_completeness, llama_clarity)
        st.metric("Overall", f"{llama_overall}/10", "✅ PASS" if llama_overall >= 6 else "❌ FAIL")
        
        # Get index for failure type
        try:
            llama_failure_idx = FAILURE_TYPES.index(llama_default_failure) if llama_default_failure in FAILURE_TYPES else 0
        except ValueError:
            llama_failure_idx = 0 if llama_overall >= 6 else 1
            
        llama_failure = st.selectbox("Failure Type", FAILURE_TYPES, key="llama_failure", index=llama_failure_idx)
        llama_notes = st.text_area("Notes", value=llama_default_notes, key="llama_notes", height=80)
    
    with col2:
        st.subheader("GPT-OSS")
        gpt_correctness = st.slider("Correctness", 1, 10, gpt_default_correctness, key="gpt_correctness")
        gpt_completeness = st.slider("Completeness", 1, 10, gpt_default_completeness, key="gpt_completeness")
        gpt_clarity = st.slider("Clarity", 1, 10, gpt_default_clarity, key="gpt_clarity")
        gpt_overall = calculate_overall_score(gpt_correctness, gpt_completeness, gpt_clarity)
        st.metric("Overall", f"{gpt_overall}/10", "✅ PASS" if gpt_overall >= 6 else "❌ FAIL")
        
        # Get index for failure type
        try:
            gpt_failure_idx = FAILURE_TYPES.index(gpt_default_failure) if gpt_default_failure in FAILURE_TYPES else 0
        except ValueError:
            gpt_failure_idx = 0 if gpt_overall >= 6 else 1
            
        gpt_failure = st.selectbox("Failure Type", FAILURE_TYPES, key="gpt_failure", index=gpt_failure_idx)
        gpt_notes = st.text_area("Notes", value=gpt_default_notes, key="gpt_notes", height=80)
    
    st.divider()
    
    # Navigation
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("⬅️ Previous"):
            st.session_state.current_query_idx = max(0, st.session_state.current_query_idx - 1)
            st.rerun()
    
    with col2:
        # Change button text based on whether we're updating or creating new
        save_button_text = "💾 Update & Next" if existing_eval else "💾 Save & Next"
        if st.button(save_button_text):
            eval_data = {
                "query_id": current_query['query_id'],
                "llama": {
                    "correctness": llama_correctness,
                    "completeness": llama_completeness,
                    "clarity": llama_clarity,
                    "failure_type": llama_failure,
                    "notes": llama_notes
                },
                "gpt_oss": {
                    "correctness": gpt_correctness,
                    "completeness": gpt_completeness,
                    "clarity": gpt_clarity,
                    "failure_type": gpt_failure,
                    "notes": gpt_notes
                }
            }
            save_evaluation(eval_data)
            st.session_state.current_query_idx += 1
            st.success("✅ Updated!" if existing_eval else "✅ Saved!")
            st.rerun()
    
    with col3:
        if st.button("⏭️ Skip"):
            st.session_state.current_query_idx += 1
            st.rerun()

if __name__ == "__main__":
    main()
