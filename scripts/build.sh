#!/usr/bin/env bash
set -euo pipefail

# Build script for smartusbhub_cli.
#
# Usage:
#   ./scripts/build.sh              # build the host-arch single-file executable + wheel/sdist
#   ./scripts/build.sh --multi-arch # also attempt the other arch via Docker
#   ./scripts/build.sh --host-only  # same as default (explicit)
#
# Artifacts are written to dist/:
#   - smartusbhub_cli-<version>-py3-none-any.whl
#   - smartusbhub_cli-<version>.tar.gz
#   - smartusbhub-linux-<arch>
#
# The single-file executable is a shiv zipapp: it contains the wheel plus all
# dependencies and runs on any Linux with Python >=3.10 installed.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Use Tsinghua PyPI mirror for all network access in this script.
export PIP_INDEX_URL="https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple"
export PIP_TRUSTED_HOST="mirrors.tuna.tsinghua.edu.cn"

# Prefer the local virtual environment if it exists.
PYTHON="${PYTHON:-${PROJECT_ROOT}/.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
    PYTHON="python3"
fi

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

PIP_INSTALL="$PYTHON -m pip install -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple"

ensure_build_deps() {
    if ! "$PYTHON" -m build --help >/dev/null 2>&1; then
        echo "Installing build tools into ${PYTHON}..."
        $PIP_INSTALL build
    fi

    if ! command -v "$PYTHON" -m shiv >/dev/null 2>&1; then
        echo "Installing shiv into ${PYTHON}..."
        $PIP_INSTALL shiv
    fi
}

build_wheel() {
    echo "Building wheel and sdist..."
    "$PYTHON" -m build --outdir "$DIST_DIR"
    echo "wheel/sdist: $DIST_DIR/smartusbhub_cli-*"
}

build_native() {
    local arch="$1"
    echo "Building single-file executable for ${arch}..."

    local wheel
    wheel=$(ls "$DIST_DIR"/smartusbhub_cli-*.whl | head -n 1)
    if [ -z "$wheel" ]; then
        echo "No wheel found in $DIST_DIR; run build_wheel first." >&2
        exit 1
    fi

    local binary="$DIST_DIR/smartusbhub-linux-${arch}"
    "$PYTHON" -m shiv \
        -c smartusbhub \
        -o "$binary" \
        --python '/usr/bin/env python3' \
        --compressed \
        "$wheel"
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

    echo "Attempting to build ${other_arch} executable via Docker (this may be slow)..."
    if docker run --rm --platform "linux/${other_arch}" \
        -v "$PROJECT_ROOT:/workspace" \
        -w /workspace \
        python:3.11-slim \
        bash -c "
            set -euo pipefail
            python -m pip install --upgrade pip -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
            pip install -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple -e '.[dev]'
            ./scripts/build.sh --host-only
            mv dist/smartusbhub-linux-x86_64 dist/smartusbhub-linux-${other_arch} || true
        "; then
        echo "Cross-arch binary: $DIST_DIR/smartusbhub-linux-${other_arch}"
    else
        echo "Warning: ${other_arch} cross-arch build failed (QEMU/binfmt_misc may be required)." >&2
    fi
}

# ---------------------------------------------------------------------------
# Direct execution mode
# ---------------------------------------------------------------------------
ensure_build_deps

echo "Building smartusbhub_cli for host architecture (${HOST_ARCH_LABEL})..."
build_wheel
build_native "$HOST_ARCH_LABEL"

if [ "$HOST_ONLY" = false ]; then
    build_other_arch_with_docker
fi

echo "Build complete. Artifacts in ${DIST_DIR}:"
ls -la "$DIST_DIR"/smartusbhub-linux-* "$DIST_DIR"/smartusbhub_cli-*.* 2>/dev/null || true
