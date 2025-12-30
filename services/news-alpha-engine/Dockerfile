# ============================================
# NEWS ALPHA ENGINE - Training Dockerfile
# ============================================
# For training on GPU (g5.xlarge with A10G)
# ============================================

FROM nvidia/cuda:12.1-cudnn8-runtime-ubuntu22.04

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    python3.10-venv \
    git \
    curl \
    wget \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set Python 3.10 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1 \
    && update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

# Create app directory
WORKDIR /app

# Copy requirements first (for caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Install PyTorch with CUDA support
RUN pip install --no-cache-dir \
    torch>=2.1.0 \
    --index-url https://download.pytorch.org/whl/cu121

# Copy application code
COPY . .

# Create directories
RUN mkdir -p /data/raw /data/processed /models /logs

# Set environment variables
ENV TRANSFORMERS_CACHE=/models/cache
ENV HF_HOME=/models/cache
ENV TORCH_HOME=/models/cache

# Default command
CMD ["python", "scripts/download_datasets.py"]

