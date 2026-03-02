# Use slimmer Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (needed for some Python packages)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies with CPU-only PyTorch to save space (CRITICAL STEP)
# We handle torch separately to force CPU version
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Pre-download the model during build to speed up runtime
RUN python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy the rest of the application
COPY . .

# Expose port (railway injects PORT env var)
EXPOSE 8000

# Start command
CMD sh -c "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"
