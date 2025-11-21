"""
CachedExecutor Demo - AI-Powered Code Generation

This script demonstrates the CachedExecutor functionality:
1. Generate Python code from natural language prompts
2. Execute code in E2B sandbox
3. Retry with error feedback on failures
4. Track costs and metadata

Requirements:
- OPENAI_API_KEY environment variable
- E2B_API_KEY environment variable

Usage:
    export OPENAI_API_KEY="sk-..."
    export E2B_API_KEY="e2b_..."
    python examples/cached_executor_demo.py
"""

import asyncio
import os
import json
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.executors import CachedExecutor


async def demo_simple_math():
    """Demo 1: Simple math calculation."""
    print("\n" + "=" * 60)
    print("DEMO 1: Simple Math Calculation")
    print("=" * 60)

    executor = CachedExecutor()

    prompt = "Calculate the sum of numbers from 1 to 100"
    context = {}

    print(f"\nPrompt: {prompt}")
    print(f"Context: {context}")

    result, metadata = await executor.execute(
        code=prompt,
        context=context,
        timeout=30
    )

    print(f"\n✅ Execution successful!")
    print(f"\nResult: {json.dumps(result, indent=2)}")

    metadata = result.get("_ai_metadata", {})
    print(f"\n📊 AI Metadata:")
    print(f"  - Model: {metadata.get('model')}")
    print(f"  - Attempts: {metadata.get('attempts')}")
    print(f"  - Tokens (input/output): {metadata.get('tokens_input')}/{metadata.get('tokens_output')}")
    print(f"  - Cost: ${metadata.get('cost_usd'):.6f}")
    print(f"  - Generation time: {metadata.get('generation_time_ms')}ms")
    print(f"  - Execution time: {metadata.get('execution_time_ms')}ms")
    print(f"\n💻 Generated Code:")
    print("-" * 60)
    print(metadata.get('generated_code'))
    print("-" * 60)


async def demo_data_processing():
    """Demo 2: Data processing with context."""
    print("\n" + "=" * 60)
    print("DEMO 2: Data Processing with Context")
    print("=" * 60)

    executor = CachedExecutor()

    prompt = "Filter numbers greater than 50 and calculate their average"
    context = {
        "numbers": [10, 25, 60, 75, 30, 90, 45, 100]
    }

    print(f"\nPrompt: {prompt}")
    print(f"Context: {context}")

    result, metadata = await executor.execute(
        code=prompt,
        context=context,
        timeout=30
    )

    print(f"\n✅ Execution successful!")
    print(f"\nFiltered numbers: {result.get('filtered')}")
    print(f"Average: {result.get('average')}")

    metadata = result.get("_ai_metadata", {})
    print(f"\n📊 Cost: ${metadata.get('cost_usd'):.6f}")


async def demo_json_parsing():
    """Demo 3: JSON data manipulation."""
    print("\n" + "=" * 60)
    print("DEMO 3: JSON Data Manipulation")
    print("=" * 60)

    executor = CachedExecutor()

    prompt = "Extract all product names and their prices from the data"
    context = {
        "data": {
            "products": [
                {"id": 1, "name": "Laptop", "price": 999.99},
                {"id": 2, "name": "Mouse", "price": 29.99},
                {"id": 3, "name": "Keyboard", "price": 79.99}
            ]
        }
    }

    print(f"\nPrompt: {prompt}")
    print(f"Context: (JSON with 3 products)")

    result, metadata = await executor.execute(
        code=prompt,
        context=context,
        timeout=30
    )

    print(f"\n✅ Execution successful!")
    print(f"\nProduct summary:")
    for item in result.get("product_summary", []):
        print(f"  - {item['name']}: ${item['price']}")

    metadata = result.get("_ai_metadata", {})
    print(f"\n📊 Cost: ${metadata.get('cost_usd'):.6f}")


async def demo_integration_detection():
    """Demo 4: Integration auto-detection (PDF example)."""
    print("\n" + "=" * 60)
    print("DEMO 4: Integration Auto-Detection")
    print("=" * 60)

    executor = CachedExecutor()

    # This prompt should trigger PDF integration docs to be loaded
    prompt = "Extract text from the first page of the PDF"
    context = {
        "pdf_path": "/tmp/sample.pdf"  # Dummy path for demo
    }

    print(f"\nPrompt: {prompt}")
    print(f"Context: {context}")
    print("\n🔍 Expected behavior:")
    print("  - KnowledgeManager detects 'pdf' keyword in prompt")
    print("  - Loads /knowledge/integrations/pdf.md (~4500 tokens)")
    print("  - Builds complete prompt with PDF documentation")
    print("  - OpenAI generates PyMuPDF code")

    print("\n⚠️  Note: This will fail since /tmp/sample.pdf doesn't exist")
    print("    but it demonstrates integration detection and retry logic")

    try:
        result, metadata = await executor.execute(
            code=prompt,
            context=context,
            timeout=30
        )

        print(f"\n✅ Execution successful (unexpected!)")
        print(f"\nResult: {result}")

    except Exception as e:
        print(f"\n❌ Execution failed (expected): {e.__class__.__name__}")
        print(f"    {str(e)[:200]}")
        print("\n✅ Demo shows error handling and retry logic work correctly")


async def demo_cost_estimation():
    """Demo 5: Cost estimation across multiple executions."""
    print("\n" + "=" * 60)
    print("DEMO 5: Cost Estimation")
    print("=" * 60)

    executor = CachedExecutor()

    tasks = [
        "Calculate factorial of 10",
        "Reverse the string 'hello world'",
        "Check if 17 is a prime number"
    ]

    total_cost = 0.0
    results = []

    for task in tasks:
        print(f"\n📝 Task: {task}")

        result, metadata = await executor.execute(
            code=task,
            context={},
            timeout=30
        )

        metadata = result.get("_ai_metadata", {})
        cost = metadata.get("cost_usd", 0.0)
        total_cost += cost

        results.append({
            "task": task,
            "cost": cost,
            "tokens": metadata.get("tokens_total"),
            "attempts": metadata.get("attempts")
        })

        print(f"  ✅ Success (${cost:.6f})")

    print("\n" + "=" * 60)
    print("💰 COST SUMMARY")
    print("=" * 60)

    for r in results:
        print(f"\nTask: {r['task']}")
        print(f"  - Cost: ${r['cost']:.6f}")
        print(f"  - Tokens: {r['tokens']}")
        print(f"  - Attempts: {r['attempts']}")

    print(f"\n💵 Total Cost: ${total_cost:.6f}")
    print(f"📊 Average Cost per Task: ${(total_cost / len(tasks)):.6f}")


async def main():
    """Run all demos."""
    print("\n" + "=" * 60)
    print("🚀 CachedExecutor Demo Suite")
    print("=" * 60)

    # Check environment variables
    if not os.getenv("OPENAI_API_KEY"):
        print("\n❌ ERROR: OPENAI_API_KEY not set")
        print("   Get API key at: https://platform.openai.com/api-keys")
        print("   Then run: export OPENAI_API_KEY='sk-...'")
        return

    if not os.getenv("E2B_API_KEY"):
        print("\n❌ ERROR: E2B_API_KEY not set")
        print("   Get API key at: https://e2b.dev/docs")
        print("   Then run: export E2B_API_KEY='e2b_...'")
        return

    print("\n✅ Environment variables set")
    print(f"   - OPENAI_API_KEY: {os.getenv('OPENAI_API_KEY')[:10]}...")
    print(f"   - E2B_API_KEY: {os.getenv('E2B_API_KEY')[:10]}...")

    # Run demos
    try:
        await demo_simple_math()
        await demo_data_processing()
        await demo_json_parsing()
        await demo_integration_detection()  # Expected to fail
        await demo_cost_estimation()

    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")

    except Exception as e:
        print(f"\n\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("✅ Demo Suite Complete")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
