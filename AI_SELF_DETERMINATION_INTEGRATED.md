# ✅ AI Self-Determination Integration Complete

## What Was Done

Successfully replaced the heuristic-based two-stage approach with **AI self-determination** in `CachedExecutor.execute()`.

---

## Key Changes

### 1. Modified `execute()` Method (Line 587-903)

**Before (Heuristic Approach)**:
```python
needs_analysis = self._needs_data_analysis(context)  # Code decides
if needs_analysis:
    analysis_result = await self._run_analysis_stage(...)
    enriched_context['_data_analysis'] = analysis_result

# Then generate task code
generated_code = await self._generate_code_with_tools(...)
```

**After (AI Self-Determination)**:
```python
# Stage loop (max 2 stages: analysis + task)
for stage_num in range(1, max_stages + 1):
    # AI generates code with self-determination prompt
    generated_code = await self._generate_code_with_tools(
        system_message=self._build_self_determination_prompt(...)
    )

    # Detect which stage AI chose
    detected_stage = self._detect_stage_from_code(generated_code)

    if detected_stage == "analysis":
        # Execute analysis, enrich context, continue loop
        analysis_result = await self.e2b_executor.execute(...)
        enriched_context['_data_analysis'] = analysis_result
        continue

    elif detected_stage == "task":
        # Break out, execute task code
        break

# Execute final task code
result = await self.e2b_executor.execute(generated_code, enriched_context, ...)
```

### 2. Enhanced `_generate_code_with_tools()` (Line 258-263)

Added optional `system_message` parameter:
```python
async def _generate_code_with_tools(
    self,
    task: str,
    context: Dict[str, Any],
    error_history: Optional[List[Dict]] = None,
    system_message: Optional[str] = None  # NEW!
) -> tuple[str, Dict[str, Any]]:
```

Now supports custom system prompts for AI self-determination while maintaining backward compatibility.

### 3. Deleted Old Heuristic Methods

Removed ~320 lines of heuristic code (lines 909-1229):
- ❌ `_needs_data_analysis()` - Hardcoded rules
- ❌ `_build_analysis_prompt()` - Separate analysis prompt
- ❌ `_generate_analysis_code()` - Separate analysis generation
- ❌ `_run_analysis_stage()` - Separate analysis orchestration

### 4. Kept AI Self-Determination Methods

These are now the ONLY methods used:
- ✅ `_detect_stage_from_code()` (Line 909+) - Detects stage markers
- ✅ `_build_self_determination_prompt()` (Line 1088+) - Unified prompt
- ✅ (Removed `_execute_with_ai_self_determination()` - integrated into main `execute()`)

---

## The Flow Now

```
User Request
    ↓
CachedExecutor.execute(task, context, timeout)
    ↓
┌─────────────── RETRY LOOP (max 3 attempts) ───────────────┐
│                                                            │
│  ┌──────────── STAGE LOOP (max 2 stages) ──────────────┐ │
│  │                                                       │ │
│  │  1. Build self-determination prompt                  │ │
│  │     - "You can optionally analyze data first..."     │ │
│  │                                                       │ │
│  │  2. Generate code with tool calling                  │ │
│  │     - AI searches docs if needed                     │ │
│  │     - AI decides: analysis or task?                  │ │
│  │     - AI marks code with stage identifier            │ │
│  │                                                       │ │
│  │  3. Detect stage from generated code                 │ │
│  │     - Look for "# STAGE: ANALYSIS" or "# STAGE: TASK"│ │
│  │                                                       │ │
│  │  4a. If ANALYSIS:                                    │ │
│  │      - Execute analysis code                         │ │
│  │      - Enrich context with results                   │ │
│  │      - Loop back (generate task code)                │ │
│  │                                                       │ │
│  │  4b. If TASK:                                        │ │
│  │      - Break out of stage loop                       │ │
│  │                                                       │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                            │
│  5. Execute task code with enriched context               │
│  6. Validate output                                       │
│  7. Return results with metadata                          │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

---

## Example: AI Decides to Analyze PDF

### Stage 1: AI Sees Complex Data

```
Context: {
    "pdf_data_b64": "JVBERi0xLjQKJeLjz9MKMSAwIG9iaiA8PCAv..."  # 450KB
}

Task: "Extract text from the PDF"
```

AI thinks: *"This PDF data is complex. I need to check if it's digital or scanned before extracting text."*

**AI Generates**:
```python
# STAGE: ANALYSIS
import base64
import fitz

pdf_bytes = base64.b64decode(context['pdf_data_b64'])
doc = fitz.open(stream=pdf_bytes, filetype="pdf")

text_sample = doc[0].get_text()
has_text = len(text_sample.strip()) > 50

result = {
    "pdf_type": "digital" if has_text else "scanned",
    "pages": len(doc),
    "recommended_method": "pymupdf" if has_text else "easyocr"
}

print(json.dumps({"status": "success", "context_updates": result}))
```

System:
- ✅ Detects `# STAGE: ANALYSIS`
- ✅ Executes code
- ✅ Enriches context with `_data_analysis`

### Stage 2: AI Gets Analysis Results

```
Context: {
    "pdf_data_b64": "JVBERi0...",
    "_data_analysis": {
        "pdf_type": "digital",
        "pages": 3,
        "recommended_method": "pymupdf"
    }
}

Task: "Extract text from the PDF"
```

AI thinks: *"Great! The analysis says it's a digital PDF with text layer. I'll use PyMuPDF to extract text."*

**AI Generates**:
```python
# STAGE: TASK
import base64
import fitz

# Use analysis recommendation
pdf_bytes = base64.b64decode(context['pdf_data_b64'])
doc = fitz.open(stream=pdf_bytes, filetype="pdf")

# Extract text from all pages
full_text = ""
for page in doc:
    full_text += page.get_text()

result = {
    "extracted_text": full_text,
    "method_used": "pymupdf",
    "pages_processed": len(doc)
}

print(json.dumps({"status": "success", "context_updates": result}))
```

System:
- ✅ Detects `# STAGE: TASK`
- ✅ Executes code
- ✅ Returns results

---

## Example: AI Decides NO Analysis Needed

### Direct to Task

```
Context: {
    "email_subject": "Invoice #12345",
    "total_amount": 1500.50
}

Task: "Extract the amount from context"
```

AI thinks: *"Simple data, just strings and numbers. I can solve this directly."*

**AI Generates**:
```python
# STAGE: TASK
amount = context['total_amount']

result = {
    "extracted_amount": amount,
    "currency": "EUR"  # Assumed based on context
}

print(json.dumps({"status": "success", "context_updates": result}))
```

System:
- ✅ Detects `# STAGE: TASK`
- ✅ Executes code (no analysis stage)
- ✅ Returns results

---

## Metadata Tracking

Results now include AI self-determination metadata:

```python
{
    "extracted_text": "...",
    "_ai_metadata": {
        "two_stage_enabled": True,
        "ai_self_determined": True,  # NEW!
        "stages_used": 2,  # 1=direct, 2=analysis+task

        # Analysis stage (if ran)
        "analysis_metadata": {
            "analysis_code": "...",
            "generation_time_ms": 1200,
            "execution_time_ms": 850,
            "tool_calls": [...]
        },

        # Task stage
        "generated_code": "...",
        "generation_time_ms": 1500,
        "execution_time_ms": 2000,
        "tool_calls": [...]
    }
}
```

---

## Tool Calling Integration

**IMPORTANT**: Tool calling (`search_documentation()`) is available at **ALL stages**:

```python
# Stage 1: AI can search docs for analysis
# STAGE: ANALYSIS
# AI first searches "pymupdf check text layer"
pdf_bytes = base64.b64decode(context['pdf_data_b64'])
doc = fitz.open(stream=pdf_bytes, filetype="pdf")
has_text = bool(doc[0].get_text().strip())
...

# Stage 2: AI can search docs for task
# STAGE: TASK
# AI searches "easyocr python usage"
import easyocr
reader = easyocr.Reader(['en'])
result = reader.readtext(image_bytes)
...
```

Tool calling happens in `_generate_code_with_tools()` which is called for BOTH stages.

---

## Files Modified

1. **src/core/executors.py**
   - Modified `execute()` (line 587-903) - New flow with AI self-determination
   - Enhanced `_generate_code_with_tools()` (line 258-263) - Added `system_message` param
   - Deleted heuristic methods (removed 320 lines)
   - Kept AI self-determination methods (line 909+)

---

## What to Test

### Test 1: PDF with Analysis
```bash
python3 test_ai_self_determination.py
```

Expected:
- Stage 1: AI generates ANALYSIS code
- Stage 2: AI generates TASK code using analysis

### Test 2: Simple Data (No Analysis)
Same test file, second test case.

Expected:
- Stage 1: AI generates TASK code directly
- No Stage 2

### Test 3: Invoice Processing Workflow
```bash
# Deploy and test with real workflow
python3 scripts/test_workflow.py fixtures/invoice_ai_workflow.json
```

---

## Prompt Customization

You can now modify the AI self-determination prompt in `_build_self_determination_prompt()` (line ~1088):

```python
def _build_self_determination_prompt(
    self,
    task: str,
    context_summary: str,
    is_first_stage: bool
) -> str:
    if is_first_stage:
        stage_instructions = """
OPTIONAL TWO-STAGE APPROACH:

If the context contains complex data (PDFs, images, large base64 strings, binary data)
that you need to UNDERSTAND before solving the task:

1. First, generate ANALYSIS code marked with:
   # STAGE: ANALYSIS

   [... modify this section ...]
```

---

## Summary

**✅ What Changed**:
- Heuristic approach → AI self-determination
- Separate analysis methods → Unified flow
- Hardcoded rules → AI decides

**✅ What Stayed**:
- Tool calling (documentation search)
- Retry loop (3 attempts)
- Validation (output + serialization)
- Metadata tracking

**✅ Benefits**:
- More flexible (AI adapts to any data type)
- Context-aware (AI considers task requirements)
- Cleaner code (320 lines removed)
- Same cost (~$0.0005 extra per execution)

**✅ Ready to**:
- Test with real PDFs
- Customize prompts
- Deploy to production
