import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from web.paths import WATCHLIST_PATH


def _load() -> List[Dict[str, Any]]:
    if not WATCHLIST_PATH.exists():
        return []
    try:
        return json.loads(WATCHLIST_PATH.read_text())
    except Exception:
        return []


def _save(entries: List[Dict[str, Any]]) -> None:
    WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    WATCHLIST_PATH.write_text(json.dumps(entries, indent=2))


def list_sites() -> List[Dict[str, Any]]:
    return _load()


def add_site(entry: Dict[str, Any]) -> Dict[str, Any]:
    entries = _load()
    entry = dict(entry)
    entry["id"] = str(uuid.uuid4())
    entries.append(entry)
    _save(entries)
    return entry


def update_site(site_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    entries = _load()
    for i, e in enumerate(entries):
        if e.get("id") == site_id:
            updated = {**e, **updates, "id": site_id}
            entries[i] = updated
            _save(entries)
            return updated
    return None


def delete_site(site_id: str) -> bool:
    entries = _load()
    new_entries = [e for e in entries if e.get("id") != site_id]
    if len(new_entries) == len(entries):
        return False
    _save(new_entries)
    return True


def seed_if_empty(seeds_path: Path) -> None:
    """Load seeds into the watchlist only when it is completely empty."""
    if _load():
        return
    if not seeds_path.exists():
        return
    try:
        seeds = json.loads(seeds_path.read_text())
    except Exception:
        return
    entries = []
    for s in seeds:
        e = dict(s)
        e["id"] = str(uuid.uuid4())
        entries.append(e)
    _save(entries)
