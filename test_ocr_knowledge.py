"""
Test OCR Knowledge Integration

Verifies that:
1. KnowledgeManager detects OCR keywords correctly
2. ocr.md documentation is loaded successfully
3. Prompt includes OCR documentation when needed
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.core.ai.knowledge_manager import KnowledgeManager


def test_ocr_detection_from_task():
    """Test that OCR is detected from task keywords."""
    print("\n" + "=" * 60)
    print("Test 1: OCR Detection from Task Keywords")
    print("=" * 60)

    km = KnowledgeManager()

    # Test cases with OCR keywords
    test_cases = [
        ("Extract text from scanned invoice", True),
        ("Read text from image using OCR", True),
        ("Process scanned document", True),
        ("Use EasyOCR to recognize handwritten text", True),
        ("Extract data from PDF", False),  # Should detect pdf, not ocr
        ("Send email notification", False),  # No OCR
    ]

    all_passed = True

    for task, should_detect_ocr in test_cases:
        detected = km.detect_integrations(task, {})

        has_ocr = 'ocr' in detected

        status = "✅ PASS" if has_ocr == should_detect_ocr else "❌ FAIL"
        print(f"\n{status}")
        print(f"  Task: '{task}'")
        print(f"  Expected OCR: {should_detect_ocr}")
        print(f"  Detected: {detected}")

        if has_ocr != should_detect_ocr:
            all_passed = False

    return all_passed


def test_ocr_detection_from_context():
    """Test that OCR is detected from context keys."""
    print("\n" + "=" * 60)
    print("Test 2: OCR Detection from Context Keys")
    print("=" * 60)

    km = KnowledgeManager()

    # Test cases with context keys
    test_cases = [
        ({"invoice_image_path": "/tmp/invoice.jpg"}, True),
        ({"image_path": "/tmp/scan.png"}, True),
        ({"scanned_pdf": "/tmp/doc.pdf"}, True),
        ({"pdf_data": "base64..."}, False),  # Should detect pdf, not ocr
        ({}, False),  # Empty context
    ]

    all_passed = True

    for context, should_detect_ocr in test_cases:
        detected = km.detect_integrations("Process document", context)

        has_ocr = 'ocr' in detected

        status = "✅ PASS" if has_ocr == should_detect_ocr else "❌ FAIL"
        print(f"\n{status}")
        print(f"  Context keys: {list(context.keys())}")
        print(f"  Expected OCR: {should_detect_ocr}")
        print(f"  Detected: {detected}")

        if has_ocr != should_detect_ocr:
            all_passed = False

    return all_passed


def test_ocr_documentation_loads():
    """Test that ocr.md documentation loads successfully."""
    print("\n" + "=" * 60)
    print("Test 3: OCR Documentation Loading")
    print("=" * 60)

    km = KnowledgeManager()

    try:
        # Load ocr.md
        ocr_doc = km.load_file("integrations/ocr.md")

        # Verify content
        checks = [
            ("EasyOCR" in ocr_doc, "Contains 'EasyOCR'"),
            ("gpu=False" in ocr_doc, "Contains 'gpu=False' (CPU-only mode)"),
            ("readtext" in ocr_doc, "Contains 'readtext' method"),
            ("Spanish" in ocr_doc or "es" in ocr_doc, "Contains Spanish language"),
            ("English" in ocr_doc or "en" in ocr_doc, "Contains English language"),
        ]

        all_passed = True

        print(f"\n✅ OCR documentation loaded ({len(ocr_doc)} chars)")
        print("\nContent checks:")

        for passed, description in checks:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  {status}: {description}")
            if not passed:
                all_passed = False

        return all_passed

    except FileNotFoundError as e:
        print(f"\n❌ FAIL: {e}")
        return False
    except Exception as e:
        print(f"\n❌ FAIL: Unexpected error: {e}")
        return False


def test_prompt_includes_ocr():
    """Test that prompt includes OCR documentation when needed."""
    print("\n" + "=" * 60)
    print("Test 4: OCR Documentation in Prompt")
    print("=" * 60)

    km = KnowledgeManager()

    # Task that should trigger OCR
    task = "Extract text from scanned invoice using OCR"
    context = {"invoice_image_path": "/tmp/invoice.jpg"}

    # Build prompt
    prompt = km.build_prompt(task, context)

    # Verify OCR docs are included
    checks = [
        ("EasyOCR" in prompt, "Prompt contains 'EasyOCR'"),
        ("gpu=False" in prompt, "Prompt contains 'gpu=False'"),
        ("readtext" in prompt, "Prompt contains 'readtext' method"),
        (task in prompt, "Task is included in prompt"),
    ]

    all_passed = True

    print(f"\n✅ Prompt built ({len(prompt)} chars)")
    print("\nContent checks:")

    for passed, description in checks:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {description}")
        if not passed:
            all_passed = False

    # Show detected integrations
    detected = km.detect_integrations(task, context)
    print(f"\nDetected integrations: {detected}")

    return all_passed


def test_ocr_and_pdf_together():
    """Test that both OCR and PDF can be detected together."""
    print("\n" + "=" * 60)
    print("Test 5: OCR + PDF Detection Together")
    print("=" * 60)

    km = KnowledgeManager()

    # Task that mentions both PDF and OCR
    task = "Extract text from scanned PDF using OCR if no text layer"
    context = {"pdf_path": "/tmp/invoice.pdf", "image_path": "/tmp/scan.jpg"}

    detected = km.detect_integrations(task, context)

    has_ocr = 'ocr' in detected
    has_pdf = 'pdf' in detected

    all_passed = has_ocr and has_pdf

    status = "✅ PASS" if all_passed else "❌ FAIL"
    print(f"\n{status}")
    print(f"  Task: '{task}'")
    print(f"  Context keys: {list(context.keys())}")
    print(f"  Detected: {detected}")
    print(f"  Has OCR: {has_ocr} (expected: True)")
    print(f"  Has PDF: {has_pdf} (expected: True)")

    return all_passed


if __name__ == "__main__":
    print("\n🧪 Testing OCR Knowledge Integration\n")

    results = []

    # Run all tests
    results.append(("OCR Detection from Task", test_ocr_detection_from_task()))
    results.append(("OCR Detection from Context", test_ocr_detection_from_context()))
    results.append(("OCR Documentation Loading", test_ocr_documentation_loads()))
    results.append(("OCR in Prompt", test_prompt_includes_ocr()))
    results.append(("OCR + PDF Together", test_ocr_and_pdf_together()))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    total_tests = len(results)
    passed_tests = sum(1 for _, passed in results if passed)

    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {test_name}")

    print("\n" + "=" * 60)
    print(f"Results: {passed_tests}/{total_tests} tests passed")
    print("=" * 60)

    # Exit with appropriate code
    sys.exit(0 if passed_tests == total_tests else 1)
