"""
AliExpress IOP (Intelligent Open Platform) SDK — base.py

Oficjalny algorytm podpisu (iop-sdk-python-20220609):
  1. timestamp = str(int(round(time.time()))) + '000'
  2. System params: app_key, sign_method=sha256, timestamp,
     partner_id=iop-sdk-python-20220609, method=<api_path>,
     simplify=false, format=json
  3. Base string = api_path + concat(sorted(all_params), key+value)
  4. sign = HMAC-SHA256(key=app_secret, msg=base_string).hexdigest().upper()
  5. POST https://gateway + api_path
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import urlencode

import requests

PARTNER_ID = "iop-sdk-python-20220609"
SDK_VERSION = "iop-sdk-python-20220609"

log = logging.getLogger(__name__)


class IopRequest:
    def __init__(self, api_path: str, http_method: str = "POST"):
        self._api_path = api_path
        self._http_method = http_method.upper()
        self._api_params: dict[str, str] = {}
        self._file_params: dict = {}

    def add_api_param(self, key: str, value) -> None:
        self._api_params[key] = str(value)

    def get_api_path(self) -> str:
        return self._api_path

    def get_api_params(self) -> dict[str, str]:
        return dict(self._api_params)


class IopResponse:
    def __init__(self, resp: requests.Response):
        self._raw = resp
        try:
            self.body = resp.json()
        except ValueError:
            self.body = {"raw": resp.text}
        self.code = self.body.get("code", "")
        self.message = self.body.get("message", "")
        self.request_id = self.body.get("request_id", "")

    @property
    def access_token(self) -> str:
        return self.body.get("access_token", "")

    @property
    def refresh_token(self) -> str:
        return self.body.get("refresh_token", "")

    @property
    def expire_time(self) -> int:
        return int(self.body.get("expire_time", 0) or 0)

    def is_success(self) -> bool:
        return bool(self.access_token)

    def __repr__(self) -> str:
        return f"IopResponse(code={self.code!r}, access_token={self.access_token[:12]!r}...)"


class IopClient:
    def __init__(self, gateway_url: str, app_key: str, app_secret: str):
        # Strip trailing slash so we can append api_path cleanly
        self._gateway = gateway_url.rstrip("/")
        self._app_key = str(app_key)
        self._app_secret = app_secret

    # ------------------------------------------------------------------
    # Podpis — oficjalny algorytm IOP SDK
    # ------------------------------------------------------------------

    def _build_sign(self, api_path: str, params: dict[str, str]) -> str:
        """
        Buduje podpis HMAC-SHA256.

        Base string = api_path + concat posortowanych (klucz+wartosc)
        Klucz HMAC = app_secret (jako bajty UTF-8, NIE wlaczany do base)
        Wynik = uppercase hex
        """
        sorted_items = sorted(params.items())
        base = api_path + "".join(f"{k}{v}" for k, v in sorted_items)
        log.debug("IOP sign base[0:120]: %s", base[:120])
        sig = hmac.new(
            key=self._app_secret.encode("utf-8"),
            msg=base.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest().upper()
        log.debug("IOP sign: %s", sig)
        return sig

    # ------------------------------------------------------------------
    # Wykonanie zapytania
    # ------------------------------------------------------------------

    def execute(
        self,
        request: IopRequest,
        access_token: str | None = None,
    ) -> IopResponse:
        """
        Wysyla zapytanie do AliExpress IOP API.

        Parametry systemowe dolaczane automatycznie:
          app_key, sign_method, timestamp, partner_id, method,
          simplify, format  (+ sign)
        """
        api_path = request.get_api_path()

        # Timestamp: sekundy zaokraglone + '000'
        timestamp = str(int(round(time.time()))) + "000"

        sys_params: dict[str, str] = {
            "app_key": self._app_key,
            "sign_method": "sha256",
            "timestamp": timestamp,
            "partner_id": PARTNER_ID,
            "method": api_path,
            "simplify": "false",
            "format": "json",
        }
        if access_token:
            sys_params["session"] = access_token

        all_params = {**sys_params, **request.get_api_params()}
        all_params["sign"] = self._build_sign(api_path, all_params)

        url = self._gateway + api_path
        log.debug("IOP POST %s  params=%s", url, {k: v for k, v in all_params.items() if k != "sign"})

        resp = requests.post(
            url,
            data=all_params,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )
        log.debug("IOP response HTTP %s: %s", resp.status_code, resp.text[:400])
        return IopResponse(resp)
