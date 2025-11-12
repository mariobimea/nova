# PyMuPDF Official Tutorial

## Importing PyMuPDF

To begin working with PyMuPDF, use this import statement:

```python
import pymupdf
print(pymupdf.__doc__)
```

### Historical Note on the Name

Early versions used `fitz` as the import name. This historical name comes from MuPDF's rendering engine, originally called "Fitz," which was designed to replace aging graphics libraries. Modern versions use `pymupdf` but maintain `fitz` as a fallback for compatibility.

## Opening Documents

Access supported file types with:

```python
doc = pymupdf.open(filename)  # or pymupdf.Document(filename)
```

The filename parameter accepts strings or `pathlib.Path` objects. You can also open documents from memory or create new PDFs. The Document class supports context manager usage.

## Document Properties and Methods

| Method/Attribute | Purpose |
|---|---|
| `Document.page_count` | Returns total page count (integer) |
| `Document.metadata` | Dictionary with document metadata |
| `Document.get_toc()` | Retrieves table of contents as nested list |
| `Document.load_page()` | Loads individual pages |

## Working with Pages

### Loading Pages

```python
page = doc.load_page(pno)  # 0-based indexing
page = doc[pno]            # Shorthand syntax
page = doc[-1]             # Last page (negative indexing)
```

Iterate through pages:

```python
for page in doc:
    # Process each page

for page in reversed(doc):
    # Process in reverse

for page in doc.pages(start, stop, step):
    # Process with slicing
```

### Rendering Pages

Create raster images:

```python
pix = page.get_pixmap()
```

The Pixmap object contains RGB image data with attributes including `width`, `height`, `stride`, and `samples` (bytes object). Options allow controlling resolution, colorspace, transparency, rotation, and transformations.

### Saving Images

```python
pix.save("page-%i.png" % page.number)
```

## Text and Image Extraction

Extract page content in various formats:

```python
text = page.get_text(opt)
```

Available formats:
- **"text"** – Plain text with line breaks
- **"blocks"** – Paragraphs as list
- **"words"** – Words without spaces
- **"html"** – Full visual version with images
- **"dict"/"json"** – Structured data as dictionary or JSON
- **"rawdict"/"rawjson"** – Extended character-level details
- **"xhtml"** – Text with images, browser-compatible
- **"xml"** – Full font and position information

### Text Search

Find text locations:

```python
areas = page.search_for("mupdf")
```

Returns list of rectangles surrounding each occurrence (case-insensitive).

## PDF Maintenance

### Page Management

```python
# Delete pages
doc.delete_page(pno)
doc.delete_pages([list of page numbers])

# Copy or move pages
doc.copy_page(pno)
doc.fullcopy_page(pno)
doc.move_page(pno, target)

# Select specific pages
doc.select([0, 2, 4])  # Keep only these pages, in order

# Insert new pages
doc.insert_page(pno)
doc.new_page()
```

### Joining and Splitting

```python
# Append entire document
doc1.insert_pdf(doc2)

# Split document (first and last 10 pages)
doc2 = pymupdf.open()
doc2.insert_pdf(doc1, to_page=9)
doc2.insert_pdf(doc1, from_page=len(doc1)-10)
doc2.save("split.pdf")
```

### Saving with Compression Options

```python
doc.save(filename, garbage=4, deflate=True)
```

Save options:
- **garbage** (1-4) – Object cleanup levels
- **clean=True** – Sanitize streams
- **deflate=True** – Compress streams
- **deflate_images=True** – Compress image streams
- **deflate_fonts=True** – Compress font streams
- **ascii=True** – Convert binary to ASCII
- **linear=True** – Create linearized version
- **expand=True** – Decompress streams

## Closing Documents

```python
doc.close()
```

Releases file control and frees associated buffers.
