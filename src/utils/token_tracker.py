# src/utils/token_tracker.py

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

class TokenTracker:
    """Track token usage and costs"""
    
    # Pricing per 1K tokens (update these for your actual model)
    PRICING = {
        "meta.llama4-maverick-17b-instruct-v1:0": {
            "input": 0.00024,   # $0.00024 per 1K input tokens
            "output": 0.00097   # $0.00097 per 1K output tokens
        },
        "anthropic.claude-3-5-sonnet-20241022-v2:0": {
            "input": 0.003,
            "output": 0.015
        },
        "meta.llama4-scout-17b-instruct-v1:0": {
            "input": 0.00017,
            "output": 0.00066
        },
    }
    
    def __init__(self, log_file: str = "token_usage.jsonl"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
    
    def log_usage(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        query: Optional[str] = None,
        response_time: Optional[float] = None,
        tools_used: bool = False,
        session_id: Optional[str] = None
    ):
        """Log token usage to file"""
        
        total_tokens = input_tokens + output_tokens
        
        # Calculate cost
        pricing = self.PRICING.get(model_id, {"input": 0, "output": 0})
        cost = (
            (input_tokens / 1000) * pricing["input"] +
            (output_tokens / 1000) * pricing["output"]
        )
        
        # Create log entry
        entry = {
            "timestamp": datetime.now().isoformat(),
            "model_id": model_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": round(cost, 6),
            "query_preview": query[:100] if query else None,
            "response_time_sec": round(response_time, 2) if response_time else None,
            "tools_used": tools_used,
            "session_id": session_id
        }
        
        # Append to JSONL file
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
        
        return entry
    
    def get_total_cost(self) -> float:
        """Calculate total cost from all logged entries"""
        if not self.log_file.exists():
            return 0.0
        
        total = 0.0
        with open(self.log_file, "r") as f:
            for line in f:
                entry = json.loads(line)
                total += entry.get("estimated_cost_usd", 0)
        
        return round(total, 4)
    
    def get_summary(self) -> dict:
        """Get usage summary"""
        if not self.log_file.exists():
            return {"total_queries": 0, "total_cost": 0, "total_tokens": 0}
        
        total_cost = 0.0
        total_tokens = 0
        queries = 0
        
        with open(self.log_file, "r") as f:
            for line in f:
                entry = json.loads(line)
                total_cost += entry.get("estimated_cost_usd", 0)
                total_tokens += entry.get("total_tokens", 0)
                queries += 1
        
        return {
            "total_queries": queries,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 4),
            "avg_tokens_per_query": round(total_tokens / queries) if queries > 0 else 0
        }
