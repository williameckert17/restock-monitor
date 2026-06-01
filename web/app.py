"""
FastAPI web dashboard for restock-monitor.

All SSE events flow through the single on_record callback wired into
StatusBoard — both real polling and demo mode use the same path, so
the browser always gets consistent live updates.

Security notes:
  - BBY_API_KEY is never returned to the browser.  GET /api/settings
    returns only a boolean { bby_key_set: true/false }.
  - The constructed Best Buy API URL (which embeds the key as a query
    param) is never logged — checker.py is responsible for that invariant.
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.models import SiteConfig
from core.status import StatusBoard
from web import store
from web.demo import DemoRunner
from web.events import bus
from web.paths import APP_DATA_DIR, ENV_PATH, SEEDS_PATH, STATIC_DIR, STATUS_PATH
from web.runner import MonitorRunner

board = StatusBoard(status_path=STATUS_PATH)
runner = MonitorRunner(board)
demo = DemoRunner(board)


# ── on_record callback ────────────────────────────────────────────────────────

def _on_record(config: SiteConfig, result, restock_fired: bool) -> None:
    state = board._states.get(config.name)
    bus.publish("status_update", {
        "name": config.name,
        "product_name": config.product_name,
        "url": config.url,
        "status": result.status.name,
        "price": result.price,
        "last_checked": state.last_checked.isoformat() if state and state.last_checked else None,
        "total_checks": state.total_checks if state else 0,
    })
    if restock_fired:
        bus.publish("restock", {
            "name": config.name,
            "product_name": config.product_name,
            "price": result.price,
            "url": config.url,
            "time": datetime.now(timezone.utc).isoformat(),
        })


# ── App lifecycle ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    board._on_record = _on_record
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    store.seed_if_empty(SEEDS_PATH)
    yield
    runner.stop()
    demo.stop()


app = FastAPI(title="restock-monitor", lifespan=lifespan)


# ── SSE ───────────────────────────────────────────────────────────────────────

@app.get("/api/stream")
async def sse():
    return StreamingResponse(
        bus.stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Watchlist ─────────────────────────────────────────────────────────────────

class WatchlistEntry(BaseModel):
    name: str
    url: str
    product_name: str
    type: str = "css"
    sku: str = ""
    selector: str = ""
    in_stock_text: str = ""
    out_of_stock_text: str = ""
    poll_interval: int = 60
    jitter: int = 15
    check_type: str = "product"   # "product" or "category"
    source: str = "public_check"  # "bestbuy_api" or "public_check"
    enabled: bool = True


@app.get("/api/watchlist")
def get_watchlist():
    return store.list_sites()


@app.post("/api/watchlist", status_code=201)
def add_watchlist(entry: WatchlistEntry):
    return store.add_site(entry.model_dump())


@app.put("/api/watchlist/{site_id}")
def update_watchlist(site_id: str, entry: WatchlistEntry):
    updated = store.update_site(site_id, entry.model_dump())
    if updated is None:
        raise HTTPException(404, "Not found")
    return updated


@app.delete("/api/watchlist/{site_id}", status_code=204)
def delete_watchlist(site_id: str):
    if not store.delete_site(site_id):
        raise HTTPException(404, "Not found")


# ── Monitor control ───────────────────────────────────────────────────────────

@app.get("/api/monitor/status")
def monitor_status():
    sites = {}
    for name, state in board._states.items():
        r = state.last_result
        sites[name] = {
            "product_name": state.config.product_name,
            "url": state.config.url,
            "status": r.status.name if r else None,
            "price": r.price if r else None,
            "last_checked": state.last_checked.isoformat() if state.last_checked else None,
            "total_checks": state.total_checks,
            "is_demo": name.startswith("Demo "),
        }
    return {
        "running": runner.running,
        "demo_mode": demo.running,
        "sites": sites,
    }


@app.post("/api/monitor/start")
async def start_monitor():
    if demo.running:
        raise HTTPException(409, "Stop demo mode before starting the monitor")
    entries = store.list_sites()
    if not entries:
        raise HTTPException(400, "No sites in watchlist — add at least one product first")
    board.clear()
    count = await runner.start(entries)
    return {"started": count}


@app.post("/api/monitor/stop")
def stop_monitor():
    runner.stop()
    board.clear()
    return {"stopped": True}


@app.post("/api/demo/start")
async def start_demo():
    if runner.running:
        raise HTTPException(409, "Stop the monitor before starting demo mode")
    board.clear()
    await demo.start()
    return {"demo": True}


@app.post("/api/demo/stop")
def stop_demo():
    demo.stop()
    board.clear()
    return {"demo": False}


# ── Alerts ────────────────────────────────────────────────────────────────────

@app.get("/api/alerts")
def get_alerts():
    return bus.alert_history()


# ── Settings ─────────────────────────────────────────────────────────────────

class SettingsIn(BaseModel):
    bby_api_key: Optional[str] = None


@app.get("/api/settings")
def get_settings():
    return {"bby_key_set": bool(os.getenv("BBY_API_KEY", ""))}


@app.post("/api/settings")
def save_settings(body: SettingsIn):
    if body.bby_api_key is not None:
        from dotenv import set_key
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        set_key(str(ENV_PATH), "BBY_API_KEY", body.bby_api_key)
        os.environ["BBY_API_KEY"] = body.bby_api_key
    return {"bby_key_set": bool(os.getenv("BBY_API_KEY", ""))}


# ── Static files ─────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
