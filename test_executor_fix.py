#!/usr/bin/env python3
"""
Quick test to verify E2BExecutor works with the new template.
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

load_dotenv()

from core.executors import E2BExecutor


async def test_executor():
    """Test E2BExecutor with nova-engine template."""

    api_key = os.getenv("E2B_API_KEY")
    template_id = os.getenv("E2B_TEMPLATE_ID")

    if not api_key or not template_id:
        print("❌ E2B_API_KEY or E2B_TEMPLATE_ID not found in .env")
        return False

    print(f"✅ E2B_API_KEY: {api_key[:10]}...")
    print(f"✅ E2B_TEMPLATE_ID: {template_id}\n")

    # Create executor
    executor = E2BExecutor(api_key=api_key, template=template_id)

    print("🚀 Testing E2BExecutor...\n")

    # Test code that uses pre-installed packages
    test_code = """
import pandas as pd
import requests

# Create a simple DataFrame
data = {"name": ["Alice", "Bob"], "age": [25, 30]}
df = pd.DataFrame(data)

# Store in context
context["dataframe_shape"] = str(df.shape)
context["package_test"] = "success"
"""

    context = {}

    try:
        print("🔍 Executing code in E2B sandbox...")
        updated_context = await executor.execute(
            code=test_code,
            context=context,
            timeout=60
        )

        print("\n📦 Execution result:")
        print(f"  dataframe_shape: {updated_context.get('dataframe_shape')}")
        print(f"  package_test: {updated_context.get('package_test')}")

        if updated_context.get("package_test") == "success":
            print("\n✅ E2BExecutor test PASSED!")
            return True
        else:
            print("\n❌ E2BExecutor test FAILED: Unexpected result")
            return False

    except Exception as e:
        print(f"\n❌ E2BExecutor test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("E2BExecutor Fix Test")
    print("=" * 60)
    print()

    success = asyncio.run(test_executor())

    print()
    print("=" * 60)
    if success:
        print("✅ Executor is working correctly!")
    else:
        print("❌ Executor test failed")
    print("=" * 60)

    sys.exit(0 if success else 1)
