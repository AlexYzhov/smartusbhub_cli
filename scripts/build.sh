#!/usr/bin/env bash
set -euo pipefail

# Build script for smartusbhub_cli.
# Produces a single-file PyInstaller binary and a zipapp fallback.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON="${PYTHON:-python3}"
BUILD_DIR="${PROJECT_ROOT}/build"
DIST_DIR="${PROJECT_ROOT}/dist"

mkdir -p "$DIST_DIR"

# Ensure dependencies are installed
if ! command -v pyinstaller &>/dev/null; then
    echo "Installing PyInstaller..."
    "$PYTHON" -m pip install pyinstaller
fi

# Determine architecture
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64)
        TARGET_ARCH="x86_64"
        ;;
    aarch64|arm64)
        TARGET_ARCH="aarch64"
        ;;
    *)
        TARGET_ARCH="$ARCH"
        ;;
esac

echo "Building smartusbhub_cli for ${TARGET_ARCH}..."

# PyInstaller single-file binary
pyinstaller smartusbhub_cli.spec
mv "$DIST_DIR/smartusbhub" "$DIST_DIR/smartusbhub-linux-${TARGET_ARCH}"
chmod +x "$DIST_DIR/smartusbhub-linux-${TARGET_ARCH}"

echo "Binary: $DIST_DIR/smartusbhub-linux-${TARGET_ARCH}"

# zipapp fallback (requires Python + dependencies installed)
ZIPAPP="$DIST_DIR/smartusbhub.pyz"
"$PYTHON" -m zipapp src \
    -m "smartusbhub_cli.__main__:app" \
    -o "$ZIPAPP"

echo "zipapp: $ZIPAPP"
