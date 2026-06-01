# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build spec for Pokepad.

Output
------
  macOS  : dist/Pokepad.app   (app bundle)
  Windows: dist/Pokepad.exe   (one-file executable)

NOTE: PyInstaller does not support cross-compilation.
Build on macOS to get a .app; build on Windows to get a .exe.

Quick build:
    pip install pyinstaller
    python scripts/build.py          # recommended
    # or directly:
    pyinstaller pokepad.spec
"""
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

IS_MACOS   = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

ICON = (
    "web/static/icons/pokepad.icns" if IS_MACOS else
    "web/static/icons/pokepad.ico"
)

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=[],
    datas=[
        # ── Bundled static assets (HTML / CSS / sprites / icons) ─────────────
        ("web/static",   "web/static"),
        # ── Example TOML site configs (read-only reference in the bundle) ────
        ("sites",        "sites"),
        # ── Env template surfaced on first-run setup ──────────────────────────
        (".env.example", "."),
        # ── Third-party package data ──────────────────────────────────────────
        *collect_data_files("fastapi"),     # JSON schema / OpenAPI assets
        *collect_data_files("starlette"),   # templates
        *collect_data_files("webview"),     # pywebview bundled HTML/JS
        *collect_data_files("certifi"),     # CA bundle for HTTPS
    ],
    hiddenimports=[
        # ── Web layer ─────────────────────────────────────────────────────────
        # These modules are only referenced by string ("web.app:app") inside
        # uvicorn.Config, so PyInstaller can't discover them via import analysis.
        "web.app", "web.demo", "web.events",
        "web.paths", "web.runner", "web.store",

        # ── Core engine ───────────────────────────────────────────────────────
        "core.checker", "core.loader", "core.models",
        "core.notifier", "core.poller", "core.status",

        # ── uvicorn ───────────────────────────────────────────────────────────
        # collect_submodules catches every uvicorn.* entry point loaded by
        # string at runtime (loops, protocols, lifespan, middleware, …).
        *collect_submodules("uvicorn"),

        # ── Async runtime ─────────────────────────────────────────────────────
        "anyio",
        "anyio._backends._asyncio",
        "sniffio",

        # ── HTTP stack ────────────────────────────────────────────────────────
        "h11",
        "httptools",
        "httpcore",
        "httpx",
        "certifi",

        # ── Pydantic v2 ───────────────────────────────────────────────────────
        "pydantic",
        "pydantic.deprecated.class_validators",
        "pydantic_core",

        # ── Misc runtime deps ─────────────────────────────────────────────────
        "jmespath",
        "selectolax.parser",
        "tomli",
        "dotenv",
        "platformdirs",

        # ── Email stdlib (SMTP notifier channel) ──────────────────────────────
        "email.mime.text",
        "email.mime.multipart",

        # ── pywebview platform backends ───────────────────────────────────────
        # Only one backend loads at runtime; listing all prevents import errors
        # when pywebview probes available backends during startup.
        "webview",
        "webview.platforms.cocoa",
        "webview.platforms.gtk",
        "webview.platforms.winforms",
        "webview.platforms.edgechromium",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Dev / build tooling — never needed at runtime
        "pytest", "pip", "setuptools", "wheel",
        # GUI toolkits we don't use
        "tkinter", "wx",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

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
    upx=False,          # UPX can trigger AV false-positives on Windows; skip it
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # windowed — no terminal on either platform
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)

# ── macOS: wrap the EXE inside a .app bundle ─────────────────────────────────
if IS_MACOS:
    app = BUNDLE(
        exe,
        name="Pokepad.app",
        icon=ICON,
        bundle_identifier="com.pokepad.restock-monitor",
        info_plist={
            "CFBundleDisplayName":        "Pokepad",
            "CFBundleShortVersionString": "0.1.0",
            "NSHighResolutionCapable":    True,
            "NSRequiresAquaSystemAppearance": False,  # allow dark mode
        },
    )
