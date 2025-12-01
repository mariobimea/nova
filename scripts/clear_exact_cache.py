#!/usr/bin/env python3
"""
Clear exact code cache (PostgreSQL)

Deletes all entries from the code_cache table.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import get_db
from src.models.code_cache import CodeCache


def main():
    """Clear exact code cache."""
    print("🗑️  Clearing exact code cache (PostgreSQL)...")

    # Get database session using context manager
    with get_db() as db:
        try:
            # Count before
            count_before = db.query(CodeCache).count()
            print(f"   Códigos en caché: {count_before}")

            # Delete all
            if count_before > 0:
                db.query(CodeCache).delete()
                db.commit()
                print(f"✓  {count_before} códigos eliminados")
            else:
                print("✓  Caché ya estaba vacía")

            # Verify
            count_after = db.query(CodeCache).count()
            print(f"   Códigos después: {count_after}")

        except Exception as e:
            print(f"❌ Error: {e}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
