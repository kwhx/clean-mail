#!/usr/bin/env bash
# ==============================================================================
# CleanMail Desktop Installer for Linux
# Installs standalone binary, desktop menu entry, application icon, and desktop shortcut.
# ==============================================================================

set -e

# Terminal colors
BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}${BOLD}"
echo "  ____ _                  __  __       _ _ "
echo " / ___| | ___  __ _ _ __ |  \/  | __ _(_) |"
echo "| |   | |/ _ \/ _\` | '_ \| |\/| |/ _\` | | |"
echo "| |___| |  __/ (_| | | | | |  | | (_| | | |"
echo " \____|_|\___|\__,_|_| |_|_|  |_|\__,_|_|_|"
echo -e "${NC}"
echo -e "${BOLD}CleanMail Desktop Installer (Linux x86_64)${NC}"
echo "---------------------------------------------------------"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Locate CleanMail standalone binary
BINARY_PATH=""
if [ -f "$SCRIPT_DIR/CleanMail" ]; then
    BINARY_PATH="$SCRIPT_DIR/CleanMail"
elif [ -f "$SCRIPT_DIR/../../dist/CleanMail" ]; then
    BINARY_PATH="$SCRIPT_DIR/../../dist/CleanMail"
elif [ -f "$SCRIPT_DIR/dist/CleanMail" ]; then
    BINARY_PATH="$SCRIPT_DIR/dist/CleanMail"
fi

if [ -z "$BINARY_PATH" ]; then
    echo -e "${RED}[ERROR] CleanMail binary not found in $SCRIPT_DIR${NC}"
    echo "Please ensure CleanMail is located in the same directory as install.sh"
    exit 1
fi

# Locate icon
ICON_SRC=""
if [ -f "$SCRIPT_DIR/cleanmail.png" ]; then
    ICON_SRC="$SCRIPT_DIR/cleanmail.png"
elif [ -f "$SCRIPT_DIR/../../packaging/linux/cleanmail.png" ]; then
    ICON_SRC="$SCRIPT_DIR/../../packaging/linux/cleanmail.png"
fi

# 2. Setup user target directories (no sudo required)
TARGET_BIN_DIR="$HOME/.local/bin"
TARGET_APP_DIR="$HOME/.local/share/applications"
TARGET_ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
TARGET_PIXMAP_DIR="$HOME/.local/share/pixmaps"

# Detect desktop folder via xdg-user-dir or fallback to ~/Desktop
DESKTOP_DIR=""
if command -v xdg-user-dir >/dev/null 2>&1; then
    DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
fi
if [ -z "$DESKTOP_DIR" ] || [ ! -d "$DESKTOP_DIR" ]; then
    DESKTOP_DIR="$HOME/Desktop"
fi

echo -e "Target user binary dir : ${BOLD}$TARGET_BIN_DIR${NC}"
echo -e "Target desktop dir     : ${BOLD}$DESKTOP_DIR${NC}"
echo ""

# Create directories
mkdir -p "$TARGET_BIN_DIR"
mkdir -p "$TARGET_APP_DIR"
mkdir -p "$TARGET_ICON_DIR"
mkdir -p "$TARGET_PIXMAP_DIR"
mkdir -p "$DESKTOP_DIR"

# 3. Copy binary
echo -e "==> Installing CleanMail executable to $TARGET_BIN_DIR/cleanmail..."
cp "$BINARY_PATH" "$TARGET_BIN_DIR/cleanmail"
chmod +x "$TARGET_BIN_DIR/cleanmail"

# 4. Copy icons
if [ -n "$ICON_SRC" ]; then
    echo -e "==> Installing application icon..."
    cp "$ICON_SRC" "$TARGET_ICON_DIR/cleanmail.png"
    cp "$ICON_SRC" "$TARGET_PIXMAP_DIR/cleanmail.png"
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
    fi
fi

# 5. Create desktop entry with absolute paths
echo -e "==> Creating system desktop application entry..."
DESKTOP_FILE="$TARGET_APP_DIR/cleanmail.desktop"
cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Version=1.0
Type=Application
Name=CleanMail
GenericName=Email Client
Comment=Fast, retro 90s-styled local desktop email client
Exec=$TARGET_BIN_DIR/cleanmail %u
Icon=$TARGET_ICON_DIR/cleanmail.png
Terminal=false
Categories=Network;Email;Utility;
StartupNotify=true
StartupWMClass=CleanMail
Keywords=email;mail;cleanmail;retro;inbox;
Actions=NewWindow;

[Desktop Action NewWindow]
Name=Open CleanMail
Exec=$TARGET_BIN_DIR/cleanmail
EOF
chmod +x "$DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$TARGET_APP_DIR" >/dev/null 2>&1 || true
fi

# 6. Place shortcut on User's Desktop
echo -e "==> Placing CleanMail shortcut on your Desktop..."
DESKTOP_SHORTCUT="$DESKTOP_DIR/CleanMail.desktop"
cp "$DESKTOP_FILE" "$DESKTOP_SHORTCUT"
chmod +x "$DESKTOP_SHORTCUT"

# Trust the desktop launcher on GNOME / Pop!_OS / Ubuntu
if command -v gio >/dev/null 2>&1; then
    gio set "$DESKTOP_SHORTCUT" metadata::trusted true >/dev/null 2>&1 || true
fi

# 7. Check for WebKitGTK runtime
echo -e "==> Checking system runtime dependencies..."
HAS_WEBKIT=false
if ldconfig -p 2>/dev/null | grep -qE "libwebkit2gtk-4\.[01]"; then
    HAS_WEBKIT=true
elif [ -f /usr/lib/x86_64-linux-gnu/libwebkit2gtk-4.1.so.0 ] || [ -f /usr/lib/x86_64-linux-gnu/libwebkit2gtk-4.0.so.37 ] || [ -f /usr/lib/libwebkit2gtk-4.1.so ]; then
    HAS_WEBKIT=true
fi

if [ "$HAS_WEBKIT" = true ]; then
    echo -e "${GREEN}[OK] WebKitGTK graphics/webview library detected.${NC}"
else
    echo -e "${YELLOW}[NOTE] WebKitGTK library was not detected in system libraries.${NC}"
    echo "If CleanMail fails to open a window, install it using your package manager:"
    echo "  - Ubuntu / Debian / Pop!_OS : sudo apt install -y libwebkit2gtk-4.1-0"
    echo "  - Fedora / RHEL             : sudo dnf install -y webkit2gtk4.1"
    echo "  - Arch Linux / Manjaro      : sudo pacman -S --noconfirm webkit2gtk-4.1"
fi

# 8. Check PATH for ~/.local/bin
if [[ ":$PATH:" != *":$TARGET_BIN_DIR:"* ]]; then
    echo -e "${YELLOW}[TIP] $TARGET_BIN_DIR is not yet in your \$PATH.${NC}"
    echo "You can add it by adding 'export PATH=\"\$HOME/.local/bin:\$PATH\"' to your ~/.bashrc"
fi

echo ""
echo -e "${GREEN}${BOLD}✓ CleanMail successfully installed!${NC}"
echo "You can launch CleanMail by:"
echo "  1. Double-clicking 'CleanMail' on your Desktop"
echo "  2. Searching for 'CleanMail' in your application menu / launcher"
echo "  3. Running '$TARGET_BIN_DIR/cleanmail' in terminal"
echo ""
