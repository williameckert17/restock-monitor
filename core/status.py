"""
In-memory status board.

Each poll records a CheckResult into a per-site SiteState ring buffer.
StatusBoard.render() returns a formatted table for stdout.
StatusBoard.save_json() writes logs/status.json after every poll so the
file is always current (useful for external scripts or health checks).
"""
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.models import CheckResult, SiteConfig, StockStatus

log = logging.getLogger(__name__)

HISTORY_SIZE = 20  # recent results to retain per site

# ANSI colours — disabled automatically when stdout is not a TTY
_TTY = os.isatty(1)

def _c(code: str, s: str) -> str:
    return f"{code}{s}\033[0m" if _TTY else s

_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_RED    = "\033[31m"

_STATUS_FMT: Dict[StockStatus, Tuple[str, str]] = {
    StockStatus.IN_STOCK:     (_GREEN,  "In Stock"),
    StockStatus.OUT_OF_STOCK: (_DIM,    "Out of Stock"),
    StockStatus.PREORDER:     (_GREEN,  "Pre-Order Open"),
    StockStatus.COMING_SOON:  (_YELLOW, "Coming Soon"),
    StockStatus.BLOCKED:      (_YELLOW, "Blocked"),
    StockStatus.ERROR:        (_RED,    "Error"),
    StockStatus.UNKNOWN:      ("",      "Unknown"),
    StockStatus.AWAITING_KEY: (_YELLOW, "Awaiting Key"),
}


def _age(dt: Optional[datetime]) -> str:
    """Human-readable time since dt (e.g. '12s', '4m', '2h')."""
    if dt is None:
        return "—"
    secs = int((datetime.now(timezone.utc) - dt).total_seconds())
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    return f"{secs // 3600}h"


@dataclass
class SiteState:
    config: SiteConfig
    last_result: Optional[CheckResult] = None
    last_checked: Optional[datetime] = None
    status_since: Optional[datetime] = None   # when the current status was first seen
    consecutive: int = 0                       # consecutive polls returning this status
    total_checks: int = 0
    error_count: int = 0
    restock_count: int = 0
    history: List[Tuple[datetime, StockStatus, Optional[str]]] = field(default_factory=list)

    def record(self, result: CheckResult, restock_fired: bool = False) -> None:
        now = datetime.now(timezone.utc)
        self.total_checks += 1
        if result.status == StockStatus.ERROR:
            self.error_count += 1
        if restock_fired:
            self.restock_count += 1

        prev = self.last_result.status if self.last_result else None
        if result.status == prev:
            self.consecutive += 1
        else:
            self.consecutive = 1
            self.status_since = now

        self.last_result = result
        self.last_checked = now
        self.history.append((now, result.status, result.price))
        if len(self.history) > HISTORY_SIZE:
            self.history.pop(0)


class StatusBoard:
    """
    Thread-safe (asyncio-safe) registry of per-site check state.

    Typical usage
    -------------
    board = StatusBoard(status_path=Path("logs/status.json"))
    board.register(config)
    board.record(config, result, restock_fired=True)
    print(board.render())
    """

    def __init__(self, status_path: Optional[Path] = None, on_record=None) -> None:
        self._states: Dict[str, SiteState] = {}
        self._path = status_path
        self._on_record = on_record  # Optional[Callable[[SiteConfig, CheckResult, bool], None]]

    def register(self, config: SiteConfig) -> None:
        self._states[config.name] = SiteState(config=config)

    def clear(self) -> None:
        self._states.clear()

    def record(self, config: SiteConfig, result: CheckResult, restock_fired: bool = False) -> None:
        """Update state, persist to JSON, and call the optional on_record hook."""
        if config.name not in self._states:
            return
        self._states[config.name].record(result, restock_fired)
        if self._path:
            self.save_json(self._path)
        if self._on_record:
            try:
                self._on_record(config, result, restock_fired)
            except Exception as exc:
                log.warning("StatusBoard on_record hook error: %s", exc)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def render(self) -> str:
        """Return a formatted summary table suitable for printing to a terminal."""
        states = self._states
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # Column widths (content only; no separators)
        W = dict(site=18, product=26, status=14, price=12, age=6, checks=7)

        ruler = "  " + "─" * (sum(W.values()) + len(W) - 1)

        def row(vals: Dict[str, str], color: str = "") -> str:
            cells = (
                f"{vals.get('site', ''):<{W['site']}}"
                f"{vals.get('product', ''):<{W['product']}}"
                f"{vals.get('status', ''):<{W['status']}}"
                f"{vals.get('price', ''):<{W['price']}}"
                f"{vals.get('age', ''):<{W['age']}}"
                f"{vals.get('checks', ''):>{W['checks']}}"
            )
            line = "  " + cells
            return _c(color, line) if color else line

        lines: List[str] = [
            _c(_BOLD, f"  restock-monitor  ·  {now_str}  ·  {len(states)} site(s)"),
            "",
            row({"site": "SITE", "product": "PRODUCT", "status": "STATUS",
                 "price": "PRICE", "age": "AGE", "checks": "CHECKS"}),
            ruler,
        ]

        for state in states.values():
            if state.last_result:
                color, label = _STATUS_FMT.get(state.last_result.status, ("", "Unknown"))
                price_str = state.last_result.price or "—"
            else:
                color, label, price_str = "", "—", "—"

            lines.append(row({
                "site":    state.config.name[:W["site"] - 1],
                "product": state.config.product_name[:W["product"] - 1],
                "status":  label[:W["status"] - 1],
                "price":   price_str[:W["price"] - 1],
                "age":     _age(state.last_checked),
                "checks":  str(state.total_checks),
            }, color))

        lines.append(ruler)
        total_checks   = sum(s.total_checks  for s in states.values())
        total_errors   = sum(s.error_count   for s in states.values())
        total_restocks = sum(s.restock_count for s in states.values())
        lines.append(
            _c(_DIM, f"  Checks: {total_checks}  Errors: {total_errors}  Restocks detected: {total_restocks}")
        )
        return "\n".join(lines)

    # ── Persistence ───────────────────────────────────────────────────────────

    def save_json(self, path: Path) -> None:
        """Write machine-readable state to path (synchronous; fast for small files)."""
        data: Dict = {
            "updated": datetime.now(timezone.utc).isoformat(),
            "sites": {},
        }
        for name, state in self._states.items():
            result = state.last_result
            data["sites"][name] = {
                "product":       state.config.product_name,
                "url":           state.config.url,
                "status":        result.status.name if result else None,
                "price":         result.price       if result else None,
                "last_checked":  state.last_checked.isoformat() if state.last_checked else None,
                "status_since":  state.status_since.isoformat() if state.status_since  else None,
                "consecutive":   state.consecutive,
                "total_checks":  state.total_checks,
                "error_count":   state.error_count,
                "restock_count": state.restock_count,
                "recent": [
                    {"time": t.isoformat(), "status": s.name, "price": p}
                    for t, s, p in state.history[-10:]
                ],
            }
        try:
            path.write_text(json.dumps(data, indent=2))
        except OSError as exc:
            log.warning("Could not write %s: %s", path, exc)
