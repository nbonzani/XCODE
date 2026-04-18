#!/usr/bin/env bash
# Native host build (Ubuntu x86_64) — for fast iteration on the GStreamer/SDL pipeline
# without round-tripping to the TV. The same source builds for ARM via scripts/build.sh.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_TYPE="${1:-Release}"
BUILD_DIR="$PROJECT_ROOT/build-host"

echo "==> Configure host ($BUILD_TYPE)"
cmake -S "$PROJECT_ROOT" -B "$BUILD_DIR" -G Ninja -DCMAKE_BUILD_TYPE="$BUILD_TYPE"

echo "==> Build"
cmake --build "$BUILD_DIR" --parallel

echo
echo "DONE: $BUILD_DIR/iptv-player"
file "$BUILD_DIR/iptv-player"
