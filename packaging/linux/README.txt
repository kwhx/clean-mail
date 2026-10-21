================================================================================
CleanMail - Standalone Desktop Email Client (Linux x86_64)
================================================================================

CleanMail is a fast, local-first email client with a nostalgic 90s aesthetic.

INSTALLATION
------------
Open a terminal in this extracted folder and run:

    ./install.sh

This will automatically:
1. Install the standalone CleanMail binary to ~/.local/bin/cleanmail
2. Install the retro CleanMail icon to your desktop icon theme
3. Add CleanMail to your system applications menu (under Internet / Email)
4. Place a launchable CleanMail shortcut directly on your Desktop

LAUNCHING
---------
- Double-click the "CleanMail" icon on your Desktop, OR
- Search for "CleanMail" in your applications launcher, OR
- Run `cleanmail` from your terminal.

UNINSTALLATION
--------------
To remove CleanMail from your system:

    ./uninstall.sh

SYSTEM REQUIREMENTS
-------------------
CleanMail uses WebKitGTK for native desktop rendering. On modern Linux
distributions (Ubuntu 20.04+, Pop!_OS, Debian 11+, Fedora 36+, Arch Linux),
WebKitGTK is typically pre-installed.

If missing, install it via:
- Ubuntu/Debian/Pop!_OS: sudo apt install libwebkit2gtk-4.1-0
- Fedora:               sudo dnf install webkit2gtk4.1
- Arch Linux:           sudo pacman -S webkit2gtk-4.1
