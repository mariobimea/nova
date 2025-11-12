"""
Quick test of KnowledgeManager with vector store retrieval.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.core.ai.knowledge_manager import KnowledgeManager

logging.basicConfig(level=logging.INFO)

# Test case
manager = KnowledgeManager(use_vector_store=True)

task = "Extract text from PDF document"
context = {
    "pdf_data": "JVBERi0xLjQK...",  # base64
    "pdf_filename": "invoice.pdf"
}

print("=" * 60)
print("Testing KnowledgeManager with Vector Store")
print("=" * 60)

print(f"\nTask: {task}")
print(f"Context: {list(context.keys())}")

# Detect integrations
integrations = manager.detect_integrations(task, context)
print(f"\nDetected integrations: {integrations}")

# Retrieve docs
docs = manager.retrieve_docs(task, integrations, top_k_per_integration=2)

print(f"\nRetrieved docs length: {len(docs)} chars")
print(f"\nFirst 500 chars of retrieved docs:")
print(docs[:500])
print("...")

print("\n" + "=" * 60)
print("✓ Test completed successfully!")
print("=" * 60)
