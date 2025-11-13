"""
Test to reproduce the empty string validation bug.
"""

import sys
sys.path.insert(0, '.')
from src.core.output_validator import auto_validate_output


def test_single_field_empty_string():
    """
    Test case: Code adds ONE field with empty string value.

    Expected: Should FAIL validation (critically empty)
    Bug: Might be passing if there's a logic error
    """
    task = "Extract OCR text from PDF"
    context_before = {"pdf_data": "binary data here"}
    context_after = {"pdf_data": "binary data here", "ocr_text": ""}
    generated_code = "context['ocr_text'] = ''"

    result = auto_validate_output(
        task=task,
        context_before=context_before,
        context_after=context_after,
        generated_code=generated_code
    )

    print(f"\n{'='*60}")
    print(f"TEST: Single field with empty string")
    print(f"{'='*60}")
    print(f"Context before: {context_before}")
    print(f"Context after:  {context_after}")
    print(f"\nValidation result:")
    print(f"  Valid: {result.valid}")
    print(f"  Error: {result.error_message}")
    print(f"  Warnings: {result.warnings}")
    print(f"  Suspicion score: {result.suspicion_score}/10")
    print(f"  Details: {result.details}")
    print(f"\n{'='*60}")
    print(f"EXPECTED: valid=False (should FAIL)")
    print(f"ACTUAL:   valid={result.valid}")
    print(f"RESULT:   {'✅ PASS' if not result.valid else '❌ BUG DETECTED!'}")
    print(f"{'='*60}\n")

    return result


def test_multiple_fields_one_empty():
    """
    Test case: Code adds multiple fields, only ONE is empty string.

    Expected: Should PASS with warning (not ALL fields are empty)
    """
    task = "Extract invoice data"
    context_before = {"pdf_data": "binary"}
    context_after = {
        "pdf_data": "binary",
        "invoice_number": "INV-001",
        "amount": "",  # Empty!
        "date": "2025-01-12"
    }
    generated_code = "..."

    result = auto_validate_output(
        task=task,
        context_before=context_before,
        context_after=context_after,
        generated_code=generated_code
    )

    print(f"\n{'='*60}")
    print(f"TEST: Multiple fields, one empty")
    print(f"{'='*60}")
    print(f"New fields: invoice_number='INV-001', amount='', date='2025-01-12'")
    print(f"\nValidation result:")
    print(f"  Valid: {result.valid}")
    print(f"  Error: {result.error_message}")
    print(f"  Warnings: {result.warnings}")
    print(f"  Suspicion score: {result.suspicion_score}/10")
    print(f"\n{'='*60}")
    print(f"EXPECTED: valid=True (should PASS with warning)")
    print(f"ACTUAL:   valid={result.valid}")
    print(f"RESULT:   {'✅ CORRECT' if result.valid else '❌ BUG: Too strict!'}")
    print(f"{'='*60}\n")

    return result


def test_all_fields_empty_string():
    """
    Test case: Code adds multiple fields, ALL are empty strings.

    Expected: Should FAIL validation (all critically empty)
    """
    task = "Extract invoice data"
    context_before = {"pdf_data": "binary"}
    context_after = {
        "pdf_data": "binary",
        "invoice_number": "",
        "amount": "",
        "date": ""
    }
    generated_code = "..."

    result = auto_validate_output(
        task=task,
        context_before=context_before,
        context_after=context_after,
        generated_code=generated_code
    )

    print(f"\n{'='*60}")
    print(f"TEST: All fields empty strings")
    print(f"{'='*60}")
    print(f"New fields: invoice_number='', amount='', date=''")
    print(f"\nValidation result:")
    print(f"  Valid: {result.valid}")
    print(f"  Error: {result.error_message}")
    print(f"  Suspicion score: {result.suspicion_score}/10")
    print(f"\n{'='*60}")
    print(f"EXPECTED: valid=False (should FAIL)")
    print(f"ACTUAL:   valid={result.valid}")
    print(f"RESULT:   {'✅ PASS' if not result.valid else '❌ BUG DETECTED!'}")
    print(f"{'='*60}\n")

    return result


if __name__ == "__main__":
    print("\n" + "="*60)
    print("TESTING OUTPUT VALIDATOR - Empty String Handling")
    print("="*60)

    # Test 1: Single empty field (should FAIL)
    result1 = test_single_field_empty_string()

    # Test 2: Multiple fields, one empty (should PASS with warning)
    result2 = test_multiple_fields_one_empty()

    # Test 3: All fields empty (should FAIL)
    result3 = test_all_fields_empty_string()

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Test 1 (single empty):     {'✅ PASS' if not result1.valid else '❌ BUG'}")
    print(f"Test 2 (one empty):        {'✅ PASS' if result2.valid else '❌ BUG'}")
    print(f"Test 3 (all empty):        {'✅ PASS' if not result3.valid else '❌ BUG'}")
    print("="*60 + "\n")