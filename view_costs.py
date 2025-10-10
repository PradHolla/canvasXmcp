# view_costs.py

from src.utils.token_tracker import TokenTracker

tracker = TokenTracker()
summary = tracker.get_summary()

print("="*60)
print("💰 TOKEN USAGE SUMMARY")
print("="*60)
print(f"Total spent: ${summary['total_cost_usd']:.4f}")
print(f"Total queries: {summary['total_queries']}")
print(f"Total tokens: {summary['total_tokens']:,}")
print(f"Avg tokens/query: {summary['avg_tokens_per_query']}")
print("="*60)
