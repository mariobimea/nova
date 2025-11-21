"""
Test script for OpenAI Tool Calling with CachedExecutor.

Tests the new dynamic documentation search capability.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.executors import CachedExecutor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s [%(name)s]: %(message)s'
)

logger = logging.getLogger(__name__)


async def test_pdf_extraction():
    """Test PDF text extraction task with tool calling."""

    logger.info("=" * 70)
    logger.info("TEST: PDF Text Extraction with Tool Calling")
    logger.info("=" * 70)

    # Initialize executor
    executor = CachedExecutor()

    # Task: Extract text from PDF
    task = "Extract all text from the PDF document"

    # Context: Fake PDF data (base64)
    context = {
        "pdf_data": "JVBERi0xLjQKJeLjz9MKNSAwIG9iago8PAovVHlwZSAvUGFnZQovUGFyZW50IDEgMCBSCi9NZWRpYUJveCBbIDAgMCA2MTIgNzkyIF0KL0NvbnRlbnRzIDMgMCBSCi9SZXNvdXJjZXMgNCAwIFIKPj4KZW5kb2JqCjQgMCBvYmoKPDwKL1Byb2NTZXQgWyAvUERGIF0KPj4KZW5kb2JqCjMgMCBvYmoKPDwKL0xlbmd0aCAzMQo+PgpzdHJlYW0KQlQKL0YxIDEyIFRmCjEwMCA3MDAgVGQKKEhlbGxvIFdvcmxkISkgVGoKRVQKZW5kc3RyZWFtCmVuZG9iagoxIDAgb2JqCjw8Ci9UeXBlIC9QYWdlcwovS2lkcyBbIDUgMCBSIF0KL0NvdW50IDEKL01lZGlhQm94IFsgMCAwIDYxMiA3OTIgXQo+PgplbmRvYmoKMiAwIG9iago8PAovVHlwZSAvQ2F0YWxvZwovUGFnZXMgMSAwIFIKPj4KZW5kb2JqCnhyZWYKMCA2CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDIzMiAwMDAwMCBuIAowMDAwMDAwMzE1IDAwMDAwIG4gCjAwMDAwMDAxNDEgMDAwMDAgbiAKMDAwMDAwMDExOSAwMDAwMCBuIAowMDAwMDAwMDIxIDAwMDAwIG4gCnRyYWlsZXIKPDwKL1NpemUgNgovUm9vdCAyIDAgUgo+PgpzdGFydHhyZWYKMzY0CiUlRU9GCg=="
    }

    # Execute with tool calling
    try:
        logger.info("\n🚀 Starting execution...")
        result, metadata = await executor.execute(
            code=task,
            context=context,
            timeout=30
        )

        logger.info("\n✅ EXECUTION SUCCESS!")
        logger.info(f"\nResult keys: {list(result.keys())}")

        # Show AI metadata
        if "_ai_metadata" in result:
            metadata = result["_ai_metadata"]
            logger.info("\n📊 AI Metadata:")
            logger.info(f"   Model: {metadata.get('model')}")
            logger.info(f"   Tool calling: {metadata.get('tool_calling_enabled')}")
            logger.info(f"   Retrieval method: {metadata.get('retrieval_method')}")
            logger.info(f"   Generation time: {metadata.get('generation_time_ms')}ms")
            logger.info(f"   Execution time: {metadata.get('execution_time_ms')}ms")
            logger.info(f"   Estimated cost: ${metadata.get('cost_usd_estimated'):.6f}")
            logger.info(f"   Attempts: {metadata.get('attempts')}")

            # Show generated code
            generated_code = metadata.get('generated_code', '')
            logger.info(f"\n📝 Generated Code ({len(generated_code)} chars):")
            logger.info("=" * 70)
            logger.info(generated_code)
            logger.info("=" * 70)

        # Show extracted text if available
        if "pdf_text" in result:
            logger.info(f"\n📄 Extracted Text:")
            logger.info(f"{result['pdf_text']}")

        return True

    except Exception as e:
        logger.error(f"\n❌ EXECUTION FAILED: {e}")
        logger.exception("Full traceback:")
        return False


async def main():
    """Run all tests."""

    # Test 1: PDF extraction
    success = await test_pdf_extraction()

    logger.info("\n" + "=" * 70)
    if success:
        logger.info("✅ ALL TESTS PASSED")
    else:
        logger.info("❌ SOME TESTS FAILED")
    logger.info("=" * 70)

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
