#!/usr/bin/env python3
"""
Test script to verify the new E2B template is working correctly.
Tests that pre-installed packages (PyMuPDF, pandas, etc.) are available.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import E2B - Try code interpreter first, fallback to standard Sandbox
try:
    from e2b_code_interpreter import Sandbox
    USE_CODE_INTERPRETER = True
except ImportError:
    try:
        from e2b import Sandbox
        USE_CODE_INTERPRETER = False
        print("⚠️  Using standard E2B Sandbox (e2b_code_interpreter not installed)")
    except ImportError:
        print("❌ E2B not installed. Run: pip install e2b or pip install e2b-code-interpreter")
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

            if USE_CODE_INTERPRETER:
                execution = sbx.run_code(test_code, timeout=30)
            else:
                # Use process.start for standard Sandbox
                proc = sbx.process.start("python3 -c '" + test_code.replace("'", "\\'") + "'")
                proc.wait()
                execution = proc

            if execution.error:
                print(f"❌ Execution error: {execution.error}")
                return False

            # Parse results
            import json
            try:
                results = json.loads(execution.logs.stdout[-1])
                print("\n📦 Package availability:")
                all_available = True
                for package, status in results.items():
                    print(f"  {package}: {status}")
                    if "❌" in status:
                        all_available = False

                if all_available:
                    print("\n✅ All packages installed correctly!")
                else:
                    print("\n⚠️  Some packages are missing")
                    return False

            except Exception as e:
                print(f"❌ Failed to parse output: {e}")
                print("Raw output:", execution.logs.stdout)
                return False

        print("\n✅ Test completed successfully!")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_template()
    sys.exit(0 if success else 1)
