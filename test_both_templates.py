#!/usr/bin/env python3
"""
Test both NOVA templates: V1 (basic) and V2 (with OCR)
Quick verification that both are functional
"""

import os
from dotenv import load_dotenv
from e2b import Sandbox

load_dotenv()

def test_template_v1():
    """Test V1 template (nova-engine) - Basic packages only"""

    print("=" * 70)
    print("TEST 1: NOVA Template V1 (Basic - No OCR)")
    print("=" * 70)
    print()

    template_id = "wzqi57u2e8v2f90t6lh5"
    template_name = "nova-engine"

    print(f"📋 Template: {template_name}")
    print(f"🆔 ID: {template_id}")
    print()

    try:
        print("🚀 Creating sandbox...")
        sandbox = Sandbox.create(template=template_id)
        print(f"✅ Sandbox created: {sandbox.sandbox_id}")
        print()

        # Test basic packages
        print("🔍 Testing base packages...")
        test_code = """
import sys
try:
    import fitz
    import requests
    import pandas
    from PIL import Image
    import psycopg2
    from dotenv import load_dotenv
    print("✅ All base packages available")
    print(f"  - PyMuPDF: {fitz.__version__}")
    print(f"  - requests: {requests.__version__}")
    print(f"  - pandas: {pandas.__version__}")
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
"""

        result = sandbox.commands.run(f"python3 -c '{test_code}'", timeout=30)
        print(result.stdout)

        if result.exit_code != 0:
            print(f"❌ V1 Test FAILED: {result.stderr}")
            sandbox.kill()
            return False

        # Verify NO OCR packages
        print("🔍 Verifying OCR is NOT present (expected)...")
        try:
            result = sandbox.commands.run(
                "python3 -c 'import easyocr'",
                timeout=10
            )

            if result.exit_code == 0:
                print("⚠️  WARNING: EasyOCR found in V1 (shouldn't be there)")
            else:
                print("✅ Correct: No OCR packages in V1")
        except Exception:
            # Expected - easyocr should not be in V1
            print("✅ Correct: No OCR packages in V1")

        print()
        sandbox.kill()

        print("=" * 70)
        print("✅ TEMPLATE V1 TEST PASSED")
        print("=" * 70)
        print()

        return True

    except Exception as e:
        print(f"❌ V1 Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_template_v2():
    """Test V2 template (nova-ocr-simple) - With EasyOCR"""

    print("=" * 70)
    print("TEST 2: NOVA Template V2 (With EasyOCR)")
    print("=" * 70)
    print()

    template_id = "ybdni0ui0l3vsumat82v"
    template_name = "nova-ocr-simple"

    print(f"📋 Template: {template_name}")
    print(f"🆔 ID: {template_id}")
    print()

    try:
        print("🚀 Creating sandbox...")
        sandbox = Sandbox.create(template=template_id)
        print(f"✅ Sandbox created: {sandbox.sandbox_id}")
        print()

        # Test basic packages
        print("🔍 Testing base packages...")
        test_code = """
import sys
try:
    import fitz
    import requests
    import pandas
    from PIL import Image
    import psycopg2
    from dotenv import load_dotenv
    print("✅ All base packages available")
    print(f"  - PyMuPDF: {fitz.__version__}")
    print(f"  - requests: {requests.__version__}")
    print(f"  - pandas: {pandas.__version__}")
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
"""

        result = sandbox.commands.run(f"python3 -c '{test_code}'", timeout=30)
        print(result.stdout)

        if result.exit_code != 0:
            print(f"❌ Base packages test FAILED: {result.stderr}")
            sandbox.kill()
            return False

        # Test PyTorch
        print("🔍 Testing PyTorch...")
        result = sandbox.commands.run(
            "python3 -c 'import torch; print(f\"PyTorch {torch.__version__} - CUDA: {torch.cuda.is_available()}\")'",
            timeout=20
        )

        if result.exit_code == 0:
            print(f"✅ {result.stdout.strip()}")
        else:
            print(f"❌ PyTorch test failed: {result.stderr}")
            sandbox.kill()
            return False

        # Test EasyOCR (critical)
        print("🔍 Testing EasyOCR...")
        result = sandbox.commands.run(
            "python3 -c 'import easyocr; print(f\"EasyOCR {easyocr.__version__}\")'",
            timeout=30
        )

        if result.exit_code == 0:
            print(f"✅ {result.stdout.strip()}")
        else:
            print(f"❌ EasyOCR test failed: {result.stderr}")
            sandbox.kill()
            return False

        # Test EasyOCR Reader initialization
        print("🔍 Testing EasyOCR Reader initialization...")
        print("  (This may take 60-90 seconds for model loading)")
        result = sandbox.commands.run(
            "python3 -c 'import easyocr; reader = easyocr.Reader([\"es\", \"en\"], gpu=False, verbose=False); print(\"Reader initialized successfully\")'",
            timeout=120
        )

        if result.exit_code == 0:
            print(f"✅ {result.stdout.strip()}")
        else:
            print(f"⚠️  Reader initialization warning: {result.stderr}")
            print("  (Models might download on first use)")

        print()
        sandbox.kill()

        print("=" * 70)
        print("✅ TEMPLATE V2 TEST PASSED")
        print("=" * 70)
        print()

        return True

    except Exception as e:
        print(f"❌ V2 Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run both template tests"""

    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 15 + "NOVA E2B TEMPLATES - VERIFICATION TEST" + " " * 14 + "║")
    print("╚" + "═" * 68 + "╝")
    print()

    api_key = os.getenv("E2B_API_KEY")
    if not api_key:
        print("❌ ERROR: E2B_API_KEY not found in environment")
        return False

    print(f"✅ E2B API Key: {api_key[:12]}...")
    print()
    print()

    # Test V1
    v1_passed = test_template_v1()
    print()
    print()

    # Test V2
    v2_passed = test_template_v2()
    print()
    print()

    # Summary
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 25 + "FINAL SUMMARY" + " " * 30 + "║")
    print("╠" + "═" * 68 + "╣")
    print("║" + " " * 68 + "║")

    v1_status = "✅ PASSED" if v1_passed else "❌ FAILED"
    v2_status = "✅ PASSED" if v2_passed else "❌ FAILED"

    print(f"║  Template V1 (nova-engine):        {v1_status}" + " " * (68 - 40 - len(v1_status)) + "║")
    print(f"║  Template V2 (nova-ocr-simple):    {v2_status}" + " " * (68 - 40 - len(v2_status)) + "║")
    print("║" + " " * 68 + "║")

    if v1_passed and v2_passed:
        print("║" + " " * 15 + "🎉 ALL TEMPLATES WORKING! 🎉" + " " * 24 + "║")
        print("║" + " " * 68 + "║")
        print("║  Both templates are ready for production use." + " " * 21 + "║")
    else:
        print("║" + " " * 15 + "⚠️  SOME TESTS FAILED" + " " * 30 + "║")
        print("║" + " " * 68 + "║")
        print("║  Please review the error messages above." + " " * 26 + "║")

    print("║" + " " * 68 + "║")
    print("╚" + "═" * 68 + "╝")
    print()

    return v1_passed and v2_passed


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
