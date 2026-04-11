"""
Analiza produktow przez Claude AI (Anthropic API).

Dla kazdego produktu Claude:
- ocenia jakosc tytulu i opisu
- generuje nowy tytul po polsku (max 70 znakow, SEO pod Allegro)
- generuje nowy opis po polsku (bullet pointy, max 500 znakow)
- sugeruje kategorie Allegro
- ocenia potencjal sprzedazowy 1-10

Wywolywany BATCH — grupy po 10 produktow w jednym prompcie aby zmniejszyc
koszty i opoznienia.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from anthropic import Anthropic, APIError

from aliexpress_client import Product
from logger import Logger


CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
BATCH_SIZE: int = 10
MAX_OUTPUT_TOKENS: int = 4096


SYSTEM_PROMPT: str = """Jestes ekspertem e-commerce specjalizujacym sie w polskim rynku Allegro.

Twoja praca:
- Oceniasz produkty z AliExpress pod katem sprzedazy w Polsce.
- Znasz zasady SEO tytulow na Allegro: najwazniejsze slowa kluczowe na poczatku, konkretne parametry (rozmiar, kolor, moc, pojemnosc), bez "clickbaitu" i znakow specjalnych.
- Piszesz po polsku, konkretnie, bez lania wody. Piszesz tak, jak pisza zwyciezcy rankingow Allegro.
- Opisy formatujesz w bullet pointach zaczynajacych sie od "- " z konkretnymi zaletami, bez marketingowego belkotu.
- Rozumiesz polskie kategorie Allegro (Elektronika, Dom i Ogrod, Motoryzacja, Sport i Turystyka, Uroda, Dla Dzieci, itd.).
- Odrzucasz produkty niskiej jakosci: z chinglish w nazwach, bez konkretnych informacji, z podejrzanie niska cena, z informacjami "no return"/"use at own risk", z mala liczba zdjec (<2).

Format odpowiedzi:
- ZAWSZE zwracasz POPRAWNY JSON — tablice obiektow w kolejnosci dokladnie takiej samej jak w wejsciu.
- Kazdy obiekt musi zawierac pola: index (int), title_pl (string, max 70 znakow), description_pl (string, max 500 znakow), category (string), potential_score (int 1-10), reject_reason (string, pusty jesli brak).
- Jesli produkt jest slaby jakosciowo: potential_score <= 5 i reject_reason z konkretnym uzasadnieniem.
- NIE dodawaj tekstu poza JSON. NIE uzywaj code fence. Pierwszy znak odpowiedzi to '['.
- Maksimum 70 znakow dla title_pl — licz znaki. Maksimum 500 znakow dla description_pl."""


class ClaudeAnalyzer:
    """Wrapper na Anthropic API do analizy produktow w batchach."""

    def __init__(self, api_key: str, logger: Logger) -> None:
        """
        Args:
            api_key: Klucz API Anthropic.
            logger: Instancja loggera.
        """
        self.client = Anthropic(api_key=api_key)
        self.logger = logger

    def analyze_products(self, products: List[Product]) -> List[Product]:
        """
        Analizuje liste produktow w batchach.

        Kazdy produkt otrzymuje wypelnione pola claude_* (title_pl,
        description_pl, category, potential_score, reject_reason).
        Produkty ktorych analiza sie nie powiedzie dostaja potential_score=0
        i reject_reason z informacja o bledzie.

        Returns:
            Ta sama lista produktow z uzupelnionymi polami claude_*.
        """
        if not products:
            return []

        batches = [
            products[i : i + BATCH_SIZE]
            for i in range(0, len(products), BATCH_SIZE)
        ]
        total_batches = len(batches)

        for batch_idx, batch in enumerate(batches, start=1):
            self.logger.ok(
                f"Analiza Claude (batch {batch_idx}/{total_batches}, {len(batch)} produktow)..."
            )
            try:
                results = self._analyze_batch(batch)
            except Exception as e:
                self.logger.fail(
                    f"Batch {batch_idx} nieudany: {e}. "
                    "Oznaczam produkty jako odrzucone."
                )
                for product in batch:
                    product.claude_potential_score = 0
                    product.claude_reject_reason = f"Claude API error: {e}"
                continue

            # Laczenie wynikow z produktami po indeksie
            for product, result in zip(batch, results):
                product.claude_title_pl = result.get("title_pl", "")[:70]
                product.claude_description_pl = result.get("description_pl", "")[:500]
                product.claude_category = result.get("category", "")
                product.claude_potential_score = int(result.get("potential_score", 0) or 0)
                product.claude_reject_reason = result.get("reject_reason", "") or ""

        return products

    def _analyze_batch(self, batch: List[Product]) -> List[Dict[str, Any]]:
        """
        Wysyla pojedynczy batch produktow do Claude i parsuje odpowiedz.

        Returns:
            Lista slownikow z polami: title_pl, description_pl, category,
            potential_score, reject_reason — w tej samej kolejnosci co batch.
        """
        user_message = self._build_batch_prompt(batch)
        try:
            response = self.client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
        except APIError as e:
            raise RuntimeError(f"Anthropic API error: {e}") from e

        # Sklej tresc z wszystkich blokow typu 'text'
        raw_text = ""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                raw_text += block.text

        parsed = self._parse_claude_response(raw_text, expected_count=len(batch))
        return parsed

    def _build_batch_prompt(self, batch: List[Product]) -> str:
        """
        Buduje tresc wiadomosci uzytkownika dla batcha.

        Zawiera liste produktow w formacie JSON (input) oraz instrukcje
        dotyczace formatu wyjscia.
        """
        products_data: List[Dict[str, Any]] = []
        for idx, p in enumerate(batch):
            products_data.append({
                "index": idx,
                "product_id": p.product_id,
                "title_original": p.title,
                "description_original": (p.description[:800] if p.description else ""),
                "price_pln": p.price,
                "stock": p.stock,
                "images_count": len(p.images),
                "ship_from": p.ship_from_country,
                "delivery_days": p.estimated_delivery_days,
                "seller_rating": p.seller_rating,
            })

        input_json = json.dumps(products_data, ensure_ascii=False, indent=2)

        prompt = f"""Przeanalizuj ponizsza liste {len(batch)} produktow z AliExpress.

Dla KAZDEGO produktu:
1. Oceni potencjal sprzedazowy na polskim Allegro (1-10).
2. Napisz nowy tytul po polsku, max 70 znakow, zoptymalizowany pod SEO Allegro (slowa kluczowe, parametry, bez clickbaitu).
3. Napisz nowy opis po polsku, max 500 znakow, w formie bullet pointow zaczynajacych sie od "- ".
4. Przypisz kategorie Allegro (np. "Elektronika > Akcesoria GSM > Uchwyty").
5. Jesli produkt jest slabej jakosci (chinglish, podejrzanie niska cena, "no return", malo zdjec) — oceni <=5 i podaj reject_reason.

Wejscie:
{input_json}

Zwroc TYLKO tablice JSON (bez code fence, bez komentarzy) w tej samej kolejnosci co wejscie. Kazdy obiekt: index, title_pl, description_pl, category, potential_score, reject_reason."""
        return prompt

    def _parse_claude_response(
        self,
        raw_text: str,
        expected_count: int,
    ) -> List[Dict[str, Any]]:
        """
        Parsuje odpowiedz Claude. Obsluguje przypadki:
        - czysty JSON
        - JSON opakowany w ```json ... ```
        - JSON z tekstem przed/po
        - niekompletny JSON (zwraca puste wyniki dla brakujacych pozycji)

        Args:
            raw_text: Surowa tresc odpowiedzi Claude.
            expected_count: Oczekiwana liczba elementow w tablicy.

        Returns:
            Lista slownikow dlugosci expected_count (uzupelniona pustymi
            wynikami jesli Claude zwrocil mniej).
        """
        text = raw_text.strip()

        # Usun ewentualne code fence
        fence_match = re.search(
            r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL
        )
        if fence_match:
            text = fence_match.group(1)
        else:
            # Wytnij od pierwszego '[' do ostatniego ']'
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1 and end > start:
                text = text[start : end + 1]

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            self.logger.warn(f"Claude zwrocil nieprawidlowy JSON: {e}. Proba naprawy...")
            parsed = self._repair_json(text)

        if not isinstance(parsed, list):
            raise ValueError(f"Claude zwrocil nie-liste: {type(parsed).__name__}")

        # Uzupelnij brakujace pozycje pustymi wynikami
        results: List[Dict[str, Any]] = []
        for idx in range(expected_count):
            if idx < len(parsed) and isinstance(parsed[idx], dict):
                item = parsed[idx]
            else:
                item = {
                    "title_pl": "",
                    "description_pl": "",
                    "category": "",
                    "potential_score": 0,
                    "reject_reason": "Claude nie zwrocil wyniku dla tego produktu",
                }
            results.append(item)

        return results

    def _repair_json(self, text: str) -> List[Any]:
        """
        Proba naprawy uciekniętego JSON — usuwa koncowe przecinki,
        zamienia pojedyncze cudzyslowy. Zwraca pusta liste jesli nie da rady.
        """
        repaired = re.sub(r",\s*([\]}])", r"\1", text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            return []


def filter_by_score(
    products: List[Product],
    min_score: int,
    logger: Logger,
) -> List[Product]:
    """
    Filtruje produkty po ocenie potencjalu Claude.

    Loguje akceptacje / odrzucenia i aktualizuje statystyki.

    Args:
        products: Produkty po analizie Claude.
        min_score: Minimalna akceptowalna ocena.
        logger: Instancja loggera.

    Returns:
        Lista zaakceptowanych produktow.
    """
    accepted: List[Product] = []
    for idx, product in enumerate(products, start=1):
        score = product.claude_potential_score
        title = product.claude_title_pl or product.title
        title_short = title[:60]

        if score >= min_score:
            logger.ok(f'Produkt {idx}: "{title_short}" — ocena {score}/10')
            accepted.append(product)
            logger.stats.accepted += 1
        else:
            reason = product.claude_reject_reason or "niska ocena"
            logger.warn(
                f'Produkt {idx}: odrzucony — ocena {score}/10 ({reason})'
            )
            logger.stats.rejected_by_claude += 1

    return accepted
