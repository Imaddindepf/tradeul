#!/bin/bash
# ============================================
# GPU Instance Setup Script
# ============================================
# Run this on your g5.xlarge instance to set up
# the training environment.
#
# Usage:
#   chmod +x scripts/setup_gpu_instance.sh
#   ./scripts/setup_gpu_instance.sh
# ============================================

set -e

echo "============================================"
echo "NEWS ALPHA ENGINE - GPU Setup"
echo "============================================"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on GPU instance
if ! nvidia-smi &> /dev/null; then
    echo -e "${YELLOW}WARNING: nvidia-smi not found. Are you on a GPU instance?${NC}"
    echo "This script is designed for AWS g5.xlarge with A10G GPU."
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo -e "${GREEN}✓ GPU detected:${NC}"
    nvidia-smi --query-gpu=name,memory.total --format=csv
fi

# Update system
echo -e "\n${GREEN}[1/6] Updating system...${NC}"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-pip python3-venv git

# Create virtual environment
echo -e "\n${GREEN}[2/6] Creating virtual environment...${NC}"
cd /opt/tradeul/services/news-alpha-engine
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel -q

# Install PyTorch with CUDA
echo -e "\n${GREEN}[3/6] Installing PyTorch with CUDA support...${NC}"
pip install torch --index-url https://download.pytorch.org/whl/cu121 -q

# Install other requirements
echo -e "\n${GREEN}[4/6] Installing requirements...${NC}"
pip install -r requirements.txt -q

# Install cuML for GPU-accelerated UMAP/HDBSCAN (optional)
echo -e "\n${GREEN}[5/6] Installing cuML (optional, for GPU UMAP)...${NC}"
pip install --extra-index-url=https://pypi.nvidia.com cuml-cu12 -q 2>/dev/null || \
    echo -e "${YELLOW}Note: cuML installation failed. Using CPU UMAP (still fast).${NC}"

# Verify installation
echo -e "\n${GREEN}[6/6] Verifying installation...${NC}"
python -c "
import torch
print(f'PyTorch version: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'GPU: {torch.cuda.get_device_name(0)}')
    print(f'VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB')
"

python -c "
from transformers import AutoModel
print('✓ Transformers OK')
from bertopic import BERTopic
print('✓ BERTopic OK')
"

echo ""
echo "============================================"
echo -e "${GREEN}Setup complete!${NC}"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Activate environment: source venv/bin/activate"
echo "  2. Download datasets: python scripts/download_datasets.py"
echo "  3. Prepare labels: python scripts/prepare_labels.py"
echo "  4. Train encoder: python src/training/train_encoder.py"
echo "  5. Train topics: python src/training/train_topics.py"
echo ""
echo "Or run the full pipeline:"
echo "  python scripts/run_full_pipeline.py"
echo ""

