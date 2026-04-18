#!/usr/bin/env bash
# Build (cross ARM) -> package -> ask -> install -> launch on the LG TV (device alias "tv").
# Confirmation is required before install/launch (memo: never deploy without explicit Enter).
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_ID="com.iptv.player.native"
DEVICE="tv"

cd "$PROJECT_ROOT"

echo "==> Cross-build + package"
./scripts/build.sh Release

IPK="$(ls -t "$PROJECT_ROOT/dist"/*.ipk 2>/dev/null | head -1 || true)"
if [[ -z "$IPK" ]]; then
    echo "ERROR: no IPK found in dist/" >&2
    exit 1
fi

echo
echo "============================================================"
echo "  IPK ready: $IPK ($(du -h "$IPK" | cut -f1))"
echo "  Target device: $DEVICE  ($(ares-device -i --device $DEVICE 2>/dev/null | grep modelName | head -1 || echo offline?))"
echo "============================================================"
echo
read -r -p "Press Enter to install + launch on the TV (or Ctrl-C to cancel) " _

echo "==> ares-install"
ares-install --device "$DEVICE" "$IPK"

echo "==> ares-launch"
ares-launch --device "$DEVICE" "$APP_ID"

echo "==> running apps on TV"
ares-launch -r --device "$DEVICE" || true
