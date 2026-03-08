# ------------ STAGE 1: Build environment ------------
FROM python:3.10-slim AS builder

# Install system dependencies needed for psycopg2 or pg8000
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies into a folder (not system-wide)
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt


# ------------ STAGE 2: Run environment ------------
FROM python:3.10-slim

# Copy installed python packages
COPY --from=builder /install /usr/local

# Set work directory
WORKDIR /app

# Copy application code
COPY . .

# Expose port for Cloud Run or local Docker
EXPOSE 8080

# Required by Cloud Run
ENV PORT=8080

# Start FastAPI with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
