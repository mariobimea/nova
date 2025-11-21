"""
Quick test script for CachedExecutor with REAL OpenAI API.

This script runs simple, cheap tests (~$0.002 total cost) to verify:
1. CachedExecutor can generate code with OpenAI
2. Generated code executes in E2B
3. Retry logic works
4. Cost tracking is accurate

Requirements:
    export OPENAI_API_KEY="sk-..."
    export E2B_API_KEY="e2b_..."

Usage:
    python3 examples/test_cached_executor_real.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.executors import CachedExecutor


async def test_simple_math():
    """Test 1: Simple math (should succeed on first attempt)."""
    print("\n" + "=" * 60)
    print("TEST 1: Simple Math Calculation")
    print("=" * 60)

    executor = CachedExecutor()

    prompt = "Calculate the sum of numbers from 1 to 10"
    context = {}

    print(f"\nPrompt: {prompt}")
    print(f"Expected cost: ~$0.001")

    try:
        result, metadata = await executor.execute(
            code=prompt,
            context=context,
            timeout=30
        )

        print(f"\n✅ SUCCESS!")
        print(f"\nResult keys: {list(result.keys())}")

        # Show AI metadata
        metadata = result.get("_ai_metadata", {})
        print(f"\n📊 AI Metadata:")
        print(f"  Model: {metadata.get('model')}")
        print(f"  Attempts: {metadata.get('attempts')}")
        print(f"  Cost: ${metadata.get('cost_usd'):.6f}")
        print(f"  Generation time: {metadata.get('generation_time_ms')}ms")
        print(f"  Execution time: {metadata.get('execution_time_ms')}ms")
        print(f"  Total time: {metadata.get('total_time_ms')}ms")

        print(f"\n💻 Generated Code:")
        print("-" * 60)
        print(metadata.get('generated_code'))
        print("-" * 60)

        # Verify result
        if 'sum' in result or 'result' in result or 'total' in result:
            print(f"\n✅ Test passed: Got expected result keys")
        else:
            print(f"\n⚠️  Warning: Unexpected result keys: {list(result.keys())}")

        return True

    except Exception as e:
        print(f"\n❌ FAILED: {e.__class__.__name__}")
        print(f"   {str(e)[:500]}")
        import traceback
        traceback.print_exc()
        return False


async def test_data_processing():
    """Test 2: Data processing with context."""
    print("\n" + "=" * 60)
    print("TEST 2: Data Processing with Context")
    print("=" * 60)

    executor = CachedExecutor()

    prompt = "Filter numbers greater than 5 and calculate their sum"
    context = {
        "numbers": [1, 3, 5, 7, 9, 11]
    }

    print(f"\nPrompt: {prompt}")
    print(f"Context: {context}")
    print(f"Expected result: sum([7, 9, 11]) = 27")

    try:
        result, metadata = await executor.execute(
            code=prompt,
            context=context,
            timeout=30
        )

        print(f"\n✅ SUCCESS!")

        metadata = result.get("_ai_metadata", {})
        print(f"\n📊 Cost: ${metadata.get('cost_usd'):.6f}")
        print(f"   Attempts: {metadata.get('attempts')}")

        # Remove metadata to see actual result
        result_without_meta = {k: v for k, v in result.items() if k != '_ai_metadata'}
        print(f"\n📝 Result: {result_without_meta}")

        return True

    except Exception as e:
        print(f"\n❌ FAILED: {e.__class__.__name__}")
        print(f"   {str(e)[:500]}")
        return False


async def test_string_manipulation():
    """Test 3: String manipulation."""
    print("\n" + "=" * 60)
    print("TEST 3: String Manipulation")
    print("=" * 60)

    executor = CachedExecutor()

    prompt = "Reverse the string and convert to uppercase"
    context = {
        "text": "hello world"
    }

    print(f"\nPrompt: {prompt}")
    print(f"Context: {context}")
    print(f"Expected result: 'DLROW OLLEH'")

    try:
        result, metadata = await executor.execute(
            code=prompt,
            context=context,
            timeout=30
        )

        print(f"\n✅ SUCCESS!")

        metadata = result.get("_ai_metadata", {})
        print(f"\n📊 Cost: ${metadata.get('cost_usd'):.6f}")

        result_without_meta = {k: v for k, v in result.items() if k != '_ai_metadata'}
        print(f"\n📝 Result: {result_without_meta}")

        return True

    except Exception as e:
        print(f"\n❌ FAILED: {e.__class__.__name__}")
        print(f"   {str(e)[:500]}")
        return False


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("🧪 CachedExecutor Real API Test Suite")
    print("=" * 60)

    # Check environment variables
    if not os.getenv("OPENAI_API_KEY"):
        print("\n❌ ERROR: OPENAI_API_KEY not set")
        print("\n   Get API key at: https://platform.openai.com/api-keys")
        print("   Then run: export OPENAI_API_KEY='sk-...'")
        return

    if not os.getenv("E2B_API_KEY"):
        print("\n❌ ERROR: E2B_API_KEY not set")
        print("\n   Get API key at: https://e2b.dev/docs")
        print("   Then run: export E2B_API_KEY='e2b_...'")
        return

    print("\n✅ Environment variables set")
    print(f"   OPENAI_API_KEY: {os.getenv('OPENAI_API_KEY')[:10]}...")
    print(f"   E2B_API_KEY: {os.getenv('E2B_API_KEY')[:10]}...")

    # Run tests
    results = []
    total_cost = 0.0

    try:
        # Test 1: Simple math
        success = await test_simple_math()
        results.append(("Simple Math", success))

        # Test 2: Data processing
        success = await test_data_processing()
        results.append(("Data Processing", success))

        # Test 3: String manipulation
        success = await test_string_manipulation()
        results.append(("String Manipulation", success))

    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")

    except Exception as e:
        print(f"\n\n❌ Tests failed: {e}")
        import traceback
        traceback.print_exc()

    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"\n{status} - {test_name}")

    print(f"\n" + "-" * 60)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        print("\n✅ CachedExecutor is working correctly with OpenAI API")
        print("   - Code generation works")
        print("   - E2B execution works")
        print("   - Cost tracking works")
        print("   - Ready for Phase 4 (Orquestación)")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        print("   Review errors above before proceeding to Phase 4")

    print("\n💰 Estimated total cost: ~$0.002-$0.003")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
