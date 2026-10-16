# =============================================================================
# core/evidence_startpruefung.py
# IT-Forensisches Ermittlungswerkzeug — Startpruefung der evidence_<uid>.db
# =============================================================================
# Zweck:
#   Prueft beim Start des Webservers die Ermittler-Datenbank des Falls
#   (evidence_<uid>.db) und behebt, was behebbar ist — damit die Ermittler
#   arbeiten koennen (Festlegung Alex 14.10.2026: "Was behebbar ist, soll
#   automatisch behoben werden. Es soll ein Eintrag erstellt werden, den lese
#   ich dann spaeter"). Anlass: PROD 13./14.10.2026, evidence_2948078.db war
#   beschaedigt und wurde von Hand neu aufgebaut.
#
# ── ABLAUF ──────────────────────────────────────────────────────────────────
#
#   0. Ausstehende Vorfaelle aus dem Puffer nachtragen (Build 777). Darf den
#      Start nie verhindern.
#   1. PRAGMA integrity_check, NUR LESEND (mode=ro). Gemessen (Build 777):
#      1,3 MB 5,6 ms, 9 MB 53 ms, 86 MB 614 ms.
#        ok              -> fertig, kein Eintrag
#        gesperrt/unklar -> kein Eingriff, Eintrag 'start_verweigert', Start
#                           verweigert (Festlegung: auch eine gesperrte Datei
#                           ist ein Eintrag; 'unklar' z. B. SQLITE_IOERR —
#                           ein Lesefehler ist kein Schaden, s. einordnen())
#        heisses_journal -> 2.
#        defekt          -> 3.
#   2. Unterbrochene Transaktion: Zustand DAVOR samt -journal sichern
#      (DefektSicherung, SHA-256), dann SQLite zurueckrollen lassen (eine
#      schreibfaehige Verbindung, ein lesender Zugriff — dasselbe, was ohne
#      diese Pruefung beim Verbindungsaufbau geschaehe), erneut pruefen.
#      ok -> Eintrag 'journal_zurueckgerollt', Start; sonst weiter wie defekt.
#   3. Schaden: EvidenceReparierer (Sicherung, neue Datei, Protokoll) ->
#      Vormerkung im Puffer -> EvidenceAustausch (AUCH bei
#      'nicht_freigegeben', Festlegung Alex 14.10.2026) -> erneute Pruefung
#      -> Eintrag ins Register (ersetzt die Vormerkung) -> Start im SELBEN
#      Prozess.
#   Scheitert ein Schritt: Eintrag 'start_verweigert', Start verweigert
#   (EvidenceStartpruefungFehler; main.py zeigt die Fehlerseite).
#
# ── SUPPORTMODUS ────────────────────────────────────────────────────────────
#
#   Im Supportmodus gehoert die Datei einer ANDEREN Person, deren Webserver
#   womoeglich gerade laeuft. Hier wird NICHTS gesichert, zurueckgerollt oder
#   ersetzt: Befund -> Eintrag 'start_verweigert' -> Start verweigert. Die
#   Reparatur geschieht beim naechsten Start der Ermittlerin bzw. des
#   Ermittlers selbst.
#
# ── WARUM HIER PAUSCHAL ABGEFANGEN WIRD ─────────────────────────────────────
#
#   Festlegung: "Wenn irgendein Schritt scheitert: Start verweigern, Eintrag
#   anlegen." Ein unerwarteter Fehler (Programmierfehler, volle Platte) in
#   Schritt 2 oder 3 ist genau so ein Schritt. Er wird mit Traceback
#   protokolliert (logger.exception) und wird zum Eintrag 'start_verweigert'
#   — nicht zu einem stummen Absturz eines Prozesses, den das Portal ohne
#   Konsole startet (management/cases/case_launcher.py).
#
# Version: v0.8.778 · Build: 778 · 2026-10-14
# =============================================================================

from __future__ import annotations

import os
import sqlite3
import time
import traceback
from typing import Any, Dict, List, Optional

from core.evidence_austausch import AustauschFehler, EvidenceAustausch
from core.evidence_startpruefung_fehler import EvidenceStartpruefungFehler
from core.integritaets_befund import IntegritaetsBefund
from core.logger import get_logger

logger = get_logger(__name__)

#: Hoechstzahl der Zeilen, die integrity_check liefert und die in den Befund
#: kommen. Das vollstaendige Bild steht im Reparaturprotokoll.
GRENZE = 100

KENNUNG = "Startpruefung evidence (Build 778)"

#: Hilfeabsaetze der Fehlerseite (core/startfehlerseite.py).
HILFE_GESPERRT = [
    "Die Arbeitsdatei dieses Falls ist gerade von einem anderen Programm "
    "geöffnet oder gesperrt — zum Beispiel von einem zweiten Fenster "
    "desselben Falls oder von einer Supportsitzung.",
    "Schließen Sie andere Fenster dieses Falls und öffnen Sie den Fall "
    "danach erneut.",
    "Bleibt die Meldung, wenden Sie sich an die Leitung und nennen Sie den "
    "Fall und die Uhrzeit. An der Datei wurde nichts verändert.",
    "Die Leitung ist über das Register „Datenbank-Vorfälle“ benachrichtigt.",
]
HILFE_UNKLAR = [
    "Die Arbeitsdatei dieses Falls konnte nicht gelesen werden — etwa weil "
    "das Netzlaufwerk kurz nicht erreichbar war. Ob die Datei beschädigt "
    "ist, lässt sich so nicht sagen; deshalb wurde nichts repariert und an "
    "der Datei nichts verändert.",
    "Versuchen Sie es in einigen Minuten erneut. Bleibt die Meldung, wenden "
    "Sie sich an die Leitung und nennen Sie den Fall und die Uhrzeit.",
]
#: Erster Absatz der Fehlerseite bei verweigertem Start nach einem Eingriff —
#: JE NACH ZUSTAND DER DATEI (Befund der unabhaengigen Durchsicht, Build 778:
#: "unveraendert" war in drei Faellen falsch).
HILFE_ZUSTAND = {
    None: "Die Arbeitsdatei dieses Falls ist beschädigt und konnte nicht "
          "automatisch ersetzt werden. Sie ist unverändert; soweit möglich "
          "wurde eine Sicherung angelegt (siehe unten).",
    "zurueckgerollt": "Beim Öffnen lag ein unterbrochener Speichervorgang "
          "vor. Er wurde verworfen (der Zustand davor ist gesichert), die "
          "Datei ist aber trotzdem nicht in Ordnung und konnte nicht ersetzt "
          "werden.",
    "ersetzt": "Die Arbeitsdatei wurde bereits durch eine reparierte Fassung "
          "ersetzt, diese hat aber die abschließende Kontrolle nicht "
          "bestanden. Die ursprüngliche Datei liegt unverändert in der "
          "Sicherung (siehe unten).",
}
HILFE_VERWEIGERT_SCHLUSS = [
    "Damit nichts verloren geht, wird der Fall nicht geöffnet.",
    "Die Leitung ist über das Register „Datenbank-Vorfälle“ benachrichtigt "
    "(oder wird es beim nächsten Start, falls die Verwaltungsdatei gerade "
    "nicht erreichbar war). Bitte arbeiten Sie an diesem Fall erst weiter, "
    "wenn die Leitung sich gemeldet hat.",
]
HILFE_SUPPORT = [
    "Im Supportmodus wird an der Datei einer anderen Person nichts "
    "repariert. Die Reparatur geschieht beim nächsten Start durch die "
    "Ermittlerin bzw. den Ermittler des Falls selbst.",
    "Die Leitung ist über das Register „Datenbank-Vorfälle“ benachrichtigt.",
]


class EvidenceStartpruefung:
    """Pruefen, sichern, reparieren, austauschen, melden."""

    def __init__(self, context: Any, config: Any, *,
                 melder: Any = None, ziel: Optional[str] = None,
                 zeitstempel: Optional[str] = None,
                 timeout: float = 10.0) -> None:
        self._ctx = context
        self._config = config
        self._melder = melder
        self._ziel = ziel
        self._ts = zeitstempel or time.strftime("%Y%m%d_%H%M%S")
        # Wartezeit auf eine Sperre eines anderen Prozesses (Sekunden).
        self._timeout = float(timeout)
        # Puffer des Melders (fuer die Vormerkung vor dem Austausch).
        self._puffer = None
        # Vormerkung vor dem Austausch: (vorfall_uid, erkannt_at, Pufferdatei).
        self._vorgemerkt: Optional[tuple] = None

    # ------------------------------------------------------------ Melder ---
    def _melder_bauen(self) -> Any:
        if self._melder is not None:
            return self._melder
        from management.db_vorfall.db_vorfall_melder import DbVorfallMelder
        from management.db_vorfall.db_vorfall_puffer import DbVorfallPuffer
        puffer = None
        try:
            puffer = DbVorfallPuffer.aus_konfiguration(self._config)
        except Exception as exc:                            # noqa: BLE001
            logger.error("Puffer der Datenbank-Vorfaelle nicht ermittelbar "
                         "(backup.dest_dir?): %s", exc)
        self._puffer = puffer
        self._melder = DbVorfallMelder(
            str(getattr(self._ctx, "coordinator_db", "") or ""), puffer)
        return self._melder

    def puffer_nachtragen(self) -> Optional[Dict[str, List[Any]]]:
        """Schritt 0. Wirft nie (Muster db_startbefund: eine Pruefung, die den
        Start wegen eines EIGENEN Fehlers verhindert, ist schlimmer als keine)."""
        try:
            return self._melder_bauen().nachtragen()
        except Exception:                                   # noqa: BLE001
            logger.exception("Nachtrag ausstehender Datenbank-Vorfaelle "
                             "gescheitert — der Start geht weiter.")
            return None

    # ----------------------------------------------------------- Pruefen ---
    @staticmethod
    def einordnen(exc: BaseException, pfad: str) -> str:
        """
        Ordnet einen SQLite-Fehler beim LESENDEN Pruefen ein. Massgeblich ist
        der SQLite-Fehlername (sqlite_errorname, Python >= 3.11); der
        Meldungstext nur, wo er fehlt.

          SQLITE_READONLY* + vorhandenes -journal  -> heisses_journal
          SQLITE_BUSY*, SQLITE_LOCKED*, SQLITE_CANTOPEN*  -> gesperrt
          SQLITE_CORRUPT*, SQLITE_NOTADB          -> defekt
          alles andere (z. B. SQLITE_IOERR*)      -> unklar

        WARUM 'unklar' (Befund der unabhaengigen Durchsicht, Build 778): ein
        voruebergehender Lesefehler auf dem Netzlaufwerk ist KEIN Schaden.
        Ihn als 'defekt' zu behandeln hiesse, eine gesunde Datei neu
        aufzubauen und auszutauschen. Bei 'unklar' wird nicht eingegriffen.
        """
        name = getattr(exc, "sqlite_errorname", "") or ""
        text = str(exc).lower()
        journal = os.path.exists(pfad + "-journal")
        if name:
            if name.startswith("SQLITE_READONLY") and journal:
                return "heisses_journal"
            if name.startswith(("SQLITE_BUSY", "SQLITE_LOCKED",
                                "SQLITE_CANTOPEN")):
                return "gesperrt"
            if name.startswith(("SQLITE_CORRUPT", "SQLITE_NOTADB")):
                return "defekt"
            return "unklar"
        if "readonly" in text and journal:
            return "heisses_journal"
        if "locked" in text or "busy" in text or "unable to open" in text:
            return "gesperrt"
        if "malformed" in text or "not a database" in text:
            return "defekt"
        return "unklar"

    @staticmethod
    def pruefen(pfad: str, timeout: float = 10.0) -> IntegritaetsBefund:
        """integrity_check NUR LESEND. Schreibt nie."""
        from core.startup_checks import _path_to_sqlite_uri
        from pathlib import Path
        t0 = time.monotonic()
        try:
            con = sqlite3.connect(_path_to_sqlite_uri(Path(pfad), "ro"),
                                  uri=True, timeout=timeout)
            try:
                zeilen = [str(r[0]) for r in con.execute(
                    "PRAGMA integrity_check(%d)" % GRENZE).fetchall()]
            finally:
                con.close()
        except sqlite3.DatabaseError as exc:
            text = str(exc)
            name = getattr(exc, "sqlite_errorname", "") or ""
            dauer = time.monotonic() - t0
            art = EvidenceStartpruefung.einordnen(exc, pfad)
            return IntegritaetsBefund(
                art=art, zeilen=[text], dauer_s=dauer, grenze=GRENZE,
                fehler="%s%s" % (type(exc).__name__,
                                 " (%s)" % name if name else ""))
        dauer = time.monotonic() - t0
        return IntegritaetsBefund(
            art="ok" if zeilen == ["ok"] else "defekt", zeilen=zeilen,
            dauer_s=dauer, grenze=GRENZE)

    # ------------------------------------------------------------ Ablauf ---
    def ausfuehren(self) -> Optional[Any]:
        """
        Gibt None zurueck, wenn die Datei in Ordnung ist, sonst das
        MeldeErgebnis des Registereintrags (Start geht weiter). Wirft
        EvidenceStartpruefungFehler, wenn der Start zu verweigern ist.
        """
        pfad = str(self._ctx.evidence_db)
        self.puffer_nachtragen()
        befund = self.pruefen(pfad, self._timeout)
        logger.info("Startpruefung evidence: %s (%.3f s) — %s",
                    befund.art, befund.dauer_s, pfad)
        if befund.ok:
            return None

        protokoll: Dict[str, Any] = {"kennung": KENNUNG,
                                     "modus": self._ctx.mode,
                                     "erkennung": befund.als_dict()}
        if befund.art in ("gesperrt", "unklar"):
            # Kein Eingriff — aber ein Eintrag (Festlegung: "Wenn irgendein
            # Schritt scheitert, z. B. die Datei von einem anderen Prozess
            # gesperrt ist: Start verweigern, Fehlerseite, Eintrag").
            gesperrt = befund.art == "gesperrt"
            grund = ("Datei gesperrt oder nicht zu oeffnen" if gesperrt
                     else "Datei nicht lesbar, Ursache unklar") + \
                ": %s. An der Datei wurde nichts veraendert." % "; ".join(
                    befund.zeilen)
            erg = self._melden("start_verweigert", pfad,
                               dict(protokoll, grund=grund))
            raise EvidenceStartpruefungFehler(
                "Die Arbeitsdatei des Falls ist %s:\n  %s\n  %s\nAn der Datei "
                "wurde nichts veraendert.\n%s" % (
                    "gesperrt oder nicht zu oeffnen" if gesperrt
                    else "nicht lesbar (Ursache unklar)", pfad,
                    "; ".join(befund.zeilen), erg.klartext()),
                hilfe=HILFE_GESPERRT if gesperrt else HILFE_UNKLAR,
                melde_ergebnis=erg)
        if self._ctx.mode == "support":
            erg = self._melden("start_verweigert", pfad, dict(
                protokoll, grund="Supportmodus: an der Datei einer anderen "
                                 "Person wird nichts repariert."))
            raise EvidenceStartpruefungFehler(
                "Die Arbeitsdatei des Falls ist nicht in Ordnung (%s). Im "
                "Supportmodus wird nichts repariert.\n  %s\n%s"
                % (befund.art, pfad, erg.klartext()),
                hilfe=HILFE_SUPPORT, melde_ergebnis=erg)

        try:
            return self._beheben(pfad, befund, protokoll)
        except EvidenceStartpruefungFehler:
            raise
        except Exception as exc:                            # noqa: BLE001
            # Begruendung des pauschalen Abfangs im Modulkopf.
            logger.exception("Startpruefung evidence: unerwarteter Fehler")
            return self._verweigern(pfad, protokoll, "Unerwarteter Fehler: %s: %s"
                                    % (type(exc).__name__, exc),
                                    traceback.format_exc())

    # ------------------------------------------------------------ intern ---
    def _ziel_ermitteln(self, pfad: str) -> str:
        from db.reparatur.reparatur_ziel import ReparaturZiel
        if self._ziel is not None:
            ziel, herkunft = os.path.abspath(self._ziel), "Aufrufer"
        else:
            ziel, herkunft = ReparaturZiel.aus_konfiguration(self._config)
        ReparaturZiel.pruefen(pfad, ziel, herkunft)
        return ziel

    def _beheben(self, pfad: str, befund: IntegritaetsBefund,
                 protokoll: Dict[str, Any]) -> Any:
        from db.reparatur.reparatur_ziel import ReparaturZielFehler
        try:
            ziel = self._ziel_ermitteln(pfad)
        except ReparaturZielFehler as exc:
            return self._verweigern(pfad, protokoll,
                                    "Ordner fuer beschaedigte Dateien nicht "
                                    "nutzbar: %s" % exc)
        protokoll["ziel"] = ziel

        if befund.art == "heisses_journal":
            nach = self._journal_zurueckrollen(pfad, ziel, protokoll)
            if nach is None:
                return self._verweigern(pfad, protokoll, protokoll["grund_journal"])
            protokoll["nach_zurueckrollen"] = nach.als_dict()
            if nach.ok:
                erg = self._melden("journal_zurueckgerollt", pfad, protokoll)
                logger.warning("Startpruefung evidence: unterbrochene "
                               "Transaktion zurueckgerollt, Datei unversehrt. %s",
                               erg.klartext())
                return erg
            if nach.art != "defekt":
                return self._verweigern(pfad, protokoll,
                                        "Nach dem Zurueckrollen: %s" % nach.art)
        return self._reparieren(pfad, ziel, protokoll)

    def _journal_zurueckrollen(self, pfad: str, ziel: str,
                               protokoll: Dict[str, Any]) -> Optional[IntegritaetsBefund]:
        """Sichert den Zustand vor dem Zurueckrollen und laesst SQLite
        zurueckrollen. None, wenn schon die Sicherung scheitert (Grund in
        protokoll['grund_journal'])."""
        from db.reparatur.defekt_sicherung import DefektSicherung
        from db.reparatur.hilfen import sha256
        # Eigener Name (Befund der unabhaengigen Durchsicht, Build 778): die
        # Sicherung VOR dem Zurueckrollen ist ein anderer Stand als die einer
        # anschliessenden Reparatur und darf von ihr nie ueberdeckt werden.
        stamm = os.path.splitext(os.path.basename(pfad))[0] + "_vor_zurueckrollen"
        sich = DefektSicherung(ziel).sichern(pfad, stamm, self._ts)
        protokoll["sicherung_vor_zurueckrollen"] = {
            "datei": sich.pfad, "sha256": sich.sha256, "begleit": sich.begleit,
            "neu_angelegt": sich.neu_angelegt, "stimmig": sich.stimmig,
            "meldung": sich.meldung}
        if not sich.stimmig:
            protokoll["grund_journal"] = ("Sicherung vor dem Zurueckrollen nicht "
                                          "stimmig: %s" % sich.meldung)
            return None
        try:
            # Eine schreibfaehige Verbindung und ein lesender Zugriff: SQLite
            # spielt dabei das heisse Journal zurueck (sqlite.org/atomiccommit,
            # 'Hot Rollback Journals'). Es wird nichts geschrieben.
            con = sqlite3.connect(pfad, timeout=self._timeout)
            try:
                con.execute("SELECT count(*) FROM sqlite_schema").fetchone()
            finally:
                con.close()
        except sqlite3.DatabaseError as exc:
            protokoll["zurueckrollen_fehler"] = "%s: %s" % (type(exc).__name__, exc)
            logger.error("Startpruefung evidence: Zurueckrollen gescheitert: %s",
                         exc)
        # Hat sich die Datei veraendert? Dann darf keine spaetere Meldung
        # behaupten, sie sei unveraendert.
        try:
            if sha256(pfad) != sich.sha256:
                protokoll["datei_veraendert"] = "zurueckgerollt"
        except OSError as exc:
            protokoll["datei_veraendert"] = "zurueckgerollt"
            logger.error("Startpruefung evidence: SHA-256 nach dem "
                         "Zurueckrollen nicht ermittelbar: %s", exc)
        return self.pruefen(pfad, self._timeout)

    def _reparieren(self, pfad: str, ziel: str, protokoll: Dict[str, Any]) -> Any:
        from db.reparatur.evidence_reparierer import EvidenceReparierer
        erg = EvidenceReparierer(
            pfad, ziel, ausgabe=logger.info, kennung=KENNUNG,
            kopfzeilen=["  Anlass: Startpruefung des Webservers (Modus %s, "
                        "Fall %s)" % (self._ctx.mode, self._ctx.subject_id)],
            zeitstempel=self._ts).ausfuehren()
        protokoll["reparatur"] = {
            "status": erg.status, "neu": erg.neu, "neu_sha256": erg.neu_sha256,
            "protokoll_txt": erg.protokoll_txt,
            "protokoll_json": erg.protokoll_json, "sperren": erg.sperren,
            "verloren": erg.verloren,
            "beschaedigte_tabellen": erg.beschaedigte_tabellen,
            "sicherung": None if erg.sicherung is None else {
                "datei": erg.sicherung.pfad, "sha256": erg.sicherung.sha256,
                "begleit": erg.sicherung.begleit,
                "neu_angelegt": erg.sicherung.neu_angelegt}}
        if not erg.neue_datei_gut:
            return self._verweigern(pfad, protokoll,
                                    "Reparatur ohne brauchbare neue Datei "
                                    "(Status %s)." % erg.status)
        ergebnis = ("repariert_freigegeben" if erg.status == "freigegeben"
                    else "repariert_nicht_freigegeben")
        self._vormerken(ergebnis, pfad, protokoll)
        try:
            protokoll["austausch"] = EvidenceAustausch(
                pfad, ziel, self._ts).ausfuehren(erg)
        except AustauschFehler as exc:
            if exc.ersetzt:
                protokoll["datei_veraendert"] = "ersetzt"
            erg.protokoll_anhaengen("AUSTAUSCH ABGEBROCHEN: %s" % exc)
            return self._verweigern(pfad, protokoll, "Austausch: %s" % exc)
        protokoll["datei_veraendert"] = "ersetzt"
        erg.protokoll_anhaengen("")
        erg.protokoll_anhaengen("AUSTAUSCH durch die Startpruefung (%s): %s "
                                "ersetzt; Original gesichert unter %s."
                                % (KENNUNG, pfad, erg.sicherung.pfad))
        nach = self.pruefen(pfad, self._timeout)
        protokoll["nachpruefung"] = nach.als_dict()
        if not nach.ok:
            return self._verweigern(pfad, protokoll,
                                    "Die eingesetzte Datei besteht die "
                                    "Pruefung nicht (%s)." % nach.art)
        melde = self._melden(ergebnis, pfad, protokoll)
        erg.protokoll_anhaengen("Registereintrag: %s" % melde.klartext())
        logger.warning("Startpruefung evidence: %s — Start geht weiter. %s",
                       ergebnis, melde.klartext())
        return melde

    def _melden(self, ergebnis: str, pfad: str, befund: Dict[str, Any]) -> Any:
        from management.db_vorfall.db_vorfall_meldung import (
            ART_STARTPRUEFUNG_EVIDENCE, DbVorfallMeldung,
        )
        from management.db_vorfall.db_vorfall_fehler import DbVorfallFehler

        def _neu(b: Dict[str, Any]):
            m = DbVorfallMeldung.neu(
                art=ART_STARTPRUEFUNG_EVIDENCE, ergebnis=ergebnis, datei=pfad,
                befund=b, subject_id=getattr(self._ctx, "subject_id", None),
                person_id=getattr(self._ctx, "investigator_id", None))
            if self._vorgemerkt is not None:
                # Dieselbe Kennung wie die Vormerkung: der Puffer haelt je
                # Kennung EINE Datei, die endgueltige Meldung ersetzt sie.
                m.vorfall_uid, m.erkannt_at = self._vorgemerkt[0], self._vorgemerkt[1]
            return m
        meldung = _neu(befund)
        try:
            meldung.pruefen()
        except DbVorfallFehler as exc:
            # Ein Befund, der sich nicht als JSON darstellen laesst, darf den
            # Eintrag nicht verhindern: er geht als Text hinein (vollstaendig,
            # nicht gekuerzt), und der Grund steht dabei.
            logger.error("Startpruefung evidence: Befund nicht darstellbar "
                         "(%s) — er wird als Text eingetragen.", exc)
            meldung = _neu({"befund_als_text": repr(befund),
                            "darstellungsfehler": str(exc)})
        erg = self._melder_bauen().melden(meldung)
        self._vormerkung_aufloesen(erg)
        return erg

    def _meldung_bauen_fuer_vormerkung(self, ergebnis: str, pfad: str,
                                       befund: Dict[str, Any]) -> Any:
        from management.db_vorfall.db_vorfall_meldung import (
            ART_STARTPRUEFUNG_EVIDENCE, DbVorfallMeldung,
        )
        return DbVorfallMeldung.neu(
            art=ART_STARTPRUEFUNG_EVIDENCE, ergebnis=ergebnis, datei=pfad,
            befund=befund, subject_id=getattr(self._ctx, "subject_id", None),
            person_id=getattr(self._ctx, "investigator_id", None))

    def _vormerken(self, ergebnis: str, pfad: str,
                   protokoll: Dict[str, Any]) -> None:
        """
        VOR dem Austausch eine vorlaeufige Meldung in den Puffer legen
        (Befund der unabhaengigen Durchsicht, Build 778): endet der Prozess
        zwischen Austausch und Eintrag, saehe der naechste Start eine
        unversehrte Datei und meldete nichts — der Austausch stuende nur im
        Protokoll. So traegt der naechste Start die Vormerkung nach. Die
        endgueltige Meldung traegt dieselbe Kennung und ersetzt sie.
        Scheitert die Vormerkung, geht es trotzdem weiter (laut protokolliert).
        """
        self._melder_bauen()
        if self._puffer is None:
            logger.warning("Startpruefung evidence: kein Puffer — Austausch "
                           "ohne Vormerkung.")
            return
        try:
            m = self._meldung_bauen_fuer_vormerkung(ergebnis, pfad, dict(
                protokoll, vorlaeufig=(
                    "Austausch eingeleitet, Abschluss nicht bestaetigt: der "
                    "Webserver wurde vermutlich waehrend des Austauschs "
                    "beendet. Ob die Datei ersetzt ist, zeigt der Vergleich "
                    "ihrer SHA-256 mit 'reparatur.neu_sha256'.")))
            self._vorgemerkt = (m.vorfall_uid, m.erkannt_at,
                                self._puffer.ablegen(m))
        except Exception:                                   # noqa: BLE001
            logger.exception("Startpruefung evidence: Vormerkung im Puffer "
                             "gescheitert — es geht ohne weiter.")

    def _vormerkung_aufloesen(self, erg: Any) -> None:
        """Nach der endgueltigen Meldung: ist sie im Register, wird die
        Vormerkung geloescht (im Puffer hat sie die Meldung schon ersetzt)."""
        if self._vorgemerkt is None or self._puffer is None:
            return
        pfad_v = self._vorgemerkt[2]
        if getattr(erg, "eingetragen", False) and pfad_v and os.path.exists(pfad_v):
            try:
                self._puffer.entfernen(pfad_v)
            except Exception as exc:                        # noqa: BLE001
                logger.error("Startpruefung evidence: Vormerkung %s nicht "
                             "geloescht (%s) — sie wird beim naechsten Start "
                             "als Widerspruch gemeldet und bleibt liegen.",
                             pfad_v, exc)

    def _verweigern(self, pfad: str, protokoll: Dict[str, Any], grund: str,
                    spur: Optional[str] = None) -> Any:
        protokoll = dict(protokoll, grund=grund)
        if spur:
            protokoll["traceback"] = spur
        erg = self._melden("start_verweigert", pfad, protokoll)
        hinweise = []
        sich = (protokoll.get("reparatur") or {}).get("sicherung") \
            or protokoll.get("sicherung_vor_zurueckrollen")
        if sich:
            hinweise.append("Sicherung: %s" % sich.get("datei"))
        prot = (protokoll.get("reparatur") or {}).get("protokoll_txt")
        if prot:
            hinweise.append("Reparaturprotokoll: %s" % prot)
        zustand = protokoll.get("datei_veraendert")
        kopf = {
            None: "Die Arbeitsdatei des Falls ist beschaedigt und konnte nicht "
                  "ersetzt werden; sie ist unveraendert.",
            "zurueckgerollt": "Die Arbeitsdatei des Falls ist beschaedigt. Ein "
                  "unterbrochener Speichervorgang wurde zurueckgerollt (der "
                  "Zustand davor ist gesichert); ersetzt werden konnte sie "
                  "nicht.",
            "ersetzt": "Die Arbeitsdatei des Falls wurde durch eine reparierte "
                  "Fassung ersetzt, diese hat die Kontrolle aber nicht "
                  "bestanden. Das Original liegt in der Sicherung.",
        }.get(zustand, "Die Arbeitsdatei des Falls ist beschaedigt.")
        raise EvidenceStartpruefungFehler(
            "%s\n  Datei: %s\n  Grund: %s\n%s%s"
            % (kopf, pfad, grund, "".join("  %s\n" % h for h in hinweise),
               erg.klartext()),
            hilfe=[HILFE_ZUSTAND.get(zustand, HILFE_ZUSTAND[None])]
            + HILFE_VERWEIGERT_SCHLUSS, melde_ergebnis=erg)
