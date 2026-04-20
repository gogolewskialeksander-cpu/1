#!/usr/bin/env python3
"""
Skrypt diagnostyczny — testuje dwa nowe endpointy AliExpress DS API.

Uruchomienie:
    python3 test_endpoints.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import os
from aliexpress_client import AliExpressClient
from logger import Logger
from config import LOGS_DIR

LOGS_DIR.mkdir(parents=True, exist_ok=True)
logger = Logger(logs_dir=LOGS_DIR)

app_key    = os.getenv("ALIEXPRESS_APP_KEY", "")
app_secret = os.getenv("ALIEXPRESS_APP_SECRET", "")
token      = os.getenv("ALIEXPRESS_ACCESS_TOKEN", "")

if not all([app_key, app_secret, token]):
    print("[FAIL] Brak kluczy API w .env (ALIEXPRESS_APP_KEY / APP_SECRET / ACCESS_TOKEN)")
    sys.exit(1)

client = AliExpressClient(app_key, app_secret, token, logger)


def dump(label: str, data: dict) -> None:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print('='*60)
    print(json.dumps(data, indent=2, ensure_ascii=False))


# ── Endpoint 1: aliexpress.ds.feedname.get ────────────────────────────────────
print("\n[1/2] Wywoluje aliexpress.ds.feedname.get ...")
try:
    resp1 = client._call("aliexpress.ds.feedname.get", {})
    dump("aliexpress.ds.feedname.get  →  pelna odpowiedz", resp1)
except Exception as e:
    print(f"  BLAD: {e}")


# ── Endpoint 2: /ds/recommend/feed/get  (slash-style method) ─────────────────
print("\n[2/2] Wywoluje /ds/recommend/feed/get (REST slash-path) ...")
try:
    resp2 = client._call(
        "/ds/recommend/feed/get",
        {
            "country": "PL",
            "target_currency": "PLN",
            "target_language": "PL",
            "page_size": "20",
            "page_no": "1",
            "feed_name": "DS_bestseller_en",
        },
    )
    dump("/ds/recommend/feed/get  →  pelna odpowiedz", resp2)
except Exception as e:
    print(f"  BLAD: {e}")

logger.close()
