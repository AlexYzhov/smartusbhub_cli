#!/usr/bin/env bash
set -euo pipefail

# Build script for smartusbhub_cli.
#
# Usage:
#   ./scripts/build.sh              # build only the host-arch binary + zipapp
#   ./scripts/build.sh --multi-arch # also attempt the other arch via Docker
#   ./scripts/build.sh --host-only  # same as default (explicit)
#   source ./scripts/build.sh       # export SMARTUSBHUB_BIN pointing to the
#                                   # host-arch binary (builds it if missing)
#
# When sourced, this script does not attempt a cross-arch build; it only
# ensures the host-arch binary exists and sets SMARTUSBHUB_BIN accordingly.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Prefer the local virtual environment if it exists.
if [ -x "${PROJECT_ROOT}/.venv/bin/python" ]; then
    PYTHON="${PYTHON:-${PROJECT_ROOT}/.venv/bin/python}"
else
    PYTHON="${PYTHON:-python3}"
fi

PYINSTALLER="${PROJECT_ROOT}/.venv/bin/pyinstaller"
if [ ! -x "$PYINSTALLER" ]; then
    PYINSTALLER="pyinstaller"
fi

BUILD_DIR="${PROJECT_ROOT}/build"
DIST_DIR="${PROJECT_ROOT}/dist"

mkdir -p "$DIST_DIR"

# Embed the current git commit hash so the built artifact can report it even
# when no git metadata is present at runtime.
write_commit_hash() {
    local hash
    hash=$(git -C "$PROJECT_ROOT" rev-parse HEAD 2>/dev/null || echo "unknown")
    echo "COMMIT_HASH = \"$hash\"" > "$PROJECT_ROOT/src/smartusbhub_cli/_built_commit.py"
}
write_commit_hash

# Parse optional flags (default: host-only)
HOST_ONLY=true
for arg in "$@"; do
    case "$arg" in
        --host-only)
            HOST_ONLY=true
            ;;
        --multi-arch)
            HOST_ONLY=false
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 [--host-only | --multi-arch]"
            exit 1
            ;;
    esac
done

# Determine host architecture
HOST_ARCH="$(uname -m)"
case "$HOST_ARCH" in
    x86_64)
        HOST_ARCH_LABEL="x86_64"
        ;;
    aarch64|arm64)
        HOST_ARCH_LABEL="aarch64"
        ;;
    *)
        HOST_ARCH_LABEL="$HOST_ARCH"
        ;;
esac

# Ensure dependencies are installed
if ! command -v "$PYINSTALLER" &>/dev/null; then
    echo "Installing PyInstaller into ${PYTHON}..."
    "$PYTHON" -m pip install pyinstaller
fi

build_zipapp() {
    echo "Building zipapp..."
    "$PYTHON" -m zipapp src \
        -m "smartusbhub_cli.__main__:app" \
        -o "$DIST_DIR/smartusbhub.pyz"
    echo "zipapp: $DIST_DIR/smartusbhub.pyz"
}

build_native() {
    local arch="$1"
    echo "Building smartusbhub binary for ${arch}..."
    "$PYINSTALLER" smartusbhub_cli.spec
    local binary="$DIST_DIR/smartusbhub-linux-${arch}"
    mv "$DIST_DIR/smartusbhub" "$binary"
    chmod +x "$binary"
    echo "Binary: $binary"
}

build_other_arch_with_docker() {
    local other_arch=""
    if [ "$HOST_ARCH_LABEL" = "x86_64" ]; then
        other_arch="aarch64"
    elif [ "$HOST_ARCH_LABEL" = "aarch64" ]; then
        other_arch="x86_64"
    else
        echo "Unsupported host architecture '${HOST_ARCH_LABEL}', skipping cross-arch build."
        return 0
    fi

    if ! command -v docker &>/dev/null; then
        echo "Docker not available, skipping ${other_arch} cross-arch build."
        return 0
    fi

    echo "Attempting to build ${other_arch} binary via Docker (this may be slow)..."
    if docker run --rm --platform "linux/${other_arch}" \
        -v "$PROJECT_ROOT:/workspace" \
        -w /workspace \
        python:3.11-slim \
        bash -c "
            set -euo pipefail
            python -m pip install --upgrade pip
            pip install -e '.[dev]'
            pyinstaller smartusbhub_cli.spec
            mv dist/smartusbhub dist/smartusbhub-linux-${other_arch}
            chmod +x dist/smartusbhub-linux-${other_arch}
        "; then
        echo "Cross-arch binary: $DIST_DIR/smartusbhub-linux-${other_arch}"
    else
        echo "Warning: ${other_arch} cross-arch build failed (QEMU/binfmt_misc may be required)." >&2
    fi
}

# ---------------------------------------------------------------------------
# Sourced mode: export SMARTUSBHUB_BIN for the host architecture.
# Build the host binary (and zipapp) only if it does not already exist.
# ---------------------------------------------------------------------------
if [ "${BASH_SOURCE[0]}" != "${0}" ]; then
    HOST_BIN="$DIST_DIR/smartusbhub-linux-${HOST_ARCH_LABEL}"
    if [ ! -f "$HOST_BIN" ]; then
        echo "Host-arch binary not found, building..."
        build_native "$HOST_ARCH_LABEL"
        build_zipapp
    fi
    export SMARTUSBHUB_BIN="$HOST_BIN"
    echo "Sourced build environment: SMARTUSBHUB_BIN=${SMARTUSBHUB_BIN}"
    return 0
fi

# ---------------------------------------------------------------------------
# Direct execution mode
# ---------------------------------------------------------------------------
echo "Building smartusbhub_cli for host architecture (${HOST_ARCH_LABEL})..."
build_native "$HOST_ARCH_LABEL"
build_zipapp

if [ "$HOST_ONLY" = false ]; then
    build_other_arch_with_docker
fi

echo "Build complete. Artifacts in ${DIST_DIR}:"
ls -la "$DIST_DIR"/smartusbhub-linux-* "$DIST_DIR"/smartusbhub.pyz 2>/dev/null || true
