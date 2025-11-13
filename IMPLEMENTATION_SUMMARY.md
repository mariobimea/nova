# AI Self-Determination Implementation Summary

## What Was Implemented

You now have **complete two-stage code generation** with **AI self-determination**.

The key insight: Instead of using hardcoded rules to decide if data analysis is needed, **the AI itself decides**.

---

## How It Works

### The Flow

```
User Task + Context
    ↓
CachedExecutor._execute_with_ai_self_determination()
    ↓
[Stage 1] AI receives task + context summary
    ↓
AI decides:
  Option A: "I need to analyze this data first"
    → Generates code marked with # STAGE: ANALYSIS
    → System executes, enriches context
    → Loop back to Stage 1 (now for task)

  Option B: "I can solve this directly"
    → Generates code marked with # STAGE: TASK
    → System executes, returns results
```

### Tool Calling Integration

The `search_documentation(library, query)` tool is **always available** at any stage:

```python
# AI can search docs during analysis
# STAGE: ANALYSIS
# AI first searches "pymupdf" to learn API
pdf_bytes = base64.b64decode(context['pdf_data_b64'])
doc = fitz.open(stream=pdf_bytes, filetype="pdf")
result = {"has_text": bool(doc[0].get_text())}

# AI can search docs during task execution
# STAGE: TASK
# AI searches "pytesseract" for OCR
text = pytesseract.image_to_string(...)
```

Tool calling is part of `_generate_code_with_tools()` which is called at every stage.

---

## What Was Added to executors.py

### 3 New Methods (Lines 1175-1460)

**1. `_detect_stage_from_code(code: str) -> str`** (Line 1179)
   - Detects stage marker in generated code
   - Returns "analysis" or "task"
   - Falls back to "task" if no marker found

**2. `_execute_with_ai_self_determination(...)` (Line 1207)**
   - Main orchestration method
   - Loops max 2 stages (analysis + task)
   - Calls `_generate_code_with_tools()` with custom prompt
   - Detects stage, routes accordingly
   - Returns results with full metadata

**3. `_build_self_determination_prompt(...)` (Line 1362)**
   - Builds system prompt for AI
   - Explains two-stage approach
   - Shows example with stage markers
   - Mentions tool calling availability
   - **This is where you'll customize prompts**

---

## The Prompt (Where You'll Make Changes)

Located in `_build_self_determination_prompt()` (line 1362):

```python
AVAILABLE TOOLS:
You can call search_documentation(library, query) at ANY point to get API documentation.
Example: If you need to work with PDFs, search for "pymupdf" or "pypdf" first.

CONTEXT PROVIDED:
{context_summary}

USER TASK:
{task}

REQUIREMENTS:
- Mark your code with the appropriate stage comment
- Return results by modifying the 'context' dict
- Handle errors gracefully
- Use clear variable names
```

**You can modify**:
- Instructions for when to analyze vs go direct
- Examples of analysis code
- Requirements and constraints
- Tone and specificity

---

## Test Files

### 1. test_two_stage.py (Heuristic approach)
Tests the original heuristic-based approach where code decides if analysis is needed.

### 2. test_ai_self_determination.py (NEW - AI approach)
Tests the new AI self-determination approach:
- Test 1: PDF (complex data) → AI should decide to analyze
- Test 2: Simple data → AI should skip analysis

**To run**:
```bash
cd /Users/marioferrer/automatizaciones/nova
python3 test_ai_self_determination.py
```

---

## Files Modified/Created

### Modified
- [src/core/executors.py](src/core/executors.py)
  - Added 3 new methods (280 lines)
  - Lines 1175-1460

### Created
- [test_ai_self_determination.py](test_ai_self_determination.py)
  - Complete test suite for AI approach

- [TWO_STAGE_APPROACHES.md](TWO_STAGE_APPROACHES.md)
  - Comparison of both approaches
  - Cost analysis
  - When to use each

- [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
  - This file!

---

## How to Use

### Option 1: Use Existing Heuristic Approach (Default)

```python
executor = CachedExecutor(db_session=session)
result = await executor.execute(
    code=task,
    context=context,
    timeout=60
)
```

Current behavior in `execute()` (line 594):
- Heuristic detects complex data
- Runs analysis if needed
- Continues to task

### Option 2: Use AI Self-Determination (New)

```python
executor = CachedExecutor(db_session=session)
result = await executor._execute_with_ai_self_determination(
    task=task,
    context=context,
    timeout=60
)
```

### Option 3: Add Feature Flag (Recommended)

Modify `execute()` to support mode selection:

```python
async def execute(
    self,
    code: str,
    context: Dict[str, Any],
    timeout: int,
    two_stage_mode: str = "heuristic"  # "heuristic" | "ai" | "hybrid"
) -> Dict[str, Any]:

    if two_stage_mode == "ai":
        return await self._execute_with_ai_self_determination(
            task=code,
            context=context,
            timeout=timeout
        )
    else:
        # Current heuristic approach
        ...
```

---

## Cost Comparison

**Heuristic approach**: ~$0.0016 per execution
**AI self-determination**: ~$0.0021 per execution

**Difference**: +$0.0005 per execution (+31%)

For 10,000 executions/month: **+$5/month**

---

## Next Steps

1. ✅ Implementation complete
2. ✅ Tool calling integrated
3. ✅ Tests created
4. 🔧 **Your turn**: Modify prompts in `_build_self_determination_prompt()`
5. 🔧 Test with real PDFs and API keys
6. 🔧 Add feature flag to `execute()` method
7. 🔧 Decide which approach to use by default

---

## Key Differences from Previous Approach

### Before (Heuristic)
```python
# Code decides
if len(value) > 10240 and key.endswith('_b64'):
    needs_analysis = True
```

### Now (AI Self-Determination)
```python
# AI decides
# AI sees context and thinks:
# "This PDF data is complex, I should analyze it first"
# STAGE: ANALYSIS
pdf_bytes = base64.b64decode(context['pdf_data_b64'])
...
```

**The AI is smarter** - it considers:
- What the task is asking for
- What information it needs from the data
- Whether it can solve directly or needs to analyze first

---

## Questions?

See [TWO_STAGE_APPROACHES.md](TWO_STAGE_APPROACHES.md) for detailed comparison and usage guidelines.
