#!/usr/bin/env python3
"""
get_token.py — Uzyskiwanie AliExpress Access Token przez OAuth 2.0.

Uzycie:
    python get_token.py

Kroki:
    1. Czyta APP_KEY / APP_SECRET z pliku .env
    2. Generuje URL autoryzacji i otwiera go w przegladarce
    3. Czeka az uzytkownik wklei authorization code z URL callback
    4. Wymienia code na Access Token (endpoint: /rest/auth/token/create)
    5. Zapisuje Access Token do .env (ALIEXPRESS_ACCESS_TOKEN)

Jesli przeglądarka sie nie otworzy automatycznie, skopiuj URL recznie.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv


# ===== ENDPOINTY =====
OAUTH_URL = "https://api-sg.aliexpress.com/oauth/authorize"
SYNC_URL = "https://api-sg.aliexpress.com/sync"

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


def debug(msg: str) -> None:
    print(f"  [DBG]  {msg}")


# ---------------------------------------------------------------------------
# Podpis HMAC-SHA256 (identyczny z aliexpress_client._build_signature)
# ---------------------------------------------------------------------------

def build_signature(params: dict[str, str], app_secret: str) -> str:
    """
    Generuje podpis HMAC-SHA256 dla AliExpress TOP API.

    Algorytm:
        1. Posortuj parametry alfabetycznie po kluczu.
        2. Sklej: klucz1wartosc1klucz2wartosc2...
        3. HMAC-SHA256 z app_secret jako kluczem.
        4. Zwroc wielkie litery (uppercase HEX).
    """
    sorted_items = sorted(params.items())
    base_string = "".join(f"{k}{v}" for k, v in sorted_items)
    debug(f"Base string (pierwsze 120 zn.): {base_string[:120]}")
    sig = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=base_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest().upper()
    debug(f"HMAC-SHA256: {sig}")
    return sig


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
    """
    Buduje URL autoryzacji OAuth AliExpress.

    Parametry zgodne z dokumentacja AliExpress TOP OAuth:
      response_type  = code
      client_id      = app_key
      redirect_uri   = callback URL z panelu aplikacji
      state          = dowolny string (ochrona CSRF)
      sp             = ae  (wymagane dla AliExpress, odroznenie od innych platform)
      view           = web (opcjonalne — wymuszone widok desktopowy)
    """
    params = {
        "response_type": "code",
        "force_auth": "true",
        "client_id": app_key,
        "redirect_uri": redirect_uri,
        "state": "ds_auth",
    }
    # urlencode domyslnie koduje wartosci (np. https:// -> https%3A%2F%2F)
    url = OAUTH_URL + "?" + urlencode(params)
    return url


# ---------------------------------------------------------------------------
# Krok 3 — Wymiana code na Access Token
# ---------------------------------------------------------------------------

def _make_sign(params_str: str, app_secret: str, algo: str, wrap: str) -> str:
    """Generuje jeden wariant podpisu."""
    if wrap == "both":
        msg = app_secret + params_str + app_secret
    elif wrap == "prefix":
        msg = app_secret + params_str
    else:
        msg = params_str

    if algo == "hmac-sha256":
        return hmac.new(
            key=app_secret.encode(), msg=msg.encode(), digestmod=hashlib.sha256
        ).hexdigest().upper()
    else:  # md5
        return hashlib.md5(msg.encode()).hexdigest().upper()


def exchange_code(code: str, app_key: str, app_secret: str) -> dict:
    """
    Wymiana authorization code na Access Token.
    Probuje kolejno wszystkie sensowne kombinacje podpisu i transport
    az do pierwszej odpowiedzi INNEJ niz IncompleteSignature.
    """
    rest_url = "https://api-sg.aliexpress.com/rest/auth/token/create"
    timestamp = str(int(time.time() * 1000))

    # ----------------------------------------------------------------
    # Zestawy parametrow do podpisania — moze sign_method tez wchodzi
    # ----------------------------------------------------------------
    base_params = {
        "app_key": app_key,
        "code": code,
        "grant_type": "authorization_code",
        "timestamp": timestamp,
    }
    base_params_with_sm = {**base_params, "sign_method": "sha256"}

    def params_str(p: dict) -> str:
        return "".join(f"{k}{v}" for k, v in sorted(p.items()))

    ps_base = params_str(base_params)
    ps_with_sm = params_str(base_params_with_sm)

    # ----------------------------------------------------------------
    # Wszystkie warianty: (etykieta, params_do_podpisu, algo, wrap)
    # ----------------------------------------------------------------
    sign_variants = [
        ("1: HMAC-SHA256 | 4 params | SECRET+p+SECRET", ps_base,    "hmac-sha256", "both"),
        ("2: HMAC-SHA256 | 4 params | SECRET+p",        ps_base,    "hmac-sha256", "prefix"),
        ("3: HMAC-SHA256 | 4 params | p only",           ps_base,    "hmac-sha256", "none"),
        ("4: HMAC-SHA256 | 5 params+sm | SECRET+p+S",   ps_with_sm, "hmac-sha256", "both"),
        ("5: HMAC-SHA256 | 5 params+sm | SECRET+p",     ps_with_sm, "hmac-sha256", "prefix"),
        ("6: HMAC-SHA256 | 5 params+sm | p only",        ps_with_sm, "hmac-sha256", "none"),
        ("7: MD5         | 4 params | SECRET+p+SECRET",  ps_base,    "md5",         "both"),
        ("8: MD5         | 4 params | SECRET+p",         ps_base,    "md5",         "prefix"),
        ("9: MD5         | 4 params | p only",            ps_base,    "md5",         "none"),
    ]

    debug("=" * 56)
    debug("WARIANTY PODPISU (params w kolejnosci alfabetycznej):")
    debug(f"  4-params string: {ps_base[:80]}")
    debug(f"  5-params string: {ps_with_sm[:80]}")
    all_sigs = {}
    for label, ps, algo, wrap in sign_variants:
        s = _make_sign(ps, app_secret, algo, wrap)
        all_sigs[label] = s
        debug(f"  [{label}]")
        debug(f"    => {s}")
    debug("=" * 56)

    # ----------------------------------------------------------------
    # Transport: probuj POST body i GET query string
    # ----------------------------------------------------------------
    transport_variants = [
        ("POST body | Content-Type: form",        "post_form"),
        ("POST body | Content-Type: json",         "post_json"),
        ("GET query string",                       "get"),
    ]

    info(f"Endpoint: {rest_url}")
    info(f"app_key={app_key}  timestamp={timestamp}  code={code[:12]}...")

    last_response: dict = {}

    for sign_label, ps, algo, wrap in sign_variants:
        sign = all_sigs[sign_label]
        body = {
            **base_params,
            "sign_method": "sha256",
            "sign": sign,
        }

        for trans_label, trans_mode in transport_variants:
            debug(f"Proba: [{sign_label}] + [{trans_label}]")

            try:
                if trans_mode == "post_form":
                    resp = requests.post(
                        rest_url, data=body, timeout=15,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                elif trans_mode == "post_json":
                    resp = requests.post(
                        rest_url, json=body, timeout=15,
                        headers={"Content-Type": "application/json"},
                    )
                else:  # get
                    resp = requests.get(rest_url, params=body, timeout=15)
            except requests.RequestException as e:
                debug(f"  => HTTP error: {e}")
                continue

            raw = resp.text[:300]
            debug(f"  => HTTP {resp.status_code} | {raw}")

            try:
                data = resp.json()
            except ValueError:
                data = {"raw": resp.text}

            last_response = data

            # Jesli NIE ma IncompleteSignature — to jest nasz wariant
            error_code = data.get("code", "") or data.get("error_code", "")
            if "IncompleteSignature" not in str(error_code) and resp.status_code == 200:
                info(f"TRAFIONY WARIANT: [{sign_label}] + [{trans_label}]")
                return data

    info("Zaden wariant nie przeszedl — zwracam ostatnia odpowiedz")
    return last_response


# ---------------------------------------------------------------------------
# Krok 4 — Parsowanie odpowiedzi
# ---------------------------------------------------------------------------

def extract_token(data: dict) -> tuple[str, str, int]:
    """
    Wyciaga (access_token, refresh_token, expire_time) z odpowiedzi.

    REST /rest/auth/token/create zwraca plaska strukture:
      { "access_token": "...", "refresh_token": "...", "expire_time": ... }
    Obslugujemy tez zagniezdzone formaty na wypadek wariantow API.
    """
    # Format REST — plaska struktura
    access_token = data.get("access_token", "")
    refresh_token = data.get("refresh_token", "")
    expire_time = int(data.get("expire_time", 0) or data.get("expires_in", 0) or 0)

    if access_token:
        return access_token, refresh_token, expire_time

    # Zagniezdzone w "result" (wariant)
    if isinstance(data.get("result"), dict):
        result = data["result"]
        access_token = result.get("access_token", "")
        refresh_token = result.get("refresh_token", "")
        expire_time = int(result.get("expire_time", 0) or 0)

    return access_token, refresh_token, expire_time


# ---------------------------------------------------------------------------
# Krok 5 — Zapis tokena do .env
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

    # Wyciagnij code z URL jesli uzytkownik wkleił cały URL
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
    step(4, "Wymiana authorization code na Access Token")
    try:
        response_data = exchange_code(code, app_key, app_secret)
    except requests.RequestException as e:
        fail(f"Blad HTTP: {e}")
        return 1

    print(f"\n  Pelna odpowiedz API:\n  {json.dumps(response_data, indent=4, ensure_ascii=False)}")

    access_token, refresh_token, expire_time = extract_token(response_data)

    if not access_token:
        print()
        fail("Nie otrzymano access_token w odpowiedzi.")
        error_msg = (
            response_data.get("error_description")
            or response_data.get("error_message")
            or response_data.get("msg")
            or response_data.get("sub_msg")
            or "brak opisu bledu"
        )
        fail(f"Blad: {error_msg}")
        return 1

    print()
    ok(f"Access Token:  {access_token[:20]}...")
    if refresh_token:
        ok(f"Refresh Token: {refresh_token[:20]}...")
    if expire_time:
        hours = expire_time // 3600
        ok(f"Waznosc:       {hours}h ({expire_time}s)")

    # ---------- KROK 5: zapis do .env ----------
    step(5, "Zapis tokenow do .env")
    save_to_env("ALIEXPRESS_ACCESS_TOKEN", access_token)
    if refresh_token:
        save_to_env("ALIEXPRESS_REFRESH_TOKEN", refresh_token)

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  GOTOWE! Token zapisany. Uruchom:  python main.py        ║")
    print("╚══════════════════════════════════════════════════════════╝")
    return 0


if __name__ == "__main__":
    sys.exit(main())
