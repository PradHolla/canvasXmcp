import logging
import os
import json
import boto3
from contextlib import asynccontextmanager
from typing import List, Dict, Optional
from datetime import datetime

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

# Global pool
_pool = None

def get_db_connection_string():
    """
    Get DB connection string from AWS Secrets Manager (Prod) or .env (Local)
    """
    # 1. Try local .env first
    if os.getenv("CANVASDB_SECRET") is None:
        return os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/canvas_db")
    
    # 2. Fetch from AWS Secrets Manager
    secret_arn = os.getenv("CANVASDB_SECRET")
    try:
        client = boto3.client('secretsmanager', region_name=os.getenv("AWS_REGION", "us-east-1"))
        response = client.get_secret_value(SecretId=secret_arn)
        secret = json.loads(response['SecretString'])
        
        return f"postgresql://{secret['username']}:{secret['password']}@{secret['host']}:{secret['port']}/{secret['dbname']}"
    except Exception as e:
        logger.error(f"Failed to fetch DB secret: {e}")
        raise e

async def get_checkpointer():
    global _pool
    
    if _pool is None:
        conn_string = get_db_connection_string()
        _pool = AsyncConnectionPool(conn_string=conn_string, max_size=10)
        await _pool.open()
        
    # Create the checkpointer with the pool
    checkpointer = AsyncPostgresSaver(_pool)
    
    # Ensure tables exist (run this once)
    await checkpointer.setup()
    
    return checkpointer

async def close_checkpointer():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None

# --- Helper to Execute Raw SQL (for Metadata) ---
async def execute_query(query: str, params: tuple = None, fetch: str = "all"):
    global _pool
    if not _pool:
        await get_checkpointer() # Init pool
        
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            if fetch == "all":
                return await cur.fetchall()
            elif fetch == "one":
                return await cur.fetchone()
            return None

# --- Re-implement your helpers using Postgres SQL syntax ---

async def get_all_conversations() -> List[Dict]:
    # Note: langgraph-postgres stores checkpoints in a 'checkpoints' table
    # Schema varies slightly, but thread_id is key.
    query = """
    SELECT thread_id, 
           MAX(checkpoint_id) as latest_checkpoint
    FROM checkpoints 
    GROUP BY thread_id 
    ORDER BY latest_checkpoint DESC
    """
    try:
        rows = await execute_query(query)
        return [{"thread_id": r[0]} for r in rows]
    except Exception as e:
        logger.error(f"Error listing threads: {e}")
        return []

async def save_conversation_title(thread_id: str, title: str):
    # You need to create this table manually or via migration script
    # For now, let's create it if missing
    await execute_query("""
        CREATE TABLE IF NOT EXISTS conversation_metadata (
            thread_id TEXT PRIMARY KEY,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """, fetch="none")
    
    await execute_query("""
        INSERT INTO conversation_metadata (thread_id, title)
        VALUES (%s, %s)
        ON CONFLICT (thread_id) DO NOTHING;
    """, (thread_id, title), fetch="none")

async def get_conversation_title(thread_id: str) -> str:
    row = await execute_query("SELECT title FROM conversation_metadata WHERE thread_id = %s", (thread_id,), fetch="one")
    if row:
        return row[0]
    return f"Thread {thread_id[:8]}"

async def delete_conversation(thread_id: str):
    await execute_query("DELETE FROM checkpoints WHERE thread_id = %s", (thread_id,), fetch="none")
    await execute_query("DELETE FROM conversation_metadata WHERE thread_id = %s", (thread_id,), fetch="none")
