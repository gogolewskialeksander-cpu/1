"""
Logger z prefiksami [OK]/[WARN]/[FAIL].

Zapisuje rownoczesnie do konsoli (z kolorami) oraz do pliku
logs/run_YYYY-MM-DD_HH-MM-SS.log. Udostepnia takze prosty licznik statystyk,
ktory mozna wydrukowac na koncu uruchomienia.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, TextIO


# Kolory ANSI dla konsoli — wylaczone automatycznie jesli stdout nie jest TTY.
_COLORS: Dict[str, str] = {
    "OK": "\033[92m",     # zielony
    "WARN": "\033[93m",   # zolty
    "FAIL": "\033[91m",   # czerwony
    "INFO": "\033[96m",   # cyan
    "RESET": "\033[0m",
}


@dataclass
class RunStats:
    """Agregacja statystyk pojedynczego uruchomienia pipeline'u."""

    fetched_from_aliexpress: int = 0
    filtered_out_eu: int = 0
    filtered_out_delivery: int = 0
    filtered_out_stock: int = 0
    rejected_by_claude: int = 0
    accepted: int = 0
    sent_to_baselinker: int = 0
    baselinker_added: int = 0
    baselinker_updated: int = 0
    baselinker_failed: int = 0
    errors: List[str] = field(default_factory=list)


class Logger:
    """
    Prosty logger z kolorami i rownoczesnym zapisem do pliku.

    Uzywany jako singleton przekazywany przez cala aplikacje. Obsluguje
    poziomy OK/WARN/FAIL/INFO oraz zbiera statystyki uruchomienia.
    """

    def __init__(self, logs_dir: Path, use_colors: Optional[bool] = None) -> None:
        """
        Args:
            logs_dir: Katalog do ktorego zapisywane sa pliki logow.
            use_colors: Czy uzywac kolorow ANSI. Domyslnie auto-detect po TTY.
        """
        logs_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.log_file_path: Path = logs_dir / f"run_{timestamp}.log"
        self._file_handle: TextIO = open(self.log_file_path, "w", encoding="utf-8")
        self._use_colors: bool = (
            use_colors if use_colors is not None else sys.stdout.isatty()
        )
        self.stats: RunStats = RunStats()

    def _format(self, level: str, message: str) -> str:
        """Zwraca sformatowana linie logu bez kolorow (do pliku)."""
        ts = datetime.now().strftime("%H:%M:%S")
        return f"{ts} [{level}] {message}"

    def _emit(self, level: str, message: str) -> None:
        """Wypisuje linie logu na konsole oraz do pliku."""
        plain = self._format(level, message)
        if self._use_colors and level in _COLORS:
            colored = f"{_COLORS[level]}{plain}{_COLORS['RESET']}"
            print(colored, flush=True)
        else:
            print(plain, flush=True)
        try:
            self._file_handle.write(plain + "\n")
            self._file_handle.flush()
        except ValueError:
            # Plik zostal juz zamkniety — ignorujemy.
            pass

    def ok(self, message: str) -> None:
        """Loguje udana operacje."""
        self._emit("OK", message)

    def warn(self, message: str) -> None:
        """Loguje ostrzezenie — operacja sie powiodla ale cos wymaga uwagi."""
        self._emit("WARN", message)

    def fail(self, message: str) -> None:
        """Loguje blad — operacja sie nie powiodla."""
        self._emit("FAIL", message)
        self.stats.errors.append(message)

    def info(self, message: str) -> None:
        """Loguje informacje diagnostyczna."""
        self._emit("INFO", message)

    def print_summary(self) -> None:
        """Drukuje podsumowanie statystyk na koncu uruchomienia."""
        s = self.stats
        self.info("===== PODSUMOWANIE URUCHOMIENIA =====")
        self.info(f"Pobrane z AliExpress:      {s.fetched_from_aliexpress}")
        self.info(f"Odrzucone (brak EU):       {s.filtered_out_eu}")
        self.info(f"Odrzucone (czas dostawy):  {s.filtered_out_delivery}")
        self.info(f"Odrzucone (niski stock):   {s.filtered_out_stock}")
        self.info(f"Odrzucone przez Claude:    {s.rejected_by_claude}")
        self.info(f"Zaakceptowane:             {s.accepted}")
        self.info(f"Dodane do BaseLinker:      {s.baselinker_added}")
        self.info(f"Zaktualizowane w BL:       {s.baselinker_updated}")
        self.info(f"Bledy BaseLinker:          {s.baselinker_failed}")
        self.info(f"Laczna liczba bledow:      {len(s.errors)}")
        self.info(f"Plik logu:                 {self.log_file_path}")

    def close(self) -> None:
        """Zamyka uchwyt pliku logu."""
        try:
            self._file_handle.close()
        except Exception:
            pass
