# =============================================================================
# db/reparatur/hilfen.py
# IT-Forensisches Ermittlungswerkzeug — Hilfsfunktionen der Reparatur
# =============================================================================
# Gemeinsame, zustandslose Funktionen und Festlegungen der Reparatur-Bausteine.
# Herkunft: tools/evidence_reparatur.py 1.2 (14.10.2026), unveraendert.
#
# Version: v0.8.776 · Build: 776 · 2026-10-14
# =============================================================================
from __future__ import annotations

import hashlib
from typing import Dict, Tuple

#: Tabellen, deren Zeilen nach dem Einfuegen NIE geaendert oder geloescht
#: werden (gemessen am Code: nur INSERT, kein UPDATE/DELETE —
#: db/evidence_db.py, Stand Build 773). Nur hier darf der Seitenscan Zeilen
#: uebernehmen. Bei allen anderen koennte eine alte Fassung einer spaeter
#: geaenderten Zeile wiederauferstehen — das waere eine Verfaelschung.
ANHAENGETABELLEN = ("viewport_events", "page_visits")

#: Tabellen mit reinem Laufzeitzustand des Berichtseditors (wer gerade
#: bearbeitet). Der Webserver leert sie bei JEDEM Start
#: (EvidenceDb.clear_stale_locks_on_startup). Sie werden deshalb LEER in die
#: neue Datei uebernommen — so, wie sie nach dem naechsten Start ohnehin
#: waeren. Gelesene Zeilen werden gezaehlt.
FLUECHTIG = ("editor_locks", "lock_queue", "lock_takeover_requests")

#: Begleitdateien einer SQLite-Datei (Rollback-Journal; WAL ist im Projekt
#: verboten, wird aber mitgesichert, falls eine vorliegt).
BEGLEIT = ("-journal", "-wal", "-shm")

#: Wie weit eine Zeilennummer aus dem Seitenscan ueber dem hoechsten sonst
#: bekannten Wert liegen darf, um als echt zu gelten. Ein falsch dekodierter
#: Datensatz kann eine beliebig grosse Nummer tragen; die Suche bis dorthin
#: waere sinnlos. Die Grenze ist weit (groesste Tabelle im PROD-Fall
#: 2948078: Zaehler 7762).
PLAUSIBEL_UEBER = 100000


def sha256(pfad) -> str:
    """SHA-256 einer Datei, blockweise gelesen."""
    h = hashlib.sha256()
    with open(pfad, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def q(name: str) -> str:
    """SQL-Bezeichner in doppelten Anfuehrungszeichen."""
    return '"%s"' % name.replace('"', '""')


def zeilen_pruefsumme(zeilen: Dict[int, Tuple]) -> str:
    """SHA-256 ueber alle Zeilen, sortiert nach rowid, in fester Darstellung."""
    h = hashlib.sha256()
    for rowid in sorted(zeilen):
        h.update(repr((rowid,) + tuple(zeilen[rowid])).encode("utf-8"))
    return h.hexdigest()
