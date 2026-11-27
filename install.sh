#!/usr/bin/env sh
set -eu

REPO="AchillesOrg/saylang"
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Darwin)
    case "$ARCH" in
      arm64) ASSET="saylang-macos-arm64" ;;
      x86_64) ASSET="saylang-macos-x64" ;;
      *) echo "Unsupported macOS architecture: $ARCH" >&2; exit 1 ;;
    esac
    ;;
  *)
    echo "install.sh targets macOS prebuilt binaries. On Linux, install via:" >&2
    echo "  pip install git+https://github.com/${REPO}.git" >&2
    exit 1
    ;;
esac

if [ -w "/usr/local/bin" ]; then
  DEST_DIR="/usr/local/bin"
else
  DEST_DIR="${HOME}/.local/bin"
  mkdir -p "$DEST_DIR"
fi

DEST="${DEST_DIR}/saylang"
URL="https://github.com/${REPO}/releases/latest/download/${ASSET}"

echo "Downloading ${URL}..."
if ! curl -fsSL "$URL" -o "$DEST"; then
  if [ "$ASSET" = "saylang-macos-x64" ]; then
    FALLBACK_URL="https://github.com/${REPO}/releases/latest/download/saylang-macos-arm64"
    echo "Trying ${FALLBACK_URL}..." >&2
    curl -fsSL "$FALLBACK_URL" -o "$DEST"
  else
    echo "Failed to download prebuilt SayLang binary. You can install from source instead:" >&2
    echo "  pip install git+https://github.com/${REPO}.git" >&2
    exit 1
  fi
fi

chmod +x "$DEST"
echo "Installed SayLang to ${DEST}"

case ":${PATH}:" in
  *":${DEST_DIR}:"*) ;;
  *)
    echo ""
    echo "Add ${DEST_DIR} to your PATH to run 'saylang' anywhere:"
    echo "  export PATH=\"${DEST_DIR}:\$PATH\""
    ;;
esac

"${DEST}" --version
