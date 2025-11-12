# Deprecated Manual Documentation

**Date**: 2025-11-12
**Reason**: Replaced by official documentation from library maintainers

---

## Files Moved

### `pdf.md` (332 lines)
**Replaced by**: `/knowledge/official_docs/pymupdf_official.md`
**Reason**: Official PyMuPDF documentation is more complete, accurate, and up-to-date.

### `ocr.md` (565 lines)
**Replaced by**: `/knowledge/official_docs/easyocr_official.md`
**Reason**: Official EasyOCR documentation is more complete, accurate, and up-to-date.

---

## Changes Made

1. **Moved files**: `pdf.md` and `ocr.md` → `_deprecated/`
2. **Updated KnowledgeManager**:
   - Changed integration names from `'pdf'` → `'pymupdf'`
   - Changed integration names from `'ocr'` → `'easyocr'`
   - Updated dependency system: `'easyocr': ['pymupdf']`
3. **Reloaded vector store**: 151 docs → 97 docs (removed 54 redundant chunks)

---

## New Sources in Vector Store

- `pymupdf` (16 chunks) - Official docs
- `easyocr` (19 chunks) - Official docs
- `imap` (15 chunks) - Manual docs (kept)
- `smtp` (12 chunks) - Manual docs (kept)
- `postgres` (20 chunks) - Manual docs (kept)
- `regex` (15 chunks) - Manual docs (kept)

**Total**: 97 chunks

---

## Impact

✅ **Better accuracy**: Official docs are maintained by library authors
✅ **Less redundancy**: Removed duplicate/conflicting information
✅ **Smaller vector DB**: 151 → 97 docs (36% reduction)
✅ **Faster retrieval**: Fewer docs to search through
✅ **Easier maintenance**: No need to manually sync with library updates

---

## Rollback Instructions

If needed, restore manual docs:

```bash
cd /Users/marioferrer/automatizaciones/nova/knowledge/integrations
mv _deprecated/pdf.md .
mv _deprecated/ocr.md .
```

Then revert changes in `src/core/ai/knowledge_manager.py`:
- Change `'pymupdf'` → `'pdf'`
- Change `'easyocr'` → `'ocr'`
- Update dependency: `'ocr': ['pdf']`

And reload vector store:
```bash
cd /Users/marioferrer/automatizaciones/nova
AUTO_CONFIRM=true python3 scripts/load_docs_to_vectorstore.py
```
