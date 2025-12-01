#!/usr/bin/env python3
"""
Clear ALL caches (exact + semantic)

Deletes all entries from:
- Exact cache (PostgreSQL code_cache table)
- Semantic cache (ChromaDB via RAG service)
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import get_db
from src.models.code_cache import CodeCache
import os
import requests


def clear_exact_cache():
    """Clear exact code cache (PostgreSQL)."""
    print("\n🗑️  [1/2] Clearing EXACT cache (PostgreSQL)...")

    with get_db() as db:
        try:
            count_before = db.query(CodeCache).count()
            print(f"   Códigos en caché: {count_before}")

            if count_before > 0:
                db.query(CodeCache).delete()
                db.commit()
                print(f"   ✓ {count_before} códigos eliminados")
            else:
                print("   ✓ Caché ya estaba vacía")

            return True

        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False


def clear_semantic_cache():
    """Clear semantic code cache (ChromaDB)."""
    print("\n🗑️  [2/2] Clearing SEMANTIC cache (ChromaDB via RAG service)...")

    rag_url = os.getenv("RAG_SERVICE_URL")
    if not rag_url:
        print("   ⚠️  RAG_SERVICE_URL not configured. Skipping semantic cache.")
        return True  # Not an error, just skip

    try:
        response = requests.post(
            f"{rag_url}/code/clear",
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            deleted_count = data.get("codes_deleted", 0)
            print(f"   ✓ {deleted_count} códigos eliminados")
            return True
        elif response.status_code == 404:
            print("   ⚠️  Endpoint no disponible. Reinicia nova-rag para limpiar.")
            return True  # Not critical
        else:
            print(f"   ❌ Error: HTTP {response.status_code}")
            return False

    except Exception as e:
        print(f"   ⚠️  Error (no crítico): {e}")
        print("   💡 Tip: Reinicia nova-rag para limpiar el cache")
        return True  # Not critical


def main():
    """Clear all caches."""
    print("=" * 60)
    print("🧹 CLEARING ALL CACHES")
    print("=" * 60)

    success_exact = clear_exact_cache()
    success_semantic = clear_semantic_cache()

    print("\n" + "=" * 60)
    if success_exact and success_semantic:
        print("✅ ALL CACHES CLEARED SUCCESSFULLY")
    elif success_exact:
        print("⚠️  EXACT CACHE CLEARED (semantic cache skipped/failed)")
    else:
        print("❌ CACHE CLEAR FAILED")
    print("=" * 60 + "\n")

    return 0 if success_exact else 1


if __name__ == "__main__":
    sys.exit(main())
