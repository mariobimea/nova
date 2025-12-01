#!/usr/bin/env python3
"""
Clear semantic code cache (ChromaDB via RAG service)

Deletes all code entries from the semantic cache.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.rag_client import RAGClient
import os


def main():
    """Clear semantic code cache."""
    print("🗑️  Clearing semantic code cache (ChromaDB via RAG service)...")

    # Check if RAG service is configured
    rag_url = os.getenv("RAG_SERVICE_URL")
    if not rag_url:
        print("❌ RAG_SERVICE_URL not configured. Cannot clear semantic cache.")
        return 1

    try:
        # Create RAG client
        rag_client = RAGClient(base_url=rag_url)

        # Clear cache using RAG service endpoint
        import requests
        response = requests.post(
            f"{rag_url}/code/clear",
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            deleted_count = data.get("codes_deleted", 0)
            print(f"✓  {deleted_count} códigos eliminados del semantic cache")
        elif response.status_code == 404:
            print("⚠️  El endpoint de clear no está disponible en el RAG service")
            print("   Alternativa: reinicia el servicio nova-rag para limpiar el cache")
            return 1
        else:
            print(f"❌ Error al limpiar cache: HTTP {response.status_code}")
            print(f"   Response: {response.text}")
            return 1

    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nAlternativa: reinicia el servicio nova-rag para limpiar el cache")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
