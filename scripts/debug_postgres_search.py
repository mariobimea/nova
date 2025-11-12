"""
Debug PostgreSQL documentation search.

This script simulates what the AI would search for and shows what docs it finds.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.ai.vector_store import VectorStore

# Initialize vector store
vector_store = VectorStore()

print("=" * 80)
print("TESTING POSTGRESQL DOCUMENTATION SEARCH")
print("=" * 80)

# Queries the AI might use
test_queries = [
    "INSERT INTO database PostgreSQL",
    "save to database PostgreSQL INSERT",
    "INSERT RETURNING PostgreSQL",
    "get inserted ID PostgreSQL",
    "capture ID after INSERT PostgreSQL",
]

for query in test_queries:
    print(f"\n{'=' * 80}")
    print(f"Query: '{query}'")
    print("=" * 80)

    results = vector_store.query(
        query_text=query,
        top_k=3,
        filter_source="postgres"
    )

    if not results:
        print("❌ NO RESULTS FOUND")
        continue

    for i, result in enumerate(results, 1):
        text = result.get("text", "")
        distance = result.get("distance", 0)
        relevance = 1.0 - distance

        print(f"\n[Result {i}] Relevance: {relevance:.2f}")
        print("-" * 80)
        print(text[:800])  # Show more than the 500 char limit
        print("-" * 80)

        # Check if it contains RETURNING info
        has_returning = "RETURNING" in text
        has_fetchone = "fetchone" in text
        has_inserted_id = "inserted_id" in text

        print(f"✓ Contains RETURNING: {has_returning}")
        print(f"✓ Contains fetchone: {has_fetchone}")
        print(f"✓ Contains inserted_id: {has_inserted_id}")

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)
