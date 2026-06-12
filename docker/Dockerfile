# docker/Dockerfile
#
# Production container for PerpScope FastAPI backend.
#
# Build:  docker build -f docker/Dockerfile -t perpscope-backend .
# Run:    docker run -p 8000:8000 --env-file .env perpscope-backend

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first
# (separate layer so Docker caches this if requirements.txt unchanged)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY backend/ ./backend/
COPY src/ ./src/
COPY coin_universe.json .
COPY market_cap_classification.json .

# Set Python path so backend can import from src/
ENV PYTHONPATH=/app

# Non-root user for security
RUN useradd --create-home appuser
USER appuser

# Expose port
EXPOSE 8000

# Health check — Docker will mark container unhealthy if this fails
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Start command
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]