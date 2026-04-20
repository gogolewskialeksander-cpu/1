"""
Persystentny cache product_id miedzy runami pipeline'u.

Zapisuje ID produktow do output/seen_ids.json z datą zobaczenia i statusem.
Wpisy starsze niz TTL_DAYS są usuwane przy wczytywaniu (stale produkty
mogą ponownie trafic do analizy po wygasnieciu cache).

Format pliku JSON:
{
  "1005006123456789": {"seen_at": "2026-04-20T15:30:00", "status": "accepted"},
  ...
}
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from logger import Logger

TTL_DAYS: int = 7

# Dozwolone statusy
STATUS_REJECTED_EU = "rejected_eu"
STATUS_REJECTED_DELIVERY = "rejected_delivery"
STATUS_REJECTED_STOCK = "rejected_stock"
STATUS_REJECTED_CLAUDE = "rejected_claude"
STATUS_ACCEPTED = "accepted"


class SeenIdsCache:
    """Cache product_id z TTL — persystuje miedzy uruchomieniami."""

    def __init__(self, data: dict, path: Path) -> None:
        self._data = data
        self._path = path

    # ------------------------------------------------------------------ #
    # Fabryki                                                              #
    # ------------------------------------------------------------------ #

    @classmethod
    def load(cls, path: Path, logger: Optional[Logger] = None) -> "SeenIdsCache":
        """
        Wczytuje cache z pliku JSON, usuwa wpisy starsze niz TTL_DAYS.

        Jesli plik nie istnieje — zwraca pusty cache.
        Jesli plik jest uszkodzony — loguje ostrzezenie i zwraca pusty cache.
        """
        data: dict = {}
        total_raw = 0

        if path.exists():
            try:
                raw: dict = json.loads(path.read_text(encoding="utf-8"))
                total_raw = len(raw)
                cutoff = datetime.now(tz=timezone.utc) - timedelta(days=TTL_DAYS)
                for pid, entry in raw.items():
                    try:
                        seen_at_str = entry.get("seen_at", "")
                        seen_at = datetime.fromisoformat(seen_at_str)
                        # Jezeli brak timezone — traktuj jako UTC
                        if seen_at.tzinfo is None:
                            seen_at = seen_at.replace(tzinfo=timezone.utc)
                        if seen_at >= cutoff:
                            data[pid] = entry
                    except (ValueError, AttributeError):
                        pass  # pomijamy uszkodzone wpisy
            except (json.JSONDecodeError, OSError) as e:
                if logger:
                    logger.warn(f"Cache: blad wczytywania {path}: {e}. Startuje z pustym cache.")

        active = len(data)
        if logger:
            logger.ok(
                f"Cache: wczytano {total_raw} ID (przed filtrem TTL), {active} aktywnych"
            )
        return cls(data, path)

    @classmethod
    def empty(cls, path: Path) -> "SeenIdsCache":
        """Zwraca pusty cache (uzywany przy --no-cache)."""
        return cls({}, path)

    # ------------------------------------------------------------------ #
    # Operacje                                                             #
    # ------------------------------------------------------------------ #

    def mark(self, product_id: str, status: str) -> None:
        """Dodaje lub nadpisuje wpis dla product_id z aktualnym czasem."""
        self._data[str(product_id)] = {
            "seen_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
            "status": status,
        }

    def contains(self, product_id: str) -> bool:
        """Zwraca True jesli product_id jest w cache (nie wygasl)."""
        return str(product_id) in self._data

    def get_all_ids(self) -> set:
        """Zwraca zbior wszystkich aktywnych product_id (do exclude_ids)."""
        return set(self._data.keys())

    def save(self) -> None:
        """Zapisuje cache do pliku JSON (tworzy katalog jesli nie istnieje)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
