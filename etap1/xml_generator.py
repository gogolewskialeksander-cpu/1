"""
Generator XML dla importu produktow do BaseLinker.

Buduje plik XML w formacie:
<offer>
  <products>
    <product id="...">
      <name>...</name>
      ...
    </product>
  </products>
</offer>

Wszystkie znaki specjalne w polach tekstowych sa escape'owane. Po zapisie
plik jest walidowany (ponowne parsowanie lxml) — jesli walidacja sie nie uda,
funkcja rzuca wyjatek.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List

from lxml import etree

from aliexpress_client import Product
from logger import Logger


def _add_text_element(parent: etree._Element, tag: str, text: str) -> etree._Element:
    """Pomocnik: tworzy element z tekstem. Text jest automatycznie escape'owany."""
    element = etree.SubElement(parent, tag)
    element.text = text if text else ""
    return element


def _add_attribute(parent: etree._Element, name: str, value: str) -> etree._Element:
    """Dodaje <attribute name="...">value</attribute> do parenta."""
    attr = etree.SubElement(parent, "attribute", name=name)
    attr.text = value
    return attr


def build_xml(
    products: List[Product],
    margin_percent: float,
) -> bytes:
    """
    Buduje strukturę XML z listy produktow.

    Args:
        products: Lista zaakceptowanych produktow.
        margin_percent: Marza do naliczenia przy obliczaniu ceny sprzedazy.

    Returns:
        Bajty XML (UTF-8) z deklaracja XML na poczatku.
    """
    root = etree.Element("offer")
    products_node = etree.SubElement(root, "products")

    for product in products:
        product_node = etree.SubElement(
            products_node, "product", id=str(product.product_id)
        )

        name = product.claude_title_pl or product.title
        description = product.claude_description_pl or product.description
        category = product.claude_category or "Inne"
        sale_price = product.compute_sale_price(margin_percent)

        _add_text_element(product_node, "name", name)
        _add_text_element(product_node, "ean", "")
        _add_text_element(product_node, "sku", product.sku or product.product_id)
        _add_text_element(product_node, "category_name", category)
        _add_text_element(product_node, "price", f"{sale_price:.2f}")
        _add_text_element(product_node, "price_wholesale", f"{product.price:.2f}")
        _add_text_element(product_node, "stock", str(product.stock))
        _add_text_element(product_node, "weight", "0")
        _add_text_element(product_node, "description", description)

        images_node = etree.SubElement(product_node, "images")
        for image_url in product.images:
            _add_text_element(images_node, "image", image_url)

        attributes_node = etree.SubElement(product_node, "attributes")
        _add_attribute(
            attributes_node,
            "Sprzedawca AliExpress",
            product.seller_id or "unknown",
        )
        _add_attribute(
            attributes_node,
            "Czas dostawy",
            f"{product.estimated_delivery_days} dni",
        )
        _add_attribute(
            attributes_node,
            "Magazyn",
            product.ship_from_country or "EU",
        )
        _add_attribute(
            attributes_node,
            "Ocena potencjalu",
            f"{product.claude_potential_score}/10",
        )

    xml_bytes: bytes = etree.tostring(
        root,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
    )
    return xml_bytes


def validate_xml(xml_bytes: bytes) -> None:
    """
    Waliduje poprawnosc skladniowa XML przez ponowne parsowanie.

    Raises:
        etree.XMLSyntaxError: Gdy XML jest niepoprawny.
    """
    parser = etree.XMLParser(encoding="utf-8")
    etree.fromstring(xml_bytes, parser=parser)


def write_xml(
    products: List[Product],
    output_dir: Path,
    margin_percent: float,
    logger: Logger,
) -> Path:
    """
    Generuje, waliduje i zapisuje plik XML z produktami.

    Args:
        products: Zaakceptowane produkty.
        output_dir: Katalog docelowy dla pliku.
        margin_percent: Marza do ceny sprzedazy.
        logger: Instancja loggera.

    Returns:
        Sciezka do zapisanego pliku XML.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    xml_bytes = build_xml(products, margin_percent)
    validate_xml(xml_bytes)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    output_path = output_dir / f"products_{timestamp}.xml"
    output_path.write_bytes(xml_bytes)

    logger.ok(f"Wygenerowano XML: {output_path}")
    return output_path
