"""
Simplest possible test: just verify OpenAI + E2B work together.
No PDF, no complex logic.
"""

import asyncio
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.executors import CachedExecutor
from src.core.circuit_breaker import e2b_circuit_breaker


async def test():
    print("\n" + "=" * 60)
    print("🧪 Simple E2B + OpenAI Test")
    print("=" * 60)

    # Reset circuit breaker
    e2b_circuit_breaker.reset()
    print("\n✅ Circuit breaker reset")

    if not os.getenv("OPENAI_API_KEY") or not os.getenv("E2B_API_KEY"):
        print("\n❌ API keys not set")
        return False

    try:
        executor = CachedExecutor()

        # Simplest possible prompt
        prompt = "Calculate 5 + 3 and save the result as 'sum'"

        print(f"\n📝 Prompt: {prompt}")
        print(f"\n⏳ Executing...")

        result = await executor.execute(
            code=prompt,
            context={},
            timeout=30
        )

        print(f"\n✅ SUCCESS!")

        metadata = result.get("_ai_metadata", {})
        print(f"\n📊 Metadata:")
        print(f"   Cost: ${metadata.get('cost_usd'):.6f}")
        print(f"   Time: {metadata.get('total_time_ms')}ms")
        print(f"   Attempts: {metadata.get('attempts')}")

        print(f"\n💻 Generated Code:")
        print("-" * 60)
        print(metadata.get('generated_code'))
        print("-" * 60)

        result_without_meta = {k: v for k, v in result.items() if k != '_ai_metadata'}
        print(f"\n📤 Result: {result_without_meta}")

        # Verify
        if 'sum' in result_without_meta and result_without_meta['sum'] == 8:
            print(f"\n✅ VERIFIED: Got expected result")
            return True
        else:
            print(f"\n⚠️  Unexpected result")
            return False

    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test())
    sys.exit(0 if success else 1)
