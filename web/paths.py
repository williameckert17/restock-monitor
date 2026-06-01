"""
Central path resolution for Pokepad.

User-writable data (watchlist, .env, status) lives in the OS per-user
app-data directory so the app works correctly when installed or frozen.

Read-only static assets are resolved via sys._MEIPASS when frozen under
PyInstaller; otherwise they come from the normal project tree.

Usage
-----
    from web.paths import APP_DATA_DIR, ENV_PATH, WATCHLIST_PATH, STATUS_PATH, STATIC_DIR
"""
import sys
from pathlib import Path

from platformdirs import user_data_dir

# ── User-writable data ────────────────────────────────────────────────────────
# macOS  → ~/Library/Application Support/Pokepad
# Windows→ %APPDATA%\Pokepad\Pokepad
# Linux  → ~/.local/share/Pokepad

APP_DATA_DIR: Path = Path(user_data_dir("Pokepad", "Pokepad"))

ENV_PATH:            Path = APP_DATA_DIR / ".env"
WATCHLIST_PATH:      Path = APP_DATA_DIR / "watchlist.json"
NOTIFICATIONS_PATH:  Path = APP_DATA_DIR / "notifications.json"
STATUS_PATH:         Path = APP_DATA_DIR / "status.json"
LOG_PATH:            Path = APP_DATA_DIR / "monitor.log"

# ── Read-only bundled assets ──────────────────────────────────────────────────
# PyInstaller extracts ("web/static", "web/static") into _MEIPASS.

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    STATIC_DIR: Path = Path(sys._MEIPASS) / "web" / "static"
    SEEDS_PATH: Path = Path(sys._MEIPASS) / "seeds.json"
else:
    STATIC_DIR = Path(__file__).parent / "static"
    SEEDS_PATH = Path(__file__).parent.parent / "seeds.json"
