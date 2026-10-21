#!/usr/bin/env bash
# ==============================================================================
# CleanMail Linux Packaging Script
# Bundles standalone binary, installer, uninstaller, desktop file, icon, and README
# into dist/CleanMail-Linux-x86_64.tar.gz
# ==============================================================================

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
PKG_DIR="$DIST_DIR/CleanMail-Linux-x86_64"

echo "==> Packaging CleanMail for Linux x86_64..."

if [ ! -f "$DIST_DIR/CleanMail" ]; then
    echo "Error: $DIST_DIR/CleanMail not found. Build it with PyInstaller first."
    exit 1
fi

rm -rf "$PKG_DIR" "$DIST_DIR/CleanMail-Linux-x86_64.tar.gz"
mkdir -p "$PKG_DIR"

# Copy files into release folder
cp "$DIST_DIR/CleanMail" "$PKG_DIR/CleanMail"
chmod +x "$PKG_DIR/CleanMail"

cp "$REPO_ROOT/packaging/linux/install.sh" "$PKG_DIR/install.sh"
chmod +x "$PKG_DIR/install.sh"

cp "$REPO_ROOT/packaging/linux/uninstall.sh" "$PKG_DIR/uninstall.sh"
chmod +x "$PKG_DIR/uninstall.sh"

cp "$REPO_ROOT/packaging/linux/cleanmail.desktop" "$PKG_DIR/cleanmail.desktop"
cp "$REPO_ROOT/packaging/linux/cleanmail.png" "$PKG_DIR/cleanmail.png"
cp "$REPO_ROOT/packaging/linux/README.txt" "$PKG_DIR/README.txt"

# Create compressed tarball
cd "$DIST_DIR"
tar -czvf "CleanMail-Linux-x86_64.tar.gz" "CleanMail-Linux-x86_64"
echo "==> Successfully created $DIST_DIR/CleanMail-Linux-x86_64.tar.gz"
