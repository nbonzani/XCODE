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
# NE PAS bundler run.sh : LD_LIBRARY_PATH=$APPDIR/lib casse NDL_DirectMediaLoad
# (cf project_iptv_runsh_ndl_conflict.md). DivX MPEG-4 ASP retombe en panne mais
# H264/HEVC NDL HW decode fonctionnent.
# install -m 0755 "$PROJECT_ROOT/run.sh" "$PACKAGE_DIR/run.sh"
cp "$PROJECT_ROOT/assets/icon.png" "$PACKAGE_DIR/" 2>/dev/null || true
cp "$PROJECT_ROOT/assets/largeIcon.png" "$PACKAGE_DIR/" 2>/dev/null || true
cp "$PROJECT_ROOT/assets/splash.png" "$PACKAGE_DIR/" 2>/dev/null || true
mkdir -p "$PACKAGE_DIR/assets"
cp "$PROJECT_ROOT/assets/font.ttf"      "$PACKAGE_DIR/assets/" 2>/dev/null || true
cp "$PROJECT_ROOT/assets/font-bold.ttf" "$PACKAGE_DIR/assets/" 2>/dev/null || true
cp "$PROJECT_ROOT/assets/test_asp.mkv"  "$PACKAGE_DIR/assets/" 2>/dev/null || true
cp "$PROJECT_ROOT/assets/test_h264.mkv" "$PACKAGE_DIR/assets/" 2>/dev/null || true
# Optional pre-baked Xtream credentials (kept out of git — see /tmp/iptv_default_config.json)
if [[ -f /tmp/iptv_default_config.json ]]; then
    cp /tmp/iptv_default_config.json "$PACKAGE_DIR/assets/default_config.json"
    echo "==> baked default_config.json (credentials preset)"
fi

# Bundle SDL2 + deps that are too recent on the TV (TV has SDL2 2.0.10, we build
# against 2.30). Binary's rpath = $ORIGIN/lib so these are picked up first.
SYSROOT="$TOOLCHAIN_ROOT/arm-webos-linux-gnueabi/sysroot"
mkdir -p "$PACKAGE_DIR/lib"
bundle_so() {
    local src="$1"
    cp --dereference "$src" "$PACKAGE_DIR/lib/$(basename "$(readlink -f "$src")")"
    # Also create the SONAME symlink the loader expects.
    local soname
    soname="$($TOOLCHAIN_ROOT/bin/arm-webos-linux-gnueabi-readelf -d "$src" | awk '/SONAME/ { gsub(/[\[\]]/,""); print $5 }')"
    if [[ -n "$soname" && "$soname" != "$(basename "$(readlink -f "$src")")" ]]; then
        ln -sf "$(basename "$(readlink -f "$src")")" "$PACKAGE_DIR/lib/$soname"
    fi
}
# We do NOT bundle SDL2 / SDL2_ttf / SDL2_image : the TV's native ones (2.0.10)
# integrate with the webOS compositor; our buildroot fork (2.30) does not.
# Same for freetype/png/jpeg — the TV already has compatible versions.
# We DO bundle libstdc++ + libgcc_s because GCC 14.2 emits symbol versions the
# TV's older libstdc++ lacks (e.g. GLIBCXX_3.4.30).
for lib in libstdc++.so.6; do
    for base in "$SYSROOT/usr/lib" "$SYSROOT/lib"; do
        if [[ -f "$base/$lib" ]]; then
            bundle_so "$base/$lib"
            break
        fi
    done
done
# libgcc_s too (GCC 14.2 support symbols newer than webOS 6.5 likely has).
if [[ -f "$SYSROOT/lib/libgcc_s.so.1" ]]; then
    bundle_so "$SYSROOT/lib/libgcc_s.so.1"
fi

# FFmpeg + gst-libav bundle: the TV doesn't ship avdec_mpeg4/h265/mpeg2video so we
# carry our own. libgstlibav.so goes under lib/gstreamer-1.0/ and is discovered via
# GST_PLUGIN_PATH set at runtime in main.cpp.
for lib in libavcodec.so.58 libavformat.so.58 libavutil.so.56 \
           libswresample.so.3 libswscale.so.5 libavfilter.so.7; do
    if [[ -f "$SYSROOT/usr/lib/$lib" ]]; then
        bundle_so "$SYSROOT/usr/lib/$lib"
    fi
done
if [[ "${BUNDLE_GST_LIBAV:-1}" == "1" ]]; then
    GST_PLUGIN_SRC="$HOME/webos-toolchain/gst-libav-1.16.3/build/ext/libav/.libs/libgstlibav.so"
    if [[ -f "$GST_PLUGIN_SRC" ]]; then
        mkdir -p "$PACKAGE_DIR/lib/gstreamer-1.0"
        cp "$GST_PLUGIN_SRC" "$PACKAGE_DIR/lib/gstreamer-1.0/libgstlibav.so"
        echo "==> bundled gst-libav plugin"
    fi
fi
# GLib polyfill shim — provides g_once_init_*_pointer (added in GLib 2.80)
# that webOS 6.5's older GLib lacks. NEEDED-injected into libgstlibav.so via
# patchelf so the dynamic linker resolves it before loading the plugin.
if [[ -f /tmp/libglib_compat.so ]]; then
    cp /tmp/libglib_compat.so "$PACKAGE_DIR/lib/libglib_compat.so"
    echo "==> bundled libglib_compat.so"
fi
echo "==> Bundled .so"
ls -la "$PACKAGE_DIR/lib/" | head

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
