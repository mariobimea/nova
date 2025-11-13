FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Make start script executable
RUN chmod +x start.sh

# Expose port (Railway will set PORT env var)
EXPOSE 8000

# Run application using bash to ensure $PORT expansion
CMD ["bash", "start.sh"]
