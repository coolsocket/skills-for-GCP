#!/bin/bash
# build_loader.sh
# Builds the benchmark Docker image

PROJECT_ID=$(gcloud config get-value project)
IMAGE_URI="gcr.io/${PROJECT_ID}/gpu-model-loader:latest"

# Ensure we are in the skill directory or have access to assets
SCRIPT_DIR=$(dirname "$0")
ASSETS_DIR="$SCRIPT_DIR/../assets"

echo "=== Building Benchmark Loader ==="
echo "Project: $PROJECT_ID"
echo "Image: $IMAGE_URI"

# Create a temporary build context
BUILD_CTX=$(mktemp -d)
cp "$ASSETS_DIR/Dockerfile" "$BUILD_CTX/"
cp "$ASSETS_DIR/server.py" "$BUILD_CTX/"

echo "Context: $BUILD_CTX"
ls -l "$BUILD_CTX"

gcloud builds submit --tag ${IMAGE_URI} "$BUILD_CTX"

rm -rf "$BUILD_CTX"
echo "✅ Build Complete."
