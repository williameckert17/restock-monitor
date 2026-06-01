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

log = logging.getLogger(__name__)

_USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36",
)
_REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "15"))
_MAX_BACKOFF = 600  # 10 minutes, caps the exponential series

_DEFINITIVE = {StockStatus.IN_STOCK, StockStatus.OUT_OF_STOCK}


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

            # Alert only on a confirmed OUT_OF_STOCK → IN_STOCK transition.
            # Transitions from UNKNOWN/BLOCKED/ERROR into IN_STOCK are ignored so
            # a fresh start or a temporary block doesn't fire spurious alerts.
            restock_fired = (status == StockStatus.IN_STOCK and last_definitive == StockStatus.OUT_OF_STOCK)
            if restock_fired:
                await notify(config, price=result.price)

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
