"""
Async SQLite checkpointer for LangGraph agent persistence with Chainlit.
"""
import logging
import sqlite3
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from contextlib import AsyncExitStack
from datetime import datetime
from typing import List, Dict, Optional

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

async def get_all_conversations() -> List[Dict]:
    """Get all unique conversation threads with metadata"""
    conn = sqlite3.connect("checkpoints.db")
    cursor = conn.cursor()
    
    try:
        # Check if checkpoints table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='checkpoints'
        """)
        
        if not cursor.fetchone():
            # Table doesn't exist yet - return empty list
            conn.close()
            return []
        
        # Get unique thread IDs with their latest checkpoint
        query = """
        SELECT 
            thread_id,
            MAX(checkpoint_id) as latest_checkpoint,
            MIN(checkpoint_id) as first_checkpoint,
            COUNT(*) as checkpoint_count
        FROM checkpoints
        GROUP BY thread_id
        ORDER BY latest_checkpoint DESC
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        conn.close()
        
        conversations = []
        for row in results:
            thread_id, latest, first, count = row
            conversations.append({
                "thread_id": thread_id,
                "latest_checkpoint": latest,
                "first_checkpoint": first,
                "checkpoint_count": count,
            })
        
        return conversations
    
    except Exception as e:
        logger.error(f"Error getting conversations: {e}")
        conn.close()
        return []


async def delete_conversation(thread_id: str):
    """Delete a conversation from the database"""
    conn = sqlite3.connect("checkpoints.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
    cursor.execute("DELETE FROM writes WHERE thread_id = ?", (thread_id,))
    conn.commit()
    conn.close()

def initialize_metadata_table():
    """Create conversation_metadata table if it doesn't exist"""
    conn = sqlite3.connect("checkpoints.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_metadata (
            thread_id TEXT PRIMARY KEY,
            title TEXT,
            created_at TEXT,
            last_updated TEXT
        )
    """)
    
    conn.commit()
    conn.close()

async def save_conversation_title(thread_id: str, title: str):
    """Save or update conversation title"""
    conn = sqlite3.connect("checkpoints.db")
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    
    # Insert or update title
    cursor.execute("""
        INSERT INTO conversation_metadata (thread_id, title, created_at, last_updated)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(thread_id) DO UPDATE SET
            title = excluded.title,
            last_updated = excluded.last_updated
    """, (thread_id, title, now, now))
    
    conn.commit()
    conn.close()

async def get_conversation_title(thread_id: str) -> str:
    """Get conversation title from metadata or generate from first message"""
    conn = sqlite3.connect("checkpoints.db")
    cursor = conn.cursor()
    
    # Try to get from metadata table
    cursor.execute(
        "SELECT title FROM conversation_metadata WHERE thread_id = ?",
        (thread_id,)
    )
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0]:
        return result[0]
    
    # Fall back to extracting from checkpoints
    try:
        checkpointer = await get_checkpointer()
        config = {"configurable": {"thread_id": thread_id}}
        state = await checkpointer.aget_tuple(config)
        
        if state and state.checkpoint:
            channel_values = state.checkpoint.get("channel_values", {})
            messages = channel_values.get("messages", [])
            
            # Find first user message
            for msg in messages:
                if hasattr(msg, 'type') and msg.type == 'user':
                    title = msg.content[:50]
                    if len(msg.content) > 50:
                        title += "..."
                    
                    # Save it for next time
                    await save_conversation_title(thread_id, title)
                    return title
        
        return f"Conversation {thread_id[:8]}..."
    except Exception as e:
        return f"Conversation {thread_id[:8]}..."
