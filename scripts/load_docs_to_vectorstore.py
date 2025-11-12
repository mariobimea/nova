"""
Script to load all documentation into Chroma vector store.

Loads:
- Existing integration docs (/knowledge/integrations/*.md)
- Official PyMuPDF docs (/knowledge/official_docs/pymupdf_official.md)
- Official EasyOCR docs (/knowledge/official_docs/easyocr_official.md)

Run once to initialize the vector store, or re-run to refresh after doc updates.
"""

import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.ai.vector_store import VectorStore
from src.core.ai.document_loader import DocumentLoader

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Load all documentation into vector store."""

    logger.info("=" * 60)
    logger.info("NOVA Documentation Loader")
    logger.info("=" * 60)

    # Initialize components
    logger.info("\n1. Initializing vector store and document loader...")
    store = VectorStore()
    loader = DocumentLoader(chunk_size=700, chunk_overlap=100)

    # Get current stats
    stats_before = store.get_stats()
    logger.info(f"   Current vector store size: {stats_before['total_documents']} documents")

    # Ask if user wants to clear existing docs (skip if AUTO_CONFIRM=true for Railway)
    import os
    auto_confirm = os.environ.get('AUTO_CONFIRM', 'false').lower() == 'true'

    if stats_before['total_documents'] > 0:
        if auto_confirm:
            # Railway mode: always clear and reload
            logger.info("   AUTO_CONFIRM=true: Clearing and reloading vector store...")
            store.clear()
            logger.info("   ✓ Vector store cleared")
        else:
            # Interactive mode: ask user
            logger.warning(f"\n   Vector store already contains {stats_before['total_documents']} documents")
            response = input("   Clear existing docs and reload? (y/n): ").strip().lower()
            if response == 'y':
                logger.info("   Clearing vector store...")
                store.clear()
                logger.info("   ✓ Vector store cleared")

    all_chunks = []

    # 2. Load integration docs (existing .md files)
    logger.info("\n2. Loading integration docs from /knowledge/integrations/...")
    integration_chunks = loader.load_integration_docs()
    all_chunks.extend(integration_chunks)
    logger.info(f"   ✓ Loaded {len(integration_chunks)} chunks from integration docs")

    # 3. Load official PyMuPDF docs
    logger.info("\n3. Loading official PyMuPDF documentation...")
    base_dir = Path(__file__).parent.parent
    pymupdf_path = base_dir / "knowledge" / "official_docs" / "pymupdf_official.md"

    if pymupdf_path.exists():
        pymupdf_chunks = loader.load_markdown_file(
            file_path=str(pymupdf_path),
            source="pymupdf",
            topic="official"
        )
        all_chunks.extend(pymupdf_chunks)
        logger.info(f"   ✓ Loaded {len(pymupdf_chunks)} chunks from PyMuPDF official docs")
    else:
        logger.warning(f"   ⚠ PyMuPDF official docs not found at {pymupdf_path}")

    # 4. Load official EasyOCR docs
    logger.info("\n4. Loading official EasyOCR documentation...")
    easyocr_path = base_dir / "knowledge" / "official_docs" / "easyocr_official.md"

    if easyocr_path.exists():
        easyocr_chunks = loader.load_markdown_file(
            file_path=str(easyocr_path),
            source="easyocr",
            topic="official"
        )
        all_chunks.extend(easyocr_chunks)
        logger.info(f"   ✓ Loaded {len(easyocr_chunks)} chunks from EasyOCR official docs")
    else:
        logger.warning(f"   ⚠ EasyOCR official docs not found at {easyocr_path}")

    # 5. Add all chunks to vector store
    logger.info(f"\n5. Adding {len(all_chunks)} total chunks to vector store...")
    count_added = store.add_documents(all_chunks)
    logger.info(f"   ✓ Successfully added {count_added} chunks")

    # 6. Show final stats
    stats_after = store.get_stats()
    logger.info("\n6. Final statistics:")
    logger.info(f"   Total documents: {stats_after['total_documents']}")
    logger.info(f"   Sources: {', '.join(stats_after['sources'])}")
    logger.info(f"   Topics: {', '.join(stats_after['topics'])}")

    # 7. Test query
    logger.info("\n7. Testing retrieval...")
    test_query = "how to open PDF from bytes"
    results = store.query(test_query, top_k=3)

    logger.info(f"   Query: '{test_query}'")
    logger.info(f"   Results ({len(results)}):")
    for i, doc in enumerate(results, 1):
        logger.info(f"   {i}. [{doc['source']}] {doc['text'][:100]}...")

    logger.info("\n" + "=" * 60)
    logger.info("✓ Documentation loaded successfully!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
