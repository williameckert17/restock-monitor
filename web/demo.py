"""
Demo runner — simulates restock events with fake product data.

Three fake products start out-of-stock.  Every 6–14 seconds one is
randomly picked, flipped to in-stock (firing the on_record hook so the
browser sees the update and the alert), held for 4–8 seconds, then
flipped back.  No real URLs are contacted.
"""
import asyncio
import logging
import random
from typing import Optional

from core.models import CheckResult, SiteConfig, StockCheck, StockStatus
from core.status import StatusBoard

log = logging.getLogger(__name__)

_DEMO_SITES = [
    SiteConfig(
        name="Demo GPU Store",
        url="https://example.com/rtx-5090",
        product_name="NVIDIA RTX 5090",
        stock=StockCheck(type="css"),
    ),
    SiteConfig(
        name="Demo Console Store",
        url="https://example.com/ps6",
        product_name="PlayStation 6",
        stock=StockCheck(type="css"),
    ),
    SiteConfig(
        name="Demo Sneaker Shop",
        url="https://example.com/air-max-99",
        product_name="Air Max 99 'Platinum'",
        stock=StockCheck(type="css"),
    ),
]

_DEMO_PRICES = {
    "NVIDIA RTX 5090":   "$1,999.99",
    "PlayStation 6":     "$599.99",
    "Air Max 99 'Platinum'": "$249.00",
}

_OUT = CheckResult(StockStatus.OUT_OF_STOCK)


class DemoRunner:
    def __init__(self, board: StatusBoard) -> None:
        self._board = board
        self._task: Optional[asyncio.Task] = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.running:
            return
        for config in _DEMO_SITES:
            self._board.register(config)
            self._board.record(config, _OUT)
        self._task = asyncio.create_task(self._run())
        log.info("Demo mode started")

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        log.info("Demo mode stopped")

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(random.uniform(6, 14))

                config = random.choice(_DEMO_SITES)
                price = _DEMO_PRICES.get(config.product_name)

                # OUT_OF_STOCK → IN_STOCK: board.on_record fires the SSE restock event
                self._board.record(config, CheckResult(StockStatus.IN_STOCK, price=price), restock_fired=True)

                await asyncio.sleep(random.uniform(4, 8))

                self._board.record(config, _OUT)
        except asyncio.CancelledError:
            pass
