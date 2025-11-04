#!/usr/bin/env python3
"""
Simple test script to verify the new E2B template works with NOVA's executor.
Tests the actual integration that NOVA uses.
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import NOVA executor
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from core.executors import E2BExecutor


async def test_nova_executor():
    """Test E2B template using NOVA's executor"""

    api_key = os.getenv("E2B_API_KEY")
    template_id = os.getenv("E2B_TEMPLATE_ID")

    if not api_key:
        print("❌ E2B_API_KEY not found in environment")
        return False

    print(f"✅ E2B_API_KEY: {api_key[:10]}...")
    print(f"✅ E2B_TEMPLATE_ID: {template_id}")

    print("\n🚀 Creating E2BExecutor...")
    executor = E2BExecutor(api_key=api_key, template=template_id)

    # Test code that checks pre-installed packages
    test_code = """
# Test all pre-installed packages
results = []

try:
    import fitz  # PyMuPDF
    results.append("PyMuPDF: ✅")
except ImportError:
    results.append("PyMuPDF: ❌")

try:
    import requests
    results.append("requests: ✅")
except ImportError:
    results.append("requests: ❌")

try:
    import pandas
    results.append("pandas: ✅")
except ImportError:
    results.append("pandas: ❌")

try:
    import PIL
    results.append("pillow: ✅")
except ImportError:
    results.append("pillow: ❌")

try:
    import psycopg2
    results.append("psycopg2: ✅")
except ImportError:
    results.append("psycopg2: ❌")

try:
    import dotenv
    results.append("python-dotenv: ✅")
except ImportError:
    results.append("python-dotenv: ❌")

context['test_results'] = results
context['status'] = 'success'
"""

    initial_context = {
        'test': 'template_verification'
    }

    print("\n🔍 Testing pre-installed packages...")
    try:
        updated_context = await executor.execute(
            code=test_code,
            context=initial_context,
            timeout=60  # 60 seconds timeout for first cold start
        )

        print("\n📦 Package availability:")
        all_available = True
        for result in updated_context.get('test_results', []):
            print(f"  {result}")
            if "❌" in result:
                all_available = False

        if all_available:
            print("\n✅ All packages installed correctly!")
            print(f"✅ Status: {updated_context.get('status')}")
            return True
        else:
            print("\n⚠️  Some packages are missing")
            return False

    except Exception as e:
        print(f"❌ Error during execution: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_nova_executor())
    print("\n" + "="*60)
    if success:
        print("✅ Template test PASSED - Ready for production!")
    else:
        print("❌ Template test FAILED")
    print("="*60)
    sys.exit(0 if success else 1)
