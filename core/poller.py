import asyncio
import logging
import os
import random
from typing import Optional

import httpx

from core.checker import check_stock, check_stock_bestbuy
from core.models import SiteConfig, StockStatus
from core.notifier import notify
from core.status import StatusBoard
from core import preorder_detect as pd

log = logging.getLogger(__name__)

_USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36",
)
_REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "15"))
_MAX_BACKOFF = 600  # 10 minutes, caps the exponential series

_DEFINITIVE = {StockStatus.IN_STOCK, StockStatus.OUT_OF_STOCK, StockStatus.PREORDER, StockStatus.COMING_SOON}

def _to_pd_state(status: Optional[StockStatus]) -> Optional[str]:
    return {
        StockStatus.IN_STOCK:     pd.IN_STOCK,
        StockStatus.PREORDER:     pd.PREORDER,
        StockStatus.OUT_OF_STOCK: pd.OUT_OF_STOCK,
        StockStatus.COMING_SOON:  pd.COMING_SOON,
        StockStatus.UNKNOWN:      pd.COMING_SOON,
        StockStatus.BLOCKED:      pd.BLOCKED,
    }.get(status)  # type: ignore[arg-type]


async def run_site(config: SiteConfig, board: StatusBoard) -> None:
    base_headers = {
        "User-Agent": _USER_AGENT,
        "Accept-Language": "en-US,en;q=0.5",
        "DNT": "1",
    }
    limits = httpx.Limits(max_connections=1, max_keepalive_connections=1)

    async with httpx.AsyncClient(
        headers=base_headers,
        timeout=_REQUEST_TIMEOUT,
        limits=limits,
        http2=True,
    ) as client:
        last_status: Optional[StockStatus] = None
        last_definitive: Optional[StockStatus] = None
        consecutive_errors = 0

        log.info("[%s] starting — polling every %ds ±%ds", config.name, config.poll_interval, config.jitter)

        while True:
            if config.stock.type == "bestbuy":
                result = await check_stock_bestbuy(client, config)
            else:
                result = await check_stock(client, config)
            status = result.status

            # Log status transitions (suppresses duplicate lines)
            if status != last_status:
                log.info(
                    "[%s] %-22s  %s",
                    config.name,
                    config.product_name,
                    status.name.replace("_", " ").title(),
                )
                last_status = status

            # Alert when transitioning into an orderable state (IN_STOCK or PREORDER)
            # from a non-orderable one. Ignores BLOCKED/ERROR/fresh-start so we
            # never fire spurious alerts.
            current_pd = _to_pd_state(status)
            prev_pd    = _to_pd_state(last_definitive)
            restock_fired = bool(current_pd and pd.should_alert(prev_pd, current_pd))
            if restock_fired:
                label = pd.alert_label(current_pd)
                await notify(config, price=result.price, label=label)

            if status in _DEFINITIVE:
                last_definitive = status

            # Record to the status board (updates in-memory state + writes JSON)
            board.record(config, result, restock_fired=restock_fired)

            if status == StockStatus.ERROR:
                consecutive_errors += 1
                # Exponential back-off: 120s, 240s, 480s, then capped at 600s
                backoff = min(60 * (2 ** consecutive_errors), _MAX_BACKOFF)
                log.info("[%s] back-off %ds after %d consecutive error(s)", config.name, backoff, consecutive_errors)
                await asyncio.sleep(backoff)
                continue

            consecutive_errors = 0
            delay = config.poll_interval + random.uniform(0, config.jitter)
            log.debug("[%s] next poll in %.1fs", config.name, delay)
            await asyncio.sleep(delay)
