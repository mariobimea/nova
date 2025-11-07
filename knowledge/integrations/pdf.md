# PDF Processing - PyMuPDF (fitz)

Extract text and data from PDF files using PyMuPDF (fitz) in NOVA workflows.

---

## Overview

**Capabilities**: Open PDFs from bytes/files, extract text, search text, extract images, read forms, get metadata.

**Use cases**: Extract invoice amounts, process PDF attachments, search keywords, read form data.

**Import**: Use `import fitz` (PyMuPDF library).

---

## Open PDF from Base64 String

⚠️ **IMPORTANT**: In NOVA workflows, `pdf_data` is stored as a **base64-encoded string** (not raw bytes). You MUST decode it first.

```python
import fitz
import io
import json
import base64

# Get PDF data from context (base64 string)
pdf_data_base64 = context['pdf_data']

# Decode base64 to bytes
pdf_data = base64.b64decode(pdf_data_base64)

# Open PDF from bytes
pdf_stream = io.BytesIO(pdf_data)
doc = fitz.open(stream=pdf_stream, filetype='pdf')

print(json.dumps({
    "status": "success",
    "context_updates": {
        "pdf_pages": len(doc)
    }
}))

# Always close
doc.close()
```

---

## Extract Text from All Pages

```python
import fitz
import io
import json
import base64

# Decode base64 to bytes
pdf_data_base64 = context['pdf_data']
pdf_data = base64.b64decode(pdf_data_base64)

pdf_stream = io.BytesIO(pdf_data)
doc = fitz.open(stream=pdf_stream, filetype='pdf')

# Extract text from all pages
full_text = ''
for page in doc:
    full_text += page.get_text()

doc.close()

print(json.dumps({
    "status": "success",
    "context_updates": {
        "pdf_text": full_text,
        "pdf_pages": len(doc)
    }
}))
```

---

## Search Text in PDF

```python
# Search on first page
page = doc[0]
search_term = "Total"

# Returns list of bounding boxes
areas = page.search_for(search_term)

if areas:
    print(json.dumps({
        "status": "success",
        "context_updates": {
            "search_term": search_term,
            "matches_found": len(areas)
        }
    }))
```

---

## Complete Example

Extract text → Search for invoice amount → Return structured data

```python
import fitz
import io
import re
import json
import base64

try:
    # Get PDF from context (base64 string)
    pdf_data_base64 = context['pdf_data']
    pdf_filename = context.get('pdf_filename', 'unknown.pdf')

    # Decode base64 to bytes
    pdf_data = base64.b64decode(pdf_data_base64)

    # Open PDF
    pdf_stream = io.BytesIO(pdf_data)
    doc = fitz.open(stream=pdf_stream, filetype='pdf')

    # Extract text from all pages
    full_text = ''
    for page in doc:
        full_text += page.get_text()

    # Search for invoice amount patterns
    amount_patterns = [
        r'total[:\s]+€?\s*(\d+[.,]\d{2})',
        r'amount[:\s]+€?\s*(\d+[.,]\d{2})',
        r'€\s*(\d+[.,]\d{2})',
    ]

    amount_found = None
    for pattern in amount_patterns:
        matches = re.findall(pattern, full_text, re.IGNORECASE)
        if matches:
            # Take last match (usually the total)
            amount_str = matches[-1].replace(',', '.')
            amount_found = float(amount_str)
            break

    doc.close()

    # Return results
    print(json.dumps({
        "status": "success",
        "context_updates": {
            "pdf_filename": pdf_filename,
            "pdf_pages": len(doc),
            "pdf_text": full_text,
            "total_amount": amount_found or 0.0,
            "amount_found": amount_found is not None
        }
    }))

except Exception as e:
    print(json.dumps({
        "status": "error",
        "message": f"PDF processing error: {str(e)}"
    }))
```

---

## Key Points

- **Always close**: Call `doc.close()` to free memory
- **Check for text**: Scanned PDFs may have no extractable text
- **Validate pdf_data**: Check it's bytes before `BytesIO()`
- **Handle errors**: Wrap in try/except for malformed PDFs
- **Limit pages**: For huge PDFs, process max 50 pages to avoid timeout

---

**Integration**: PDF Processing (PyMuPDF / fitz)
**Use with**: Invoice processing, document extraction, form reading
