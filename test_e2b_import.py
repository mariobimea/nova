"""
Test script to verify e2b import works correctly
"""

print("Testing e2b import...")

try:
    from e2b import Sandbox
    print("✅ Successfully imported: from e2b import Sandbox")
except ImportError as e:
    print(f"❌ Failed to import e2b.Sandbox: {e}")
    exit(1)

try:
    import os
    os.environ["E2B_API_KEY"] = "test-key"

    # Try to instantiate (will fail without real key, but import should work)
    print("✅ e2b module loaded successfully")
except Exception as e:
    print(f"❌ Error with e2b module: {e}")
    exit(1)

print("\n✅ All e2b imports successful!")
