"""
Output Validator - Smart automatic validation of AI-generated code execution results.

This module provides ZERO-CONFIGURATION validation that detects false positives:
- Code executed without errors but didn't do anything useful
- Empty outputs when data extraction was expected
- No new fields added to context

NO manual configuration needed - all validations are automatic based on:
1. Context comparison (before vs after)
2. Output content inspection (non-empty values)
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of output validation."""
    valid: bool
    error_message: Optional[str] = None
    warnings: List[str] = None
    suspicion_score: int = 0
    details: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.details is None:
            self.details = {}


def auto_validate_output(
    task: str,
    context_before: Dict[str, Any],
    context_after: Dict[str, Any],
    generated_code: str
) -> ValidationResult:
    """
    Automatically validate if code execution produced meaningful results.

    This is the main validation function - NO configuration needed!

    Checks performed:
    1. ✅ Were any new fields added to context?
    2. ✅ Are the new fields non-empty and meaningful?

    Args:
        task: The task description (natural language prompt)
        context_before: Context dictionary BEFORE execution
        context_after: Context dictionary AFTER execution
        generated_code: The code that was executed

    Returns:
        ValidationResult with validation outcome

    Example:
        >>> result = auto_validate_output(
        ...     task="Extract text from PDF using OCR",
        ...     context_before={"pdf_data": "..."},
        ...     context_after={"pdf_data": "...", "ocr_text": ""},
        ...     generated_code="..."
        ... )
        >>> result.valid
        False
        >>> result.error_message
        'Code executed but produced EMPTY output. Expected field "ocr_text" is empty.'
    """
    warnings = []
    suspicion_score = 0

    # Remove internal fields (those starting with _)
    context_before_clean = {k: v for k, v in context_before.items() if not k.startswith('_')}
    context_after_clean = {k: v for k, v in context_after.items() if not k.startswith('_')}

    # ========================================
    # CHECK 1: Were any fields added OR modified?
    # ========================================
    # Detect fields that are NEW or UPDATED (changed value)
    new_or_updated_fields = set()

    for key in context_after_clean:
        # Field is new (didn't exist before)
        if key not in context_before_clean:
            new_or_updated_fields.add(key)
        # Field was modified (different value)
        elif context_after_clean[key] != context_before_clean.get(key):
            new_or_updated_fields.add(key)

    if len(new_or_updated_fields) == 0:
        # NO fields added or modified!
        logger.warning(
            f"⚠️  Validation suspicion: Code executed but did NOT modify context. "
            f"Before: {list(context_before_clean.keys())}, "
            f"After: {list(context_after_clean.keys())}"
        )

        return ValidationResult(
            valid=False,
            error_message=(
                "Code executed but did NOT modify context.\n\n"
                "The code must either:\n"
                "  - Add new fields to context\n"
                "  - Update existing fields with new values\n\n"
                "Example FIX:\n"
                "  ❌ ocr_text = '...extracted text...'  # Variable never added to context\n"
                "  ✅ context_updates = {'ocr_text': ocr_text}  # Properly added to output\n"
                "  ✅ context_updates = {'has_pdf': True}  # Update existing field"
            ),
            suspicion_score=10,
            details={
                "new_or_updated_fields": list(new_or_updated_fields),
                "context_before_keys": list(context_before_clean.keys()),
                "context_after_keys": list(context_after_clean.keys())
            }
        )

    logger.debug(f"✅ Check 1 passed: {len(new_or_updated_fields)} field(s) added/updated: {list(new_or_updated_fields)}")

    # ========================================
    # CHECK 2: Are new/updated fields CRITICALLY empty?
    # ========================================
    # Only flag as "critical" if value is None or empty string
    # ✅ Allow: bool (even False), numbers (even 0), empty lists/dicts
    critical_empty_fields = []

    for field in new_or_updated_fields:
        value = context_after_clean[field]

        # Only consider "critical" in these cases:
        if value is None:
            critical_empty_fields.append(f"{field} (None)")
            suspicion_score += 2
        elif isinstance(value, str) and len(value) == 0:
            critical_empty_fields.append(f"{field} (empty string)")
            suspicion_score += 3
        # ✅ DO NOT penalize:
        # - bool (True/False are both valid)
        # - int/float (including 0, 0.0)
        # - empty list [] or dict {} (valid structures)

    if critical_empty_fields:
        logger.warning(
            f"⚠️  Validation suspicion: Some fields are None or empty strings: {critical_empty_fields}"
        )

        # Only fail if ALL fields are critically empty (None or "")
        if len(critical_empty_fields) == len(new_or_updated_fields):
            return ValidationResult(
                valid=False,
                error_message=(
                    f"Code executed but produced ONLY None or empty string values.\n\n"
                    f"Fields: {', '.join(critical_empty_fields)}\n\n"
                    f"Make sure the code actually extracted/generated meaningful data.\n"
                    f"If the code had errors, they should be raised, not silently caught."
                ),
                suspicion_score=suspicion_score,
                details={
                    "critical_empty_fields": critical_empty_fields,
                    "new_or_updated_fields": list(new_or_updated_fields)
                }
            )
        else:
            # Some fields empty, some not → warning only
            warnings.append(
                f"Some fields are None or empty strings: {', '.join(critical_empty_fields)}"
            )

    logger.debug(f"✅ Check 2 passed: Fields have valid content (suspicion score: {suspicion_score})")

    # ========================================
    # CHECK 3: REMOVED - Field name expectations
    # ========================================
    # We removed this check because it was too prescriptive.
    # The AI should be free to name fields as it sees fit, as long as:
    # - It adds/modifies fields (CHECK 1)
    # - Fields are not critically empty (CHECK 2)

    # ========================================
    # FINAL DECISION
    # ========================================

    # If suspicion score is high but not critical → warning only
    if suspicion_score >= 5:
        logger.warning(
            f"⚠️  Output validation suspicion score: {suspicion_score}/10. "
            f"Warnings: {warnings}"
        )

    # Passed all checks!
    logger.info(
        f"✅ Output validation PASSED. Modified fields: {list(new_or_updated_fields)}, "
        f"Suspicion score: {suspicion_score}/10"
    )

    return ValidationResult(
        valid=True,
        warnings=warnings,
        suspicion_score=suspicion_score,
        details={
            "new_or_updated_fields": list(new_or_updated_fields),
            "checks_passed": ["fields_modified", "fields_not_critically_empty"]
        }
    )
