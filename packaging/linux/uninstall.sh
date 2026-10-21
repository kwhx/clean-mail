#!/usr/bin/env bash
# ==============================================================================
# CleanMail Desktop Uninstaller for Linux
# Removes binary, desktop menu entry, icons, and desktop shortcut.
# ==============================================================================

set -e

echo "Uninstalling CleanMail..."

# Binary
rm -f "$HOME/.local/bin/cleanmail"

# Menu launcher
rm -f "$HOME/.local/share/applications/cleanmail.desktop"

# Icons
rm -f "$HOME/.local/share/icons/hicolor/256x256/apps/cleanmail.png"
rm -f "$HOME/.local/share/pixmaps/cleanmail.png"

# Desktop shortcut
DESKTOP_DIR=""
if command -v xdg-user-dir >/dev/null 2>&1; then
    DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
fi
if [ -z "$DESKTOP_DIR" ] || [ ! -d "$DESKTOP_DIR" ]; then
    DESKTOP_DIR="$HOME/Desktop"
fi
rm -f "$DESKTOP_DIR/CleanMail.desktop"

# Refresh caches if tools exist
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

echo "✓ CleanMail uninstalled cleanly."
