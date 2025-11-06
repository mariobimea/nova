FROM e2bdev/code-interpreter:latest

# Install PyMuPDF for PDF processing
RUN pip install PyMuPDF==1.24.0

# Install psycopg2 for PostgreSQL connections
RUN pip install psycopg2-binary==2.9.10
