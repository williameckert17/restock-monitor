import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

_DATA_PATH = Path("data/watchlist.json")


def _load() -> List[Dict[str, Any]]:
    if not _DATA_PATH.exists():
        return []
    try:
        return json.loads(_DATA_PATH.read_text())
    except Exception:
        return []


def _save(entries: List[Dict[str, Any]]) -> None:
    _DATA_PATH.parent.mkdir(exist_ok=True)
    _DATA_PATH.write_text(json.dumps(entries, indent=2))


def list_sites() -> List[Dict[str, Any]]:
    return _load()


def add_site(entry: Dict[str, Any]) -> Dict[str, Any]:
    entries = _load()
    entry = dict(entry)
    entry["id"] = str(uuid.uuid4())
    entries.append(entry)
    _save(entries)
    return entry


def delete_site(site_id: str) -> bool:
    entries = _load()
    new_entries = [e for e in entries if e.get("id") != site_id]
    if len(new_entries) == len(entries):
        return False
    _save(new_entries)
    return True
