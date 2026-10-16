# =============================================================================
# management/db_vorfall/db_vorfall_melder.py
# IT-Forensisches Ermittlungswerkzeug — Register "Datenbank-Vorfaelle" (Build 777)
# =============================================================================
# Zweck:
#   Die EINE Stelle, an der ein Erkennender (ab Build 778 die Startpruefung
#   der evidence_<uid>.db im Webserver) einen Vorfall meldet. Der Melder
#   entscheidet, wohin die Meldung kommt:
#
#     1. ins Register (coordinator.db, DbVorfallRepo.erfassen, mit Beleg)
#     2. scheitert das: in den Puffer (DbVorfallPuffer), Nachtrag spaeter
#     3. scheitert auch das: VOLLSTAENDIG ins Protokoll (Stufe CRITICAL)
#
#   In JEDEM Fall steht die Meldung zusaetzlich im Protokoll (Stufe WARNING
#   bzw. ERROR), damit der Vorfall auch dann nachvollziehbar ist, wenn das
#   Register spaeter verloren ginge.
#
# ── WARUM HIER PAUSCHAL ABGEFANGEN WIRD ─────────────────────────────────────
#
#   Lehre aus Build 769: 'except Exception' verschluckte dort einen
#   Programmierfehler. Hier ist der Zweck umgekehrt: eine Meldung darf NIE
#   verloren gehen. Jeder Fehler beim Eintragen fuehrt deshalb in den Puffer —
#   mit Traceback im Protokoll (logger.exception), also laut. Ein
#   Programmierfehler im Schreibweg wird so sichtbar UND der Vorfall bleibt
#   erhalten. Eine UNZULAESSIGE Meldung (DbVorfallMeldung.pruefen) wird
#   dagegen VOR jedem Versuch geworfen: sie waere auch im Puffer unzulaessig.
#
# ── coordinator.db WIRD NIE ANGELEGT ────────────────────────────────────────
#
#   Geoeffnet wird mit mode=rw. Fehlt die Datei (Netzlaufwerk nicht
#   verbunden), entsteht KEINE leere coordinator.db am falschen Ort, sondern
#   ein Fehler — und die Meldung geht in den Puffer.
#
# Version: v0.8.777 · Build: 777 · 2026-10-14
# =============================================================================

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from management.db_vorfall.db_vorfall_meldung import DbVorfallMeldung
from management.db_vorfall.db_vorfall_puffer import DbVorfallPuffer
from management.db_vorfall.melde_ergebnis import (
    EINGETRAGEN, GEPUFFERT, NUR_PROTOKOLL, MeldeErgebnis,
)

logger = logging.getLogger(__name__)


class DbVorfallMelder:
    """Melden ins Register, sonst in den Puffer; Nachtrag des Puffers."""

    def __init__(self, coordinator_pfad: Optional[str],
                 puffer: Optional[DbVorfallPuffer], *,
                 timeout: float = 5.0) -> None:
        self._pfad = str(coordinator_pfad) if coordinator_pfad else None
        self._puffer = puffer
        self._timeout = float(timeout)

    # ------------------------------------------------------------ intern ---
    def _verbinden(self) -> sqlite3.Connection:
        """Schreibverbindung auf coordinator.db; legt die Datei NIE an."""
        from db.journal_policy import apply_journal_mode
        if not self._pfad:
            raise RuntimeError("Kein coordinator.db-Pfad bekannt.")
        uri = "file:" + self._pfad.replace("?", "%3f") + "?mode=rw"
        con = sqlite3.connect(uri, uri=True, timeout=self._timeout,
                              isolation_level=None)
        try:
            apply_journal_mode(con, self._pfad, log=logger)
            con.execute("PRAGMA busy_timeout=%d" % int(self._timeout * 1000))
        except BaseException:
            con.close()
            raise
        return con

    def _repo(self, con: sqlite3.Connection):
        from management.audit.audit_log import AuditLog
        from management.db_vorfall.db_vorfall_repo import DbVorfallRepo
        from management.gateway.coordinator_writer import CoordinatorWriter
        return DbVorfallRepo(con, CoordinatorWriter(con, AuditLog(con)))

    # ------------------------------------------------------------ Melden ---
    def melden(self, meldung: DbVorfallMeldung) -> MeldeErgebnis:
        """Meldet den Vorfall. Wirft nur bei einer unzulaessigen Meldung."""
        meldung.pruefen()
        abbild = json.dumps(meldung.als_dict(), ensure_ascii=False,
                            sort_keys=True)
        logger.warning("DB-Vorfall erkannt: %s", abbild)
        erg = MeldeErgebnis(vorfall_uid=meldung.vorfall_uid, ausgang="")

        try:
            con = self._verbinden()
            try:
                erg.audit_seq = self._repo(con).erfassen(meldung)
            finally:
                con.close()
            erg.ausgang = EINGETRAGEN
            return erg
        except Exception as exc:                            # noqa: BLE001
            # Begruendung des pauschalen Abfangs im Modulkopf.
            logger.exception("DB-Vorfall %s: Eintrag ins Register (%s) "
                             "gescheitert — es wird gepuffert.",
                             meldung.vorfall_uid, self._pfad)
            erg.fehler.append("Register: %s: %s" % (type(exc).__name__, exc))

        if self._puffer is not None:
            try:
                erg.puffer_pfad = self._puffer.ablegen(meldung)
                erg.ausgang = GEPUFFERT
                logger.error("DB-Vorfall %s gepuffert: %s",
                             meldung.vorfall_uid, erg.puffer_pfad)
                return erg
            except Exception as exc:                        # noqa: BLE001
                logger.exception("DB-Vorfall %s: auch der Puffer (%s) ist "
                                 "nicht beschreibbar.", meldung.vorfall_uid,
                                 self._puffer.verzeichnis)
                erg.fehler.append("Puffer: %s: %s" % (type(exc).__name__, exc))
        else:
            erg.fehler.append("Puffer: kein Pufferordner bekannt")

        erg.ausgang = NUR_PROTOKOLL
        logger.critical("DB-Vorfall %s steht NUR im Protokoll. Vollstaendige "
                        "Meldung zum Nachtragen von Hand: %s",
                        meldung.vorfall_uid, abbild)
        return erg

    # --------------------------------------------------------- Nachtragen ---
    def nachtragen(self) -> Dict[str, List[Any]]:
        """
        Traegt alle Meldungen aus dem Puffer nach. Rueckgabe:
          {'nachgetragen': [uid, ...],
           'nicht_entfernt': [pfad, ...],   # eingetragen, Datei blieb liegen
           'fehlgeschlagen': [{'datei', 'fehler'}, ...],
           'unlesbar': [{'datei', 'fehler'}, ...]}
        Eine Datei wird NUR nach erfolgreichem Eintrag geloescht.
        """
        aus: Dict[str, List[Any]] = {"nachgetragen": [], "nicht_entfernt": [],
                                     "fehlgeschlagen": [], "unlesbar": []}
        if self._puffer is None:
            return aus
        eintraege = self._puffer.eintraege()
        if not eintraege:
            return aus
        for pfad, meldung, fehler in eintraege:
            if meldung is None:
                aus["unlesbar"].append({"datei": pfad, "fehler": fehler})
                logger.error("DB-Vorfall-Puffer: %s nicht nachtragbar: %s",
                             pfad, fehler)
        lesbar = [(p, m) for p, m, _f in eintraege if m is not None]
        if not lesbar:
            return aus
        try:
            con = self._verbinden()
        except Exception as exc:                            # noqa: BLE001
            text = "%s: %s" % (type(exc).__name__, exc)
            logger.error("DB-Vorfall-Puffer: coordinator.db (%s) nicht "
                         "erreichbar, %d Meldung(en) bleiben liegen: %s",
                         self._pfad, len(lesbar), text)
            aus["fehlgeschlagen"].extend(
                {"datei": p, "fehler": text} for p, _m in lesbar)
            return aus
        try:
            repo = self._repo(con)
            for pfad, meldung in lesbar:
                try:
                    repo.erfassen(meldung, nachgetragen=True)
                except Exception as exc:                    # noqa: BLE001
                    logger.exception("DB-Vorfall-Puffer: Nachtrag von %s "
                                     "gescheitert; die Datei bleibt liegen.",
                                     pfad)
                    aus["fehlgeschlagen"].append(
                        {"datei": pfad,
                         "fehler": "%s: %s" % (type(exc).__name__, exc)})
                    continue
                aus["nachgetragen"].append(meldung.vorfall_uid)
                try:
                    self._puffer.entfernen(pfad)
                except OSError as exc:
                    # Unschaedlich: der naechste Nachtrag findet den Vorfall
                    # im Register und schreibt nichts (Idempotenz).
                    logger.warning("DB-Vorfall-Puffer: %s eingetragen, aber "
                                   "nicht geloescht: %s", pfad, exc)
                    aus["nicht_entfernt"].append(pfad)
        finally:
            con.close()
        if aus["nachgetragen"]:
            logger.warning("DB-Vorfall-Puffer: %d Meldung(en) nachgetragen: %s",
                           len(aus["nachgetragen"]),
                           ", ".join(aus["nachgetragen"]))
        return aus
