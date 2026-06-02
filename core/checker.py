import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from typing import Any, List, Optional, Tuple

import httpx
import jmespath
from selectolax.parser import HTMLParser

from core.models import CheckResult, SiteConfig, StockCheck, StockStatus

log = logging.getLogger(__name__)

_BLOCKED_STATUS_CODES = {403, 406, 429, 503, 999}
_BLOCK_RE = re.compile(
    r"(captcha|hcaptcha|recaptcha|cf-challenge|cf_chl|access.?denied|bot.?detected|automated.?access)",
    re.IGNORECASE,
)
_ATOM_NS = "http://www.w3.org/2005/Atom"

_ACCEPT_BY_TYPE = {
    "json":    "application/json, */*;q=0.8",
    "bestbuy": "application/json, */*;q=0.8",
    "rss":     "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8",
    "css":     "text/html, application/xhtml+xml, */*;q=0.8",
}

_BBY_API = "https://api.bestbuy.com/v1"
_BBY_FIELDS = "sku,name,onlineAvailability,salePrice,regularPrice"


# ── Matching helper ───────────────────────────────────────────────────────────

def _match(value: str, pattern: str, match_type: str) -> bool:
    if match_type == "exact":
        return value.lower() == pattern.lower()
    if match_type == "regex":
        return bool(re.search(pattern, value, re.IGNORECASE))
    if match_type == "not_contains":
        return pattern.lower() not in value.lower()
    return pattern.lower() in value.lower()  # "contains" default


# ── Stock checkers ────────────────────────────────────────────────────────────

def _check_css(html: str, check: StockCheck) -> StockStatus:
    from core import preorder_detect as pd

    if not check.selector:
        return StockStatus.UNKNOWN
    nodes = HTMLParser(html).css(check.selector)
    if not nodes:
        return StockStatus.UNKNOWN

    text = (
        " ".join(n.attributes.get(check.attribute, "") for n in nodes)
        if check.attribute
        else " ".join(n.text(strip=True) for n in nodes)
    )

    # Pre-order detection runs before configured patterns so a "Pre-Order"
    # button is never misclassified as simply out-of-stock.
    pd_state = pd.classify({"listed": True, "buy_text": text})
    if pd_state == pd.PREORDER:
        return StockStatus.PREORDER
    if pd_state == pd.COMING_SOON and not check.in_stock_text and not check.out_of_stock_text:
        return StockStatus.COMING_SOON

    if check.in_stock_text:
        return StockStatus.IN_STOCK if _match(text, check.in_stock_text, check.match_type) else StockStatus.OUT_OF_STOCK
    if check.out_of_stock_text:
        return StockStatus.OUT_OF_STOCK if _match(text, check.out_of_stock_text, check.match_type) else StockStatus.IN_STOCK
    return StockStatus.IN_STOCK if text.strip() else StockStatus.OUT_OF_STOCK


def _check_json(body: str, check: StockCheck) -> StockStatus:
    if not check.json_path:
        return StockStatus.UNKNOWN
    try:
        data: Any = json.loads(body)
    except json.JSONDecodeError:
        return StockStatus.ERROR
    value = jmespath.search(check.json_path, data)
    if value is None:
        return StockStatus.UNKNOWN
    return StockStatus.IN_STOCK if _match(str(value), check.in_stock_value, check.match_type) else StockStatus.OUT_OF_STOCK


def _rss_items(body: str) -> List[Tuple[str, str]]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ValueError(f"XML parse error: {exc}") from exc

    items: List[Tuple[str, str]] = []
    for item in root.findall(".//item"):
        items.append(((item.findtext("title") or "").strip(), (item.findtext("description") or "").strip()))
    for entry in root.findall(f".//{{{_ATOM_NS}}}entry"):
        t_el = entry.find(f"{{{_ATOM_NS}}}title")
        s_el = entry.find(f"{{{_ATOM_NS}}}summary") or entry.find(f"{{{_ATOM_NS}}}content")
        items.append(((t_el.text or "").strip() if t_el is not None else "", (s_el.text or "").strip() if s_el is not None else ""))
    return items


def _check_rss(body: str, check: StockCheck) -> StockStatus:
    try:
        items = _rss_items(body)
    except ValueError as exc:
        log.debug("RSS parse error: %s", exc)
        return StockStatus.ERROR

    if not items:
        return StockStatus.UNKNOWN

    keyword = check.selector.lower()
    if keyword:
        items = [(t, d) for t, d in items if keyword in t.lower() or keyword in d.lower()]
    if not items:
        return StockStatus.OUT_OF_STOCK

    if check.in_stock_text:
        combined = " ".join(t + " " + d for t, d in items)
        return StockStatus.IN_STOCK if _match(combined, check.in_stock_text, check.match_type) else StockStatus.OUT_OF_STOCK
    return StockStatus.IN_STOCK


# ── Best Buy API ─────────────────────────────────────────────────────────────

def _bby_url(config: SiteConfig) -> str:
    key = os.getenv("BBY_API_KEY", "")
    return f"{_BBY_API}/products(sku={config.stock.sku})?apiKey={key}&format=json&show={_BBY_FIELDS}"


def _check_bestbuy(body: str) -> StockStatus:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return StockStatus.ERROR
    products = data.get("products", [])
    if not products:
        return StockStatus.UNKNOWN
    return StockStatus.IN_STOCK if products[0].get("onlineAvailability", False) else StockStatus.OUT_OF_STOCK


def _price_bestbuy(body: str) -> Optional[str]:
    try:
        products = json.loads(body).get("products", [])
        if not products:
            return None
        val = products[0].get("salePrice") or products[0].get("regularPrice")
        return f"${val:.2f}" if isinstance(val, (int, float)) else None
    except Exception:
        return None


# ── Price extraction ──────────────────────────────────────────────────────────

def _extract_price(body: str, config: SiteConfig) -> Optional[str]:
    """Extract price from the same response body used for the stock check."""
    if config.stock.type == "css" and config.price_selector:
        nodes = HTMLParser(body).css(config.price_selector)
        if nodes:
            text = nodes[0].text(strip=True)
            return text if text else None

    if config.stock.type in ("json", "bestbuy") and config.price_json_path:
        try:
            value = jmespath.search(config.price_json_path, json.loads(body))
            if value is None:
                return None
            return f"${value:.2f}" if isinstance(value, (int, float)) else str(value)
        except Exception:
            return None

    if config.stock.type == "bestbuy":
        return _price_bestbuy(body)

    return None


# ── Block detection ───────────────────────────────────────────────────────────

def _is_blocked(response: httpx.Response) -> bool:
    if response.status_code in _BLOCKED_STATUS_CODES:
        return True
    if response.headers.get("cf-mitigated"):
        return True
    return bool(_BLOCK_RE.search(response.text[:4096]))


# ── Public entry point ────────────────────────────────────────────────────────

async def check_stock(client: httpx.AsyncClient, config: SiteConfig) -> CheckResult:
    headers = dict(config.extra_headers)
    headers.setdefault("Accept", _ACCEPT_BY_TYPE.get(config.stock.type, _ACCEPT_BY_TYPE["css"]))

    try:
        response = await client.get(config.url, headers=headers, follow_redirects=True)
    except httpx.RequestError as exc:
        log.warning("[%s] request error: %s", config.name, exc)
        return CheckResult(StockStatus.ERROR)

    if _is_blocked(response):
        log.warning("[%s] blocked (HTTP %d) — logging and skipping", config.name, response.status_code)
        return CheckResult(StockStatus.BLOCKED)

    if response.status_code != 200:
        log.warning("[%s] unexpected HTTP %d", config.name, response.status_code)
        return CheckResult(StockStatus.ERROR)

    try:
        t = config.stock.type
        if t == "json":
            status = _check_json(response.text, config.stock)
        elif t == "rss":
            status = _check_rss(response.text, config.stock)
        else:
            status = _check_css(response.text, config.stock)
    except Exception as exc:
        log.error("[%s] parse error: %s", config.name, exc)
        return CheckResult(StockStatus.ERROR)

    price = _extract_price(response.text, config)
    return CheckResult(status=status, price=price)


async def check_stock_bestbuy(client: httpx.AsyncClient, config: SiteConfig) -> CheckResult:
    key = os.getenv("BBY_API_KEY", "")
    if not key:
        return CheckResult(StockStatus.AWAITING_KEY)

    url = _bby_url(config)
    headers = {"Accept": _ACCEPT_BY_TYPE["bestbuy"]}
    headers.update(config.extra_headers)

    try:
        response = await client.get(url, headers=headers, follow_redirects=True)
    except httpx.RequestError as exc:
        log.warning("[%s] request error: %s", config.name, exc)
        return CheckResult(StockStatus.ERROR)

    if response.status_code == 401:
        log.warning("[%s] BBY_API_KEY rejected (401) — check your key", config.name)
        return CheckResult(StockStatus.ERROR)
    if response.status_code in (403, 429, 503):
        log.warning("[%s] Best Buy API blocked (HTTP %d)", config.name, response.status_code)
        return CheckResult(StockStatus.BLOCKED)
    if response.status_code != 200:
        log.warning("[%s] unexpected HTTP %d", config.name, response.status_code)
        return CheckResult(StockStatus.ERROR)

    try:
        status = _check_bestbuy(response.text)
    except Exception as exc:
        log.error("[%s] parse error: %s", config.name, exc)
        return CheckResult(StockStatus.ERROR)

    price = _price_bestbuy(response.text)
    return CheckResult(status=status, price=price)
