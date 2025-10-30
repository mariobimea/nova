"""
Test script for E2BExecutor

This script verifies that the E2B cloud sandbox works correctly:
1. Creates an E2BExecutor instance
2. Executes simple Python code
3. Verifies context injection and result parsing

Requirements:
- E2B API key (get free $100 credits at https://e2b.dev)
- Set environment variable: export E2B_API_KEY=your_key_here
- Install e2b-code-interpreter: pip install e2b-code-interpreter==1.0.4

Usage:
    python examples/test_e2b_executor.py
"""

import asyncio
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.executors import E2BExecutor, ExecutionError


async def test_simple_execution():
    """Test 1: Simple arithmetic execution"""
    print("=" * 60)
    print("TEST 1: Simple Arithmetic")
    print("=" * 60)

    try:
        executor = E2BExecutor()

        code = """
# Simple calculation
context['result'] = 2 + 2
context['message'] = 'Hello from E2B!'
"""

        initial_context = {"initial_value": 100}

        print(f"\nInitial context: {initial_context}")
        print(f"\nCode to execute:\n{code}")

        result = await executor.execute(
            code=code,
            context=initial_context,
            timeout=10
        )

        print(f"\nResult context: {result}")

        # Verify results
        assert result["result"] == 4, f"Expected result=4, got {result['result']}"
        assert result["message"] == "Hello from E2B!", f"Expected message='Hello from E2B!', got {result['message']}"
        assert result["initial_value"] == 100, "Initial value should be preserved"

        print("\n✅ TEST 1 PASSED")
        return True

    except Exception as e:
        print(f"\n❌ TEST 1 FAILED: {e}")
        return False


async def test_network_access():
    """Test 2: Network access (HTTP request)"""
    print("\n" + "=" * 60)
    print("TEST 2: Network Access (HTTP Request)")
    print("=" * 60)

    try:
        executor = E2BExecutor()

        code = """
import requests

# Make HTTP request to public API
response = requests.get('https://api.github.com/users/github')
data = response.json()

context['github_login'] = data['login']
context['github_name'] = data['name']
context['status_code'] = response.status_code
"""

        initial_context = {}

        print(f"\nCode to execute:\n{code}")

        result = await executor.execute(
            code=code,
            context=initial_context,
            timeout=15
        )

        print(f"\nResult context: {result}")

        # Verify results
        assert result["status_code"] == 200, f"Expected status_code=200, got {result['status_code']}"
        assert result["github_login"] == "github", f"Expected github_login='github', got {result['github_login']}"

        print("\n✅ TEST 2 PASSED - Network access works!")
        return True

    except Exception as e:
        print(f"\n❌ TEST 2 FAILED: {e}")
        return False


async def test_error_handling():
    """Test 3: Error handling for invalid code"""
    print("\n" + "=" * 60)
    print("TEST 3: Error Handling")
    print("=" * 60)

    try:
        executor = E2BExecutor()

        # Code with error (undefined variable)
        code = """
# This will fail - undefined variable
context['result'] = undefined_variable * 2
"""

        print(f"\nCode to execute (should fail):\n{code}")

        try:
            result = await executor.execute(
                code=code,
                context={},
                timeout=10
            )

            print("\n❌ TEST 3 FAILED - Should have raised ExecutionError")
            return False

        except ExecutionError as e:
            print(f"\n✅ TEST 3 PASSED - Correctly caught error: {e}")
            return True

    except Exception as e:
        print(f"\n❌ TEST 3 FAILED with unexpected error: {e}")
        return False


async def test_context_preservation():
    """Test 4: Context preservation and modification"""
    print("\n" + "=" * 60)
    print("TEST 4: Context Preservation")
    print("=" * 60)

    try:
        executor = E2BExecutor()

        code = """
# Modify existing values
context['amount'] = context['amount'] * 1.21  # Add IVA

# Add new values
context['tax_applied'] = 'IVA 21%'
context['processed'] = True
"""

        initial_context = {
            "invoice_id": "INV-001",
            "amount": 1000,
            "client": "Acme Corp"
        }

        print(f"\nInitial context: {initial_context}")
        print(f"\nCode to execute:\n{code}")

        result = await executor.execute(
            code=code,
            context=initial_context,
            timeout=10
        )

        print(f"\nResult context: {result}")

        # Verify results
        assert result["invoice_id"] == "INV-001", "invoice_id should be preserved"
        assert result["client"] == "Acme Corp", "client should be preserved"
        assert result["amount"] == 1210, f"Expected amount=1210, got {result['amount']}"
        assert result["tax_applied"] == "IVA 21%", "tax_applied should be added"
        assert result["processed"] is True, "processed should be True"

        print("\n✅ TEST 4 PASSED")
        return True

    except Exception as e:
        print(f"\n❌ TEST 4 FAILED: {e}")
        return False


async def main():
    """Run all tests"""
    print("\n🚀 E2B EXECUTOR TEST SUITE")
    print("=" * 60)

    # Check for API key
    if not os.getenv("E2B_API_KEY"):
        print("\n❌ ERROR: E2B_API_KEY environment variable not set")
        print("\nTo get a free API key:")
        print("1. Visit https://e2b.dev")
        print("2. Sign up (free $100 credits)")
        print("3. Copy your API key")
        print("4. Run: export E2B_API_KEY=your_key_here")
        print("\nThen run this script again.")
        sys.exit(1)

    print(f"\n✓ E2B_API_KEY found: {os.getenv('E2B_API_KEY')[:10]}...")

    # Run tests
    results = []

    results.append(await test_simple_execution())
    results.append(await test_network_access())
    results.append(await test_error_handling())
    results.append(await test_context_preservation())

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"\nTests passed: {passed}/{total}")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        print("\nNext steps:")
        print("1. E2BExecutor is working correctly")
        print("2. Ready to create invoice processing workflow")
        print("3. Network access confirmed (can use IMAP, SMTP, APIs)")
        sys.exit(0)
    else:
        print("\n⚠️  SOME TESTS FAILED")
        print("\nPlease review the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
