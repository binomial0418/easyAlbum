FROM python:3.12-slim

# Set environment variables to prevent Python from buffering stdout/stderr
# and ensuring UTF-8 encoding
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8

WORKDIR /app

# Install system dependencies if any (none for now, but good practice to have apt-get ready)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # libjpeg-dev zlib1g-dev are often needed for Pillow but slim image might have basic support
    # keeping it minimal for now
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src /app/src

# Create directries for mounting
RUN mkdir -p /app/photos /app/thumbnails

# Expose port
EXPOSE 5002

# Default command (can be overridden in docker-compose)
# Using gunicorn for production-like performance, or python main.py for dev
CMD ["gunicorn", "--bind", "0.0.0.0:5002", "src.app.main:app"]
