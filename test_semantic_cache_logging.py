#!/usr/bin/env python3
"""
Test script to verify semantic cache search logging in Chain of Work.

This script executes a simple workflow and checks that semantic cache metadata
is properly recorded in the Chain of Work.
"""

import asyncio
import json
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from models import Base, Workflow, Execution, ChainOfWork
from core.graph_engine import GraphEngine


async def test_semantic_cache_logging():
    """Test semantic cache logging in Chain of Work."""

    # Setup database
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/nova')
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Create simple test workflow with CachedExecutor
        workflow_def = {
            "name": "Test Semantic Cache Logging",
            "description": "Test workflow to verify semantic cache search is logged",
            "executor_type": "cached",  # Use CachedExecutor
            "nodes": [
                {
                    "id": "start",
                    "type": "start"
                },
                {
                    "id": "test_node",
                    "type": "action",
                    "description": "Extract text from PDF file",  # This should trigger semantic cache search
                    "action": "Extract text from the PDF file and return it as plain text"
                },
                {
                    "id": "end",
                    "type": "end"
                }
            ],
            "edges": [
                {"from": "start", "to": "test_node"},
                {"from": "test_node", "to": "end"}
            ]
        }

        # Create workflow in DB
        workflow = Workflow(
            name=workflow_def['name'],
            description=workflow_def['description'],
            definition=workflow_def,
            executor_type='cached'
        )
        db.add(workflow)
        db.commit()
        db.refresh(workflow)

        print(f"✓ Created workflow: {workflow.name} (ID: {workflow.id})")

        # Create initial context with PDF data
        initial_context = {
            "pdf_data": "base64_encoded_pdf_content_here...",
            "client_id": 123
        }

        print(f"\n🚀 Executing workflow with initial context: {list(initial_context.keys())}")

        # Execute workflow
        engine = GraphEngine(db_session=db)

        try:
            result = await engine.execute_workflow(
                workflow_id=workflow.id,
                initial_context=initial_context
            )

            print(f"\n✅ Workflow execution completed!")
            print(f"   Status: {result['status']}")
            print(f"   Execution ID: {result['execution_id']}")

            # Fetch Chain of Work entries
            execution_id = result['execution_id']
            chain_entries = db.query(ChainOfWork).filter(
                ChainOfWork.execution_id == execution_id
            ).all()

            print(f"\n📊 Chain of Work Analysis:")
            print(f"   Total entries: {len(chain_entries)}")

            # Look for semantic cache metadata
            found_semantic_metadata = False

            for entry in chain_entries:
                if entry.node_id == "test_node":
                    print(f"\n📝 Node: {entry.node_id}")
                    print(f"   Type: {entry.node_type}")
                    print(f"   Status: {entry.status}")

                    if entry.ai_metadata:
                        ai_meta = entry.ai_metadata

                        # Check for semantic cache search metadata
                        if 'semantic_cache_search' in ai_meta:
                            found_semantic_metadata = True
                            sem_cache = ai_meta['semantic_cache_search']

                            print(f"\n   🔍 Semantic Cache Search:")
                            print(f"      Query (truncated): {sem_cache.get('query', '')[:100]}...")
                            print(f"      Threshold: {sem_cache.get('threshold')}")
                            print(f"      Available keys: {sem_cache.get('available_keys')}")
                            print(f"      Search time: {sem_cache.get('search_time_ms')}ms")
                            print(f"      Results found: {len(sem_cache.get('results', []))}")
                            print(f"      Cache hit: {sem_cache.get('cache_hit')}")

                            if sem_cache.get('fallback_reason'):
                                print(f"      Fallback reason: {sem_cache.get('fallback_reason')}")

                            if 'selected_match' in sem_cache:
                                match = sem_cache['selected_match']
                                print(f"\n      ✨ Selected Match:")
                                print(f"         Score: {match.get('score')}")
                                print(f"         Action: {match.get('node_action')}")
                                print(f"         Key validation: {match.get('key_validation')}")
                                print(f"         Output validation: {match.get('output_validation')}")

                            # Print full metadata as JSON (formatted)
                            print(f"\n   📄 Full semantic_cache_search metadata:")
                            print(json.dumps(sem_cache, indent=6, default=str))
                        else:
                            print(f"\n   ⚠️  No semantic_cache_search in ai_metadata")
                            print(f"   Available keys: {list(ai_meta.keys())}")
                    else:
                        print(f"\n   ⚠️  No ai_metadata in Chain of Work entry")

            if found_semantic_metadata:
                print(f"\n✅ SUCCESS: Semantic cache metadata was properly logged!")
            else:
                print(f"\n❌ FAILED: No semantic cache metadata found in Chain of Work")

        except Exception as e:
            print(f"\n❌ Workflow execution failed: {e}")
            import traceback
            traceback.print_exc()

    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 80)
    print("Testing Semantic Cache Logging in Chain of Work")
    print("=" * 80)
    print()

    # Check required env vars
    required_vars = ['OPENAI_API_KEY', 'E2B_API_KEY', 'RAG_SERVICE_URL']
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print(f"⚠️  Missing environment variables: {', '.join(missing_vars)}")
        print(f"   Set these variables before running this test.")
        sys.exit(1)

    # Run test
    asyncio.run(test_semantic_cache_logging())
