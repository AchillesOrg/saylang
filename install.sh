#!/usr/bin/env sh
set -eu

REPO="AchillesOrg/saylang"
RELEASES="https://github.com/${REPO}/releases"
VERSION="${SAYLANG_VERSION:-latest}"

usage() {
  echo "Usage: sh install.sh [--version latest|VERSION]"
}

case "$#" in
  0) ;;
  1)
    case "$1" in
      -h|--help) usage; exit 0 ;;
      *) usage >&2; exit 2 ;;
    esac
    ;;
  2)
    if [ "$1" != "--version" ] || [ -z "$2" ]; then
      usage >&2
      exit 2
    fi
    VERSION="$2"
    ;;
  *) usage >&2; exit 2 ;;
esac

if [ "$VERSION" = "latest" ]; then
  BASE_URL="${RELEASES}/latest/download"
else
  if ! printf '%s\n' "$VERSION" | LC_ALL=C awk '
    NR != 1 || $0 !~ /^v?[0-9]+\.[0-9]+\.[0-9]+([-+][0-9A-Za-z.+-]+)?$/ { invalid = 1 }
    END { exit invalid }
  '; then
    echo "Invalid SayLang version '$VERSION'. Use 'latest' or a version such as 'v0.3.2'." >&2
    exit 2
  fi
  BASE_URL="${RELEASES}/download/v${VERSION#v}"
fi

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
TMP="$(mktemp "${DEST}.tmp.XXXXXX")"
trap 'rm -f "$TMP"' EXIT

URL="${BASE_URL}/${ASSET}"
echo "Downloading ${URL}..."
if ! curl -fsSL -H 'Cache-Control: no-cache' "$URL" -o "$TMP"; then
  echo "Could not download ${ASSET} for '${VERSION}'. Check the published assets at ${RELEASES}." >&2
  exit 1
fi

chmod +x "$TMP"
mv -f "$TMP" "$DEST"
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
