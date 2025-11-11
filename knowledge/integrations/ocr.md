# EasyOCR - Optical Character Recognition

## Overview

EasyOCR is a ready-to-use OCR library with 80+ supported languages and all popular writing scripts including Latin, Chinese, Arabic, Devanagari, Cyrillic and etc.

**Pre-installed in NOVA E2B Template:**
- **Version**: 1.7.2
- **PyTorch Backend**: CPU-only (2.1.0+cpu)
- **Pre-downloaded Models**: Spanish (es) + English (en)
- **Accuracy**: 90-95% on clean scans, 85-90% on difficult scans

**When to use EasyOCR:**
- PDF is scanned/image-based (no text layer)
- Handwritten documents
- Low-quality scans
- Multi-language documents (Spanish + English)

**When NOT to use EasyOCR:**
- PDF has text layer (use PyMuPDF instead - faster)
- Speed is critical (OCR is slower than text extraction)

---

## Installation (Already Installed)

EasyOCR is pre-installed in the NOVA E2B sandbox with Spanish and English models pre-downloaded.

```python
# Already available - no installation needed
import easyocr
```

For reference, standard installation would be:
```bash
pip install easyocr
```

---

## Basic Usage

### Step 1: Create Reader (Once)

The Reader loads models into memory. This should be done **once** and reused for multiple images.

```python
import easyocr

# Initialize reader with language codes
# gpu=False is REQUIRED in NOVA (sandbox is CPU-only)
reader = easyocr.Reader(['es', 'en'], gpu=False)
```

**Language Codes:**
- English: `'en'`
- Spanish: `'es'`
- Multiple languages: `['es', 'en']` (English is compatible with all languages)

**Important Parameters:**
- `lang_list` (list): List of language codes to recognize
- `gpu` (bool): **MUST be False** in NOVA sandbox (CPU-only environment)
- `model_storage_directory` (str, optional): Custom path for models (default: `~/.EasyOCR/model`)
- `download_enabled` (bool): Auto-download missing models (default: True)

### Step 2: Read Text from Image

```python
# Read text from image file
result = reader.readtext('image.jpg')

# Result format (detail=1, default):
# [
#   ([[x1,y1], [x2,y2], [x3,y3], [x4,y4]], 'detected text', confidence),
#   ...
# ]

# Example output:
# [
#   ([[189, 75], [469, 75], [469, 165], [189, 165]], 'INVOICE', 0.9876),
#   ([[70, 200], [300, 200], [300, 250], [70, 250]], 'Total: $1,234.56', 0.9234)
# ]
```

---

## readtext() Method - Complete API

```python
reader.readtext(
    image,                  # REQUIRED: file path, numpy array, bytes, or URL
    decoder='greedy',       # 'greedy', 'beamsearch', or 'wordbeamsearch'
    beamWidth=5,           # Beam width for beamsearch decoder
    batch_size=1,          # Higher = faster but more memory
    workers=0,             # Number of CPU workers
    allowlist=None,        # Force recognition of only these characters
    blocklist=None,        # Exclude these characters from recognition
    detail=1,              # 1 = full details, 0 = text only
    rotation_info=None,    # List of angles [90, 180, 270] to try
    paragraph=False,       # Combine results into paragraphs
    min_size=20,           # Minimum text box height
    contrast_ths=0.1,      # Threshold for low-contrast text
    adjust_contrast=0.5,   # Contrast adjustment level
    filter_ths=0.003,      # Text box filtering threshold
    text_threshold=0.7,    # Text detection confidence threshold
    low_text=0.4,          # Low text threshold
    link_threshold=0.4,    # Link threshold for text connection
    canvas_size=2560,      # Maximum image dimension
    mag_ratio=1.0,         # Magnification ratio
    slope_ths=0.1,         # Slope threshold for merging boxes
    ycenter_ths=0.5,       # Y-center threshold for merging
    height_ths=0.5,        # Height threshold for merging
    width_ths=0.5,         # Width threshold for merging
    y_ths=0.5,             # Y-distance threshold
    x_ths=1.0,             # X-distance threshold
    add_margin=0.1         # Margin to add around text boxes
)
```

**Most Important Parameters:**

- **image**: Input image (file path, numpy array, bytes, or URL)
- **detail**:
  - `1` (default): Returns `[coordinates, text, confidence]`
  - `0`: Returns just the text strings (simplified)
- **paragraph**:
  - `False` (default): Each detected box is separate
  - `True`: Combines results into readable paragraphs
- **allowlist**: String of allowed characters (e.g., `'0123456789.$,'` for currency)
- **blocklist**: String of characters to exclude
- **batch_size**: Higher values process faster but use more memory (default: 1)

---

## Common Use Cases

### Use Case 1: Extract Text from Scanned PDF (Using pdf_data from Context)

**IMPORTANT**: In NOVA workflows, PDFs are stored as `pdf_data` (base64-encoded string in context).
You MUST decode it to bytes, then convert PDF pages to images using PyMuPDF.

```python
import easyocr
import pymupdf  # PyMuPDF (also known as 'fitz')
import base64
import io
import json
import numpy as np
from PIL import Image

try:
    # Get PDF data from context (base64 string)
    pdf_data_base64 = context.get("pdf_data")

    if not pdf_data_base64:
        raise ValueError("Missing pdf_data in context")

    # Decode base64 to bytes
    pdf_data = base64.b64decode(pdf_data_base64)

    # Open PDF from bytes
    pdf_stream = io.BytesIO(pdf_data)
    doc = pymupdf.open(stream=pdf_stream, filetype='pdf')

    # Initialize EasyOCR reader (CPU-only)
    reader = easyocr.Reader(['es', 'en'], gpu=False)

    # Extract text from all pages using OCR
    all_text = []

    for page_num in range(doc.page_count):
        page = doc[page_num]

        # Convert PDF page to image (pixmap)
        pix = page.get_pixmap(dpi=200)  # 200 DPI for good quality

        # Convert pixmap to PIL Image
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))

        # Convert PIL Image to numpy array (EasyOCR accepts numpy arrays)
        img_array = np.array(img)

        # Extract text from page using OCR
        result = reader.readtext(img_array, detail=0, paragraph=True)

        # Join results
        page_text = '\n'.join(result)
        all_text.append(page_text)

    # Close PDF
    doc.close()

    # Combine all pages
    full_text = '\n\n--- PAGE BREAK ---\n\n'.join(all_text)

    # Return result
    print(json.dumps({
        "status": "success",
        "context_updates": {
            "ocr_text": full_text,
            "page_count": doc.page_count,
            "ocr_method": "EasyOCR"
        },
        "message": f"Extracted text from {doc.page_count} pages using OCR"
    }))

except Exception as e:
    print(json.dumps({
        "status": "error",
        "context_updates": {},
        "message": f"OCR extraction failed: {str(e)}"
    }))
```

**Key Steps:**
1. Decode `pdf_data` (base64 string) → bytes
2. Open PDF with PyMuPDF from bytes
3. Convert each page to image using `page.get_pixmap()`
4. Convert pixmap to PIL Image → numpy array
5. Pass numpy array to `reader.readtext()`
6. Always close the PDF with `doc.close()`

### Use Case 2: Extract Specific Fields (Invoice Total)

```python
import easyocr
import re
import json

try:
    # Get image path from context
    image_path = context.get("invoice_image_path")

    if not image_path:
        raise ValueError("Missing invoice_image_path in context")

    # Initialize reader
    reader = easyocr.Reader(['es', 'en'], gpu=False)

    # Extract all text with coordinates
    results = reader.readtext(image_path, detail=1)

    # Search for total amount
    total_amount = None

    for (bbox, text, confidence) in results:
        # Look for patterns like "Total: $1,234.56" or "TOTAL 1234.56"
        if 'total' in text.lower():
            # Extract numbers from text
            numbers = re.findall(r'\d+[,.]?\d*', text)
            if numbers:
                # Clean and parse
                amount_str = numbers[-1].replace(',', '')
                total_amount = float(amount_str)
                break

    if total_amount is None:
        raise ValueError("Could not find total amount in invoice")

    # Return result
    print(json.dumps({
        "status": "success",
        "context_updates": {
            "invoice_total": total_amount,
            "ocr_confidence": "high" if confidence > 0.9 else "medium"
        },
        "message": f"Extracted total: ${total_amount}"
    }))

except Exception as e:
    print(json.dumps({
        "status": "error",
        "context_updates": {},
        "message": f"Failed to extract total: {str(e)}"
    }))
```

### Use Case 3: Simplified Text Extraction (detail=0)

```python
import easyocr
import json

try:
    # Get image from context
    image_path = context.get("image_path")

    if not image_path:
        raise ValueError("Missing image_path in context")

    # Initialize reader
    reader = easyocr.Reader(['es', 'en'], gpu=False)

    # Extract text (simplified output - just text strings)
    text_list = reader.readtext(image_path, detail=0)

    # Join into single string
    full_text = '\n'.join(text_list)

    # Return result
    print(json.dumps({
        "status": "success",
        "context_updates": {
            "extracted_text": full_text,
            "line_count": len(text_list)
        },
        "message": f"Extracted {len(text_list)} lines of text"
    }))

except Exception as e:
    print(json.dumps({
        "status": "error",
        "context_updates": {},
        "message": f"OCR failed: {str(e)}"
    }))
```

### Use Case 4: Extract Only Numbers (allowlist)

```python
import easyocr
import json

try:
    # Get invoice image
    image_path = context.get("invoice_image_path")

    if not image_path:
        raise ValueError("Missing invoice_image_path in context")

    # Initialize reader
    reader = easyocr.Reader(['es', 'en'], gpu=False)

    # Extract only numbers, dots, and commas (useful for amounts)
    results = reader.readtext(
        image_path,
        detail=0,
        allowlist='0123456789.,$€'  # Only recognize these characters
    )

    # Filter out non-numeric results
    amounts = []
    for text in results:
        # Remove currency symbols
        cleaned = text.replace('$', '').replace('€', '').replace(',', '').strip()
        try:
            amount = float(cleaned)
            amounts.append(amount)
        except ValueError:
            continue

    # Return result
    print(json.dumps({
        "status": "success",
        "context_updates": {
            "extracted_amounts": amounts,
            "total_found": sum(amounts) if amounts else 0
        },
        "message": f"Found {len(amounts)} numeric values"
    }))

except Exception as e:
    print(json.dumps({
        "status": "error",
        "context_updates": {},
        "message": f"Amount extraction failed: {str(e)}"
    }))
```

---

## Output Formats

### Detailed Output (detail=1, default)

```python
result = reader.readtext('invoice.jpg', detail=1)

# Returns: List of tuples
# [
#   (bounding_box, text, confidence),
#   ...
# ]

# Example:
# [
#   ([[189, 75], [469, 75], [469, 165], [189, 165]], 'FACTURA', 0.9876),
#   ([[70, 200], [300, 200], [300, 250], [70, 250]], 'Total: $1,234.56', 0.9234)
# ]

# Access components:
for (bbox, text, confidence) in result:
    print(f"Text: {text}")
    print(f"Confidence: {confidence:.2%}")
    print(f"Coordinates: {bbox}")
```

### Simplified Output (detail=0)

```python
result = reader.readtext('invoice.jpg', detail=0)

# Returns: List of strings
# ['FACTURA', 'Total: $1,234.56', ...]

# Example:
text_only = result  # ['line 1', 'line 2', ...]
full_text = '\n'.join(result)
```

### Paragraph Mode (paragraph=True)

```python
result = reader.readtext('document.jpg', paragraph=True)

# Returns: Same format as detail=1, but with combined text boxes
# Useful for documents where you want natural reading flow
```

---

## Best Practices

### DO:
- ✅ Use `gpu=False` (REQUIRED in NOVA - CPU-only sandbox)
- ✅ Pre-process images for better accuracy:
  - Convert to grayscale if colored background interferes
  - Increase DPI for small text (200-300 DPI recommended)
  - Crop to region of interest to reduce noise
- ✅ Use `allowlist` for structured data (invoices, forms)
- ✅ Check confidence scores (`confidence > 0.8` is good)
- ✅ Combine with regex for field extraction
- ✅ Handle OCR errors gracefully (low confidence = manual review)

### DON'T:
- ❌ Use `gpu=True` (will crash - sandbox has no GPU)
- ❌ Process very large images without resizing (memory limits)
- ❌ Expect 100% accuracy (always validate critical data)
- ❌ Use OCR when PDF has text layer (use PyMuPDF instead)
- ❌ Store `reader` object in context (not JSON-serializable)

---

## Performance Characteristics

**Cold Start Time:**
- First execution: ~2-3 seconds (models already pre-downloaded)
- Subsequent executions: ~0.5-1 second

**Processing Time:**
- Single page (A4, 200 DPI): ~3-5 seconds
- Multi-page document: ~3-5 seconds per page

**Memory Usage:**
- Reader initialization: ~500 MB RAM
- Processing: +100-200 MB per page

**Accuracy:**
- Clean scans (high quality): 90-95%
- Difficult scans (low quality, handwritten): 85-90%
- vs Tesseract: +15-20% accuracy improvement

---

## Error Handling

```python
import easyocr
import json

try:
    # Initialize reader
    reader = easyocr.Reader(['es', 'en'], gpu=False)

    # Get image from context
    image_path = context.get("image_path")

    if not image_path:
        raise ValueError("Missing image_path in context")

    # Extract text
    result = reader.readtext(image_path, detail=0)

    if not result:
        raise ValueError("No text detected in image")

    # Success
    print(json.dumps({
        "status": "success",
        "context_updates": {
            "ocr_text": '\n'.join(result)
        },
        "message": "OCR completed successfully"
    }))

except FileNotFoundError as e:
    print(json.dumps({
        "status": "error",
        "context_updates": {},
        "message": f"Image file not found: {str(e)}"
    }))

except ValueError as e:
    print(json.dumps({
        "status": "error",
        "context_updates": {},
        "message": f"Validation error: {str(e)}"
    }))

except Exception as e:
    print(json.dumps({
        "status": "error",
        "context_updates": {},
        "message": f"OCR error: {str(e)}"
    }))
```

---

## JSON Serialization Rules

**✅ ALLOWED** (Safe to store in context):
```python
# Strings
"ocr_text": "Extracted text here"

# Numbers
"confidence": 0.95

# Lists of primitives
"extracted_lines": ["line 1", "line 2"]

# Dicts of primitives
"invoice_data": {"total": 1234.56, "date": "2024-11-10"}
```

**❌ NOT ALLOWED** (Will cause serialization errors):
```python
# ❌ EasyOCR Reader object
"reader": reader  # Not JSON-serializable

# ❌ PIL Image objects
"image": img  # Not JSON-serializable

# ❌ Numpy arrays
"image_array": np_array  # Not JSON-serializable
```

**Solution**: Always extract primitive values (strings, numbers, lists) from complex objects.

---

## References

- **Official Documentation**: https://www.jaided.ai/easyocr/documentation/
- **GitHub Repository**: https://github.com/JaidedAI/EasyOCR
- **PyPI Package**: https://pypi.org/project/easyocr/
- **Tutorial**: https://www.jaided.ai/easyocr/tutorial/

---

**Last Updated**: November 2025
**Version**: 1.7.2
**Pre-installed in**: NOVA E2B Template (ybdni0ui0l3vsumat82v)
