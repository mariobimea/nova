# PDF Processing - PyMuPDF (fitz)

**Official Documentation**: https://github.com/pymupdf/pymupdf

Extract text and data from PDF files using PyMuPDF (fitz) in NOVA workflows.

---

## Basic Usage: Open PDF and Extract Text

Import the library as `pymupdf` (or `fitz` for backward compatibility):

```python
import pymupdf  # or: import fitz

doc = pymupdf.open("example.pdf")  # open a document
for page in doc:  # iterate the document pages
    text = page.get_text()  # get plain text encoded as UTF-8
    print(text)

doc.close()  # always close when done
```

---

## Open PDF from Bytes (Base64)

**IMPORTANT**: In NOVA workflows, `pdf_data` is stored as a **base64-encoded string**. You MUST decode it first.

```python
import pymupdf
import io
import base64
import json

# Get PDF data from context (base64 string)
pdf_data_base64 = context['pdf_data']

# Decode base64 to bytes
pdf_data = base64.b64decode(pdf_data_base64)

# Open PDF from bytes
pdf_stream = io.BytesIO(pdf_data)
doc = pymupdf.open(stream=pdf_stream, filetype='pdf')

print(json.dumps({
    "status": "success",
    "context_updates": {
        "pdf_pages": doc.page_count
    }
}))

# Always close
doc.close()
```

**Alternative approach** (open from bytes directly):

```python
import pymupdf

# Open from byte stream (e.g., read from a file in binary mode)
with open("example.pdf", "rb") as file:
    file_content = file.read()
    doc = pymupdf.open(stream=file_content, filetype="pdf")

doc.close()
```

---

## Extract Text from All Pages

```python
import pymupdf
import io
import json
import base64

try:
    # Decode base64 to bytes
    pdf_data_base64 = context['pdf_data']
    pdf_data = base64.b64decode(pdf_data_base64)

    # Open PDF
    pdf_stream = io.BytesIO(pdf_data)
    doc = pymupdf.open(stream=pdf_stream, filetype='pdf')

    # Extract text from all pages
    full_text = ''
    for page in doc:
        full_text += page.get_text()

    doc.close()

    print(json.dumps({
        "status": "success",
        "context_updates": {
            "pdf_text": full_text,
            "pdf_pages": doc.page_count
        }
    }))

except Exception as e:
    print(json.dumps({
        "status": "error",
        "message": f"PDF processing error: {str(e)}"
    }))
```

---

## Extract Text with Different Formats

PyMuPDF supports multiple output formats:

```python
import pymupdf

doc = pymupdf.open("document.pdf")
page = doc[0]

# Plain text extraction
text = page.get_text()

# HTML format with positioning and styling
html = page.get_text("html")

# Structured dictionary format with detailed positioning
text_dict = page.get_text("dict")
for block in text_dict["blocks"]:
    if block["type"] == 0:  # Text block
        for line in block["lines"]:
            for span in line["spans"]:
                print(f"Text: {span['text']}, Font: {span['font']}, Size: {span['size']}")

# Extract with flags for better control
text_preserved = page.get_text("text", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)

doc.close()
```

---

## Search Text in PDF

```python
import pymupdf

doc = pymupdf.open("document.pdf")
page = doc[0]

search_term = "Total"

# Returns list of bounding boxes where term was found
areas = page.search_for(search_term)

if areas:
    print(f"Found '{search_term}' in {len(areas)} locations")

doc.close()
```

---

## Extract Text from Specific Rectangle

```python
import pymupdf

doc = pymupdf.open("document.pdf")
page = doc[0]

# Define rectangle (x0, y0, x1, y1)
rect = pymupdf.Rect(0, 0, 200, 100)

# Extract text only from this area
text_in_box = page.get_textbox(rect)
print(f"Text in rectangle: {text_in_box}")

doc.close()
```

---

## Complete Example: Extract Invoice Amount

Extract text → Search for invoice amount → Return structured data

```python
import pymupdf
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
    doc = pymupdf.open(stream=pdf_stream, filetype='pdf')

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
            "pdf_pages": doc.page_count,
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

## Extract Images from PDF

```python
import pymupdf

doc = pymupdf.open("document.pdf")

# Extract all images from document
for page_num in range(doc.page_count):
    image_list = doc.get_page_images(page_num)

    for img_index, img in enumerate(image_list):
        xref = img[0]  # xref number

        # Extract image
        image_dict = doc.extract_image(xref)
        image_bytes = image_dict["image"]
        image_ext = image_dict["ext"]

        # Save to file
        filename = f"image_p{page_num}_i{img_index}.{image_ext}"
        with open(filename, "wb") as f:
            f.write(image_bytes)

        print(f"Saved {filename} ({image_dict['width']}x{image_dict['height']})")

doc.close()
```

---

## Key Points

- **Always close**: Call `doc.close()` to free memory
- **Check for text**: Scanned PDFs may have no extractable text (use OCR in that case)
- **Base64 decoding**: In NOVA, `pdf_data` is base64-encoded, decode it first
- **Handle errors**: Wrap in try/except for malformed PDFs
- **Limit pages**: For huge PDFs, process max 50 pages to avoid timeout
- **Use `page_count`**: Access via `doc.page_count` (not `len(doc)`)

---

**Integration**: PDF Processing (PyMuPDF / fitz)
**Use with**: Invoice processing, document extraction, form reading
**Official Docs**: https://pymupdf.readthedocs.io/
