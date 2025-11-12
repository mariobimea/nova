# EasyOCR Official Documentation

## Overview

Ready-to-use OCR with 80+ supported languages and all popular writing scripts including: Latin, Chinese, Arabic, Devanagari, Cyrillic, etc.

## Installation

### Via pip

```bash
pip install easyocr
```

### System Requirements

- **Windows**: Install PyTorch and TorchVision first
- **GPU Memory**: For low-memory GPUs or CPU-only execution, use `gpu=False` parameter

## Quick Start

### Basic Usage

```python
import easyocr

# Initialize reader (runs once to load model)
reader = easyocr.Reader(['ch_sim', 'en'])

# Read text from image
result = reader.readtext('chinese.jpg')
```

### Output Format

Results return a list of tuples containing:
- Bounding box coordinates (4 corner points)
- Detected text
- Confidence score (0-1)

Example output:
```
[
  ([[189, 75], [469, 75], [469, 165], [189, 165]], '愚园路', 0.375),
  ([[86, 80], [134, 80], [134, 128], [86, 128]], '西', 0.405)
]
```

## Reader Class

### Constructor
```python
easyocr.Reader(languages, gpu=True)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `languages` | list | Language codes (e.g., `['en', 'ch_sim']`) |
| `gpu` | bool | Enable GPU acceleration (default: True) |

**Notes:**
- English compatible with all languages
- Languages sharing common characters usually compatible
- Not all language combinations work together

## readtext() Method

```python
reader.readtext(image, detail=1)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `image` | str/array/bytes | - | File path, URL, OpenCV image, or image bytes |
| `detail` | int | 1 | 1 for detailed output, 0 for text only |

### Image Input Types
- File path: `'image.jpg'`
- OpenCV array: numpy ndarray
- Raw bytes: image file bytes
- URL: Raw image URL

### Output Examples

**With detail=1 (default):**
```python
result = reader.readtext('image.jpg', detail=1)
# Returns: [([coords], 'text', confidence), ...]
```

**With detail=0:**
```python
result = reader.readtext('image.jpg', detail=0)
# Returns: ['text1', 'text2', 'text3', ...]
```

## Model Management

### Automatic Download
Models automatically download to `~/.EasyOCR/model/` on first use

### Manual Download
Access the model hub at https://www.jaided.ai/easyocr/modelhub

## Supported Languages

80+ languages supported including all major writing systems.

## Technical Architecture

**Detection**: CRAFT algorithm for text localization

**Recognition**: CRNN model composed of:
- Feature extraction (ResNet/VGG)
- Sequence labeling (LSTM)
- Decoding (CTC)
