# =============================================================================
# db/schreibvorgang.py
# IT-Forensisches Ermittlungswerkzeug — Transaktionsschutz (Build 774)
# =============================================================================
# Zweck:
#   Rahmen fuer JEDE Schreibfunktion auf der geteilten Verbindung des
#   Webservers. Er sorgt fuer zwei Dinge:
#
#   1. ROLLBACK BEI JEDEM FEHLER. Scheitert ein Schreibvorgang mit einer
#      Ausnahme, wird die Transaktion zurueckgerollt, BEVOR die Ausnahme
#      weiterlaeuft. Die Ausnahme selbst bleibt unveraendert.
#   2. KEINE VERZAHNUNG. Fuer die gesamte Dauer des Schreibvorgangs wird der
#      Lock der LockingConnection gehalten (falls die Verbindung eine ist).
#      Ein anderer Thread kann seine Anweisungen also nicht zwischen unsere
#      INSERT und unser commit() schieben — und unser rollback() kann keine
#      fremden Anweisungen mit zuruecknehmen.
#
# WARUM (Befund 13./14.10.2026, Fall 2948078):
#   Die geteilte Verbindung laeuft im Legacy-Transaktionsmodus von sqlite3:
#   vor INSERT/UPDATE/DELETE/REPLACE setzt das Modul selbst ein BEGIN ab.
#   Scheitert die Anweisung danach, ist die Anweisung zurueckgenommen, die
#   TRANSAKTION aber bleibt offen (con.in_transaction == True). Ohne
#   rollback() blieb sie es bis zum naechsten commit() irgendeines Threads.
#   Jede Lesung auf einer angebundenen Datei (z. B. cdb = coordinator.db)
#   haelt in dieser offenen Transaktion eine SHARED-Sperre auf DIESER Datei.
#   Ein Schreiber ueber eine andere Verbindung (CoordinatorWriter beim
#   Bildschleier) bekam dann nach 5 s 'database is locked'.
#   Gemessen (AST-Zaehlung Build 773): db/evidence_db.py 38 von 40,
#   db/coordinator_db.py 3 von 3 Schreibfunktionen ohne rollback().
#
# VORBILD:
#   management/gateway/evidence_writer.py, EvidenceWriter.transaction()
#   (Lock fuer die gesamte Dauer + ROLLBACK bei jeder Exception). Dieser
#   Rahmen uebernimmt genau das, laesst aber den Transaktionsmodus der
#   Verbindung unveraendert (kein BEGIN IMMEDIATE, kein isolation_level).
#
# WAS DER RAHMEN NICHT LEISTET:
#   Eine Ausnahme, die die Schreibfunktion SELBST faengt und verschluckt,
#   sieht er nicht. Dort muss die Funktion im Behandler selbst rollback()
#   aufrufen. Das prueft der Waechtertest
#   tests/test_transaktionsschutz_waechter.py (Regel R2).
#
# Version: v0.8.774 · Build: 774 · 2026-10-14
# =============================================================================
from __future__ import annotations

import sqlite3
import threading
from typing import Any, Optional

from core.logger import get_logger

logger = get_logger(__name__)


class Schreibvorgang:
    """
    Kontextmanager um einen Schreibvorgang auf einer sqlite3-Verbindung.

    Verwendung (in einer Schreibfunktion):

        with Schreibvorgang(self._con, "save_annotation"):
            self._con.execute("INSERT ...")
            self._con.commit()

    con          — sqlite3.Connection oder LockingConnection. Bei einer
                   LockingConnection wird deren Lock (con.lock) gehalten.
    bezeichnung  — Name der Schreibfunktion, erscheint im Protokoll.
    """

    def __init__(self, con: Any, bezeichnung: str) -> None:
        self._con = con
        self._bezeichnung = bezeichnung
        self._lock: Optional[Any] = None

    def __enter__(self) -> "Schreibvorgang":
        # Nur die LockingConnection hat ein Attribut 'lock' mit acquire().
        # Auf einer rohen sqlite3.Connection gibt es keins; getattr liefert
        # dann None. (LockingConnection.__getattr__ reicht unbekannte Namen
        # an die rohe Verbindung weiter — 'lock' ist dort aber ein eigenes,
        # internes Attribut und wird nicht weitergereicht.)
        lock = getattr(self._con, "lock", None)
        if lock is not None and hasattr(lock, "acquire"):
            lock.acquire()
            self._lock = lock
        try:
            # Eine schon offene Transaktion, die nicht diesem Thread gehoert,
            # ist ein Leck aus einem anderen Pfad (alle Schreibfunktionen
            # halten den Lock fuer ihre ganze Dauer — waehrend wir ihn haben,
            # kann kein anderer Schreibvorgang mitten in seiner Arbeit sein).
            # Sie wird NICHT zurueckgerollt (sie koennte Daten tragen), aber
            # laut gemeldet: unser commit() wuerde sie mit festschreiben.
            if getattr(self._con, "in_transaction", False):
                besitzer = getattr(self._con, "transaktions_besitzer", None)
                if besitzer is not None and besitzer != threading.get_ident():
                    logger.error(
                        "Schreibvorgang '%s': Auf der Verbindung ist bereits "
                        "eine Transaktion offen, eroeffnet von Thread %s "
                        "(dieser Thread: %s). Sie wird mit diesem Vorgang "
                        "festgeschrieben oder zurueckgerollt.",
                        self._bezeichnung, besitzer, threading.get_ident())
        except Exception:
            # Die Pruefung darf den Schreibvorgang nie verhindern.
            pass
        return self

    def __exit__(self, typ: Any, wert: Any, tb: Any) -> bool:
        try:
            if typ is not None:
                # Offen oder nicht: rollback() wird IMMER versucht (auf einer
                # Verbindung ohne offene Transaktion ist es ein No-op). Die
                # Abfrage dient nur der Meldung — eine Pruefausnahme vor der
                # ersten Anweisung (z. B. 'Titel leer') ist kein Vorfall und
                # soll das Protokoll nicht fuellen.
                try:
                    offen = bool(getattr(self._con, "in_transaction", True))
                except Exception:
                    offen = True
                try:
                    self._con.rollback()
                except sqlite3.Error as exc:
                    # Ein scheiterndes rollback() (z. B. geschlossene
                    # Verbindung) darf die eigentliche Ausnahme nicht
                    # verdecken. Es wird gemeldet, die Ausnahme laeuft weiter.
                    logger.error(
                        "Schreibvorgang '%s': rollback() nach Fehler "
                        "gescheitert: %s: %s",
                        self._bezeichnung, type(exc).__name__, exc)
                if offen:
                    logger.warning(
                        "Schreibvorgang '%s' gescheitert (%s: %s) — offene "
                        "Transaktion zurueckgerollt.",
                        self._bezeichnung, typ.__name__, wert)
                else:
                    logger.debug(
                        "Schreibvorgang '%s' abgebrochen (%s), keine "
                        "Transaktion offen.", self._bezeichnung, typ.__name__)
        finally:
            if self._lock is not None:
                self._lock.release()
                self._lock = None
        return False  # Ausnahme NICHT unterdruecken
