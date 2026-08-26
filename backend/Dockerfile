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

# Run FastAPI backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
