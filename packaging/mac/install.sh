#!/usr/bin/env bash
# ==============================================================================
# CleanMail macOS Installer
# Copies CleanMail.app to ~/Applications and creates a Desktop shortcut.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_SRC="$SCRIPT_DIR/CleanMail.app"

if [ ! -d "$APP_SRC" ]; then
    echo "Error: CleanMail.app not found in $SCRIPT_DIR"
    exit 1
fi

TARGET_DIR="$HOME/Applications"
mkdir -p "$TARGET_DIR"

echo "==> Installing CleanMail.app to $TARGET_DIR..."
rm -rf "$TARGET_DIR/CleanMail.app"
cp -R "$APP_SRC" "$TARGET_DIR/"

# Create Desktop alias/symlink
DESKTOP_DIR="$HOME/Desktop"
if [ -d "$DESKTOP_DIR" ]; then
    echo "==> Creating shortcut on your Desktop..."
    ln -sf "$TARGET_DIR/CleanMail.app" "$DESKTOP_DIR/CleanMail"
fi

echo "✓ CleanMail installed successfully! You can launch it from Applications or your Desktop."
