#!/bin/bash
set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_ROOT/image/remote"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
IMAGE_NAME="daisy_front:remote"
OUTPUT_FILE="$OUTPUT_DIR/daisyFront_remote_${TIMESTAMP}.tar.gz"
PLATFORM="linux/amd64"

echo "=== Daisy Front Remote Build ==="
echo "Project Root: $PROJECT_ROOT"
echo "Target Platform: $PLATFORM"
echo "Output File: $OUTPUT_FILE"

cd "$PROJECT_ROOT"

# Load env vars for build (VITE_API_BASE_URL)
# We override the one in .env with the hardcoded one required by user if needed, 
# but since we updated .env, we can just let Vite pick it up OR force it.
# The user asked to compile with specific env vars. I updated .env.
# Vite picks up .env automatically.
# But to be safe and explicit as per the PS1 script logic:
export VITE_API_BASE_URL="http://171.43.173.125:30026/api"
echo "Using VITE_API_BASE_URL from .env"

echo "1. Installing dependencies..."
npm install

echo "2. Building frontend app..."
npm run build

echo "3. Building Docker image..."
docker build --platform "$PLATFORM" -t "$IMAGE_NAME" .

echo "4. Saving image..."
mkdir -p "$OUTPUT_DIR"
docker save "$IMAGE_NAME" | gzip > "$OUTPUT_FILE"

echo "Build complete!"
echo "Image location: $OUTPUT_FILE"
