# =============================================================================
# core/evidence_austausch.py
# IT-Forensisches Ermittlungswerkzeug — Startpruefung der evidence_<uid>.db
# =============================================================================
# Zweck:
#   Setzt die vom EvidenceReparierer erzeugte NEUE Datei an die Stelle der
#   beschaedigten evidence_<uid>.db (Festlegung Alex 14.10.2026: "Auch dann
#   austauschen ... Die Ermittler MUESSEN ARBEITEN KOENNEN" — also auch bei
#   'nicht_freigegeben').
#
# ── WO DAS ORIGINAL BLEIBT ──────────────────────────────────────────────────
#
#   Festlegung: das Original gehoert in den Ordner fuer beschaedigte Dateien,
#   nicht nach data/evidence. Es LIEGT dort bereits: der EvidenceReparierer hat
#   es vor jeder Reparatur nach <ziel>/<stamm>_defekt_<ts>.db gesichert und
#   die Sicherung per SHA-256 bestaetigt (DefektSicherung, Build 776). Der
#   Austausch prueft deshalb UNMITTELBAR davor, dass das Original noch
#   byte-gleich mit dieser Sicherung ist — und ersetzt es erst dann. Eine
#   zweite Kopie desselben Inhalts entsteht so nicht (Festlegung
#   'keine zweite Kopie bei identischer SHA-256', Build 776).
#
# ── BEGLEITDATEIEN ──────────────────────────────────────────────────────────
#
#   Ein '-journal' neben der NEUEN Datei wuerde von SQLite beim naechsten
#   Oeffnen als heisses Journal auf die neue Datei angewandt — und sie
#   zerstoeren. Vorhandene Begleitdateien (-journal, -wal, -shm) werden
#   deshalb in den Zielordner VERSCHOBEN (<stamm>_ersetzt_<ts>.db<endung>),
#   nachdem ihre SHA-256 mit der mitgesicherten Fassung verglichen wurde.
#   Geloescht wird nichts.
#
# ── REIHENFOLGE, DAMIT EIN ABBRUCH NICHTS ZERSTOERT ─────────────────────────
#
#   1. Original == Sicherung? (sonst Abbruch, nichts veraendert)
#   2. neue Datei als <original>.aiw_neu.tmp neben das Original kopieren,
#      fsync, SHA-256 pruefen (sonst Abbruch, .tmp entfernt)
#   3. Begleitdateien verschieben
#   4. os.replace(.tmp, original) — atomar. Unter Windows scheitert es, wenn
#      ein anderer Prozess die Datei offen hat; dann werden die
#      Begleitdateien ZURUECKverschoben und abgebrochen.
#   5. SHA-256 der eingesetzten Datei == neue Datei
#
# Version: v0.8.778 · Build: 778 · 2026-10-14
# =============================================================================

from __future__ import annotations

import os
import shutil
from typing import Any, Dict, List, Tuple

from core.austausch_fehler import AustauschFehler
from core.logger import get_logger
from db.reparatur.hilfen import BEGLEIT, sha256

logger = get_logger(__name__)


class EvidenceAustausch:
    """Neue Datei an die Stelle des Originals setzen — geprueft, umkehrbar."""

    TMP_ENDUNG = ".aiw_neu.tmp"

    def __init__(self, original: str, ziel: str, zeitstempel: str) -> None:
        self._original = os.path.abspath(original)
        self._ziel = os.path.abspath(ziel)
        self._ts = zeitstempel

    def ausfuehren(self, erg: Any) -> Dict[str, Any]:
        """erg: ReparaturErgebnis mit neue_datei_gut. Rueckgabe: Angaben fuer
        den Befund. Wirft AustauschFehler."""
        original = self._original
        sich = erg.sicherung
        if not erg.neue_datei_gut or not erg.neu or sich is None:
            raise AustauschFehler(
                "Keine gepruefte neue Datei vorhanden (Status %s) — nichts "
                "ausgetauscht." % erg.status)

        # 1. Original unveraendert seit der Sicherung?
        sha_jetzt = sha256(original)
        if sha_jetzt != sich.sha256:
            raise AustauschFehler(
                "Das Original hat sich seit der Sicherung veraendert (SHA-256 "
                "jetzt %s, gesichert %s). Vermutlich schreibt ein anderer "
                "Prozess. Nichts ausgetauscht." % (sha_jetzt, sich.sha256))

        stamm = os.path.splitext(os.path.basename(original))[0]
        tmp = original + self.TMP_ENDUNG
        verschoben: List[Tuple[str, str]] = []
        try:
            # 2. neue Datei neben das Original (Build 778, Befund der
            #    Durchsicht: INNERHALB des Rueckwegs — eine volle Platte
            #    hinterliesse sonst eine halbe .tmp in data/evidence).
            shutil.copyfile(erg.neu, tmp)
            with open(tmp, "rb+") as fh:
                os.fsync(fh.fileno())
            sha_tmp = sha256(tmp)
            if sha_tmp != erg.neu_sha256:
                raise AustauschFehler(
                    "Die Kopie der neuen Datei weicht ab (SHA-256 %s statt %s). "
                    "Nichts ausgetauscht." % (sha_tmp, erg.neu_sha256))
            # 3./4. Begleitdateien weg, dann ersetzen
            for endung in BEGLEIT:
                quelle = original + endung
                if not os.path.exists(quelle):
                    continue
                sha_b = sha256(quelle)
                if sich.begleit.get(endung) != sha_b:
                    raise AustauschFehler(
                        "Begleitdatei %s weicht von der mitgesicherten Fassung "
                        "ab (SHA-256 %s, gesichert %s)."
                        % (quelle, sha_b, sich.begleit.get(endung)))
                ziel_b = os.path.join(self._ziel, "%s_ersetzt_%s.db%s"
                                      % (stamm, self._ts, endung))
                shutil.move(quelle, ziel_b)
                verschoben.append((quelle, ziel_b))
            os.replace(tmp, original)
        except Exception as exc:
            # Rueckweg: jeder Schritt einzeln, keiner verdeckt den Grund.
            for quelle, ziel_b in reversed(verschoben):
                try:
                    shutil.move(ziel_b, quelle)
                except OSError as exc2:            # Grundregel 1: laut
                    logger.error("Austausch: Begleitdatei %s konnte nicht "
                                 "zurueckverschoben werden (%s) — sie liegt "
                                 "unter %s.", quelle, exc2, ziel_b)
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError as exc3:
                logger.error("Austausch: %s konnte nicht entfernt werden (%s) "
                             "— bitte von Hand loeschen; sie ist NICHT die "
                             "Arbeitsdatei.", tmp, exc3)
            if isinstance(exc, AustauschFehler):
                raise
            raise AustauschFehler(
                "Das Original konnte nicht ersetzt werden (%s: %s). Haeufigste "
                "Ursache: ein anderes Programm hat die Datei geoeffnet. Das "
                "Original ist unveraendert." % (type(exc).__name__, exc)) from exc

        # 5. Kontrolle
        sha_nach = sha256(original)
        if sha_nach != erg.neu_sha256:
            raise AustauschFehler(
                "Nach dem Austausch weicht die eingesetzte Datei ab (SHA-256 %s "
                "statt %s). Das Original WAR bereits ersetzt; es liegt "
                "unveraendert unter %s." % (sha_nach, erg.neu_sha256, sich.pfad),
                ersetzt=True)
        logger.warning("Austausch: %s ersetzt (vorher %s, jetzt %s); Original "
                       "gesichert unter %s.", original, sha_jetzt, sha_nach,
                       sich.pfad)
        return {"original_sha256": sha_jetzt, "eingesetzt_sha256": sha_nach,
                "original_gesichert_unter": sich.pfad,
                "begleit_verschoben": [b for _q, b in verschoben]}
