import asyncio
import logging
import os
from typing import Any, Dict, List

from core.models import CheckResult, SiteConfig, StockCheck, StockStatus
from core.poller import run_site
from core.status import StatusBoard

log = logging.getLogger(__name__)

_MIN_INTERVAL = 30


class MonitorRunner:
    def __init__(self, board: StatusBoard) -> None:
        self._board = board
        self._tasks: List[asyncio.Task] = []
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    async def start(self, entries: List[Dict[str, Any]]) -> int:
        if self._running:
            return 0

        configs = []
        for e in entries:
            if not e.get("enabled", True):
                log.debug("Skipping disabled entry: %s", e.get("product_name", "?"))
                continue
            try:
                configs.append(_entry_to_config(e))
            except Exception as exc:
                log.warning("Skipping watchlist entry %r: %s", e.get("product_name", "?"), exc)

        if not configs:
            return 0

        key = os.getenv("BBY_API_KEY", "")
        active = []
        for config in configs:
            self._board.register(config)
            if config.stock.type == "bestbuy" and not key:
                self._board.record(config, CheckResult(StockStatus.AWAITING_KEY))
            else:
                active.append(config)

        self._tasks = [asyncio.create_task(run_site(c, self._board)) for c in active]
        self._running = True
        log.info("Monitor started — %d site(s) polling", len(active))
        return len(active)

    def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
        self._running = False
        log.info("Monitor stopped")


def _entry_to_config(e: Dict[str, Any]) -> SiteConfig:
    # source=bestbuy_api always implies type=bestbuy regardless of stored type field
    stock_type = "bestbuy" if e.get("source") == "bestbuy_api" else e.get("type", "css")
    return SiteConfig(
        name=e["name"],
        url=e["url"],
        product_name=e["product_name"],
        poll_interval=max(int(e.get("poll_interval", 60)), _MIN_INTERVAL),
        jitter=int(e.get("jitter", 15)),
        stock=StockCheck(
            type=stock_type,
            sku=e.get("sku", ""),
            selector=e.get("selector", ""),
            in_stock_text=e.get("in_stock_text", ""),
            out_of_stock_text=e.get("out_of_stock_text", ""),
            match_type=e.get("match_type", "contains"),
            json_path=e.get("json_path", ""),
            in_stock_value=e.get("in_stock_value", ""),
        ),
        extra_headers=e.get("extra_headers", {}),
        price_selector=e.get("price_selector", ""),
        price_json_path=e.get("price_json_path", ""),
    )
