"""
Async SQLite checkpointer for LangGraph agent persistence with Chainlit.
"""
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from contextlib import AsyncExitStack
import logging

logger = logging.getLogger(__name__)

# Global state
_checkpointer = None
_stack = None

async def get_checkpointer():
    """
    Get or create async SQLite checkpointer.
    Uses AsyncExitStack to keep the context manager alive across requests.
    
    Returns:
        AsyncSqliteSaver: Initialized async SQLite checkpointer
    """
    global _checkpointer, _stack
    
    if _checkpointer is None:
        logger.info("Initializing async SQLite checkpointer...")
        
        # Create AsyncExitStack to manage the context
        _stack = AsyncExitStack()
        
        # Enter the context manager and keep it alive
        conn_manager = AsyncSqliteSaver.from_conn_string("checkpoints.db")
        _checkpointer = await _stack.enter_async_context(conn_manager)
        
        logger.info("✅ Async checkpointer ready")
    
    return _checkpointer

async def close_checkpointer():
    """Close the checkpointer connection and cleanup"""
    global _stack, _checkpointer
    
    if _stack:
        await _stack.aclose()
        _stack = None
        _checkpointer = None
        logger.info("Checkpointer connection closed")
