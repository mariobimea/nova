#!/usr/bin/env python3
"""
Test script for NOVA E2B custom template.
Verifies that all pre-installed packages are available.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    from e2b import Sandbox
except ImportError:
    print("❌ e2b SDK not installed")
    print("Install with: pip install e2b")
    sys.exit(1)


def test_nova_template():
    """Test that all packages are available in the template."""

    api_key = os.getenv("E2B_API_KEY")
    template_id = os.getenv("E2B_TEMPLATE_ID")

    if not api_key:
        print("❌ E2B_API_KEY not found in .env")
        return False

    if not template_id:
        print("❌ E2B_TEMPLATE_ID not found in .env")
        return False

    print(f"✅ E2B_API_KEY: {api_key[:10]}...")
    print(f"✅ E2B_TEMPLATE_ID: {template_id}\n")

    print("🚀 Creating sandbox from template...\n")

    try:
        sbx = Sandbox.create(
            template=template_id,
            api_key=api_key,
            timeout=120
        )

        print("✅ Sandbox created successfully\n")

        # Test all pre-installed packages
        test_code = """
import fitz
import requests
import pandas
from PIL import Image
import PIL
import psycopg2
from dotenv import load_dotenv

print(f"PyMuPDF: ✅ {fitz.__version__}")
print(f"requests: ✅ {requests.__version__}")
print(f"pandas: ✅ {pandas.__version__}")
print(f"pillow: ✅ {PIL.__version__}")
print(f"psycopg2: ✅ {psycopg2.__version__}")
print(f"python-dotenv: ✅ installed")
"""

        print("🔍 Testing pre-installed packages...\n")

        # Execute code in sandbox using commands
        result = sbx.commands.run(f"python3 -c '{test_code}'")

        print("📦 Package availability:")
        print(result.stdout)

        if result.stderr:
            print(f"\n⚠️  Errors:\n{result.stderr}")

        if result.exit_code != 0:
            print(f"\n❌ Command failed with exit code {result.exit_code}")
            sbx.kill()
            return False

        # Check if all packages are available
        if "✅" not in result.stdout or "❌" in result.stdout:
            print("\n⚠️  Some packages are missing!")
            sbx.kill()
            return False

        print("\n✅ All packages installed correctly!")

        # Close sandbox
        sbx.kill()
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        try:
            sbx.kill()
        except:
            pass
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("NOVA E2B Template Test")
    print("=" * 60)
    print()

    success = test_nova_template()

    print()
    print("=" * 60)
    if success:
        print("✅ Template test PASSED - Ready for production!")
    else:
        print("❌ Template test FAILED")
    print("=" * 60)

    sys.exit(0 if success else 1)
