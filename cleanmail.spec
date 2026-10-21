# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from pathlib import Path

block_cipher = None

# Bundled web templates, retro styles, fonts, and meme gifs
datas = [
    ('templates', 'templates'),
    ('static', 'static'),
]

# Ensure uvicorn, fastapi, and app submodules are explicitly included
hiddenimports = [
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'fastapi',
    'starlette',
    'jinja2',
    'sqlite3',
    'app',
    'app.main',
    'app.config',
    'app.database',
    'app.parser',
    'app.classifier',
    'app.mcp_bridge',
    'webview',
    'webview.platforms.gtk',
    'webview.platforms.winforms',
    'webview.platforms.edgechromium',
    'webview.platforms.cocoa',
    'gi',
]

a = Analysis(
    ['desktop.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'transformers', 'scipy', 'sympy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

icon_file = None
if sys.platform.startswith('win') and os.path.exists('packaging/windows/cleanmail.ico'):
    icon_file = 'packaging/windows/cleanmail.ico'
elif sys.platform == 'darwin' and os.path.exists('packaging/mac/cleanmail.icns'):
    icon_file = 'packaging/mac/cleanmail.icns'

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='CleanMail',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='CleanMail.app',
        icon='packaging/mac/cleanmail.icns' if os.path.exists('packaging/mac/cleanmail.icns') else None,
        bundle_identifier='com.khwahish.cleanmail',
    )

