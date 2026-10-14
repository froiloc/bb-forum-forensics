# =============================================================================
# management/db_vorfall/db_vorfall_meldung.py
# IT-Forensisches Ermittlungswerkzeug — Register "Datenbank-Vorfaelle" (Build 777)
# =============================================================================
# Zweck:
#   Ein Datenbankvorfall, wie ihn der ERKENNENDE beschreibt — unabhaengig
#   davon, ob er sofort ins Register kommt oder erst aus dem Puffer
#   nachgetragen wird. Die Meldung ist die Einheit, die beide Wege teilen:
#   was im Puffer liegt, ist genau diese Meldung als JSON.
#
# ── DIE KENNUNG ENTSTEHT BEI DER ERKENNUNG ──────────────────────────────────
#
#   vorfall_uid (uuid4, 32 Hexzeichen) und erkannt_at werden in neu()
#   vergeben, also im Moment der Erkennung. Ein spaeterer Nachtrag traegt
#   dieselbe Kennung und denselben Zeitpunkt; das Register erkennt daran, dass
#   es denselben Vorfall schon kennt (UNIQUE in M041).
#
# ── DIE ZULAESSIGEN WERTE STEHEN HIER, NICHT IN DER TABELLE ─────────────────
#
#   M041 traegt fuer 'art' und 'ergebnis' bewusst keinen CHECK (Begruendung
#   im Kopf von M041). Die Werte sind deshalb an EINER Stelle festgelegt —
#   hier — und pruefen() wird von jedem Schreibweg aufgerufen (Repo und
#   Puffer). Ein neuer Wert ist eine Zeile hier plus sein Klartext.
#
# ── DER BEFUND MUSS ALS JSON DARSTELLBAR SEIN ───────────────────────────────
#
#   befund_json() serialisiert STRENG (kein default=str). Ein Objekt, das
#   json nicht kennt, ist ein Programmierfehler des Melders und soll bei der
#   Pruefung auffallen — nicht als stillschweigend verkuerzte Zeichenkette im
#   Register landen.
#
# Version: v0.8.777 · Build: 777 · 2026-10-14
#   Build 778: Ergebnis 'journal_zurueckgerollt'.
# =============================================================================

from __future__ import annotations

import json
import re
import socket
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from management.db_vorfall.db_vorfall_fehler import DbVorfallFehler

#: Art der Pruefung, die den Vorfall erkannt hat.
ART_STARTPRUEFUNG_EVIDENCE = "startpruefung_evidence"

#: Alle zulaessigen Arten mit Klartext fuer die Oberflaeche.
ARTEN: Dict[str, str] = {
    ART_STARTPRUEFUNG_EVIDENCE:
        "Startprüfung der Ermittler-Datenbank (evidence_<uid>.db)",
}

#: Ergebnisse (Festlegung Alex 14.10.2026: "Die Ermittler MUESSEN ARBEITEN
#: KOENNEN" — auch eine nicht freigegebene neue Datei wird eingesetzt; der
#: Eintrag hier ist die Benachrichtigung).
ERGEBNIS_FREIGEGEBEN = "repariert_freigegeben"
ERGEBNIS_NICHT_FREIGEGEBEN = "repariert_nicht_freigegeben"
ERGEBNIS_START_VERWEIGERT = "start_verweigert"
#: Build 778: beim Start lag ein '-journal' einer unterbrochenen Transaktion
#: vor (Absturz waehrend eines Schreibvorgangs). Der Zustand DAVOR wurde samt
#: Journal gesichert, SQLite hat zurueckgerollt, die Datei war danach
#: unversehrt. Kein Schaden — aber der letzte, unterbrochene Schreibvorgang
#: ist verloren, und das soll die Leitung wissen.
ERGEBNIS_JOURNAL = "journal_zurueckgerollt"

ERGEBNISSE: Dict[str, str] = {
    ERGEBNIS_FREIGEGEBEN:
        "Repariert und ausgetauscht — freigegeben",
    ERGEBNIS_NICHT_FREIGEGEBEN:
        "Repariert und ausgetauscht — NICHT freigegeben (Ermittlungsergebnisse "
        "betroffen, bitte prüfen)",
    ERGEBNIS_START_VERWEIGERT:
        "Start verweigert — nicht repariert",
    ERGEBNIS_JOURNAL:
        "Unterbrochener Schreibvorgang zurückgerollt — Datei danach unversehrt",
}

_UID = re.compile(r"^[0-9a-f]{32}$")


@dataclass
class DbVorfallMeldung:
    """Ein Vorfall, wie ihn der Erkennende beschreibt."""

    vorfall_uid: str
    erkannt_at: int
    art: str
    ergebnis: str
    datei: str
    befund: Dict[str, Any] = field(default_factory=dict)
    subject_id: Optional[int] = None
    host: Optional[str] = None
    person_id: Optional[int] = None

    # ---------------------------------------------------------- Erzeugen ---
    @classmethod
    def neu(cls, *, art: str, ergebnis: str, datei: str,
            befund: Dict[str, Any], subject_id: Optional[int] = None,
            person_id: Optional[int] = None, host: Optional[str] = None,
            jetzt: Optional[int] = None) -> "DbVorfallMeldung":
        """Eine neue Meldung: Kennung und Erkennungszeitpunkt werden JETZT
        vergeben. host faellt auf den Rechnernamen zurueck."""
        if host is None:
            try:
                host = socket.gethostname()
            except OSError:
                host = None
        return cls(
            vorfall_uid=uuid.uuid4().hex,
            erkannt_at=int(time.time()) if jetzt is None else int(jetzt),
            art=art, ergebnis=ergebnis, datei=str(datei),
            befund=dict(befund),
            subject_id=None if subject_id is None else int(subject_id),
            host=host,
            person_id=None if person_id is None else int(person_id))

    # ------------------------------------------------------------ Pruefen ---
    def befund_json(self) -> str:
        """Der Befund als JSON (streng, sortiert, UTF-8 im Klartext)."""
        return json.dumps(self.befund, ensure_ascii=False, sort_keys=True)

    def pruefen(self) -> None:
        """Wirft DbVorfallFehler, wenn die Meldung so nicht eingetragen
        werden darf. Schreibt nichts."""
        if not isinstance(self.vorfall_uid, str) or not _UID.match(self.vorfall_uid):
            raise DbVorfallFehler(
                "vorfall_uid muss aus 32 Hexzeichen bestehen, erhalten: %r"
                % (self.vorfall_uid,))
        if self.art not in ARTEN:
            raise DbVorfallFehler(
                "Unbekannte Art %r (zulaessig: %s)."
                % (self.art, ", ".join(sorted(ARTEN))))
        if self.ergebnis not in ERGEBNISSE:
            raise DbVorfallFehler(
                "Unbekanntes Ergebnis %r (zulaessig: %s)."
                % (self.ergebnis, ", ".join(sorted(ERGEBNISSE))))
        if not isinstance(self.datei, str) or not self.datei.strip():
            raise DbVorfallFehler("Die betroffene Datei fehlt.")
        if not isinstance(self.erkannt_at, int) or isinstance(self.erkannt_at, bool):
            raise DbVorfallFehler(
                "erkannt_at muss eine ganze Zahl sein, erhalten: %r"
                % (self.erkannt_at,))
        if not isinstance(self.befund, dict):
            raise DbVorfallFehler("Der Befund muss ein Objekt (dict) sein.")
        try:
            self.befund_json()
        except (TypeError, ValueError) as exc:
            raise DbVorfallFehler(
                "Der Befund ist nicht als JSON darstellbar: %s" % exc)

    # -------------------------------------------- Puffer (JSON-Abbild) ---
    def als_dict(self) -> Dict[str, Any]:
        """Vollstaendiges Abbild fuer die Pufferdatei."""
        return {
            "vorfall_uid": self.vorfall_uid, "erkannt_at": self.erkannt_at,
            "art": self.art, "ergebnis": self.ergebnis, "datei": self.datei,
            "befund": self.befund, "subject_id": self.subject_id,
            "host": self.host, "person_id": self.person_id,
        }

    @classmethod
    def aus_dict(cls, d: Dict[str, Any]) -> "DbVorfallMeldung":
        """Gegenstueck zu als_dict(). Fehlende Pflichtfelder -> DbVorfallFehler;
        die inhaltliche Pruefung macht pruefen()."""
        if not isinstance(d, dict):
            raise DbVorfallFehler("Pufferinhalt ist kein Objekt.")
        fehlend = [k for k in ("vorfall_uid", "erkannt_at", "art", "ergebnis",
                               "datei", "befund") if k not in d]
        if fehlend:
            raise DbVorfallFehler(
                "Pufferinhalt unvollstaendig, es fehlt: %s" % ", ".join(fehlend))
        return cls(
            vorfall_uid=d["vorfall_uid"], erkannt_at=d["erkannt_at"],
            art=d["art"], ergebnis=d["ergebnis"], datei=d["datei"],
            befund=d["befund"], subject_id=d.get("subject_id"),
            host=d.get("host"), person_id=d.get("person_id"))
