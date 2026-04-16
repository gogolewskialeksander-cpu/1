"""
Klient AliExpress Dropshipping API.

Obsluguje:
- podpisywanie requestow HMAC-SHA256
- rate limiting (max 1000 req/dzien)
- retry z exponential backoff
- pobieranie produktow (aliexpress.ds.product.get)
- sprawdzanie dostawy (aliexpress.ds.shipping.info.query)
- filtrowanie po europejskich magazynach

Dodatkowo udostepnia funkcje get_mock_products() do trybu testowego.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

from logger import Logger


API_URL: str = "https://api-sg.aliexpress.com/rest"
SIGN_METHOD: str = "sha256"
PARTNER_ID: str = "iop-sdk-python-20220609"
DAILY_REQUEST_LIMIT: int = 1000
REQUEST_TIMEOUT_SECONDS: int = 30

SCRAPE_TARGET: str = "https://www.aliexpress.com/wholesale"
SCRAPE_MIN_IDS: int = 50
SCRAPE_MAX_PAGES: int = 10
SCRAPE_DELAY_RANGE: tuple = (1.0, 3.0)

_SCRAPE_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}


@dataclass
class Product:
    """
    Pojedynczy produkt z AliExpress — znormalizowana forma.

    Uzywane w calym pipeline. Pole `claude_*` jest wypelniane pozniej przez
    ClaudeAnalyzer; poczatkowo pozostaje puste.
    """

    product_id: str
    title: str
    description: str
    images: List[str]
    price: float                    # cena zakupu (hurtowa) w PLN
    price_original: float           # cena oryginalna z AliExpress
    currency: str
    sku: str
    stock: int
    seller_id: str
    seller_rating: float
    ship_from_country: str
    estimated_delivery_days: int
    variants: List[Dict[str, Any]] = field(default_factory=list)

    # Wymiary i waga opakowania
    weight_kg: float = 0.0
    length_cm: float = 0.0
    width_cm: float = 0.0
    height_cm: float = 0.0

    # Pola wypelniane przez Claude
    claude_title_pl: str = ""
    claude_description_pl: str = ""
    claude_category: str = ""
    claude_potential_score: int = 0
    claude_reject_reason: str = ""

    def compute_sale_price(self, margin_percent: float) -> float:
        """Oblicza cene sprzedazy detalicznej z podana marza (w procentach)."""
        return round(self.price * (1 + margin_percent / 100.0), 2)


class AliExpressAPIError(RuntimeError):
    """Blad komunikacji z AliExpress API."""


class AliExpressClient:
    """Klient oficjalnego AliExpress Dropshipping API."""

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        access_token: str,
        logger: Logger,
    ) -> None:
        """
        Args:
            app_key: Klucz aplikacji z panelu AliExpress Open Platform.
            app_secret: Sekret aplikacji.
            access_token: Token sesji uzytkownika (OAuth).
            logger: Instancja loggera.
        """
        self.app_key = app_key
        self.app_secret = app_secret
        self.access_token = access_token
        self.logger = logger
        self._session = requests.Session()
        self._request_count: int = 0

    def _build_signature(self, method: str, params: Dict[str, str]) -> str:
        """
        Oblicza HMAC-SHA256 zgodnie z oficjalnym IOP SDK AliExpress.

        Format bazowy: method + klucz1wartosc1klucz2wartosc2...
        (params posortowane alfabetycznie, bez pola 'sign')
        Klucz HMAC = app_secret
        """
        sorted_items = sorted((k, v) for k, v in params.items() if k != "sign")
        base_string = method + "".join(f"{k}{v}" for k, v in sorted_items)
        signature = hmac.new(
            key=self.app_secret.encode("utf-8"),
            msg=base_string.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest().upper()
        return signature

    def _call(
        self,
        method: str,
        method_params: Dict[str, Any],
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """
        Wykonuje pojedyncze zapytanie do AliExpress z retry i podpisem.

        Args:
            method: Nazwa metody API (np. 'aliexpress.ds.product.get').
            method_params: Parametry specyficzne dla metody.
            max_retries: Liczba prob w razie bledu sieciowego.

        Raises:
            AliExpressAPIError: Gdy limit dzienny przekroczony lub wszystkie proby
                zakoncza sie bledem.
        """
        if self._request_count >= DAILY_REQUEST_LIMIT:
            raise AliExpressAPIError(
                f"Osiagnieto dzienny limit {DAILY_REQUEST_LIMIT} requestow do AliExpress."
            )

        # Parametry systemowe — format IOP SDK (partner_id, sec+'000' timestamp)
        params: Dict[str, str] = {
            "app_key": self.app_key,
            "sign_method": SIGN_METHOD,
            "timestamp": str(int(round(time.time()))) + "000",
            "partner_id": PARTNER_ID,
            "method": method,
            "simplify": "false",
            "format": "json",
            "access_token": self.access_token,
        }
        # Dokladamy parametry metody (zawsze jako string do podpisu)
        for key, value in method_params.items():
            if isinstance(value, (dict, list)):
                params[key] = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
            else:
                params[key] = str(value)

        params["sign"] = self._build_signature(method, params)

        backoff_seconds: float = 2.0
        last_error: Optional[Exception] = None

        for attempt in range(1, max_retries + 1):
            try:
                self._request_count += 1
                response = self._session.post(
                    API_URL,
                    data=params,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict) and "error_response" in data:
                    err = data["error_response"]
                    raise AliExpressAPIError(
                        f"AliExpress API error: {err.get('msg', 'unknown')} "
                        f"(code={err.get('code', '?')})"
                    )
                return data
            except (requests.RequestException, AliExpressAPIError, ValueError) as e:
                last_error = e
                if attempt < max_retries:
                    self.logger.warn(
                        f"AliExpress API blad (proba {attempt}/{max_retries}): {e}. "
                        f"Ponawiam za {backoff_seconds:.0f}s..."
                    )
                    time.sleep(backoff_seconds)
                    backoff_seconds *= 2
                else:
                    self.logger.fail(
                        f"AliExpress API — wszystkie proby nieudane: {e}"
                    )

        raise AliExpressAPIError(f"AliExpress API nieosiagalne: {last_error}")

    def get_product(self, product_id: str, language: str = "pl", country: str = "PL") -> Dict[str, Any]:
        """
        Pobiera szczegoly produktu przez aliexpress.ds.product.get.

        Args:
            product_id: Identyfikator produktu na AliExpress.
            language: Kod jezyka (np. 'pl', 'en').
            country: Kod kraju docelowego.

        Returns:
            Surowa odpowiedz API jako dict.
        """
        return self._call(
            "aliexpress.ds.product.get",
            {
                "product_id": product_id,
                "ship_to_country": country,
                "target_currency": "PLN",
                "target_language": language.upper(),
            },
        )

    def query_shipping(
        self,
        product_id: str,
        country: str = "PL",
        quantity: int = 1,
    ) -> Dict[str, Any]:
        """
        Pobiera informacje o dostawie dla produktu przez
        aliexpress.ds.shipping.info.query.
        """
        return self._call(
            "aliexpress.ds.shipping.info.query",
            {
                "product_id": product_id,
                "country_code": country,
                "product_num": quantity,
            },
        )

    def _scrape_product_ids(
        self,
        ship_to: str,
        keyword: str,
        target: int,
    ) -> List[str]:
        """
        Scrappuje AliExpress Local+ (/wholesale?shipto=PL&local_sale=y).

        Zwraca liste unikalnych product_id lub [] jesli AliExpress zablokuje
        request (503/403 z datacenter IP — wtedy uzyj VPN/proxy rezydencjalnego).
        """
        collected: List[str] = []
        seen: set = set()

        scrape_session = requests.Session()
        scrape_session.headers.update(_SCRAPE_HEADERS)

        self.logger.ok(f"Scraping AliExpress Local+ (shipto={ship_to}, cel={target} ID)...")

        for page in range(1, SCRAPE_MAX_PAGES + 1):
            if len(collected) >= target:
                break
            params = {
                "SearchText": keyword or "",
                "shipto": ship_to,
                "local_sale": "y",
                "page": str(page),
                "SortType": "total_tranpro_desc",
            }
            try:
                resp = scrape_session.get(
                    SCRAPE_TARGET,
                    params=params,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                if resp.status_code in (403, 429, 503):
                    self.logger.warn(
                        f"  Scraping zablokowany HTTP {resp.status_code} "
                        f"(serwer/datacenter IP — uzyj proxy rezydencjalnego)"
                    )
                    break
                resp.raise_for_status()
                html = resp.text

                found = re.findall(r"/item/(\d{8,19})\.html", html)
                new_ids = [pid for pid in found if pid not in seen]
                for pid in new_ids:
                    seen.add(pid)
                    collected.append(pid)

                self.logger.ok(
                    f"  strona {page}: +{len(new_ids)} nowych ID "
                    f"(lacznie {len(collected)})"
                )

                if not found:
                    self.logger.warn(f"  strona {page}: brak linkow — koniec wynikow")
                    break

                if page < SCRAPE_MAX_PAGES and len(collected) < target:
                    time.sleep(random.uniform(*SCRAPE_DELAY_RANGE))

            except requests.RequestException as e:
                self.logger.warn(f"  strona {page}: blad HTTP — {e}")
                break

        return collected

    def _search_via_api(self, ship_to: str, limit: int) -> List[str]:
        """
        Wyszukuje produkty przez IOP API aliexpress.ds.product.search.

        Fallback gdy scraping jest zablokowany.
        """
        self.logger.ok(f"Fallback: aliexpress.ds.product.search (shipto={ship_to})...")
        ids: List[str] = []
        try:
            data = self._call(
                "aliexpress.ds.product.search",
                {
                    "ship_to_country": ship_to,
                    "target_language": "PL",
                    "target_currency": "PLN",
                    "page_no": "1",
                    "page_size": str(min(limit, 50)),
                    "sort": "SALE_PRICE_ASC",
                },
            )
            # Rozne klucze odpowiedzi zaleznie od wersji API
            root = (
                data.get("aliexpress_ds_product_search_response", {})
                or data.get("result", {})
            )
            items = (
                root.get("products", {}).get("product", [])
                or root.get("data", {}).get("products", [])
                or []
            )
            for item in items:
                pid = str(item.get("product_id", item.get("id", "")))
                if pid:
                    ids.append(pid)
            self.logger.ok(f"  API search zwrocil {len(ids)} produktow")
        except AliExpressAPIError as e:
            self.logger.warn(f"  API search nieudany: {e}")
        return ids

    def search_products(
        self,
        ship_from_countries: List[str],
        limit: int,
        keyword: str = "",
    ) -> List[str]:
        """
        Zwraca product_id do sprawdzenia przez DS API.

        Kolejnosc:
        1. Scraping AliExpress Local+ (dziala z IP rezydencjalnych/VPN)
        2. Fallback: aliexpress.ds.product.search przez IOP API

        Args:
            ship_from_countries: Lista kodow krajow EU (uzywany pierwszy).
            limit: Maksymalna liczba ID do zwrocenia.
            keyword: Fraza wyszukiwania (opcjonalna).
        """
        ship_to = ship_from_countries[0] if ship_from_countries else "PL"
        target = max(limit, SCRAPE_MIN_IDS)

        ids = self._scrape_product_ids(ship_to, keyword, target)

        if not ids:
            self.logger.warn("Scraping nieudany — proba przez IOP API...")
            ids = self._search_via_api(ship_to, limit)

        if not ids:
            raise AliExpressAPIError(
                "Brak produktow: scraping zablokowany i IOP search nieudany. "
                "Uruchom z VPN/proxy lub sprawdz uprawnienia aplikacji."
            )

        result = ids[:limit]
        self.logger.ok(f"Lacznie {len(result)} product_id do sprawdzenia przez DS API")
        return result

    def fetch_products(
        self,
        ship_from_countries: List[str],
        limit: int,
    ) -> List[Product]:
        """
        Kompletny workflow pobierania produktow z AliExpress.

        1. Wyszukuje id produktow z europejskich magazynow.
        2. Dla kazdego pobiera szczegoly i informacje o dostawie.
        3. Zwraca liste obiektow Product.

        Args:
            ship_from_countries: Lista kodow krajow EU.
            limit: Maksymalna liczba produktow.
        """
        self.logger.ok(f"AliExpress: wyszukuje do {limit} produktow z {ship_from_countries}...")
        try:
            product_ids = self.search_products(ship_from_countries, limit)
        except AliExpressAPIError as e:
            self.logger.fail(f"Nie udalo sie wyszukac produktow: {e}")
            return []

        self.logger.ok(f"AliExpress: znaleziono {len(product_ids)} produktow")
        products: List[Product] = []

        eu_set = {c.upper() for c in ship_from_countries} if ship_from_countries else set()

        for idx, pid in enumerate(product_ids, start=1):
            if len(products) >= limit:
                break
            try:
                raw_product = self.get_product(pid)

                # DEBUG: surowa odpowiedz ds.product.get
                if "aliexpress_ds_product_get_response" in raw_product:
                    ds_result = raw_product["aliexpress_ds_product_get_response"].get("result", {})
                else:
                    ds_result = raw_product.get("result", {})
                ds_logistics = ds_result.get("logistics_info_dto", {})
                raw_ship_from = str(ds_logistics.get("ship_from_country", "")).upper() or "BRAK"
                ds_ok = bool(ds_result)
                # Sprawdz tez ship_from w SKU properties
                sku_list = ds_result.get("ae_item_sku_info_dtos", [])
                if isinstance(sku_list, dict):
                    sku_list = sku_list.get("ae_item_sku_info_d_t_o", [])
                sku_ship_from = ""
                for sku in (sku_list or []):
                    raw_p = sku.get("ae_sku_property_dtos", [])
                    if isinstance(raw_p, dict):
                        p_list = (
                            raw_p.get("ae_sku_property_d_t_o")
                            or (list(raw_p.values())[0] if raw_p else [])
                        )
                        if not isinstance(p_list, list):
                            p_list = [p_list]
                    elif isinstance(raw_p, list):
                        p_list = raw_p
                    else:
                        p_list = []
                    for prop in p_list:
                        if not isinstance(prop, dict):
                            continue
                        if (prop.get("sku_property_id") == 200007763
                                or prop.get("sku_property_name", "") == "Ships From"):
                            sku_ship_from = prop.get("sku_property_value", "")
                            break
                    if sku_ship_from:
                        break
                # Loguj surowy typ ae_sku_property_dtos dla diagnozy
                if sku_list:
                    raw_p_sample = sku_list[0].get("ae_sku_property_dtos", "BRAK")
                    self.logger.ok(
                        f"    [DEBUG] ae_sku_property_dtos type={type(raw_p_sample).__name__} "
                        f"sample={str(raw_p_sample)[:200]}"
                    )
                ship_display = sku_ship_from or raw_ship_from
                self.logger.ok(
                    f"  [{idx}/{len(product_ids)}] {pid} | "
                    f"DS: {'OK' if ds_ok else 'BRAK'} | "
                    f"ship_from={ship_display!r} | "
                    f"EU={ship_display.upper() in eu_set if eu_set else 'brak_filtru'}"
                )
                if not ds_ok:
                    self.logger.warn(f"    => pusta odpowiedz: {str(raw_product)[:300]}")

                raw_shipping = self.query_shipping(pid)
                product = self._parse_product(raw_product, raw_shipping)
                if product is None:
                    self.logger.warn(f"    => _parse_product zwrocil None (brak id/tytulu/ceny)")
                    continue
                # Filtruj po magazynie EU
                if eu_set and product.ship_from_country not in eu_set:
                    self.logger.warn(
                        f"    => ODRZUCONY — ship_from={product.ship_from_country} "
                        f"nie w EU {sorted(eu_set)}"
                    )
                    continue
                products.append(product)
                self.logger.ok(
                    f"    => PRZYJETY: {product.title[:55]} [{product.ship_from_country}] "
                    f"{product.price:.2f} PLN stock={product.stock}"
                )
            except AliExpressAPIError as e:
                self.logger.warn(f"  [{idx}/{len(product_ids)}] {pid}: API error: {e}")
                continue
            except Exception as e:  # pragma: no cover — defensywne
                self.logger.warn(f"  [{idx}/{len(product_ids)}] {pid}: nieoczekiwany blad: {e}")
                continue

        return products

    def _parse_product(
        self,
        raw_product: Dict[str, Any],
        raw_shipping: Dict[str, Any],
    ) -> Optional[Product]:
        """
        Konwertuje surowa odpowiedz API na obiekt Product.

        Zwraca None jesli brakuje krytycznych pol (id, tytul, cena).
        """
        # Odpowiedz moze miec klucz opakowujacy lub "result" bezposrednio na gorze
        if "aliexpress_ds_product_get_response" in raw_product:
            root = raw_product["aliexpress_ds_product_get_response"].get("result", {})
        else:
            root = raw_product.get("result", {})
        if not root:
            return None

        base_info = root.get("ae_item_base_info_dto", {})
        multimedia = root.get("ae_multimedia_info_dto", {})
        store_info = root.get("ae_store_info", {})
        logistics = root.get("logistics_info_dto", {})
        package_info = root.get("package_info_dto", {})

        # ae_item_sku_info_dtos: moze byc lista lub dict z lista wewnatrz
        raw_skus = root.get("ae_item_sku_info_dtos", [])
        if isinstance(raw_skus, dict):
            sku_info_list: List[Dict[str, Any]] = raw_skus.get("ae_item_sku_info_d_t_o", [])
        elif isinstance(raw_skus, list):
            sku_info_list = raw_skus
        else:
            sku_info_list = []

        product_id = str(base_info.get("product_id", ""))
        if not product_id:
            return None

        title = base_info.get("subject", "").strip()
        description = base_info.get("detail", "") or base_info.get("product_description", "")

        # Zdjecia z image_urls (string z ";")
        images: List[str] = []
        image_urls = multimedia.get("image_urls", "")
        if isinstance(image_urls, str):
            images = [u.strip() for u in image_urls.split(";") if u.strip()]
        elif isinstance(image_urls, list):
            images = [str(u).strip() for u in image_urls if u]

        # Mapowanie pelnych nazw krajow na kody ISO (uzywane przy parsowaniu SKU)
        COUNTRY_MAP: Dict[str, str] = {
            # angielskie
            "poland": "PL",
            "germany": "DE", "deutschland": "DE",
            "czech republic": "CZ", "czechia": "CZ",
            "spain": "ES", "españa": "ES",
            "france": "FR",
            "italy": "IT", "italia": "IT",
            "netherlands": "NL", "holland": "NL",
            "united kingdom": "GB", "uk": "GB",
            "united states": "US", "usa": "US",
            "china": "CN",
            "australia": "AU",
            "japan": "JP",
            # polskie
            "polska": "PL", "polonia": "PL",
            "niemcy": "DE",
            "republika czeska": "CZ",
            "hiszpania": "ES",
            "francja": "FR",
            "włochy": "IT", "wlochy": "IT",
            "holandia": "NL", "niderlandy": "NL",
            "wielka brytania": "GB", "wielka brytania": "GB",
            "stany zjednoczone": "US",
            "japonia": "JP",
            "australia": "AU",
            "chiny": "CN",
        }

        # Ceny i SKU
        price: float = 0.0
        price_original: float = 0.0
        sku_code: str = ""
        stock: int = 0
        currency: str = "PLN"
        variants: List[Dict[str, Any]] = []
        all_ship_from_values: List[str] = []  # wszystkie raw wartosci ze wszystkich SKU

        for sku in sku_info_list:
            sku_price = float(sku.get("sku_price", 0) or 0)
            offer_price = float(sku.get("offer_sale_price", 0) or 0)
            effective_price = offer_price if offer_price > 0 else sku_price
            sku_stock = int(sku.get("sku_available_stock", 0) or 0)
            sku_id = str(sku.get("sku_id", ""))

            variants.append({
                "sku_id": sku_id,
                "price": effective_price,
                "stock": sku_stock,
            })
            if price == 0.0 or (effective_price > 0 and effective_price < price):
                price = effective_price
                price_original = sku_price
                sku_code = sku_id
            stock += sku_stock

            # Zbierz ship_from ze WSZYSTKICH wariantow SKU
            raw_props = sku.get("ae_sku_property_dtos", [])
            if isinstance(raw_props, dict):
                # Moze byc owiniety w ae_sku_property_d_t_o lub bezposrednio
                props: List[Any] = (
                    raw_props.get("ae_sku_property_d_t_o")
                    or raw_props.get("ae_sku_property_dtos")
                    or list(raw_props.values())[0] if raw_props else []
                )
                if not isinstance(props, list):
                    props = [props]
            elif isinstance(raw_props, list):
                props = raw_props
            else:
                props = []

            for prop in props:
                if not isinstance(prop, dict):
                    continue
                prop_id = prop.get("sku_property_id")
                prop_name = str(prop.get("sku_property_name", "")).strip()
                # Szukaj po ID (200007763) lub nazwie "Ships From"
                if prop_id == 200007763 or prop_name == "Ships From":
                    val = str(prop.get("sku_property_value", "")).strip()
                    if val and val not in all_ship_from_values:
                        all_ship_from_values.append(val)

        if sku_info_list:
            currency = sku_info_list[0].get("currency_code", "PLN")

        if price == 0.0:
            return None

        # Waga i wymiary
        weight_kg = float(package_info.get("package_weight", 0) or 0)
        length_cm = float(package_info.get("package_length", 0) or 0)
        width_cm = float(package_info.get("package_width", 0) or 0)
        height_cm = float(package_info.get("package_height", 0) or 0)

        # Loguj wszystkie raw ship_from values ze SKU
        logistics_ship_from = logistics.get("ship_from_country", "")
        self.logger.ok(
            f"    ship_from raw values: {all_ship_from_values} "
            f"| logistics: {logistics_ship_from!r} "
            f"| sku_count={len(sku_info_list)}"
        )

        # Zamien raw wartosci na kody ISO i wybierz EU jesli dostepne
        def to_code(raw: str) -> str:
            return COUNTRY_MAP.get(raw.strip().lower(), raw.strip().upper())

        sku_codes = [to_code(v) for v in all_ship_from_values]
        logistics_code = to_code(logistics_ship_from) if logistics_ship_from else ""

        # Preferuj EU wariant jesli jakikolwiek SKU ma EU magazyn
        EU_CODES = {"PL", "DE", "CZ", "ES", "FR", "IT", "NL", "GB", "BE", "AT", "SE", "DK", "FI", "PT", "HU", "RO", "SK", "HR", "SI", "BG", "LT", "LV", "EE"}
        eu_codes_found = [c for c in sku_codes if c in EU_CODES]
        if eu_codes_found:
            ship_from_code = eu_codes_found[0]
        elif sku_codes:
            ship_from_code = sku_codes[0]
        elif logistics_code:
            ship_from_code = logistics_code
        else:
            ship_from_code = "CN"

        # Czas dostawy
        estimated_days = int(logistics.get("delivery_time", 30) or 30)

        # Nadpisanie przez shipping query jesli dostepne
        shipping_root = raw_shipping.get(
            "aliexpress_ds_shipping_info_query_response", {}
        ).get("result", {})
        if not shipping_root:
            shipping_root = raw_shipping.get("result", {})
        freight_list = shipping_root.get("freight_list", {}).get("freight_item", [])
        if isinstance(freight_list, list) and freight_list:
            fastest = min(
                (int(opt.get("estimate_delivery_days", estimated_days) or estimated_days)
                 for opt in freight_list),
                default=estimated_days,
            )
            estimated_days = fastest

        return Product(
            product_id=product_id,
            title=title,
            description=description,
            images=images,
            price=price,
            price_original=price_original,
            currency=currency,
            sku=sku_code or product_id,
            stock=stock,
            seller_id=str(store_info.get("store_id", "")),
            seller_rating=float(store_info.get("communication_rating", 0) or 0),
            ship_from_country=ship_from_code,
            estimated_delivery_days=estimated_days,
            variants=variants,
            weight_kg=weight_kg,
            length_cm=length_cm,
            width_cm=width_cm,
            height_cm=height_cm,
        )


def get_mock_products() -> List[Product]:
    """
    Zwraca 10 zahardkodowanych produktow do trybu testowego.

    Produkty obejmuja rozne kategorie (elektronika, sport, dom, akcesoria)
    i maja rozne poziomy jakosci aby mozna bylo sprawdzic zarowno akceptacje
    jak i odrzucenie przez Claude.
    """
    return [
        Product(
            product_id="1005006123456789",
            title="Universal Bike Phone Holder 360 Rotation Waterproof Motorcycle Mount",
            description=(
                "High quality aluminum alloy phone holder. Fits all smartphones "
                "from 4.7 to 7 inches. 360 degree rotation, shockproof design, "
                "easy installation on handlebar 22-32mm."
            ),
            images=[
                "https://ae01.alicdn.com/kf/S01/mock-bike-holder-1.jpg",
                "https://ae01.alicdn.com/kf/S01/mock-bike-holder-2.jpg",
                "https://ae01.alicdn.com/kf/S01/mock-bike-holder-3.jpg",
            ],
            price=18.50,
            price_original=29.90,
            currency="PLN",
            sku="BIKE-HOLDER-BLK",
            stock=247,
            seller_id="store_001",
            seller_rating=4.8,
            ship_from_country="PL",
            estimated_delivery_days=4,
            variants=[
                {"sku_id": "BIKE-HOLDER-BLK", "price": 18.50, "stock": 120},
                {"sku_id": "BIKE-HOLDER-SLV", "price": 19.50, "stock": 127},
            ],
            weight_kg=0.15, length_cm=12.0, width_cm=8.0, height_cm=5.0,
        ),
        Product(
            product_id="1005006234567890",
            title="USB-C Cable 2m Fast Charging 100W Nylon Braided Type-C to Type-C",
            description=(
                "Premium nylon braided USB-C cable. Supports 100W PD fast charging "
                "and USB 3.1 data transfer up to 10Gbps. 2 meter length, durable "
                "aluminum connectors, compatible with MacBook, iPad, Samsung."
            ),
            images=[
                "https://ae01.alicdn.com/kf/S01/mock-usbc-1.jpg",
                "https://ae01.alicdn.com/kf/S01/mock-usbc-2.jpg",
            ],
            price=12.30,
            price_original=24.90,
            currency="PLN",
            sku="USBC-2M-BLK",
            stock=890,
            seller_id="store_002",
            seller_rating=4.9,
            ship_from_country="CZ",
            estimated_delivery_days=5,
            variants=[
                {"sku_id": "USBC-2M-BLK", "price": 12.30, "stock": 450},
                {"sku_id": "USBC-2M-WHT", "price": 12.30, "stock": 440},
            ],
            weight_kg=0.08, length_cm=15.0, width_cm=8.0, height_cm=3.0,
        ),
        Product(
            product_id="1005006345678901",
            title="cheap plastic keychain key ring lot 100pcs color random",
            description="random color plastic keychain cheap good quality bulk.",
            images=[
                "https://ae01.alicdn.com/kf/S01/mock-keychain-1.jpg",
            ],
            price=2.10,
            price_original=3.50,
            currency="PLN",
            sku="KEYCHAIN-RND",
            stock=50,
            seller_id="store_003",
            seller_rating=3.9,
            ship_from_country="PL",
            estimated_delivery_days=6,
            variants=[
                {"sku_id": "KEYCHAIN-RND", "price": 2.10, "stock": 50},
            ],
            weight_kg=0.05, length_cm=10.0, width_cm=6.0, height_cm=2.0,
        ),
        Product(
            product_id="1005006456789012",
            title="Smart LED Strip Light 5m RGB WiFi Alexa Google Home Compatible",
            description=(
                "5 meter RGB LED strip with WiFi control. Works with Alexa and "
                "Google Home. 16 million colors, music sync mode, timer function. "
                "Easy to install with self-adhesive backing. Power adapter included."
            ),
            images=[
                "https://ae01.alicdn.com/kf/S01/mock-led-1.jpg",
                "https://ae01.alicdn.com/kf/S01/mock-led-2.jpg",
                "https://ae01.alicdn.com/kf/S01/mock-led-3.jpg",
                "https://ae01.alicdn.com/kf/S01/mock-led-4.jpg",
            ],
            price=45.80,
            price_original=89.90,
            currency="PLN",
            sku="LED-RGB-5M",
            stock=178,
            seller_id="store_004",
            seller_rating=4.7,
            ship_from_country="DE",
            estimated_delivery_days=7,
            variants=[
                {"sku_id": "LED-RGB-5M", "price": 45.80, "stock": 88},
                {"sku_id": "LED-RGB-10M", "price": 79.80, "stock": 90},
            ],
            weight_kg=0.30, length_cm=20.0, width_cm=10.0, height_cm=5.0,
        ),
        Product(
            product_id="1005006567890123",
            title="Waterproof Sport Fitness Tracker Smart Watch Heart Rate Monitor",
            description=(
                "Fitness smartwatch with heart rate and blood oxygen monitoring. "
                "IP68 waterproof, 14 sports modes, sleep tracking, call and message "
                "notifications. 1.4 inch color display, 7 day battery life."
            ),
            images=[
                "https://ae01.alicdn.com/kf/S01/mock-watch-1.jpg",
                "https://ae01.alicdn.com/kf/S01/mock-watch-2.jpg",
                "https://ae01.alicdn.com/kf/S01/mock-watch-3.jpg",
            ],
            price=78.40,
            price_original=149.00,
            currency="PLN",
            sku="SMARTWATCH-BLK",
            stock=95,
            seller_id="store_005",
            seller_rating=4.6,
            ship_from_country="ES",
            estimated_delivery_days=8,
            variants=[
                {"sku_id": "SMARTWATCH-BLK", "price": 78.40, "stock": 45},
                {"sku_id": "SMARTWATCH-SLV", "price": 78.40, "stock": 50},
            ],
            weight_kg=0.12, length_cm=9.0, width_cm=7.0, height_cm=4.0,
        ),
        Product(
            product_id="1005006678901234",
            title="bad qualit broken item NO RETURN not working use own risk china",
            description="item NO working, use at own risk, no refund. buyer beware.",
            images=[
                "https://ae01.alicdn.com/kf/S01/mock-broken-1.jpg",
            ],
            price=1.99,
            price_original=1.99,
            currency="PLN",
            sku="BROKEN-001",
            stock=10,
            seller_id="store_006",
            seller_rating=2.1,
            ship_from_country="PL",
            estimated_delivery_days=4,
            variants=[{"sku_id": "BROKEN-001", "price": 1.99, "stock": 10}],
            weight_kg=0.05, length_cm=5.0, width_cm=5.0, height_cm=2.0,
        ),
        Product(
            product_id="1005006789012345",
            title="Foldable Camping Chair Lightweight Portable Outdoor Fishing Beach",
            description=(
                "Ultra-light foldable camping chair, weighs only 1kg. Holds up to "
                "150kg. Compact carry bag included. Perfect for camping, fishing, "
                "festivals and beach. Durable aluminum frame and 600D oxford fabric."
            ),
            images=[
                "https://ae01.alicdn.com/kf/S01/mock-chair-1.jpg",
                "https://ae01.alicdn.com/kf/S01/mock-chair-2.jpg",
                "https://ae01.alicdn.com/kf/S01/mock-chair-3.jpg",
            ],
            price=58.90,
            price_original=119.00,
            currency="PLN",
            sku="CAMP-CHAIR-GRN",
            stock=143,
            seller_id="store_007",
            seller_rating=4.8,
            ship_from_country="DE",
            estimated_delivery_days=6,
            variants=[
                {"sku_id": "CAMP-CHAIR-GRN", "price": 58.90, "stock": 70},
                {"sku_id": "CAMP-CHAIR-BLU", "price": 58.90, "stock": 73},
            ],
            weight_kg=1.20, length_cm=55.0, width_cm=12.0, height_cm=12.0,
        ),
        Product(
            product_id="1005006890123456",
            title="Kitchen Electric Garlic Chopper Wireless Mini Food Processor USB",
            description=(
                "Wireless USB rechargeable mini food chopper. Perfect for garlic, "
                "onions, herbs, nuts. 250ml capacity, stainless steel blades, "
                "one-touch operation. Easy to clean, dishwasher safe bowl."
            ),
            images=[
                "https://ae01.alicdn.com/kf/S01/mock-chopper-1.jpg",
                "https://ae01.alicdn.com/kf/S01/mock-chopper-2.jpg",
            ],
            price=32.50,
            price_original=65.00,
            currency="PLN",
            sku="CHOPPER-WHT",
            stock=67,
            seller_id="store_008",
            seller_rating=4.5,
            ship_from_country="PL",
            estimated_delivery_days=3,
            variants=[{"sku_id": "CHOPPER-WHT", "price": 32.50, "stock": 67}],
            weight_kg=0.45, length_cm=14.0, width_cm=14.0, height_cm=12.0,
        ),
        Product(
            product_id="1005006901234567",
            title="Pet Dog Cat Automatic Water Fountain 2L Filter USB Powered Silent",
            description=(
                "2 liter capacity automatic pet water fountain with activated carbon "
                "filter. USB powered, silent operation below 40dB. Stimulates pets "
                "to drink more water, prevents stagnation. Easy to disassemble and clean."
            ),
            images=[
                "https://ae01.alicdn.com/kf/S01/mock-fountain-1.jpg",
                "https://ae01.alicdn.com/kf/S01/mock-fountain-2.jpg",
                "https://ae01.alicdn.com/kf/S01/mock-fountain-3.jpg",
            ],
            price=54.20,
            price_original=109.00,
            currency="PLN",
            sku="PET-FOUNTAIN-WHT",
            stock=82,
            seller_id="store_009",
            seller_rating=4.7,
            ship_from_country="FR",
            estimated_delivery_days=7,
            variants=[
                {"sku_id": "PET-FOUNTAIN-WHT", "price": 54.20, "stock": 40},
                {"sku_id": "PET-FOUNTAIN-GRY", "price": 54.20, "stock": 42},
            ],
            weight_kg=0.65, length_cm=22.0, width_cm=22.0, height_cm=15.0,
        ),
        Product(
            product_id="1005007012345678",
            title="Wireless Bluetooth 5.3 Earbuds ANC Noise Cancelling IPX5 30h Playtime",
            description=(
                "True wireless earbuds with active noise cancellation. Bluetooth 5.3, "
                "30 hours total playtime with charging case, IPX5 water resistant. "
                "Touch controls, built-in microphone for calls, comfortable fit."
            ),
            images=[
                "https://ae01.alicdn.com/kf/S01/mock-earbuds-1.jpg",
                "https://ae01.alicdn.com/kf/S01/mock-earbuds-2.jpg",
                "https://ae01.alicdn.com/kf/S01/mock-earbuds-3.jpg",
            ],
            price=69.00,
            price_original=139.00,
            currency="PLN",
            sku="EARBUDS-BLK",
            stock=214,
            seller_id="store_010",
            seller_rating=4.8,
            ship_from_country="CN",  # Ten produkt zostanie odrzucony (brak EU magazynu)
            estimated_delivery_days=18,
            variants=[{"sku_id": "EARBUDS-BLK", "price": 69.00, "stock": 214}],
            weight_kg=0.10, length_cm=8.0, width_cm=6.0, height_cm=4.0,
        ),
    ]
