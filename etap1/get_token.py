#!/usr/bin/env python3
"""
get_token.py — Uzyskiwanie AliExpress Access Token przez OAuth 2.0.

Uzycie:
    python get_token.py

Kroki:
    1. Czyta APP_KEY / APP_SECRET z pliku .env
    2. Generuje URL autoryzacji i otwiera go w przegladarce
    3. Czeka az uzytkownik wklei authorization code z URL callback
    4. Wymienia code na Access Token (IOP SDK, endpoint /auth/token/create)
    5. Zapisuje Access Token do .env (ALIEXPRESS_ACCESS_TOKEN)

Jesli przeglądarka sie nie otworzy automatycznie, skopiuj URL recznie.
"""
from __future__ import annotations

import json
import os
import re
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

# IOP SDK — oficjalny klient AliExpress Open Platform
sys.path.insert(0, str(Path(__file__).resolve().parent))
import iop


# ===== ENDPOINTY =====
OAUTH_URL = "https://api-sg.aliexpress.com/oauth/authorize"
IOP_GATEWAY = "https://api-sg.aliexpress.com"

SCRIPT_DIR = Path(__file__).resolve().parent
ENV_PATH = SCRIPT_DIR / ".env"


# ---------------------------------------------------------------------------
# Pomocnicze
# ---------------------------------------------------------------------------

def step(n: int, msg: str) -> None:
    print(f"\n{'='*60}")
    print(f"  KROK {n}: {msg}")
    print(f"{'='*60}")


def ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def info(msg: str) -> None:
    print(f"  [INFO] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Krok 1 — Zaladowanie danych z .env
# ---------------------------------------------------------------------------

def load_credentials() -> tuple[str, str, str]:
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH)
        info(f"Wczytano .env z: {ENV_PATH}")
    else:
        load_dotenv()
        info(".env nie znaleziony — czytam ze zmiennych srodowiskowych")

    app_key = os.getenv("ALIEXPRESS_APP_KEY", "").strip()
    app_secret = os.getenv("ALIEXPRESS_APP_SECRET", "").strip()
    redirect_uri = os.getenv("ALIEXPRESS_REDIRECT_URI", "").strip()

    return app_key, app_secret, redirect_uri


# ---------------------------------------------------------------------------
# Krok 2 — Generowanie URL autoryzacji
# ---------------------------------------------------------------------------

def generate_oauth_url(app_key: str, redirect_uri: str) -> str:
    params = {
        "response_type": "code",
        "force_auth": "true",
        "client_id": app_key,
        "redirect_uri": redirect_uri,
        "state": "ds_auth",
    }
    return OAUTH_URL + "?" + urlencode(params)


# ---------------------------------------------------------------------------
# Krok 3 — Wymiana code na Access Token przez IOP SDK
# ---------------------------------------------------------------------------

def exchange_code(code: str, app_key: str, app_secret: str) -> iop.IopResponse:
    """
    Wymienia authorization code na Access Token uzywajac oficjalnego IOP SDK.

    Oficjalny algorytm podpisu:
      timestamp = str(int(round(time.time()))) + '000'
      params = {app_key, sign_method=sha256, timestamp,
                partner_id=iop-sdk-python-20220609,
                method=/auth/token/create, simplify=false, format=json,
                code=CODE}
      base = '/auth/token/create' + concat(sorted(params), key+value)
      sign = HMAC-SHA256(key=app_secret, msg=base).hexdigest().upper()
      POST https://api-sg.aliexpress.com/auth/token/create
    """
    client = iop.IopClient(IOP_GATEWAY, app_key, app_secret)
    request = iop.IopRequest("/auth/token/create")
    request.add_api_param("code", code)

    info(f"IOP gateway: {IOP_GATEWAY}")
    info(f"API path:    /auth/token/create")
    info(f"code:        {code[:12]}...")

    response = client.execute(request)

    info(f"HTTP odpowiedz: {response._raw.status_code}")
    print(f"\n  Pelna odpowiedz:\n  {json.dumps(response.body, indent=4, ensure_ascii=False)}")

    return response


# ---------------------------------------------------------------------------
# Krok 4 — Zapis tokena do .env
# ---------------------------------------------------------------------------

def save_to_env(key: str, value: str) -> None:
    """Aktualizuje lub dodaje klucz=wartosc w pliku .env."""
    if not ENV_PATH.exists():
        fail(f".env nie istnieje ({ENV_PATH}) — nie mozna zapisac automatycznie.")
        info(f"Dodaj recznie do .env: {key}={value}")
        return

    content = ENV_PATH.read_text(encoding="utf-8")
    pattern = rf"^{re.escape(key)}=.*$"

    if re.search(pattern, content, flags=re.MULTILINE):
        content = re.sub(pattern, f"{key}={value}", content, flags=re.MULTILINE)
        info(f"Zaktualizowano {key} w .env")
    else:
        content = content.rstrip("\n") + f"\n{key}={value}\n"
        info(f"Dodano {key} do .env")

    ENV_PATH.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> int:
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   AliExpress Dropshipping — uzyskiwanie Access Token     ║")
    print("╚══════════════════════════════════════════════════════════╝")

    # ---------- KROK 1: dane ----------
    step(1, "Ladowanie konfiguracji z .env")
    app_key, app_secret, redirect_uri = load_credentials()

    if not app_key:
        fail("Brak ALIEXPRESS_APP_KEY w .env")
        return 1
    if not app_secret:
        fail("Brak ALIEXPRESS_APP_SECRET w .env")
        return 1
    if not redirect_uri:
        fail("Brak ALIEXPRESS_REDIRECT_URI w .env")
        info("Dodaj do .env: ALIEXPRESS_REDIRECT_URI=https://callback.megasklep.pl")
        return 1

    ok(f"APP_KEY:      {app_key}")
    ok(f"APP_SECRET:   {app_secret[:6]}{'*' * max(0, len(app_secret) - 6)}")
    ok(f"REDIRECT_URI: {redirect_uri}")

    # ---------- KROK 2: OAuth URL ----------
    step(2, "Generowanie URL autoryzacji i otwarcie w przegladarce")
    oauth_url = generate_oauth_url(app_key, redirect_uri)

    print(f"\n  URL:\n  {oauth_url}\n")

    opened = webbrowser.open(oauth_url)
    if opened:
        ok("URL otwarty w przegladarce")
    else:
        info("Nie udalo sie otworzyc przegladarki automatycznie")
        info("Skopiuj URL powyzej i otworz recznie")

    print()
    print("  Instrukcja:")
    print("  1. Zaloguj sie na AliExpress jesli wymagane")
    print("  2. Kliknij 'Agree' / 'Authorize'")
    print(f"  3. Zostaniesz przekierowany na: {redirect_uri}?code=XXXX&state=ds_auth")
    print("  4. Skopiuj wartosc parametru 'code' z paska adresu przegladarki")
    print()
    print("  Jesli strona callback zwroci blad 404/Connection refused — to normalne.")
    print("  Wazny jest tylko URL — skopiuj go z paska adresu.")

    # ---------- KROK 3: authorization code ----------
    step(3, "Wklejenie authorization code")
    print()
    code_input = input("  Wklej code (lub caly URL z code=...): ").strip()

    if not code_input:
        fail("Nie podano code.")
        return 1

    code = code_input
    if "code=" in code_input:
        match = re.search(r"[?&]code=([^&]+)", code_input)
        if match:
            code = match.group(1)
            info(f"Wyciagniety code z URL: {code[:12]}...")
        else:
            fail("Nie mozna wyciagnac code z URL. Wklej sam code.")
            return 1

    ok(f"Code: {code[:12]}... (dlugosc: {len(code)})")

    # ---------- KROK 4: wymiana na token ----------
    step(4, "Wymiana authorization code na Access Token (IOP SDK)")
    try:
        response = exchange_code(code, app_key, app_secret)
    except requests.RequestException as e:
        fail(f"Blad HTTP: {e}")
        return 1

    if not response.is_success():
        print()
        fail("Nie otrzymano access_token w odpowiedzi.")
        fail(f"Kod bledu:  {response.code}")
        fail(f"Komunikat: {response.message}")
        return 1

    print()
    ok(f"Access Token:  {response.access_token[:20]}...")
    if response.refresh_token:
        ok(f"Refresh Token: {response.refresh_token[:20]}...")
    if response.expire_time:
        hours = response.expire_time // 3600
        ok(f"Waznosc:       {hours}h ({response.expire_time}s)")

    # ---------- KROK 5: zapis do .env ----------
    step(5, "Zapis tokenow do .env")
    save_to_env("ALIEXPRESS_ACCESS_TOKEN", response.access_token)
    if response.refresh_token:
        save_to_env("ALIEXPRESS_REFRESH_TOKEN", response.refresh_token)

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  GOTOWE! Token zapisany. Uruchom:  python main.py        ║")
    print("╚══════════════════════════════════════════════════════════╝")
    return 0


if __name__ == "__main__":
    sys.exit(main())
