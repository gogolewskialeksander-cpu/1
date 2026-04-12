"""
Generator XML dla importu produktow do BaseLinker (format Ceneo XML).

<?xml version="1.0" encoding="UTF-8"?>
<offers>
 <o id="ID" url="" price="..." price_netto="..." vat="23" avail="1" weight="0" stock="...">
  <cat><![CDATA[KATEGORIA]]></cat>
  <name><![CDATA[TYTUL]]></name>
  <desc><![CDATA[OPIS]]></desc>
  <imgs>
   <main url="PIERWSZE_ZDJECIE"/>
   <i url="DRUGIE_ZDJECIE"/>
  </imgs>
  <attrs>
   <a name="Kod_producenta"><![CDATA[SKU]]></a>
   ...
  </attrs>
 </o>
</offers>

Wszystkie pola tekstowe opakowane w CDATA. Po zapisie plik jest walidowany
przez ponowne parsowanie lxml.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List

from lxml import etree

from aliexpress_client import Product
from logger import Logger


def _cdata(parent: etree._Element, tag: str, text: str) -> etree._Element:
    """Tworzy element <tag><![CDATA[text]]></tag> i dodaje go do parenta."""
    element = etree.SubElement(parent, tag)
    element.text = etree.CDATA(text if text else "")
    return element


def _attr_cdata(parent: etree._Element, name: str, value: str) -> etree._Element:
    """Tworzy <a name="name"><![CDATA[value]]></a> i dodaje do parenta."""
    element = etree.SubElement(parent, "a", name=name)
    element.text = etree.CDATA(value if value else "")
    return element


def build_xml(
    products: List[Product],
    margin_percent: float,
) -> bytes:
    """
    Buduje strukturę XML zgodna z formatem importu BaseLinker (<offers>).

    Args:
        products: Lista zaakceptowanych produktow.
        margin_percent: Marza do naliczenia przy obliczaniu ceny sprzedazy.

    Returns:
        Bajty XML (UTF-8) z deklaracja XML na poczatku.
    """
    root = etree.Element("offers")

    for product in products:
        name = product.claude_title_pl or product.title
        description = product.claude_description_pl or product.description
        category = product.claude_category or "Inne"
        sale_price = product.compute_sale_price(margin_percent)
        price_netto = round(sale_price / 1.23, 2)
        avail = "1" if product.stock > 0 else "0"
        product_url = f"https://www.aliexpress.com/item/{product.product_id}.html"

        offer = etree.SubElement(
            root,
            "o",
            attrib={
                "id": str(product.product_id),
                "url": product_url,
                "price": f"{sale_price:.2f}",
                "price_netto": f"{price_netto:.2f}",
                "vat": "23",
                "avail": avail,
                "weight": "0",
                "stock": str(product.stock),
            },
        )

        _cdata(offer, "cat", category)
        _cdata(offer, "name", name)
        _cdata(offer, "desc", description)

        imgs = etree.SubElement(offer, "imgs")
        for idx, url in enumerate(product.images):
            if idx == 0:
                etree.SubElement(imgs, "main", url=url)
            else:
                etree.SubElement(imgs, "i", url=url)

        attrs = etree.SubElement(offer, "attrs")
        _attr_cdata(attrs, "Kod_producenta", product.sku or product.product_id)
        _attr_cdata(attrs, "Czas_dostawy", f"{product.estimated_delivery_days} dni")
        _attr_cdata(attrs, "Magazyn", product.ship_from_country or "EU")
        _attr_cdata(attrs, "AliExpress_ID", str(product.product_id))

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
