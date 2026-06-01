#!/usr/bin/env python3
"""Start the restock-monitor web dashboard.

Usage:
    python serve.py            # http://localhost:8000
    PORT=9000 python serve.py  # custom port
"""
import os

from dotenv import load_dotenv

from web.paths import APP_DATA_DIR, ENV_PATH

APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(ENV_PATH, override=True)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    print(f"\n  restock-monitor  →  http://localhost:{port}\n")
    uvicorn.run("web.app:app", host="127.0.0.1", port=port, reload=False)
