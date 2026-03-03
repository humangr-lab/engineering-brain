#!/bin/sh
# Ontology Map — one-line installer
# Usage: curl -LsSf https://github.com/gustavoschneiter/ontology-map/releases/latest/download/install.sh | sh

set -e

REPO="gustavoschneiter/ontology-map"
BINARY="ontology-map"
INSTALL_DIR="${INSTALL_DIR:-/usr/local/bin}"

# Detect OS and architecture
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)

case "$OS" in
    linux)  OS_TARGET="unknown-linux-gnu" ;;
    darwin) OS_TARGET="apple-darwin" ;;
    *)      echo "Unsupported OS: $OS"; exit 1 ;;
esac

case "$ARCH" in
    x86_64|amd64)  ARCH_TARGET="x86_64" ;;
    aarch64|arm64) ARCH_TARGET="aarch64" ;;
    *)             echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

TARGET="${ARCH_TARGET}-${OS_TARGET}"

# Get latest release tag
LATEST=$(curl -sL "https://api.github.com/repos/${REPO}/releases/latest" | grep '"tag_name"' | sed 's/.*"tag_name": "\(.*\)".*/\1/')

if [ -z "$LATEST" ]; then
    echo "Error: Could not determine latest release"
    exit 1
fi

ARCHIVE="${BINARY}-${TARGET}-${LATEST}.tar.gz"
URL="https://github.com/${REPO}/releases/download/${LATEST}/${ARCHIVE}"

echo "Installing ${BINARY} ${LATEST} for ${TARGET}..."
echo "  From: ${URL}"
echo "  To:   ${INSTALL_DIR}/${BINARY}"

# Download and extract
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

curl -LsSf "$URL" -o "${TMPDIR}/${ARCHIVE}"

# Verify download succeeded and file is non-empty
if [ ! -s "${TMPDIR}/${ARCHIVE}" ]; then
    echo "Error: Download failed or file is empty"
    echo "  URL: ${URL}"
    echo "  Check that the release exists for your platform (${TARGET})"
    exit 1
fi

tar xzf "${TMPDIR}/${ARCHIVE}" -C "$TMPDIR"

# Verify binary was extracted
if [ ! -f "${TMPDIR}/${BINARY}" ]; then
    echo "Error: Binary '${BINARY}' not found after extraction"
    echo "  Archive contents:"
    ls -la "$TMPDIR"
    exit 1
fi

# Install
if [ -w "$INSTALL_DIR" ]; then
    cp "${TMPDIR}/${BINARY}" "${INSTALL_DIR}/${BINARY}"
else
    echo "Need sudo to install to ${INSTALL_DIR}"
    sudo cp "${TMPDIR}/${BINARY}" "${INSTALL_DIR}/${BINARY}"
fi

chmod +x "${INSTALL_DIR}/${BINARY}"

# Verify installation
if ! command -v "${BINARY}" >/dev/null 2>&1; then
    if [ ! -x "${INSTALL_DIR}/${BINARY}" ]; then
        echo "Warning: ${BINARY} was copied but may not be executable"
    fi
fi

echo ""
echo "✅ ${BINARY} ${LATEST} installed successfully!"
echo "   Run: ontology-map /path/to/project"
