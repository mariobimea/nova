"""
E2B Template V2 for NOVA Invoice Processing

This template includes:
- PyMuPDF (fitz) for PDF OCR
- psycopg2-binary for PostgreSQL connections
"""

from e2b import Sandbox

# Base template with all standard libraries
template = Sandbox.from_dockerfile(
    dockerfile="""
FROM e2bdev/code-interpreter:latest

# Install PyMuPDF for PDF processing
RUN pip install PyMuPDF==1.24.0

# Install psycopg2 for PostgreSQL connections
RUN pip install psycopg2-binary==2.9.10
    """,
    # Working directory for code execution
    cwd="/home/user"
)

if __name__ == "__main__":
    template_id = template.create("nova-sandbox-v2")
    print(f"Template created with ID: {template_id}")
