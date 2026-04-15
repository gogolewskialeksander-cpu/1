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

def _do_request(url: str, body: dict, mode: str) -> requests.Response:
    """Wysyla request i drukuje pelny request body + naglowki."""
    from urllib.parse import urlencode as _ue
    if mode == "post_form":
        hdrs = {"Content-Type": "application/x-www-form-urlencoded"}
        debug(f"  REQUEST: POST {url}")
        debug(f"  Headers: {hdrs}")
        debug(f"  Body:    {_ue(sorted(body.items()))}")
        return requests.post(url, data=body, headers=hdrs, timeout=15)
    elif mode == "post_json":
        hdrs = {"Content-Type": "application/json"}
        debug(f"  REQUEST: POST {url}")
        debug(f"  Headers: {hdrs}")
        debug(f"  Body:    {json.dumps(body, sort_keys=True)}")
        return requests.post(url, json=body, headers=hdrs, timeout=15)
    else:  # get
        debug(f"  REQUEST: GET {url}?{_ue(sorted(body.items()))}")
        return requests.get(url, params=body, timeout=15)


def _is_incomplete_sig(data: dict) -> bool:
    return "IncompleteSignature" in str(data.get("code", "")) or \
           "IncompleteSignature" in str(data.get("error_code", ""))


def exchange_code(code: str, app_key: str, app_secret: str) -> dict:
    """
    Wymiana authorization code na Access Token.

    Probuje kolejno:
      1. Standardowy OAuth 2.0 (bez custom podpisu AliExpress) — NOWY
      2. Wszystkie warianty custom podpisu (HMAC/MD5, rozne param-sety)
      3. Warianty z path-prefix w base stringu
      4. Wariant z redirect_uri w podpisie

    Drukuje pelny request body i naglowki HTTP dla kazdej proby.
    """
    rest_url = "https://api-sg.aliexpress.com/rest/auth/token/create"
    redirect_uri = os.getenv("ALIEXPRESS_REDIRECT_URI", "")
    timestamp = str(int(time.time() * 1000))

    info(f"Endpoint: {rest_url}")
    info(f"app_key={app_key}  timestamp={timestamp}  code={code[:12]}...")
    last_response: dict = {}

    def try_request(label: str, body: dict, mode: str) -> dict | None:
        nonlocal last_response
        debug(f"--- Proba [{label}] [{mode}] ---")
        try:
            resp = _do_request(rest_url, body, mode)
        except requests.RequestException as e:
            debug(f"  => HTTP error: {e}")
            return None
        debug(f"  RESPONSE: HTTP {resp.status_code}")
        debug(f"  Body:     {resp.text[:400]}")
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text}
        last_response = data
        # Sukces tylko jesli odpowiedz zawiera access_token
        if resp.status_code == 200 and data.get("access_token"):
            info(f"TRAFIONY WARIANT: [{label}] [{mode}]")
            return data
        return None

    # ================================================================
    # WARIANT 0a: app_key (nie client_id) + app_secret, bez podpisu
    # Odpowiedz powiedzila ze brakuje app_key — uzywamy app_key
    # ================================================================
    debug("=" * 56)
    debug("WARIANTY BEZ CUSTOM SIGN (rozne kombinacje app_key)")
    debug("=" * 56)

    no_sign_variants = [
        # etykieta, body
        ("0a: app_key + app_secret", {
            "app_key": app_key, "app_secret": app_secret,
            "code": code, "grant_type": "authorization_code",
        }),
        ("0b: app_key + app_secret + redirect_uri", {
            "app_key": app_key, "app_secret": app_secret,
            "code": code, "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }),
        ("0c: app_key tylko (bez secret)", {
            "app_key": app_key,
            "code": code, "grant_type": "authorization_code",
        }),
        ("0d: app_key + client_secret", {
            "app_key": app_key, "client_secret": app_secret,
            "code": code, "grant_type": "authorization_code",
        }),
        ("0e: app_key + timestamp (bez sign)", {
            "app_key": app_key, "timestamp": timestamp,
            "code": code, "grant_type": "authorization_code",
        }),
    ]

    for label, body in no_sign_variants:
        for mode in ("post_form", "get"):
            result = try_request(label, body, mode)
            if result is not None:
                return result

    # ================================================================
    # WARIANT 1-9: Custom podpis AliExpress (HMAC/MD5, rozne zestawy)
    # ================================================================
    def ps(p: dict) -> str:
        return "".join(f"{k}{v}" for k, v in sorted(p.items()))

    p4 = {"app_key": app_key, "code": code,
          "grant_type": "authorization_code", "timestamp": timestamp}
    p5 = {**p4, "sign_method": "sha256"}
    p5r = {**p4, "redirect_uri": redirect_uri} if redirect_uri else p4
    path = "/rest/auth/token/create"

    sign_sets = [
        # etykieta,          params_str,              base_prefix, base_suffix, algo
        ("1: HMAC 4p S+p+S", ps(p4),                  app_secret,  app_secret,  "h"),
        ("2: HMAC 4p S+p",   ps(p4),                  app_secret,  "",          "h"),
        ("3: HMAC 4p p",     ps(p4),                  "",          "",          "h"),
        ("4: HMAC 5p S+p+S", ps(p5),                  app_secret,  app_secret,  "h"),
        ("5: HMAC 5p S+p",   ps(p5),                  app_secret,  "",          "h"),
        ("6: HMAC 5p p",     ps(p5),                  "",          "",          "h"),
        ("7: MD5  4p S+p+S", ps(p4),                  app_secret,  app_secret,  "m"),
        ("8: MD5  4p S+p",   ps(p4),                  app_secret,  "",          "m"),
        ("9: MD5  4p p",     ps(p4),                  "",          "",          "m"),
        # z path-prefix
        ("10: HMAC path+4p", path + ps(p4),            "",          "",          "h"),
        ("11: HMAC path+5p", path + ps(p5),            "",          "",          "h"),
        ("12: MD5  path+4p", path + ps(p4),            "",          "",          "m"),
        # z redirect_uri w parametrach
        ("13: HMAC 4p+redir", ps(p5r),                app_secret,  app_secret,  "h"),
    ]

    debug("=" * 56)
    debug("WARIANTY 1-13: Custom podpis AliExpress")
    debug("=" * 56)

    for label, msg_str, prefix, suffix, algo in sign_sets:
        base = prefix + msg_str + suffix
        if algo == "h":
            sign = hmac.new(
                key=app_secret.encode(), msg=base.encode(),
                digestmod=hashlib.sha256,
            ).hexdigest().upper()
        else:
            sign = hashlib.md5(base.encode()).hexdigest().upper()
        debug(f"  [{label}] base[0:80]={base[:80]}  sign={sign}")

        body = {**p4, "sign_method": "sha256", "sign": sign}

        for mode in ("post_form", "get"):
            result = try_request(label, body, mode)
            if result is not None:
                return result

    # ================================================================
    # WARIANT 14-20: Sync endpoint z method=aliexpress.system.oauth.token
    # Standard TOP API wymaga method, format, v w sygnaturze.
    # ================================================================
    debug("=" * 56)
    debug("WARIANTY 14-20: SYNC endpoint (aliexpress.system.oauth.token)")
    debug("=" * 56)

    sync_url = SYNC_URL  # https://api-sg.aliexpress.com/sync
    p_sync = {
        "method": "aliexpress.system.oauth.token",
        "app_key": app_key,
        "timestamp": timestamp,
        "format": "json",
        "v": "2.0",
        "sign_method": "sha256",
        "code": code,
        "grant_type": "authorization_code",
    }
    p_sync_md5 = {**p_sync}

    def _hmac_sign(params: dict) -> str:
        base = "".join(f"{k}{v}" for k, v in sorted(params.items()))
        debug(f"  HMAC base[0:100]={base[:100]}")
        return hmac.new(
            key=app_secret.encode(), msg=base.encode(),
            digestmod=hashlib.sha256,
        ).hexdigest().upper()

    def _hmac_sign_lower(params: dict) -> str:
        base = "".join(f"{k}{v}" for k, v in sorted(params.items()))
        return hmac.new(
            key=app_secret.encode(), msg=base.encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()

    def _md5_sign(params: dict, prefix: str = "", suffix: str = "") -> str:
        base = prefix + "".join(f"{k}{v}" for k, v in sorted(params.items())) + suffix
        debug(f"  MD5 base[0:100]={base[:100]}")
        return hashlib.md5(base.encode()).hexdigest().upper()

    def try_sync(label: str, extra_params: dict, sign_fn) -> dict | None:
        p = {**p_sync, **extra_params}
        s = sign_fn(p)
        body = {**p, "sign": s}
        debug(f"--- Proba [{label}] sync_url ---")
        try:
            resp = _do_request(sync_url, body, "post_form")
        except requests.RequestException as e:
            debug(f"  => HTTP error: {e}")
            return None
        nonlocal last_response
        debug(f"  RESPONSE: HTTP {resp.status_code}")
        debug(f"  Body:     {resp.text[:400]}")
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text}
        last_response = data
        # REST: plaska struktura z access_token
        # SYNC: zagniezdzone w aliexpress_system_oauth_token_response
        nested = data.get("aliexpress_system_oauth_token_response", {})
        if resp.status_code == 200 and (
            data.get("access_token") or nested.get("access_token")
        ):
            if nested.get("access_token"):
                data = nested  # normalizuj do plaskiej struktury
            info(f"TRAFIONY WARIANT: [{label}]")
            return data
        return None

    # 14: SYNC HMAC-SHA256 standard
    r = try_sync("14: SYNC HMAC sha256", {}, _hmac_sign)
    if r: return r

    # 15: SYNC MD5 S+p+S (classic TOP format)
    r = try_sync("15: SYNC MD5 S+p+S", {},
                 lambda p: _md5_sign(p, prefix=app_secret, suffix=app_secret))
    if r: return r

    # 16: SYNC HMAC lowercase hex
    r = try_sync("16: SYNC HMAC lower", {}, _hmac_sign_lower)
    if r: return r

    # 17: SYNC bez format i v (minimalny zestaw)
    p_sync_minimal = {
        "method": "aliexpress.system.oauth.token",
        "app_key": app_key,
        "timestamp": timestamp,
        "sign_method": "sha256",
        "code": code,
        "grant_type": "authorization_code",
    }
    s17 = _hmac_sign(p_sync_minimal)
    body17 = {**p_sync_minimal, "sign": s17}
    r = try_request("17: SYNC-minimal HMAC", body17, "post_form")
    if r: return r

    # ================================================================
    # WARIANT 18-22: REST endpoint z nowymi kombinacjami
    # ================================================================
    debug("=" * 56)
    debug("WARIANTY 18-22: REST z nowymi kombinacjami")
    debug("=" * 56)

    # 18: REST + redirect_uri w body I podpisie
    if redirect_uri:
        p18 = {**p5, "redirect_uri": redirect_uri}
        s18 = _hmac_sign(p18)
        body18 = {**p18, "sign": s18}
        r = try_request("18: REST+redirect_uri HMAC", body18, "post_form")
        if r: return r

    # 19: REST + format=json + v=2.0 w podpisie
    p19 = {**p5, "format": "json", "v": "2.0"}
    s19 = _hmac_sign(p19)
    body19 = {**p19, "sign": s19}
    r = try_request("19: REST+format+v HMAC", body19, "post_form")
    if r: return r

    # 20: REST lowercase hex
    s20 = _hmac_sign_lower(p5)
    body20 = {**p4, "sign_method": "sha256", "sign": s20}
    r = try_request("20: REST HMAC lowercase", body20, "post_form")
    if r: return r

    # 21: REST timestamp w sekundach (nie milisekundach)
    ts_sec = str(int(time.time()))
    p21 = {"app_key": app_key, "code": code, "grant_type": "authorization_code",
           "timestamp": ts_sec, "sign_method": "sha256"}
    s21 = _hmac_sign(p21)
    body21 = {**p21, "sign": s21}
    r = try_request("21: REST timestamp-sec HMAC", body21, "post_form")
    if r: return r

    # 22: REST base string z = i & separatorami (URL-query format)
    def _hmac_url_fmt(params: dict) -> str:
        qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        debug(f"  HMAC url-fmt base[0:100]={qs[:100]}")
        return hmac.new(
            key=app_secret.encode(), msg=qs.encode(),
            digestmod=hashlib.sha256,
        ).hexdigest().upper()

    s22 = _hmac_url_fmt(p5)
    body22 = {**p4, "sign_method": "sha256", "sign": s22}
    r = try_request("22: REST base-with-equals HMAC", body22, "post_form")
    if r: return r

    # 23: REST auth params w URL query, business w body
    p23_url = {"app_key": app_key, "timestamp": timestamp,
               "sign_method": "sha256"}
    p23_biz = {"code": code, "grant_type": "authorization_code"}
    p23_all = {**p23_url, **p23_biz}
    s23 = _hmac_sign(p23_all)
    p23_url["sign"] = s23
    from urllib.parse import urlencode as _ue23
    rest_url_with_qs = rest_url + "?" + _ue23(p23_url)
    debug(f"--- Proba [23: REST split URL/body] ---")
    debug(f"  URL: {rest_url_with_qs}")
    debug(f"  Body: {p23_biz}")
    try:
        resp23 = requests.post(rest_url_with_qs, data=p23_biz,
                               headers={"Content-Type": "application/x-www-form-urlencoded"},
                               timeout=15)
        debug(f"  RESPONSE: HTTP {resp23.status_code}  {resp23.text[:400]}")
        try:
            d23 = resp23.json()
        except ValueError:
            d23 = {"raw": resp23.text}
        last_response = d23
        if resp23.status_code == 200 and d23.get("access_token"):
            info("TRAFIONY WARIANT: [23: REST split URL/body]")
            return d23
    except requests.RequestException as e:
        debug(f"  => HTTP error: {e}")

    info("Zaden z wariantow nie zwrocil sukcesu.")
    info("Pelna ostatnia odpowiedz powyzej w [DBG].")
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

    # Format SYNC — aliexpress_system_oauth_token_response
    nested = data.get("aliexpress_system_oauth_token_response", {})
    if nested.get("access_token"):
        return (
            nested.get("access_token", ""),
            nested.get("refresh_token", ""),
            int(nested.get("expire_time", 0) or 0),
        )

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
