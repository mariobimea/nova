# PDF OCR Workflow

## How to Extract Text from Scanned PDFs using OCR

When a PDF is scanned (images only, no text layer), you CANNOT use PyMuPDF's `get_text()` directly. You need to:

1. **Convert PDF pages to images** using PyMuPDF
2. **Apply OCR to each image** using EasyOCR

## Complete Working Example

```python
import fitz  # PyMuPDF
import easyocr
import base64
import io
import json

# Step 1: Decode PDF from base64
pdf_bytes = base64.b64decode(context['pdf_data'])
pdf_stream = io.BytesIO(pdf_bytes)

# Step 2: Open PDF with PyMuPDF
doc = fitz.open(stream=pdf_stream, filetype='pdf')

# Step 3: Initialize EasyOCR reader
# Use 'en' for English, add 'es' for Spanish, etc.
reader = easyocr.Reader(['en', 'es'], gpu=False)

# Step 4: Process each page
all_text = []

for page_num in range(len(doc)):
    page = doc[page_num]

    # Convert page to image (PNG format)
    # Use higher DPI (300) for better OCR accuracy
    pix = page.get_pixmap(dpi=300)

    # Get image bytes in PNG format
    img_bytes = pix.tobytes("png")

    # Apply OCR to image bytes
    # detail=0 returns only text (no coordinates or confidence)
    result = reader.readtext(img_bytes, detail=0)

    # Add page text to results
    all_text.extend(result)

doc.close()

# Step 5: Join all extracted text
ocr_text = ' '.join(all_text)

# Step 6: Return results
print(json.dumps({
    "status": "success",
    "context_updates": {
        "ocr_text": ocr_text,
        "extraction_method_used": "easyocr"
    },
    "message": f"OCR extracted {len(ocr_text)} chars from {page_num + 1} pages"
}))
```

## Important Notes

### DO NOT do this (common mistake):
```python
# ❌ WRONG - EasyOCR cannot read PDF bytes directly
pdf_data = base64.b64decode(context['pdf_data'])
reader = easyocr.Reader(['en'])
result = reader.readtext(pdf_data)  # This will FAIL or return empty!
```

### DO this instead:
```python
# ✅ CORRECT - Convert PDF to image first, then OCR
import fitz
doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype='pdf')
pix = doc[0].get_pixmap(dpi=300)  # Page to image
img_bytes = pix.tobytes("png")     # Image as PNG bytes
result = reader.readtext(img_bytes)  # OCR the image
```

## When to Use OCR vs PyMuPDF Text Extraction

### Use PyMuPDF `get_text()` when:
- PDF has a text layer (digital PDF, searchable)
- Faster and more accurate than OCR

### Use EasyOCR when:
- PDF is scanned (no text layer)
- PDF contains images of text
- context['recommended_extraction_method'] == 'ocr'

## Performance Tips

1. **DPI setting**: Higher DPI = better accuracy but slower
   - 150 DPI: Fast but lower quality
   - 300 DPI: Good balance (recommended)
   - 600 DPI: Maximum quality but very slow

2. **GPU acceleration**: Set `gpu=True` if GPU available (much faster)

3. **Language selection**: Only include languages you need
   - `['en']` - English only
   - `['en', 'es']` - English + Spanish
   - More languages = slower initialization

## Error Handling

```python
try:
    # OCR workflow here
    ocr_text = ' '.join(all_text)
except Exception as e:
    # Fallback: return empty text on error
    ocr_text = ""
    print(json.dumps({
        "status": "error",
        "context_updates": {"ocr_text": "", "ocr_error": str(e)},
        "message": f"OCR failed: {str(e)}"
    }))
```

## Example Context Usage

```python
# Context should have:
# - pdf_data: base64 encoded PDF
# - recommended_extraction_method: 'ocr' or 'pymupdf'

recommended_method = context.get('recommended_extraction_method', 'pymupdf')

if recommended_method == 'ocr':
    # Use the OCR workflow above
    pass
elif recommended_method == 'pymupdf':
    # Use PyMuPDF get_text() instead
    doc = fitz.open(stream=pdf_stream, filetype='pdf')
    ocr_text = ''
    for page in doc:
        ocr_text += page.get_text()
    doc.close()
```
