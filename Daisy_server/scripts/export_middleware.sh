#!/bin/bash
set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_ROOT/image/remote"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Define images to pull
REDIS_IMAGE="redis:alpine"
QDRANT_IMAGE="qdrant/qdrant:latest"

echo "=== Daisy Middleware Export ==="
echo "Output Directory: $OUTPUT_DIR"

mkdir -p "$OUTPUT_DIR"

# 1. Pull Images
echo "1. Pulling Redis image ($REDIS_IMAGE)..."
docker pull $REDIS_IMAGE

echo "2. Pulling Qdrant image ($QDRANT_IMAGE)..."
docker pull $QDRANT_IMAGE

# 2. Save Images
echo "3. Exporting Redis..."
docker save $REDIS_IMAGE | gzip > "$OUTPUT_DIR/redis_alpine_${TIMESTAMP}.tar.gz"

echo "4. Exporting Qdrant..."
docker save $QDRANT_IMAGE | gzip > "$OUTPUT_DIR/qdrant_latest_${TIMESTAMP}.tar.gz"

echo "Middleware export complete!"
echo "Files in $OUTPUT_DIR:"
ls -lh "$OUTPUT_DIR" | grep ".tar.gz"
