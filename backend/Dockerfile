# GridSentinel Backend Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application code and trained models
COPY . .

# Expose FastAPI REST/WS port (8000) and simulated Modbus RTU ports (5021-5025)
EXPOSE 8000 5021 5022 5023 5024 5025

# Run one lifecycle-owned FastAPI worker. Render supplies PORT; local Docker
# keeps the 8000 default. Do not add --reload or multiple workers: the OT RTU
# servers and SimulationLoop are process-local singletons.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
