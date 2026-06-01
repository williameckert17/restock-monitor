"""
Server-Sent Events bus.

All live browser updates flow through the module-level `bus` singleton.
Subscribers get their own asyncio.Queue; `stream()` is an async generator
that yields SSE-formatted strings, sending a heartbeat comment every 20 s
so the browser doesn't time out on idle.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List

log = logging.getLogger(__name__)

_MAX_HISTORY = 50  # restock alerts to keep in memory


class EventBus:
    def __init__(self) -> None:
        self._subscribers: List[asyncio.Queue] = []
        self._alert_history: List[Dict[str, Any]] = []

    def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        payload = json.dumps({"type": event_type, **data})
        dead = []
        for q in self._subscribers:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

        if event_type == "restock":
            self._alert_history.append({"time": datetime.now(timezone.utc).isoformat(), **data})
            if len(self._alert_history) > _MAX_HISTORY:
                self._alert_history.pop(0)

    def alert_history(self) -> List[Dict[str, Any]]:
        return list(self._alert_history)

    async def stream(self) -> AsyncIterator[str]:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subscribers.append(q)
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=20.0)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass


bus = EventBus()
