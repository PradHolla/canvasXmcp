# test_agent.py

import asyncio
from src.agent.canvas_agent import CanvasAgent


async def main():
    # Initialize agent
    agent = CanvasAgent()
    await agent.initialize()
    
    print("="*60)
    print("TESTING CANVAS AGENT")
    print("="*60)
    
    # Test queries
    queries = [
        "What courses am I enrolled in?",
        "What assignments are due in the next 7 days?",
        "Show me recent announcements from my courses"
    ]
    
    for i, query in enumerate(queries, 1):
        print(f"\n{'='*60}")
        print(f"Query {i}: {query}")
        print("="*60)
        
        response = await agent.query(query)
        print(f"\nAgent Response:\n{response}\n")
    
    # Cleanup
    await agent.cleanup()
    print("\n✅ All tests complete!")

    # After cleanup
    summary = agent.tracker.get_summary()
    print("\n" + "="*60)
    print("💰 COST SUMMARY")
    print("="*60)
    print(f"Total queries: {summary['total_queries']}")
    print(f"Total tokens: {summary['total_tokens']:,}")
    print(f"Average tokens/query: {summary['avg_tokens_per_query']}")
    print(f"Total cost: ${summary['total_cost_usd']:.4f}")
    print("="*60)



if __name__ == "__main__":
    asyncio.run(main())
