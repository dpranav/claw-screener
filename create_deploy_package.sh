#!/usr/bin/env bash
set -euo pipefail

# Creates a portable deployment tarball for a new VM.
# The package intentionally excludes .env and other local state/secrets.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

OUT_DIR="${OUT_DIR:-dist}"
STAMP="$(date +%Y%m%d-%H%M%S)"
PKG_NAME="claw-screener-deploy-${STAMP}"
WORK_DIR="${OUT_DIR}/${PKG_NAME}"
ARCHIVE="${OUT_DIR}/${PKG_NAME}.tar.gz"

mkdir -p "$WORK_DIR"

copy_if_exists() {
  local p="$1"
  if [[ -e "$p" ]]; then
    cp -R "$p" "$WORK_DIR/"
  else
    echo "[package][warn] Missing: $p"
  fi
}

echo "[package] Preparing deployment payload at $WORK_DIR"

copy_if_exists "Dockerfile"
copy_if_exists "docker-compose.yml"
copy_if_exists "docker-entrypoint.sh"
copy_if_exists ".dockerignore"
copy_if_exists ".env.example"
copy_if_exists "bootstrap.sh"
copy_if_exists "cloud-init.yaml"
copy_if_exists "SKILL.md"
copy_if_exists "README.md"
copy_if_exists "package.json"
copy_if_exists "bun.lock"
copy_if_exists "tsconfig.json"
copy_if_exists "src"
copy_if_exists "scripts"
copy_if_exists "SAP_SpendCube_Skill"

# Clean cache/artifact folders from copied tree.
find "$WORK_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$WORK_DIR" -type f -name "*.pyc" -delete

mkdir -p "$OUT_DIR"
tar -czf "$ARCHIVE" -C "$OUT_DIR" "$PKG_NAME"

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$ARCHIVE" > "${ARCHIVE}.sha256"
fi

cat <<EOF
[package] Done.
Archive: $ARCHIVE
Checksum: ${ARCHIVE}.sha256

Next steps:
1) Copy archive to target VM.
2) Extract: tar -xzf $(basename "$ARCHIVE")
3) cd $PKG_NAME
4) cp .env.example .env   # fill real values
5) ./bootstrap.sh
EOF
