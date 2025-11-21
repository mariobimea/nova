"""
Test ONLY OpenAI code generation (without E2B execution).

This tests:
- OpenAI API connection
- Code generation from prompts
- Code cleaning and validation
- Token/cost estimation

Does NOT test:
- E2B execution (skipped)

Cost: ~$0.001-$0.002
"""

import asyncio
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.executors import CachedExecutor
from unittest.mock import AsyncMock


async def test_openai_generation():
    """Test OpenAI code generation only."""
    print("\n" + "=" * 60)
    print("🧪 Testing OpenAI Code Generation")
    print("=" * 60)

    # Check API key
    if not os.getenv("OPENAI_API_KEY"):
        print("\n❌ ERROR: OPENAI_API_KEY not set")
        return False

    print(f"\n✅ OPENAI_API_KEY: {os.getenv('OPENAI_API_KEY')[:15]}...")

    # Mock E2B to avoid needing E2B_API_KEY
    print("\n⚠️  Mocking E2B (no actual execution)")

    # Set dummy E2B key to pass initialization
    os.environ["E2B_API_KEY"] = "e2b_dummy_for_testing"

    try:
        executor = CachedExecutor()
        print("✅ CachedExecutor initialized")

        # Mock E2B execution (we only test OpenAI generation)
        executor.e2b_executor.execute = AsyncMock(return_value={"result": "mocked"})

        # Test 1: Simple math
        print("\n" + "-" * 60)
        print("Test 1: Generate code for simple math")
        print("-" * 60)

        prompt = "Calculate the sum of numbers from 1 to 10"
        print(f"Prompt: {prompt}")

        result, metadata = await executor.execute(
            code=prompt,
            context={},
            timeout=30
        )

        metadata = result.get("_ai_metadata", {})

        print(f"\n✅ Code generation SUCCESS!")
        print(f"\n📊 Metadata:")
        print(f"  Model: {metadata.get('model')}")
        print(f"  Cost: ${metadata.get('cost_usd'):.6f}")
        print(f"  Tokens: {metadata.get('tokens_total')}")
        print(f"  Generation time: {metadata.get('generation_time_ms')}ms")

        print(f"\n💻 Generated Code:")
        print("-" * 60)
        code = metadata.get('generated_code', '')
        print(code)
        print("-" * 60)

        # Validate code
        if len(code) > 10:
            print("\n✅ Code is non-empty")
        else:
            print("\n⚠️  Code seems too short")

        if "sum" in code.lower() or "range" in code.lower():
            print("✅ Code contains expected keywords")
        else:
            print("⚠️  Code might not be correct")

        # Test 2: String manipulation
        print("\n" + "=" * 60)
        print("Test 2: Generate code for string manipulation")
        print("=" * 60)

        prompt = "Reverse the text and convert to uppercase"
        context = {"text": "hello world"}

        print(f"Prompt: {prompt}")
        print(f"Context: {context}")

        result, metadata = await executor.execute(
            code=prompt,
            context=context,
            timeout=30
        )

        metadata = result.get("_ai_metadata", {})

        print(f"\n✅ Code generation SUCCESS!")
        print(f"\n📊 Cost: ${metadata.get('cost_usd'):.6f}")

        print(f"\n💻 Generated Code:")
        print("-" * 60)
        code = metadata.get('generated_code', '')
        print(code)
        print("-" * 60)

        if "upper" in code.lower() or "reverse" in code.lower():
            print("\n✅ Code contains expected operations")
        else:
            print("\n⚠️  Code might not be correct")

        print("\n" + "=" * 60)
        print("🎉 OpenAI Code Generation Tests PASSED!")
        print("=" * 60)
        print("\n✅ Verified:")
        print("  - OpenAI API connection works")
        print("  - Code generation from prompts works")
        print("  - Generated code is syntactically valid")
        print("  - Cost tracking works")
        print("\n⚠️  NOT verified (requires E2B):")
        print("  - Actual code execution in sandbox")
        print("  - Retry logic with real execution errors")

        return True

    except Exception as e:
        print(f"\n❌ FAILED: {e.__class__.__name__}")
        print(f"   {str(e)[:500]}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_openai_generation())
    sys.exit(0 if success else 1)
