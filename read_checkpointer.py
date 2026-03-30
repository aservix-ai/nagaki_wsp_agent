import os
import sys
import argparse
import asyncio
import json
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional, Dict, Any

# Add src to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
import psycopg

load_dotenv()

def get_connection_string():
    conn_string = os.getenv("POSTGRES_CONNECTION_STRING")
    if not conn_string:
        print("Error: POSTGRES_CONNECTION_STRING not found in environment variables.")
        sys.exit(1)
    return conn_string

def list_threads(conn_string: str, limit: int = 20):
    """List recent thread IDs directly from the database."""
    print(f"\nListing top {limit} most recent threads...")
    
    try:
        with psycopg.connect(conn_string) as conn:
            with conn.cursor() as cur:
                # Assuming standard langgraph schema where thread_id is in metadata or config
                # The schema for PostgresSaver usually has columns: thread_id, checkpoint_id, parent_checkpoint_id, checkpoint, metadata
                
                # Check table structure if needed, but standard is 'checkpoints'
                cur.execute("""
                    SELECT DISTINCT thread_id 
                    FROM checkpoints 
                    ORDER BY thread_id DESC 
                    LIMIT %s
                """, (limit,))
                
                threads = cur.fetchall()
                
                if not threads:
                    print("No threads found in 'checkpoints' table.")
                    return

                print(f"{'Thread ID':<40} | {'Last Checkpoint ID'}")
                print("-" * 60)
                
                for thread in threads:
                    thread_id = thread[0]
                    # Get last checkpoint for this thread to show context
                    cur.execute("""
                        SELECT checkpoint_id, checkpoint, metadata 
                        FROM checkpoints 
                        WHERE thread_id = %s 
                        ORDER BY checkpoint_id DESC 
                        LIMIT 1
                    """, (thread_id,))
                    last_cp = cur.fetchone()
                    cp_id = last_cp[0] if last_cp else "N/A"
                    print(f"{thread_id:<40} | {cp_id}")

    except Exception as e:
        print(f"Error listing threads: {e}")
        # Fallback to inspecting table schema if query failed
        print("Tip: Ensure the table 'checkpoints' exists and has a 'thread_id' column.")

def inspect_thread(conn_string: str, thread_id: str):
    """Inspect state for a specific thread using PostgresSaver."""
    print(f"\nInspecting thread: {thread_id}")
    
    # Use PostgresSaver to inspect
    try:
        saver = PostgresSaver.from_conn_string(conn_string)
        
        # We use a context manager as required by the implementation
        with saver as checkpointer:
            config = {"configurable": {"thread_id": thread_id}}
            
            # Get latest checkpoint
            checkpoint_tuple = checkpointer.get_tuple(config)
            
            if not checkpoint_tuple:
                print(f"No checkpoint found for thread_id: {thread_id}")
                return

            print("\n=== LATEST CHECKPOINT STATE ===")
            
            # Handle different versions of LangGraph return values
            if len(checkpoint_tuple) >= 4:
                config = checkpoint_tuple[0]
                checkpoint = checkpoint_tuple[1]
                metadata = checkpoint_tuple[2]
                parent_config = checkpoint_tuple[3]
                # Ignore extra values if any
            else:
                print(f"Unexpected tuple length: {len(checkpoint_tuple)}")
                print(checkpoint_tuple)
                return

            print(f"Checkpoint ID: {checkpoint.get('id')}")
            print(f"Metadata: {json.dumps(metadata, indent=2, default=str)}")
            
            print("\n--- Channel Values ---")
            for channel, value in checkpoint.get("channel_values", {}).items():
                print(f"\n[{channel}]:")
                if isinstance(value, list) and len(value) > 0:
                    # Likely messages
                    for item in value:
                        print(f"  - {item}")
                elif isinstance(value, dict):
                    print(json.dumps(value, indent=2, default=str))
                else:
                    print(f"  {value}")

            # List history
            print("\n=== HISTORY (Last 5 checkpoints) ===")
            # list() returns an iterator of CheckpointTuple
            # format: list(config, limit=None, before=None)
            history = list(checkpointer.list(config, limit=5))
            
            for i, cp_tuple in enumerate(history):
                if len(cp_tuple) >= 4:
                    c_checkpoint = cp_tuple[1]
                    c_metadata = cp_tuple[2]
                else:
                    c_checkpoint = {}
                    c_metadata = {}
                    
                print(f"\n{i+1}. ID: {c_checkpoint.get('id')} | Time: {c_metadata.get('ts') if c_metadata else 'N/A'}")
                # print(f"   Step: {c_metadata.get('step')}")

    except Exception as e:
        print(f"Error inspecting thread: {e}")
        import traceback
        traceback.print_exc()

def delete_thread(conn_string: str, thread_id: str, force: bool = False):
    """Delete all checkpoint data for a specific thread_id."""
    print(f"\nPreparing deletion for thread_id: {thread_id}")

    if not force:
        confirmation = input(
            "This will permanently delete checkpoint data for this thread. Type 'DELETE' to continue: "
        ).strip()
        if confirmation != "DELETE":
            print("Deletion canceled.")
            return

    # Order matters to avoid FK issues in deployments without cascading deletes.
    table_order = ["checkpoint_writes", "checkpoint_blobs", "checkpoints"]

    try:
        with psycopg.connect(conn_string) as conn:
            with conn.cursor() as cur:
                deleted_counts = {}

                for table_name in table_order:
                    cur.execute(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM information_schema.tables
                            WHERE table_schema = 'public'
                              AND table_name = %s
                        )
                        """,
                        (table_name,),
                    )
                    exists = cur.fetchone()[0]
                    if not exists:
                        deleted_counts[table_name] = 0
                        continue

                    cur.execute(
                        f"DELETE FROM {table_name} WHERE thread_id = %s",
                        (thread_id,),
                    )
                    deleted_counts[table_name] = cur.rowcount

            conn.commit()

        total_deleted = sum(deleted_counts.values())
        print("Deletion complete.")
        for table_name in table_order:
            print(f"  - {table_name}: {deleted_counts.get(table_name, 0)} rows deleted")
        print(f"Total rows deleted: {total_deleted}")

    except Exception as e:
        print(f"Error deleting thread data: {e}")
        import traceback
        traceback.print_exc()

def main():
    parser = argparse.ArgumentParser(description="Read LangGraph database checkpoints")
    parser.add_argument("--thread", "-t", type=str, help="Thread ID to inspect")
    parser.add_argument("--list", "-l", action="store_true", help="List recent threads")
    parser.add_argument("--limit", type=int, default=20, help="Limit for listing threads")
    parser.add_argument("--delete-thread", "-d", type=str, help="Thread ID to delete from checkpointer tables")
    parser.add_argument("--yes", action="store_true", help="Skip delete confirmation prompt")
    
    args = parser.parse_args()
    
    conn_string = get_connection_string()
    
    if args.delete_thread:
        delete_thread(conn_string, args.delete_thread, force=args.yes)
    elif args.thread:
        inspect_thread(conn_string, args.thread)
    else:
        # Default behavior: list threads
        list_threads(conn_string, args.limit)
        print("\nTo inspect a specific thread, run:")
        print("  python read_checkpointer.py --thread <thread_id>")
        print("\nTo delete a specific thread, run:")
        print("  python read_checkpointer.py --delete-thread <thread_id>")

if __name__ == "__main__":
    main()
