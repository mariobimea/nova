#!/usr/bin/env python3
"""
Test which packages are installed in the E2B template.
Run this to verify if pymupdf and easyocr are available.
"""
import os
from dotenv import load_dotenv
from e2b import Sandbox

load_dotenv()

template_id = os.getenv("E2B_TEMPLATE_ID")
if not template_id:
    print("❌ E2B_TEMPLATE_ID not set in .env")
    exit(1)

print(f"Testing template: {template_id}")
print("=" * 60)

# Test code
test_code = """
import sys
import json

packages_to_test = [
    'pymupdf',
    'fitz',  # PyMuPDF imports as 'fitz'
    'easyocr',
    'torch',
    'pdf2image',
    'requests',
    'pandas',
    'psycopg2'
]

results = {}

for package in packages_to_test:
    try:
        module = __import__(package)
        version = getattr(module, '__version__', 'unknown')
        results[package] = {'installed': True, 'version': version}
    except ImportError as e:
        results[package] = {'installed': False, 'error': str(e)}

print(json.dumps(results, indent=2))
"""

try:
    print(f"🚀 Creating sandbox from template '{template_id}'...")
    sandbox = Sandbox.create(template=template_id)
    print(f"✅ Sandbox created\n")

    # Run test
    print("🔍 Testing package availability...\n")

    # Write code to file first (safer than -c)
    sandbox.files.write("/tmp/test.py", test_code)
    result = sandbox.commands.run("python3 /tmp/test.py", timeout=30)

    if result.exit_code != 0:
        print(f"❌ Test failed:")
        print(f"stderr: {result.stderr}")
    else:
        print("📦 Package availability:\n")
        import json
        packages = json.loads(result.stdout)

        for package, info in packages.items():
            if info['installed']:
                print(f"  ✅ {package:15s} - v{info['version']}")
            else:
                print(f"  ❌ {package:15s} - NOT INSTALLED")
                print(f"     Error: {info['error']}")

    sandbox.kill()
    print("\n" + "=" * 60)
    print("✅ Test completed")

except Exception as e:
    print(f"❌ Error: {e}")
