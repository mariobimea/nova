# NOVA Invoice Processing Template
# Based on E2B code-interpreter with custom libraries for invoice workflows

FROM e2bdev/code-interpreter:latest

# Set working directory
WORKDIR /home/user

# Update package lists
RUN apt-get update

# Install system dependencies for PDF and OCR processing
RUN apt-get install -y \
    # Tesseract OCR engine
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-spa \
    # Poppler utilities for PDF processing
    poppler-utils \
    # Image processing dependencies
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    # Clean up
    && rm -rf /var/lib/apt/lists/*

# Install Python packages for invoice processing
RUN pip install --no-cache-dir \
    # PDF processing
    PyPDF2==3.0.1 \
    pdfplumber==0.10.3 \
    # OCR and image processing
    pytesseract==0.3.10 \
    pdf2image==1.16.3 \
    Pillow==10.1.0 \
    # Database
    psycopg2-binary==2.9.9 \
    # Email parsing (enhanced)
    email-validator==2.1.0 \
    # File type detection
    python-magic==0.4.27 \
    # HTTP requests (already in base, but ensure version)
    requests==2.32.5 \
    # Date parsing
    python-dateutil==2.8.2

# Set Tesseract data path
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata

# Create directories for temporary files
RUN mkdir -p /tmp/nova-invoices /tmp/nova-pdfs && \
    chmod 777 /tmp/nova-invoices /tmp/nova-pdfs

# Verify installations
RUN python -c "import PyPDF2; import pdfplumber; import pytesseract; import pdf2image; import psycopg2; print('All packages installed successfully!')"

# Set default working directory
WORKDIR /home/user
