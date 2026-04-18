#!/usr/bin/env bash
# Cross-build SDL2 hello-world for LG webOS TV (ARMv7 buildroot).
# Usage: scripts/build.sh [Debug|Release]
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_TYPE="${1:-Release}"
BUILD_DIR="$PROJECT_ROOT/build"
PACKAGE_DIR="$PROJECT_ROOT/package"

# Toolchain location (relocate-sdk.sh must have been run once after extraction).
TOOLCHAIN_ROOT="${WEBOS_TOOLCHAIN:-$HOME/webos-toolchain/arm-webos-linux-gnueabi_sdk-buildroot}"
TOOLCHAIN_FILE="$TOOLCHAIN_ROOT/share/buildroot/toolchainfile.cmake"

if [[ ! -f "$TOOLCHAIN_FILE" ]]; then
    echo "ERROR: toolchain file not found: $TOOLCHAIN_FILE" >&2
    echo "Did you run relocate-sdk.sh after extracting the SDK?" >&2
    exit 1
fi

echo "==> Configure ($BUILD_TYPE)"
cmake -S "$PROJECT_ROOT" -B "$BUILD_DIR" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$TOOLCHAIN_FILE" \
    -DCMAKE_BUILD_TYPE="$BUILD_TYPE" \
    -DCMAKE_INSTALL_PREFIX="$PACKAGE_DIR"

echo "==> Build"
cmake --build "$BUILD_DIR" --parallel

echo "==> Stage (install to $PACKAGE_DIR)"
rm -rf "$PACKAGE_DIR"
cmake --install "$BUILD_DIR"

# webOS package layout: appinfo.json + icons + binary (placed in app root, not usr/bin).
# We move the binary up so appinfo's "main" lookup works the standard way.
mkdir -p "$PACKAGE_DIR"
cp "$PROJECT_ROOT/appinfo.json" "$PACKAGE_DIR/"
cp "$PROJECT_ROOT/assets/icon.png" "$PACKAGE_DIR/" 2>/dev/null || true
cp "$PROJECT_ROOT/assets/largeIcon.png" "$PACKAGE_DIR/" 2>/dev/null || true
cp "$PROJECT_ROOT/assets/splash.png" "$PACKAGE_DIR/" 2>/dev/null || true
mkdir -p "$PACKAGE_DIR/assets"
cp "$PROJECT_ROOT/assets/font.ttf"      "$PACKAGE_DIR/assets/" 2>/dev/null || true
cp "$PROJECT_ROOT/assets/font-bold.ttf" "$PACKAGE_DIR/assets/" 2>/dev/null || true

# Move binary to package root
if [[ -f "$PACKAGE_DIR/usr/bin/iptv-player" ]]; then
    mv "$PACKAGE_DIR/usr/bin/iptv-player" "$PACKAGE_DIR/iptv-player"
    rm -rf "$PACKAGE_DIR/usr"
fi

echo "==> File summary"
file "$PACKAGE_DIR/iptv-player" || true
ls -la "$PACKAGE_DIR/"

echo "==> Package IPK"
cd "$PROJECT_ROOT"
ares-package "$PACKAGE_DIR" -o "$PROJECT_ROOT/dist"

echo
echo "DONE. IPK in: $PROJECT_ROOT/dist/"
ls -la "$PROJECT_ROOT/dist/"
