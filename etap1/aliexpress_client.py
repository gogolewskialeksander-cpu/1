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

# Produkty z EU/Local+ magazynow (zweryfikowane recznie)
# Uzupelnij liste o kolejne ID jesli potrzebujesz wiecej produktow.
SEED_PRODUCT_IDS: List[str] = [
    "1005009674342871",
    "1005008529307600",
    "1005009522530165",
    "1005011931202367",
    "1005011681407049",
    "1005011657852671",
    "1005007077687499",
    "1005009114857306",
    "1005009260839172",
    "1005009770876958",
    "1005007853697935",
    "1005009667701880",
    "1005008984834308",
    "1005007813226384",
    "1005009887005491",
    "1005008121531331",
    "1005010687254406",
    "32883030040",
    "1005009685411506",
    "1005008378098130",
]


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

    def search_products(
        self,
        ship_from_countries: List[str],
        limit: int,
        keyword: str = "",
    ) -> List[str]:
        """
        Zwraca liste product_id ze statycznej listy SEED_PRODUCT_IDS.

        Produkty zebrane recznym przegladem AliExpress Local+ (shipto=PL,
        local_sale=y). Filtrowanie po ship_from_country (EU) odbywa sie
        pozniej w fetch_products() na podstawie odpowiedzi ds.product.get.

        Args:
            ship_from_countries: Lista kodow krajow EU — uzywana w fetch_products().
            limit: Maksymalna liczba produktow do sprawdzenia.

        Returns:
            Lista identyfikatorow produktow do sprawdzenia przez DS API.
        """
        ids = SEED_PRODUCT_IDS[:limit]
        self.logger.ok(f"SEED: {len(ids)} product_id do sprawdzenia przez DS API")
        return ids

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
                for sku in (sku_list[:1] if sku_list else []):
                    props = sku.get("ae_sku_property_dtos", [])
                    if isinstance(props, dict):
                        props = props.get("ae_sku_property_d_t_o", [])
                    for prop in props:
                        if prop.get("sku_property_name", "") == "Ships From":
                            sku_ship_from = prop.get("sku_property_value", "")
                            break
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

        # Ceny i SKU
        price: float = 0.0
        price_original: float = 0.0
        sku_code: str = ""
        stock: int = 0
        currency: str = "PLN"
        variants: List[Dict[str, Any]] = []
        ship_from_sku: str = ""  # wyciagniete z ae_sku_property_dtos

        for sku in sku_info_list:
            # Cena: sku_price jest cena zakupu; offer_sale_price moze nie byc
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

            # ship_from z wlasciwosci SKU ("Ships From")
            if not ship_from_sku:
                props = sku.get("ae_sku_property_dtos", [])
                if isinstance(props, dict):
                    props = props.get("ae_sku_property_d_t_o", [])
                for prop in props:
                    if str(prop.get("sku_property_name", "")).strip() == "Ships From":
                        ship_from_sku = str(prop.get("sku_property_value", "")).strip()
                        break

        if sku_info_list:
            currency = sku_info_list[0].get("currency_code", "PLN")

        if price == 0.0:
            return None

        # Waga i wymiary
        weight_kg = float(package_info.get("package_weight", 0) or 0)
        length_cm = float(package_info.get("package_length", 0) or 0)
        width_cm = float(package_info.get("package_width", 0) or 0)
        height_cm = float(package_info.get("package_height", 0) or 0)

        # ship_from_country: SKU properties > logistics_info_dto
        logistics_ship_from = logistics.get("ship_from_country", "")
        ship_from_raw = ship_from_sku or logistics_ship_from or "CN"

        # Mapowanie nazw krajow na kody ISO
        COUNTRY_NAME_TO_CODE: Dict[str, str] = {
            "poland": "PL", "polska": "PL",
            "germany": "DE", "deutschland": "DE", "niemcy": "DE",
            "czech republic": "CZ", "czechia": "CZ", "czechy": "CZ",
            "spain": "ES", "espana": "ES", "espana": "ES", "hiszpania": "ES",
            "france": "FR", "francja": "FR",
            "united states": "US", "usa": "US",
            "china": "CN", "chiny": "CN",
        }
        ship_from_upper = ship_from_raw.upper()
        ship_from_code = COUNTRY_NAME_TO_CODE.get(ship_from_raw.lower(), ship_from_upper)

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
