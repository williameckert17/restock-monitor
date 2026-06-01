"""Persistence for Notification Center settings (SMS recipients and enabled flag)."""
import json
from typing import Any, Dict

from web.paths import NOTIFICATIONS_PATH

_DEFAULT: Dict[str, Any] = {"sms_enabled": False, "recipients": []}


def load() -> Dict[str, Any]:
    if not NOTIFICATIONS_PATH.exists():
        return dict(_DEFAULT)
    try:
        data = json.loads(NOTIFICATIONS_PATH.read_text())
        data.setdefault("sms_enabled", False)
        data.setdefault("recipients", [])
        return data
    except Exception:
        return dict(_DEFAULT)


def save(config: Dict[str, Any]) -> Dict[str, Any]:
    NOTIFICATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOTIFICATIONS_PATH.write_text(json.dumps(config, indent=2))
    return config
