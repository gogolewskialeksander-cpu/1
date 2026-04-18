#!/usr/bin/env python3
"""
Glowny skrypt pipeline'u dropshipping Etap 1.

Uruchomienie:
    python main.py                 # pelny tryb produkcyjny
    python main.py --test          # tryb testowy (mock AliExpress, bez BL)
    python main.py --limit 50      # pobierz max 50 produktow
    python main.py --country PL    # tylko polskie magazyny

Pipeline:
    1. Konfiguracja i inicjalizacja loggera.
    2. Pobranie produktow (AliExpress API lub mock).
    3. Filtrowanie: magazyn EU, czas dostawy, stock, ocena sprzedawcy.
    4. Analiza Claude (batch 10 produktow).
    5. Filtrowanie po ocenie potencjalu.
    6. Generowanie XML dla BaseLinker.
    7. Wyslanie do BaseLinker (pominiete w trybie testowym).
    8. Podsumowanie statystyk.

Obsluguje SIGINT (Ctrl+C) — zapisuje postep przed wyjsciem.
"""
from __future__ import annotations

import argparse
import signal
import sys
from types import FrameType
from typing import List, Optional

from aliexpress_client import (
    AliExpressClient,
    Product,
    get_mock_products,
)
from baselinker_client import BaseLinkerClient
from claude_analyzer import ClaudeAnalyzer, filter_by_score
from config import (
    FAILED_PRODUCTS_PATH,
    LOGS_DIR,
    OUTPUT_DIR,
    Config,
    ConfigError,
    load_config,
)
from logger import Logger
from xml_generator import write_xml


# Globalny logger — ustawiany w main() aby handler SIGINT mial do niego dostep.
_GLOBAL_LOGGER: Optional[Logger] = None
_INTERRUPTED: bool = False


def _sigint_handler(signum: int, frame: Optional[FrameType]) -> None:
    """Handler SIGINT — loguje przerwanie i ustawia flage."""
    global _INTERRUPTED
    _INTERRUPTED = True
    if _GLOBAL_LOGGER is not None:
        _GLOBAL_LOGGER.warn("Przerwane przez uzytkownika (Ctrl+C). Zapisuje postep...")
    else:
        print("\n[WARN] Przerwane przez uzytkownika (Ctrl+C).", flush=True)


def filter_eu_warehouses(
    products: List[Product],
    allowed_countries: List[str],
    logger: Logger,
) -> List[Product]:
    """
    Filtruje produkty pozostawiajac tylko te z dozwolonych krajow wysylki.

    Args:
        products: Lista produktow do przefiltrowania.
        allowed_countries: Lista kodow krajow (np. ['PL', 'DE']).
        logger: Instancja loggera.
    """
    allowed_set = {c.upper() for c in allowed_countries}
    kept: List[Product] = []
    for product in products:
        if product.ship_from_country.upper() in allowed_set:
            kept.append(product)
        else:
            logger.stats.filtered_out_eu += 1
    logger.ok(
        f"Filtrowanie EU magazynow... {len(kept)}/{len(products)} przeszlo"
    )
    return kept


def filter_delivery_time(
    products: List[Product],
    max_days: int,
    logger: Logger,
) -> List[Product]:
    """Odrzuca produkty z czasem dostawy powyzej max_days."""
    kept: List[Product] = []
    for product in products:
        if product.estimated_delivery_days <= max_days:
            kept.append(product)
        else:
            logger.stats.filtered_out_delivery += 1
    if len(kept) < len(products):
        logger.ok(
            f"Filtrowanie czasu dostawy (max {max_days} dni)... "
            f"{len(kept)}/{len(products)} przeszlo"
        )
    return kept


def filter_stock_and_rating(
    products: List[Product],
    min_stock: int,
    min_rating: float,
    logger: Logger,
) -> List[Product]:
    """Odrzuca produkty z niskim stockiem lub niska ocena sprzedawcy."""
    kept: List[Product] = []
    for product in products:
        if product.stock < min_stock:
            logger.stats.filtered_out_stock += 1
            continue
        # Ocena sprzedawcy: akceptujemy rowniez 0 jesli brak danych (w trybie testowym)
        if product.seller_rating and product.seller_rating < min_rating:
            logger.stats.filtered_out_stock += 1
            continue
        kept.append(product)
    if len(kept) < len(products):
        logger.ok(
            f"Filtrowanie stock/rating... {len(kept)}/{len(products)} przeszlo"
        )
    return kept


def parse_args() -> argparse.Namespace:
    """Parsuje argumenty CLI."""
    parser = argparse.ArgumentParser(
        description="Etap 1: pobieranie AliExpress -> Claude -> XML -> BaseLinker",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Tryb testowy z mock danymi (bez wysylki do BaseLinker)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Docelowa liczba ZAAKCEPTOWANYCH produktow (nadpisuje MAX_PRODUCTS_PER_RUN)",
    )
    parser.add_argument(
        "--fetch-batch",
        type=int,
        default=100,
        dest="fetch_batch",
        help="Ile produktow pobierac z AliExpress na runde (domyslnie 100)",
    )
    parser.add_argument(
        "--baselinker",
        action="store_true",
        help="Włącz wysyłkę do BaseLinker (domyślnie wyłączona)",
    )
    parser.add_argument(
        "--country",
        type=str,
        default=None,
        help="Ogranicz do jednego kraju wysylki (np. PL)",
    )
    return parser.parse_args()


def run_pipeline(config: Config, args: argparse.Namespace, logger: Logger) -> int:
    """
    Uruchamia caly pipeline Etapu 1.

    Returns:
        Kod wyjscia (0 = sukces, inne = blad).
    """
    # Aplikacja parametrow CLI na config
    target_accepted = args.limit if args.limit is not None else config.max_products_per_run
    fetch_batch = args.fetch_batch
    if args.country:
        config.ship_from_countries = [args.country.upper()]

    logger.ok("Konfiguracja zaladowana")

    # ===== TRYB TESTOWY =====
    if config.test_mode:
        logger.ok("Tryb testowy — uzywam mock danych")
        products = get_mock_products()
        logger.ok(f"Zaladowano {len(products)} produktow testowych")
        logger.stats.fetched_from_aliexpress = len(products)

        products = filter_eu_warehouses(products, config.ship_from_countries, logger)
        products = filter_delivery_time(products, config.max_delivery_days, logger)
        products = filter_stock_and_rating(
            products, config.min_stock, config.min_seller_rating, logger
        )

        if not products:
            logger.warn("Po filtrowaniu nie pozostal zaden produkt.")
            logger.print_summary()
            return 0

        analyzer = ClaudeAnalyzer(api_key=config.anthropic_api_key, logger=logger)
        products = analyzer.analyze_products(products)
        accepted = filter_by_score(products, config.min_potential_score, logger)

        if not accepted:
            logger.warn("Claude odrzucil wszystkie produkty.")
            logger.print_summary()
            return 0

        try:
            xml_path = write_xml(
                products=accepted,
                output_dir=OUTPUT_DIR,
                margin_percent=config.margin_target_percent,
                logger=logger,
            )
        except Exception as e:
            logger.fail(f"Nie udalo sie wygenerowac XML: {e}")
            logger.print_summary()
            return 2

        logger.ok(f"GOTOWE: {len(accepted)} produktow gotowych do importu")
        logger.ok(f"Plik XML: {xml_path}")
        logger.print_summary()
        return 0

    # ===== TRYB PRODUKCYJNY: PETLA DO TARGET =====
    ae_client = AliExpressClient(
        app_key=config.aliexpress_app_key,
        app_secret=config.aliexpress_app_secret,
        access_token=config.aliexpress_access_token,
        logger=logger,
    )
    analyzer = ClaudeAnalyzer(api_key=config.anthropic_api_key, logger=logger)

    all_accepted: List[Product] = []
    all_seen_ids: set = set()
    round_num = 0
    no_new_rounds = 0
    MAX_EMPTY_ROUNDS = 3

    while len(all_accepted) < target_accepted:
        if _INTERRUPTED:
            return 130

        round_num += 1
        logger.ok(
            f"Runda {round_num}: pobieranie {fetch_batch} produktow "
            f"(zaakceptowane: {len(all_accepted)}/{target_accepted})"
        )

        products = ae_client.fetch_products(
            ship_from_countries=config.ship_from_countries,
            limit=fetch_batch,
            exclude_ids=all_seen_ids,
        )

        if not products:
            no_new_rounds += 1
            logger.warn(
                f"Runda {round_num}: brak nowych produktow "
                f"({no_new_rounds}/{MAX_EMPTY_ROUNDS} pustych rund)"
            )
            if no_new_rounds >= MAX_EMPTY_ROUNDS:
                logger.warn("Wyczerpano zrodla produktow. Przerywam petle.")
                break
            continue

        no_new_rounds = 0
        all_seen_ids.update(p.product_id for p in products)
        logger.stats.fetched_from_aliexpress += len(products)

        # Filtrowanie
        products = filter_eu_warehouses(products, config.ship_from_countries, logger)
        products = filter_delivery_time(products, config.max_delivery_days, logger)
        products = filter_stock_and_rating(
            products, config.min_stock, config.min_seller_rating, logger
        )

        if not products:
            logger.warn(f"Runda {round_num}: wszystkie produkty odfiltrowane.")
            continue

        if _INTERRUPTED:
            return 130

        # Analiza Claude
        products = analyzer.analyze_products(products)

        if _INTERRUPTED:
            return 130

        new_accepted = filter_by_score(products, config.min_potential_score, logger)
        all_accepted.extend(new_accepted)
        logger.ok(
            f"Runda {round_num}: +{len(new_accepted)} zaakceptowanych "
            f"(lacznie {len(all_accepted)}/{target_accepted})"
        )

    # Przytnij do dokladnego targetu
    accepted = all_accepted[:target_accepted]

    if not accepted:
        logger.warn("Nie zaakceptowano zadnego produktu.")
        logger.print_summary()
        return 0

    # ===== GENEROWANIE XML =====
    try:
        xml_path = write_xml(
            products=accepted,
            output_dir=OUTPUT_DIR,
            margin_percent=config.margin_target_percent,
            logger=logger,
        )
    except Exception as e:
        logger.fail(f"Nie udalo sie wygenerowac XML: {e}")
        logger.print_summary()
        return 2

    # ===== WYSYLKA DO BASELINKER =====
    if not args.baselinker:
        logger.ok("Pominieto wysylke do BaseLinker (dodaj --baselinker zeby wyslac)")
    else:
        bl_client = BaseLinkerClient(
            token=config.baselinker_api_token,
            inventory_id=config.baselinker_inventory_id,
            storage_id=config.baselinker_storage_id,
            margin_percent=config.margin_target_percent,
            logger=logger,
        )
        bl_client.upload_products(accepted, FAILED_PRODUCTS_PATH)

    # ===== PODSUMOWANIE =====
    logger.ok(f"GOTOWE: {len(accepted)} produktow gotowych do importu")
    logger.ok(f"Plik XML: {xml_path}")
    logger.print_summary()
    return 0


def main() -> int:
    """Punkt wejscia. Zwraca kod wyjscia procesu."""
    global _GLOBAL_LOGGER

    args = parse_args()

    try:
        config = load_config(test_mode=args.test)
        config.validate()
    except ConfigError as e:
        print(f"[FAIL] Blad konfiguracji:\n{e}", file=sys.stderr, flush=True)
        return 3

    logger = Logger(logs_dir=LOGS_DIR)
    _GLOBAL_LOGGER = logger
    signal.signal(signal.SIGINT, _sigint_handler)

    try:
        exit_code = run_pipeline(config, args, logger)
    except Exception as e:
        logger.fail(f"Nieoczekiwany blad pipeline'u: {e}")
        logger.print_summary()
        exit_code = 1
    finally:
        logger.close()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
