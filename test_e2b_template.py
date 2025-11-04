#!/usr/bin/env python3
"""
Quick test script to verify E2B template is working correctly.
Tests that pre-installed packages (PyMuPDF, pandas, etc.) are available.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import E2B
try:
    from e2b_code_interpreter import Sandbox
except ImportError:
    print("❌ e2b_code_interpreter not installed. Run: pip install e2b-code-interpreter")
    sys.exit(1)

def test_template():
    """Test E2B template with pre-installed packages"""

    api_key = os.getenv("E2B_API_KEY")
    template_id = os.getenv("E2B_TEMPLATE_ID")

    if not api_key:
        print("❌ E2B_API_KEY not found in environment")
        sys.exit(1)

    if not template_id:
        print("⚠️  E2B_TEMPLATE_ID not found - using base template")
        template_id = None
    else:
        print(f"✅ Using custom template: {template_id}")

    print("\n🚀 Starting E2B sandbox...")

    # Create sandbox with custom template
    try:
        create_kwargs = {"api_key": api_key, "timeout": 120}
        if template_id:
            create_kwargs["template"] = template_id

        # Use context manager for automatic cleanup
        with Sandbox.create(**create_kwargs) as sbx:
            print("✅ Sandbox created successfully")

            # Test pre-installed packages
            test_code = """
import sys
import json

# Test all pre-installed packages
results = {}

try:
    import fitz  # PyMuPDF
    results['PyMuPDF'] = '✅ Available'
except ImportError:
    results['PyMuPDF'] = '❌ Not installed'

try:
    import requests
    results['requests'] = '✅ Available'
except ImportError:
    results['requests'] = '❌ Not installed'

try:
    import pandas
    results['pandas'] = '✅ Available'
except ImportError:
    results['pandas'] = '❌ Not installed'

try:
    import PIL
    results['pillow'] = '✅ Available'
except ImportError:
    results['pillow'] = '❌ Not installed'

try:
    import psycopg2
    results['psycopg2'] = '✅ Available'
except ImportError:
    results['psycopg2'] = '❌ Not installed'

try:
    import dotenv
    results['python-dotenv'] = '✅ Available'
except ImportError:
    results['python-dotenv'] = '❌ Not installed'

print(json.dumps(results))
"""

            print("\n🔍 Testing pre-installed packages...")
            execution = sbx.run_code(test_code, timeout=30)

            if execution.error:
                print(f"❌ Execution error: {execution.error}")
                return False

            # Parse results
            import json
            try:
                results = json.loads(execution.logs.stdout[-1])
                print("\n📦 Package availability:")
                for package, status in results.items():
                    print(f"  {package}: {status}")
            except:
                print("Raw output:", execution.logs.stdout)

        print("\n✅ Test completed successfully!")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = test_template()
    sys.exit(0 if success else 1)
