#!/bin/bash
set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_ROOT/image/remote"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
IMAGE_NAME="daisy_server:remote"
BASE_IMAGE_NAME="daisy_server:base-amd64"
OUTPUT_FILE="$OUTPUT_DIR/daisyServer_remote_${TIMESTAMP}.tar.gz"
PLATFORM="linux/amd64"

echo "=== Daisy Server Remote Build ==="
echo "Project Root: $PROJECT_ROOT"
echo "Target Platform: $PLATFORM"
echo "Base Image: $BASE_IMAGE_NAME"
echo "Output File: $OUTPUT_FILE"

cd "$PROJECT_ROOT"

echo "1. Building Base Docker image ($PLATFORM)..."
# Explicitly build base image for AMD64 to avoid conflict with local ARM64 base
docker build --platform "$PLATFORM" -t "$BASE_IMAGE_NAME" -f Dockerfile.base .

echo "2. Building Application Docker image..."
# Use the specific AMD64 base image
docker build --platform "$PLATFORM" \
    --build-arg BASE_IMAGE="$BASE_IMAGE_NAME" \
    -t "$IMAGE_NAME" \
    -f Dockerfile .

echo "3. Saving image..."
mkdir -p "$OUTPUT_DIR"
docker save "$IMAGE_NAME" | gzip > "$OUTPUT_FILE"

echo "Build complete!"
echo "Image location: $OUTPUT_FILE"
