"""
Konfiguracja aplikacji.

Laduje zmienne srodowiskowe z pliku .env i udostepnia je jako staly obiekt
Config. Waliduje obecnosc wymaganych kluczy API w zaleznosci od trybu dzialania
(produkcyjny vs testowy).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv


BASE_DIR: Path = Path(__file__).resolve().parent
ENV_PATH: Path = BASE_DIR / ".env"
OUTPUT_DIR: Path = BASE_DIR / "output"
LOGS_DIR: Path = BASE_DIR / "logs"
FAILED_PRODUCTS_PATH: Path = BASE_DIR / "failed_products.json"


class ConfigError(RuntimeError):
    """Blad konfiguracji — brakujace lub nieprawidlowe wartosci w .env."""


@dataclass
class Config:
    """Kontener na wszystkie parametry konfiguracyjne uruchomienia."""

    # Klucze API
    aliexpress_app_key: str = ""
    aliexpress_app_secret: str = ""
    aliexpress_access_token: str = ""
    anthropic_api_key: str = ""
    baselinker_api_token: str = ""
    baselinker_inventory_id: str = ""
    baselinker_storage_id: str = "bl_1"

    # Filtry biznesowe
    ship_from_countries: List[str] = field(default_factory=lambda: ["PL", "CZ", "DE", "ES", "FR"])
    target_currency: str = "PLN"
    target_language: str = "pl"
    min_seller_rating: float = 4.5
    min_stock: int = 5
    margin_target_percent: float = 30.0
    max_products_per_run: int = 100
    min_potential_score: int = 6
    max_delivery_days: int = 10

    # Tryb uruchomienia
    test_mode: bool = False

    def ensure_directories(self) -> None:
        """Upewnia sie ze katalogi output/ i logs/ istnieja."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

    def validate(self) -> None:
        """
        Waliduje obecnosc wymaganych kluczy API.

        Zarowno --test jak i tryb normalny chodza po realnych feedach AliExpress
        (rozniaca sie tylko limitami), wiec wymagamy wszystkich kluczy.
        BASELINKER_API_TOKEN wymagany tylko gdy user wywola --baselinker.

        Raises:
            ConfigError: Gdy brakuje wymaganych wartosci.
        """
        missing: List[str] = []

        if not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        if not self.aliexpress_app_key:
            missing.append("ALIEXPRESS_APP_KEY")
        if not self.aliexpress_app_secret:
            missing.append("ALIEXPRESS_APP_SECRET")
        if not self.aliexpress_access_token:
            missing.append("ALIEXPRESS_ACCESS_TOKEN")

        if missing:
            raise ConfigError(
                "Brakuje wymaganych zmiennych srodowiskowych w pliku .env:\n"
                + "\n".join(f"  - {key}" for key in missing)
                + f"\n\nSkopiuj {ENV_PATH.parent / '.env.example'} do .env "
                "i uzupelnij brakujace wartosci."
            )


def _parse_countries(raw: Optional[str]) -> List[str]:
    """Parsuje liste krajow z formatu 'PL,CZ,DE' do listy stringow."""
    if not raw:
        return ["PL", "CZ", "DE", "ES", "FR"]
    return [country.strip().upper() for country in raw.split(",") if country.strip()]


def _parse_int(raw: Optional[str], default: int) -> int:
    """Bezpiecznie parsuje int z env. W razie bledu zwraca wartosc domyslna."""
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _parse_float(raw: Optional[str], default: float) -> float:
    """Bezpiecznie parsuje float z env. W razie bledu zwraca wartosc domyslna."""
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _normalize_storage_id(raw: str) -> str:
    """Zapewnia prefix 'bl_' w storage_id BaseLinker (np. '135610' -> 'bl_135610')."""
    raw = raw.strip()
    if not raw:
        return "bl_1"
    return raw if raw.startswith("bl_") else f"bl_{raw}"


def load_config(test_mode: bool = False) -> Config:
    """
    Laduje konfiguracje ze zmiennych srodowiskowych.

    Args:
        test_mode: Czy uruchamiamy w trybie testowym (mock dane AliExpress).

    Returns:
        Zainicjalizowany obiekt Config.
    """
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH)
    else:
        load_dotenv()

    config = Config(
        aliexpress_app_key=os.getenv("ALIEXPRESS_APP_KEY", ""),
        aliexpress_app_secret=os.getenv("ALIEXPRESS_APP_SECRET", ""),
        aliexpress_access_token=os.getenv("ALIEXPRESS_ACCESS_TOKEN", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        baselinker_api_token=os.getenv("BASELINKER_API_TOKEN", ""),
        baselinker_inventory_id=os.getenv("BASELINKER_INVENTORY_ID", ""),
        baselinker_storage_id=_normalize_storage_id(os.getenv("BASELINKER_STORAGE_ID", "bl_1")),
        ship_from_countries=_parse_countries(os.getenv("SHIP_FROM_COUNTRIES")),
        target_currency=os.getenv("TARGET_CURRENCY", "PLN"),
        target_language=os.getenv("TARGET_LANGUAGE", "pl"),
        min_seller_rating=_parse_float(os.getenv("MIN_SELLER_RATING"), 4.5),
        min_stock=_parse_int(os.getenv("MIN_STOCK"), 5),
        margin_target_percent=_parse_float(os.getenv("MARGIN_TARGET_PERCENT"), 30.0),
        max_products_per_run=_parse_int(os.getenv("MAX_PRODUCTS_PER_RUN"), 100),
        min_potential_score=_parse_int(os.getenv("MIN_POTENTIAL_SCORE"), 6),
        max_delivery_days=_parse_int(os.getenv("MAX_DELIVERY_DAYS"), 10),
        test_mode=test_mode,
    )
    config.ensure_directories()
    return config
