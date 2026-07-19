# =============================================================================
# management/export/checksum.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem (AP-2B)
# =============================================================================
# Zweck:
#   Pruefsummen fuer das Export-Subsystem. Zwei bewusst getrennte Verfahren,
#   weil zwei verschiedene Fragen beantwortet werden:
#
#   (1) content_sha256_bytes / content_sha256_text — PRUEFSUMME DER EXPORTDATEI.
#       SHA-256 ueber exakt die Bytes, die in die Ausgabedatei geschrieben
#       werden. Ein Pruefer kann die erhaltene Datei mit `sha256sum` selbst
#       nachrechnen und muss denselben Wert erhalten. Das ist die
#       verifizierbarste Form fuer beliebige (auch binaere: xlsx/pdf) Exporte.
#
#   (2) canonical_rows_sha256 — DATENSATZ-KANONIK, deckungsgleich zum
#       Berichts-Siegel. Zeilenformat und repr()-Kodierung sind BEWUSST
#       IDENTISCH zu management/reports/report_sealer.py::_hash bzw.
#       core/startup_checks.py._compute_content_sha256 (Beleg: report_sealer.py
#       Zeile 148 "bewusst identisch"). Damit ist ein daten-basierter
#       Export-Digest mit dem Berichts-Siegel vergleichbar — nuetzlich, wenn ein
#       Export dieselbe Datenlage wie ein gesiegelter Bericht abbilden soll.
#
#   REINE FUNKTIONEN (kein DB-/Datei-/Netzzugriff) -> vollstaendig testbar.
#   UTF-8 wird durchgaengig erhalten (multilinguales Forum, Fallregel 2).
#
# Version: v0.7.440 · Build: 440 · 2026-07-19
# =============================================================================

from __future__ import annotations

import hashlib
import json
from typing import Iterable, Sequence


def content_sha256_bytes(data: bytes) -> str:
    """
    SHA-256-Hexdigest ueber die exakten Ausgabebytes.

    Beleg-Zweck: Der Empfaenger rechnet `sha256sum <datei>` nach und erhaelt
    denselben Wert -> die Datei ist unveraendert. Fuer JEDES Ausgabeformat
    geeignet (HTML/TXT/CSV/XLSX/PDF), da rein byte-basiert.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError(
            "content_sha256_bytes erwartet bytes; fuer Text "
            "content_sha256_text verwenden."
        )
    return hashlib.sha256(bytes(data)).hexdigest()


def content_sha256_text(text: str, *, encoding: str = "utf-8") -> str:
    """
    SHA-256 ueber Text, nach Kodierung (Default UTF-8). Bequemlichkeits-
    Wrapper um content_sha256_bytes; der Empfaenger muss zum Nachrechnen die
    Datei in genau dieser Kodierung vorliegen haben (Exporte sind UTF-8).
    """
    return content_sha256_bytes(text.encode(encoding))


def canonical_rows_sha256(tables: Iterable[tuple]) -> str:
    """
    Datensatz-Kanonik, deckungsgleich zum Berichts-Siegel (report_sealer._hash).

    Eingabe: iterierbare Folge von (table_name, values_sequence). Jede Zeile
    wird als  table + ":" + "|".join(repr(v) for v in values) + "\n"  in UTF-8
    gehasht — Byte fuer Byte identisch zum Sealer-Verfahren. Reihenfolge der
    Zeilen ist SIGNIFIKANT (der Aufrufer stellt eine stabile Ordnung her, so wie
    der Sealer nach id ASC ordnet).

    Belegkette: report_sealer.py:145-161, startup_checks.py:516 ("bewusst
    identisch"). So bleibt ein Export-Datendigest mit dem Siegel vergleichbar.
    """
    sha = hashlib.sha256()
    for table, values in tables:
        if not isinstance(table, str):
            raise TypeError("table-Name muss str sein")
        seq: Sequence = values
        line = table + ":" + "|".join(repr(v) for v in seq) + "\n"
        sha.update(line.encode("utf-8"))
    return sha.hexdigest()


def json_payload_sha256(obj) -> str:
    """
    Pruefsumme ueber eine JSON-serialisierbare Nutzlast (z. B. die in eine
    HTML-Sicht eingebettete Datenliste). Kanonisch: sort_keys=True,
    ensure_ascii=False (UTF-8 erhalten), kompakte Separatoren.

    Deterministisch und vom Empfaenger unabhaengig nachrechenbar: er extrahiert
    dieselbe Nutzlast (z. B. window.__AIW_*__) und bildet json.dumps mit
    denselben Parametern. So traegt jede Sichten-Ausgabe eine pruefbare
    Datensummen-Signatur, ohne von CSS-/JS-Versionen abzuhaengen.
    """
    canonical = json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return content_sha256_text(canonical)
