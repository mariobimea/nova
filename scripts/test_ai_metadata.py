"""
Test AI metadata storage - verify tool calling info is saved correctly.

This script:
1. Creates a simple task that requires documentation search
2. Runs CachedExecutor
3. Inspects the returned AI metadata
4. Verifies all debugging fields are present
"""

import asyncio
import logging
import sys
import json
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


async def test_metadata():
    """Test that AI metadata includes all tool calling details."""

    logger.info("=" * 70)
    logger.info("TEST: AI Metadata Storage")
    logger.info("=" * 70)

    # Initialize executor
    executor = CachedExecutor()

    # Simple task that will trigger doc search
    task = "Extract text from the PDF using the recommended extraction method"

    # Context with PDF data
    context = {
        "pdf_data": "JVBERi0xLjQKJeLjz9MK...",  # Truncated for brevity
        "recommended_extraction_method": "ocr",  # Force OCR
        "pdf_filename": "test.pdf"
    }

    try:
        logger.info("\n🚀 Starting execution...")
        result = await executor.execute(
            code=task,
            context=context,
            timeout=60
        )

        logger.info("\n✅ EXECUTION SUCCESS!")

        # Extract AI metadata
        if "_ai_metadata" in result:
            metadata = result["_ai_metadata"]

            logger.info("\n" + "=" * 70)
            logger.info("📊 AI METADATA INSPECTION")
            logger.info("=" * 70)

            # Check basic fields
            logger.info(f"\nBasic Info:")
            logger.info(f"  Model: {metadata.get('model')}")
            logger.info(f"  Prompt: {metadata.get('prompt_task', '')[:100]}...")
            logger.info(f"  Code Length: {metadata.get('code_length')} chars")
            logger.info(f"  Attempts: {metadata.get('attempts')}")

            # Check timing
            logger.info(f"\nTiming:")
            logger.info(f"  Generation: {metadata.get('generation_time_ms')}ms")
            logger.info(f"  Execution: {metadata.get('execution_time_ms')}ms")
            logger.info(f"  Total: {metadata.get('total_time_ms')}ms")

            # Check cost
            logger.info(f"\nCost (estimated):")
            logger.info(f"  Input tokens: {metadata.get('tokens_input_estimated')}")
            logger.info(f"  Output tokens: {metadata.get('tokens_output_estimated')}")
            logger.info(f"  Cost: ${metadata.get('cost_usd_estimated'):.6f}")

            # ===== NEW FIELDS FOR DEBUGGING =====
            logger.info(f"\n🔍 Tool Calling Details:")
            logger.info(f"  Enabled: {metadata.get('tool_calling_enabled')}")
            logger.info(f"  Retrieval Method: {metadata.get('retrieval_method')}")
            logger.info(f"  Tool Iterations: {metadata.get('tool_iterations')}")
            logger.info(f"  Total Tool Calls: {metadata.get('total_tool_calls')}")

            # Show each tool call
            tool_calls = metadata.get('tool_calls', [])
            if tool_calls:
                logger.info(f"\n  Tool Calls Made ({len(tool_calls)}):")
                for i, tc in enumerate(tool_calls, 1):
                    logger.info(f"    {i}. Iteration {tc.get('iteration')}:")
                    logger.info(f"       Function: {tc.get('function')}")
                    logger.info(f"       Arguments: {tc.get('arguments')}")

                    # Show preview of documentation found
                    if 'result_preview' in tc:
                        preview = tc['result_preview']
                        logger.info(f"       Documentation Preview:")
                        logger.info(f"         {preview[:200]}...")
            else:
                logger.info("  ⚠️  No tool calls found!")

            # Show context summary
            context_summary = metadata.get('context_summary', '')
            if context_summary:
                logger.info(f"\n  Context Summary Sent to AI:")
                logger.info(f"    {context_summary[:300]}...")
            else:
                logger.info("  ⚠️  No context summary found!")

            # Show generated code
            logger.info(f"\n📝 Generated Code:")
            logger.info("=" * 70)
            logger.info(metadata.get('generated_code', 'No code found'))
            logger.info("=" * 70)

            # Verification
            logger.info(f"\n✅ VERIFICATION:")
            checks = {
                "tool_calls field exists": "tool_calls" in metadata,
                "tool_iterations field exists": "tool_iterations" in metadata,
                "total_tool_calls field exists": "total_tool_calls" in metadata,
                "context_summary field exists": "context_summary" in metadata,
                "At least one tool call made": len(metadata.get("tool_calls", [])) > 0
            }

            all_passed = True
            for check, passed in checks.items():
                status = "✅" if passed else "❌"
                logger.info(f"  {status} {check}")
                if not passed:
                    all_passed = False

            if all_passed:
                logger.info(f"\n🎉 All metadata fields present and correct!")
                return True
            else:
                logger.error(f"\n❌ Some metadata fields missing!")
                return False

        else:
            logger.error(f"\n❌ No _ai_metadata in result!")
            return False

    except Exception as e:
        logger.error(f"\n❌ EXECUTION FAILED: {e}")
        logger.exception("Full traceback:")
        return False


async def main():
    """Run metadata test."""

    success = await test_metadata()

    logger.info("\n" + "=" * 70)
    if success:
        logger.info("✅ METADATA TEST PASSED")
    else:
        logger.info("❌ METADATA TEST FAILED")
    logger.info("=" * 70)

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
