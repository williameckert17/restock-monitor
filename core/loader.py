import logging
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]

from core.models import SiteConfig, StockCheck

log = logging.getLogger(__name__)

MIN_POLL_INTERVAL = 30  # seconds — hard floor to stay polite


def load_sites(directory: Path) -> list[SiteConfig]:
    configs: list[SiteConfig] = []
    for path in sorted(directory.glob("*.toml")):
        if path.stem.endswith("_example"):
            continue
        try:
            configs.append(_parse(path))
            log.debug("Loaded config: %s", path.name)
        except Exception as exc:
            log.warning("Skipping %s — %s", path.name, exc)
    return configs


def _parse(path: Path) -> SiteConfig:
    with path.open("rb") as f:
        data = tomllib.load(f)

    site = data.get("site", {})
    product = data.get("product", {})
    stock_raw = data.get("stock", {})
    extra_headers = data.get("extra_headers", {})

    name = site.get("name")
    url = site.get("url")
    product_name = product.get("name")
    missing = [k for k, v in {"site.name": name, "site.url": url, "product.name": product_name}.items() if not v]
    if missing:
        raise ValueError(f"missing required fields: {missing}")

    stock = StockCheck(
        type=stock_raw.get("type", "css"),
        sku=stock_raw.get("sku", ""),
        selector=stock_raw.get("selector", ""),
        in_stock_text=stock_raw.get("in_stock_text", ""),
        out_of_stock_text=stock_raw.get("out_of_stock_text", ""),
        attribute=stock_raw.get("attribute", ""),
        match_type=stock_raw.get("match_type", "contains"),
        json_path=stock_raw.get("json_path", ""),
        in_stock_value=stock_raw.get("in_stock_value", ""),
    )

    poll_interval = int(site.get("poll_interval", 60))
    if poll_interval < MIN_POLL_INTERVAL:
        log.warning(
            "%s: poll_interval %ds is below the %ds minimum — clamping. "
            "Lower values risk overwhelming the server and may violate its ToS.",
            path.name, poll_interval, MIN_POLL_INTERVAL,
        )
        poll_interval = MIN_POLL_INTERVAL

    return SiteConfig(
        name=name,
        url=url,
        product_name=product_name,
        poll_interval=poll_interval,
        jitter=int(site.get("jitter", 15)),
        stock=stock,
        extra_headers=extra_headers,
        price_selector=product.get("price_selector", ""),
        price_json_path=product.get("price_json_path", ""),
    )
