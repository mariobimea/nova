# Two-Stage Code Generation Approaches

NOVA now has **two different approaches** for two-stage code generation. Both solve the same problem (AI needs to understand complex data before generating task code), but use different decision mechanisms.

---

## The Problem

When context contains complex data (PDFs, images, large text), the AI is "blind" to it because:
- Context summarization truncates large fields to 100 chars
- Passing full binary data is too expensive (~179K tokens for a 450KB PDF)
- AI can't determine file type/format without analyzing it first

**Result**: AI generates incorrect code (e.g., tries to extract text from a scanned PDF that needs OCR)

---

## Solution: Two-Stage Generation

### Stage 1 (Optional): Data Analysis
- AI generates code to analyze the data structure/content
- Code runs, extracts metadata (type, format, properties)
- Context is enriched with analysis results

### Stage 2 (Always): Task Execution
- AI generates task-solving code
- Uses enriched context (including analysis results)
- More accurate because AI now "knows" the data

---

## Approach 1: Heuristic-Based (Current Default)

**Decision maker**: Python code with hardcoded rules

### How It Works

```python
# CachedExecutor.execute() calls:
needs_analysis = self._needs_data_analysis(context)

if needs_analysis:
    # Run Stage 1 (analysis)
    analysis_result = await self._run_analysis_stage(...)
    enriched_context['_data_analysis'] = analysis_result

# Run Stage 2 (task) with enriched context
```

### Decision Logic

Triggers Stage 1 if any of:
- Large base64 data (>10KB) → likely PDF/image
- Keys containing "pdf", "image", "file", "attachment" → file-like data
- Large text fields (>50KB) → needs summarization

### Pros
- ✅ Fast decision (no AI call needed)
- ✅ Predictable behavior
- ✅ Easy to debug (clear rules)

### Cons
- ❌ Rigid: can't adapt to new data types
- ❌ May miss edge cases not covered by rules
- ❌ May trigger unnecessarily (false positives)

### Files
- Implementation: [executors.py](src/core/executors.py) lines 807-1173
- Test: [test_two_stage.py](test_two_stage.py)

---

## Approach 2: AI Self-Determination (New)

**Decision maker**: The AI itself

### How It Works

```python
# AI receives task + context summary
# AI decides: "Do I need to analyze this data first?"

# Option A: AI thinks analysis is needed
# STAGE: ANALYSIS
pdf_bytes = base64.b64decode(context['pdf_data_b64'])
doc = fitz.open(stream=pdf_bytes, filetype="pdf")
result = {"type": "pdf", "has_text": ...}

# System detects stage, executes, enriches context, loops back

# Option B: AI thinks data is simple
# STAGE: TASK
amount = context['amount']
result = {"extracted_amount": amount}
```

### Decision Logic

AI decides based on:
- Task requirements (what does the task need to know?)
- Data complexity (is this data simple or complex?)
- Self-assessment ("can I solve this now, or do I need to understand the data first?")

### Pros
- ✅ Flexible: adapts to any data type
- ✅ Context-aware: considers task requirements
- ✅ Self-improving: learns from experience (future)

### Cons
- ❌ Slower: requires AI call for decision
- ❌ Less predictable: AI might make wrong decision
- ❌ Harder to debug: decision is "black box"

### Files
- Implementation: [executors.py](src/core/executors.py) lines 1175-1460
- Test: [test_ai_self_determination.py](test_ai_self_determination.py)

---

## Tool Calling Integration

**IMPORTANT**: Both approaches support tool calling (documentation search).

The `search_documentation(library, query)` tool is available at **ANY stage**:

```python
# AI can search docs during analysis
# STAGE: ANALYSIS
# (AI searches "pymupdf" to learn how to check for text layer)
pdf_bytes = base64.b64decode(context['pdf_data_b64'])
doc = fitz.open(stream=pdf_bytes, filetype="pdf")
result = {"has_text": bool(doc[0].get_text())}

# AI can search docs during task execution
# STAGE: TASK
# (AI searches "pytesseract" to learn OCR API)
from PIL import Image
import pytesseract
text = pytesseract.image_to_string(...)
```

Tool calling happens **before** stage detection, so the AI has full access to documentation in both approaches.

---

## Comparison Table

| Feature | Heuristic-Based | AI Self-Determination |
|---------|----------------|----------------------|
| **Decision Speed** | Instant | +1 AI call (~500ms) |
| **Token Cost** | $0 | +$0.0005 per decision |
| **Flexibility** | Low (fixed rules) | High (adaptive) |
| **Predictability** | High | Medium |
| **Debuggability** | Easy | Harder |
| **False Positives** | Possible | Less likely |
| **Tool Calling** | ✅ Supported | ✅ Supported |
| **Best For** | Known data types | Novel/unexpected data |

---

## Which Approach to Use?

### Use Heuristic-Based When:
- You have **known data types** (PDFs, images, emails)
- You need **predictable behavior** for auditing
- You want to **minimize costs**
- You're dealing with **high volume** (thousands of executions)

### Use AI Self-Determination When:
- You're handling **diverse/unknown data types**
- You want **maximum flexibility**
- You need AI to **adapt to task requirements**
- You're willing to trade cost for accuracy

### Hybrid Approach (Future):
- Use heuristics for common cases (fast path)
- Fall back to AI decision for edge cases
- Feature flag: `two_stage_mode: "heuristic" | "ai" | "hybrid"`

---

## Implementation Status

### ✅ Completed
- Heuristic-based approach (lines 807-1173)
- AI self-determination approach (lines 1175-1460)
- Tests for both approaches
- Tool calling integration

### 🔧 To Do
- Add feature flag to switch between approaches
- Modify prompts (user wants to customize them)
- Test with real PDFs and API keys
- Add hybrid mode
- Document prompt engineering best practices

---

## Cost Analysis

### Example: Invoice Processing with 450KB PDF

**Approach 1 (Heuristic)**:
- Decision: $0 (code-based)
- Stage 1 (analysis): $0.0008 (~3.8K tokens)
- Stage 2 (task): $0.0008 (~3.8K tokens)
- **Total: ~$0.0016 per execution**

**Approach 2 (AI Self-Determination)**:
- Decision: $0.0005 (~2K tokens, AI decides)
- Stage 1 (analysis): $0.0008 (~3.8K tokens)
- Stage 2 (task): $0.0008 (~3.8K tokens)
- **Total: ~$0.0021 per execution**

**Difference**: +31% cost for AI self-determination (~$0.0005 per execution)

For 10,000 executions/month:
- Heuristic: $16/month
- AI Self-Determination: $21/month
- **Extra cost: $5/month for more flexibility**

---

## Next Steps

1. **Test both approaches** with real PDFs
2. **User customizes prompts** (especially AI self-determination prompt)
3. **Add feature flag** to switch approaches:
   ```python
   executor = CachedExecutor(
       db_session=session,
       two_stage_mode="ai"  # "heuristic" | "ai" | "hybrid"
   )
   ```
4. **Collect metrics** on decision accuracy
5. **Consider hybrid mode** for best of both worlds

---

## Code References

### Heuristic-Based
- `_needs_data_analysis()` - [executors.py:807](src/core/executors.py#L807)
- `_run_analysis_stage()` - [executors.py:1032](src/core/executors.py#L1032)

### AI Self-Determination
- `_detect_stage_from_code()` - [executors.py:1179](src/core/executors.py#L1179)
- `_execute_with_ai_self_determination()` - [executors.py:1207](src/core/executors.py#L1207)
- `_build_self_determination_prompt()` - [executors.py:1362](src/core/executors.py#L1362)

### Tool Calling
- `_generate_code_with_tools()` - [executors.py:320](src/core/executors.py#L320)
- Tool definition - [ai/tools.py](src/core/ai/tools.py)
