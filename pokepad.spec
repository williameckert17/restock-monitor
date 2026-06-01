# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Pokepad (restock-monitor)
#
# Build:
#   pip install pyinstaller
#   pyinstaller pokepad.spec
#
# Output:
#   dist/Pokepad.app   (macOS)
#   dist/Pokepad.exe   (Windows — change icon= below to pokepad.ico)

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=[],
    datas=[
        # Web layer
        ("web/static",   "web/static"),
        ("web/__init__.py", "web"),
        ("web/app.py",    "web"),
        ("web/demo.py",   "web"),
        ("web/events.py", "web"),
        ("web/paths.py",  "web"),
        ("web/runner.py", "web"),
        ("web/store.py",  "web"),
        # Core engine
        ("core",  "core"),
        # Config & data dirs
        ("sites", "sites"),
        ("data",  "data"),
        (".env.example", "."),
        # FastAPI / Starlette templates and schema files
        *collect_data_files("fastapi"),
        *collect_data_files("starlette"),
        # pywebview bundled HTML/JS assets
        *collect_data_files("webview"),
    ],
    hiddenimports=[
        # uvicorn internals
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.wsproto_impl",
        "uvicorn.middleware.asgi2",
        "uvicorn.middleware.message_logger",
        "uvicorn.middleware.proxy_headers",
        # HTTP / async
        "h11",
        "anyio",
        "anyio._backends._asyncio",
        "httptools",
        # Pydantic
        "pydantic",
        "pydantic.deprecated.class_validators",
        "pydantic_core",
        # Project deps
        "jmespath",
        "selectolax.parser",
        "httpx",
        "tomli",
        "dotenv",
        # Email stdlib (used by notifier.py SMTP channel)
        "email.mime.text",
        "email.mime.multipart",
        # platformdirs
        "platformdirs",
        # pywebview platform backends
        "webview",
        "webview.platforms.cocoa",
        "webview.platforms.gtk",
        "webview.platforms.winforms",
        "webview.platforms.edgechromium",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Pokepad",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                          # no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # ── Icons ────────────────────────────────────────────────────────────────
    # macOS uses .icns; swap to pokepad.ico for Windows builds
    icon="web/static/icons/pokepad.icns",
)

app = BUNDLE(
    exe,
    name="Pokepad.app",
    icon="web/static/icons/pokepad.icns",
    bundle_identifier="com.pokepad.restock-monitor",
    info_plist={
        "CFBundleDisplayName":      "Pokepad",
        "CFBundleShortVersionString": "0.1.0",
        "NSHighResolutionCapable":  True,
        "NSRequiresAquaSystemAppearance": False,  # support dark mode
    },
)
