#!/bin/bash
# Daily pattern matching index update
# Run after market close ~8 PM ET (1 AM UTC)

cd /opt/tradeul

# Download new flat files
docker compose exec -T pattern_matching python -c "
from flat_files_downloader import FlatFilesDownloader
d = FlatFilesDownloader()
d.download_last_n_days(3)
"

# Update index with 16GB RAM
docker run --rm \
  --memory=16g \
  -v tradeul_pattern_indexes:/app/indexes \
  -v tradeul_polygon_data:/app/data \
  tradeul-pattern_matching \
  python daily_updater.py

# Restart service to load updated index
docker restart tradeul_pattern_matching

echo "Pattern matching update complete: $(date)"
