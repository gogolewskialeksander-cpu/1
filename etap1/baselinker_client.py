"""
Klient BaseLinker API.

Obsluguje metody:
- addInventoryProduct — dodaje nowy produkt do katalogu BaseLinker
- getInventoryProductsList — sprawdza czy produkt juz istnieje (do decyzji
  add vs update)

BaseLinker limituje API do 100 requestow/minute. Klient automatycznie odczekuje
gdy zostanie zwrocony blad 429 / error_code 'ERROR_RATE_LIMIT_EXCEEDED'.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from aliexpress_client import Product
from logger import Logger


API_URL: str = "https://api.baselinker.com/connector.php"
REQUEST_TIMEOUT_SECONDS: int = 30
RATE_LIMIT_WAIT_SECONDS: float = 60.0
MAX_RETRIES: int = 3


class BaseLinkerAPIError(RuntimeError):
    """Blad komunikacji z BaseLinker API."""


class BaseLinkerClient:
    """Klient BaseLinker Connector API."""

    def __init__(
        self,
        token: str,
        inventory_id: str,
        margin_percent: float,
        logger: Logger,
    ) -> None:
        """
        Args:
            token: Token API BaseLinker.
            inventory_id: ID katalogu produktow (inventory_id). Moze byc pusty,
                wtedy produkty dodajemy do domyslnego katalogu.
            margin_percent: Marza do ceny sprzedazy.
            logger: Instancja loggera.
        """
        self.token = token
        self.inventory_id = inventory_id
        self.margin_percent = margin_percent
        self.logger = logger
        self._session = requests.Session()

    def _call(self, method: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Wywoluje metode BaseLinker Connector API.

        Args:
            method: Nazwa metody (np. 'addInventoryProduct').
            parameters: Parametry metody (zostana zserializowane jako JSON).

        Raises:
            BaseLinkerAPIError: Gdy API zwroci blad nie do odzyskania.
        """
        headers = {
            "X-BLToken": self.token,
        }
        payload = {
            "method": method,
            "parameters": json.dumps(parameters, ensure_ascii=False),
        }

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._session.post(
                    API_URL,
                    headers=headers,
                    data=payload,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                data = response.json()
            except (requests.RequestException, ValueError) as e:
                if attempt < MAX_RETRIES:
                    backoff = 2.0 ** attempt
                    self.logger.warn(
                        f"BaseLinker API blad sieciowy (proba {attempt}/{MAX_RETRIES}): {e}. "
                        f"Ponawiam za {backoff:.0f}s..."
                    )
                    time.sleep(backoff)
                    continue
                raise BaseLinkerAPIError(f"BaseLinker API nieosiagalne: {e}") from e

            status = data.get("status")
            if status == "SUCCESS":
                return data

            error_code = data.get("error_code", "")
            error_message = data.get("error_message", "unknown error")

            if error_code == "ERROR_RATE_LIMIT_EXCEEDED":
                if attempt < MAX_RETRIES:
                    self.logger.warn(
                        f"BaseLinker rate limit. Czekam {RATE_LIMIT_WAIT_SECONDS:.0f}s..."
                    )
                    time.sleep(RATE_LIMIT_WAIT_SECONDS)
                    continue

            raise BaseLinkerAPIError(
                f"BaseLinker error [{error_code}]: {error_message}"
            )

        raise BaseLinkerAPIError("BaseLinker API — wyczerpano proby")

    def _product_to_parameters(self, product: Product) -> Dict[str, Any]:
        """
        Konwertuje obiekt Product na payload wymagany przez addInventoryProduct.
        """
        sale_price = product.compute_sale_price(self.margin_percent)
        name = product.claude_title_pl or product.title
        description = product.claude_description_pl or product.description
        category = product.claude_category or "Inne"

        params: Dict[str, Any] = {
            "inventory_id": self.inventory_id or "bl_catalog",
            "product_id": str(product.product_id),
            "sku": product.sku or product.product_id,
            "ean": "",
            "text_fields": {
                "name": name,
                "description": description,
                "category": category,
            },
            "prices": {
                "default": sale_price,
            },
            "stock": {
                "bl_1": product.stock,
            },
            "images": product.images,
            "features": {
                "Sprzedawca AliExpress": product.seller_id or "unknown",
                "Czas dostawy": f"{product.estimated_delivery_days} dni",
                "Magazyn": product.ship_from_country or "EU",
                "Ocena potencjalu": f"{product.claude_potential_score}/10",
            },
        }
        return params

    def add_product(self, product: Product) -> Dict[str, Any]:
        """
        Dodaje lub aktualizuje pojedynczy produkt w katalogu BaseLinker.

        BaseLinker automatycznie wykrywa duplikaty po product_id i zwraca
        status: 'added' lub 'updated'.
        """
        parameters = self._product_to_parameters(product)
        return self._call("addInventoryProduct", parameters)

    def upload_products(
        self,
        products: List[Product],
        failed_path: Path,
    ) -> None:
        """
        Wysyla liste produktow do BaseLinker.

        Produkty ktore zwroca blad sa zapisywane do pliku failed_products.json
        do ponownego przegladu.

        Args:
            products: Lista produktow do wyslania.
            failed_path: Sciezka pliku do zapisu nieudanych produktow.
        """
        failed: List[Dict[str, Any]] = []

        for idx, product in enumerate(products, start=1):
            try:
                result = self.add_product(product)
                # BaseLinker zwraca 'product_id' przy sukcesie
                bl_id = result.get("product_id", "?")
                was_update = result.get("warnings", [])
                if was_update:
                    self.logger.stats.baselinker_updated += 1
                    self.logger.ok(
                        f"  [{idx}/{len(products)}] zaktualizowano w BL: {bl_id}"
                    )
                else:
                    self.logger.stats.baselinker_added += 1
                    self.logger.ok(
                        f"  [{idx}/{len(products)}] dodano do BL: {bl_id}"
                    )
                self.logger.stats.sent_to_baselinker += 1
            except BaseLinkerAPIError as e:
                self.logger.fail(
                    f"  [{idx}/{len(products)}] blad BL dla {product.product_id}: {e}"
                )
                self.logger.stats.baselinker_failed += 1
                failed.append({
                    "product_id": product.product_id,
                    "title": product.claude_title_pl or product.title,
                    "error": str(e),
                })

        if failed:
            failed_path.write_text(
                json.dumps(failed, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.logger.warn(
                f"Zapisano {len(failed)} nieudanych produktow do {failed_path}"
            )
