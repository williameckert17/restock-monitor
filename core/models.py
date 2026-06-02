from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, Literal, Optional


class StockStatus(Enum):
    IN_STOCK = auto()
    OUT_OF_STOCK = auto()
    PREORDER = auto()       # orderable as pre-order -> fires alert
    COMING_SOON = auto()    # listed but not yet orderable
    BLOCKED = auto()
    ERROR = auto()
    UNKNOWN = auto()
    AWAITING_KEY = auto()  # API-keyed retailer with no key configured yet


@dataclass
class CheckResult:
    status: StockStatus
    price: Optional[str] = None  # raw text as scraped; None when not configured or not found


@dataclass
class StockCheck:
    type: Literal["css", "json", "rss", "bestbuy"] = "css"

    # Best Buy API mode
    sku: str = ""                # Best Buy SKU (14-digit product identifier)

    # CSS mode
    selector: str = ""           # CSS selector; reused as keyword filter in rss mode
    in_stock_text: str = ""      # text/value present when IN stock
    out_of_stock_text: str = ""  # text present when OUT of stock
    attribute: str = ""          # check this HTML attribute value instead of element text

    # JSON mode
    json_path: str = ""          # JMESPath expression
    in_stock_value: str = ""     # expected value when in stock

    # Shared — how in_stock_text / in_stock_value is compared to the extracted string
    # "contains"     — substring match (default)
    # "exact"        — full-string equality (case-insensitive)
    # "regex"        — in_stock_text treated as a regex pattern
    # "not_contains" — in stock when the string is NOT present (inverse test)
    match_type: str = "contains"


@dataclass
class SiteConfig:
    name: str
    url: str
    product_name: str
    poll_interval: int = 60
    jitter: int = 15
    stock: StockCheck = field(default_factory=StockCheck)
    extra_headers: Dict[str, str] = field(default_factory=dict)
    # Optional price extraction — extracted from the same response as the stock check
    price_selector: str = ""    # CSS selector whose text becomes the price string (css type)
    price_json_path: str = ""   # JMESPath expression for price (json type)
