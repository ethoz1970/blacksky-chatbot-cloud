FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for psycopg2 and sentence-transformers
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (production only, no llama-cpp-python)
COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

# Copy application code
COPY . .

# Expose port (Railway sets PORT dynamically)
EXPOSE 8000

# Run with uvicorn - use shell form to expand $PORT
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}
