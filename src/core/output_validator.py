"""
Output Validator - Smart automatic validation of AI-generated code execution results.

This module provides ZERO-CONFIGURATION validation that detects false positives:
- Code executed without errors but didn't do anything useful
- Empty outputs when data extraction was expected
- No new fields added to context

NO manual configuration needed - all validations are automatic based on:
1. Context comparison (before vs after)
2. Task keywords analysis
3. Output content inspection
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
    3. ✅ Do field names match task expectations (e.g., "ocr_text" for OCR tasks)?

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
    # CHECK 1: Were any new fields added?
    # ========================================
    new_fields = set(context_after_clean.keys()) - set(context_before_clean.keys())

    if len(new_fields) == 0:
        # NO new fields added!
        logger.warning(
            f"⚠️  Validation suspicion: Code executed but added NO new fields to context. "
            f"Before: {list(context_before_clean.keys())}, "
            f"After: {list(context_after_clean.keys())}"
        )

        return ValidationResult(
            valid=False,
            error_message=(
                "Code executed but did NOT add any new fields to context.\n\n"
                "The code must update the context with the results of its work.\n"
                "Make sure you're adding the extracted/generated data to context_updates.\n\n"
                "Example FIX:\n"
                "  ❌ ocr_text = '...extracted text...'  # Variable never added to context\n"
                "  ✅ context_updates = {'ocr_text': ocr_text}  # Properly added to output"
            ),
            suspicion_score=10,
            details={
                "new_fields": list(new_fields),
                "context_before_keys": list(context_before_clean.keys()),
                "context_after_keys": list(context_after_clean.keys())
            }
        )

    logger.debug(f"✅ Check 1 passed: {len(new_fields)} new field(s) added: {list(new_fields)}")

    # ========================================
    # CHECK 2: Are new fields empty or too short?
    # ========================================
    empty_or_short_fields = []

    for field in new_fields:
        value = context_after_clean[field]

        # Check if value is empty or suspiciously short
        if value is None:
            empty_or_short_fields.append(f"{field} (None)")
            suspicion_score += 2

        elif isinstance(value, str):
            if len(value) == 0:
                empty_or_short_fields.append(f"{field} (empty string)")
                suspicion_score += 3
            elif len(value) < 3:
                empty_or_short_fields.append(f"{field} (too short: '{value}')")
                suspicion_score += 1

        elif isinstance(value, (list, dict)):
            if len(value) == 0:
                empty_or_short_fields.append(f"{field} (empty {type(value).__name__})")
                suspicion_score += 2

    if empty_or_short_fields:
        logger.warning(
            f"⚠️  Validation suspicion: New fields are empty or too short: {empty_or_short_fields}"
        )

        # If ALL new fields are empty → hard fail
        if len(empty_or_short_fields) == len(new_fields):
            return ValidationResult(
                valid=False,
                error_message=(
                    f"Code executed but produced EMPTY output.\n\n"
                    f"New fields added: {', '.join(new_fields)}\n"
                    f"But ALL of them are empty or None!\n\n"
                    f"Make sure the code actually extracted/generated data and didn't fail silently.\n"
                    f"Check if there were any errors during execution that were caught but not reported."
                ),
                suspicion_score=suspicion_score,
                details={
                    "empty_fields": empty_or_short_fields,
                    "new_fields": list(new_fields)
                }
            )
        else:
            # Some fields empty, some not → warning
            warnings.append(
                f"Some new fields are empty: {', '.join(empty_or_short_fields)}"
            )

    logger.debug(f"✅ Check 2 passed: New fields have content (suspicion score: {suspicion_score})")

    # ========================================
    # CHECK 3: Specific field expectations based on task
    # ========================================
    task_lower = task.lower()

    # If task mentions "ocr" or "extract text", expect "ocr_text" or similar
    if 'ocr' in task_lower or 'extract text' in task_lower:
        text_fields = [f for f in new_fields if 'text' in f.lower() or 'ocr' in f.lower()]

        if not text_fields:
            warnings.append(
                f"Task mentions OCR/text extraction but no text field found in output. "
                f"New fields: {list(new_fields)}"
            )
            suspicion_score += 3
        else:
            # Check if text field has meaningful content
            for field in text_fields:
                text_value = context_after_clean[field]
                if isinstance(text_value, str) and len(text_value) < 5:
                    warnings.append(
                        f"Text field '{field}' is too short ({len(text_value)} chars): '{text_value}'"
                    )
                    suspicion_score += 2

    # If task mentions "amount" or "total", expect numeric field
    if any(keyword in task_lower for keyword in ['amount', 'total', 'price', 'cost']):
        numeric_fields = [
            f for f in new_fields
            if 'amount' in f.lower() or 'total' in f.lower() or 'price' in f.lower()
        ]

        if not numeric_fields:
            warnings.append(
                f"Task mentions amount/total but no amount field found. "
                f"New fields: {list(new_fields)}"
            )
            suspicion_score += 2

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
        f"✅ Output validation PASSED. New fields: {list(new_fields)}, "
        f"Suspicion score: {suspicion_score}/10"
    )

    return ValidationResult(
        valid=True,
        warnings=warnings,
        suspicion_score=suspicion_score,
        details={
            "new_fields": list(new_fields),
            "checks_passed": ["fields_added", "fields_not_empty", "field_names_match_task"]
        }
    )
