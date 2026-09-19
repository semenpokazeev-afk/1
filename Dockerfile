# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    DATABASE_URL=sqlite+aiosqlite:///./arbiter.db

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Expose standard port
EXPOSE 8000

# Run uvicorn with shell variable expansion for $PORT (supports Render, Railway, Heroku, Cloud Run)
CMD ["sh", "-c", "uvicorn arbiter.gateway.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
