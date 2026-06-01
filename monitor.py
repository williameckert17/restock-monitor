import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from core.loader import load_sites
from core.poller import run_site
from core.status import StatusBoard

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/monitor.log"),
    ],
)
log = logging.getLogger(__name__)

_STATUS_PATH = Path("logs/status.json")
_DEFAULT_DASHBOARD_INTERVAL = 60  # seconds between console table refreshes


async def _dashboard_loop(board: StatusBoard, interval: int) -> None:
    """Periodically print a summary table to stdout. interval=0 disables it."""
    if interval <= 0:
        return
    while True:
        await asyncio.sleep(interval)
        # Blank line before table so it stands apart from the rolling log lines
        print("\n" + board.render() + "\n", flush=True)


async def main() -> None:
    sites_dir = Path("sites")
    configs = load_sites(sites_dir)

    if not configs:
        log.error(
            "No active site configs found in %s/\n"
            "Copy an *_example.toml, rename it (remove _example), fill in the URL and selectors.",
            sites_dir,
        )
        sys.exit(1)

    log.info("Loaded %d site(s): %s", len(configs), [c.name for c in configs])

    board = StatusBoard(status_path=_STATUS_PATH)
    for config in configs:
        board.register(config)

    # Print initial (empty) table so the user sees the monitor has started
    print("\n" + board.render() + "\n", flush=True)

    dashboard_interval = int(os.getenv("DASHBOARD_INTERVAL", str(_DEFAULT_DASHBOARD_INTERVAL)))

    await asyncio.gather(
        *(run_site(c, board) for c in configs),
        _dashboard_loop(board, dashboard_interval),
    )


def main_sync() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Monitor stopped by user.")


if __name__ == "__main__":
    main_sync()
