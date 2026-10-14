# =============================================================================
# tests/test_evidence_startpruefung.py
# IT-Forensisches Ermittlungswerkzeug — Startpruefung der evidence_<uid>.db
# =============================================================================
# Prueft core/evidence_startpruefung.py, core/evidence_austausch.py,
# core/startfehlerseite.py und die Anbindung in core/startup_checks.py
# (Build 778) — mit ECHTEM Schema (EvidenceDb) und kuenstlich beschaedigten
# Dateien (tests/_reparatur_testdateien.py), echter coordinator.db ueber die
# volle Migrationskette (tests/test_db_vorfall.baue_coordinator).
#
#   ES01  unversehrt -> nichts geschieht (kein Eintrag, Datei unveraendert,
#         kein Ordner 'defekt')
#   ES02  Schaden nur in einer Anhaengetabelle -> repariert, freigegeben,
#         ausgetauscht; Original byte-gleich in der Sicherung; Eintrag
#   ES03  Schaden in annotations -> NICHT freigegeben, TROTZDEM ausgetauscht
#         (Festlegung Alex 14.10.2026), Eintrag 'repariert_nicht_freigegeben'
#   ES04  heisses Journal -> Zustand davor samt Journal gesichert,
#         zurueckgerollt, Inhalt wie vor der Transaktion, Eintrag
#   ES05  Supportmodus -> nichts gesichert/repariert, Eintrag, Start verweigert
#   ES06  gesperrt -> Start verweigert, Eintrag, Datei unveraendert
#   ES07  Austausch scheitert (Datei von anderem Prozess offen, Windows) ->
#         Begleitdateien zurueck, .tmp weg, Original unveraendert, Eintrag
#         'start_verweigert'
#   ES08  coordinator.db unerreichbar -> gepuffert; der naechste Start traegt
#         nach
#   ES09  Austausch: Original seit der Sicherung veraendert -> Abbruch ohne
#         Aenderung
#   ES10  backup.dest_dir fehlt -> Start verweigert, Eintrag trotzdem
#   ES11  forensic_db keine SQLite-Datei -> verstaendliche Meldung statt
#         Traceback (DatabaseError, alle drei forensic-Pruefungen)
#   ES12  Fehlerseite: maskiert, nennt Hilfe und Benachrichtigung; weicht in
#         den temporaeren Ordner aus
#   ES13  unerwarteter Fehler in der Reparatur -> Eintrag mit Traceback,
#         Start verweigert
#   ES14  StartupChecker: evidence-Pruefung laeuft ZULETZT, Ergebnis in
#         evidence_meldung
#   ES15  besteht die eingesetzte Datei die erneute Pruefung nicht -> Start
#         verweigert, Eintrag
#   ES16  Startfehlerseite.anzeigen oeffnet die Seite als file:-Adresse und
#         wirft nie
#   ES17  main.py: beide Abfangzweige von Schritt 6 zeigen die Fehlerseite
#   --- Befunde der unabhaengigen Durchsicht (Build 778) ---
#   ES06  (geaendert) gesperrte Datei -> Eintrag 'start_verweigert'
#   ES18  Abbruch zwischen Austausch und Eintrag -> Vormerkung im Puffer,
#         der naechste Start traegt nach; ES18b Vormerkung wird ersetzt
#   ES19  heisses Journal UND danach noch defekt -> zwei Sicherungen, keine
#         ueberschrieben, keine fremde -journal-Kopie
#   ES20  Einordnung nach SQLite-Fehlername; ES20b 'unklar' greift nicht ein
#   ES21  Meldung/Hilfe nennen den wirklichen Zustand der Datei
#   ES09  (erweitert) volle Platte beim Kopieren -> keine halbe .tmp
#   ES22  DefektSicherung ueberschreibt nie (_2), dedupliziert weiter
#
# Version: v0.8.778 · Build: 778 · 2026-10-14
# =============================================================================

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))
sys.path.insert(0, str(WURZEL / "tests"))

import _reparatur_testdateien as T                                # noqa: E402
from test_db_vorfall import baue_coordinator                      # noqa: E402
from core.evidence_austausch import AustauschFehler, EvidenceAustausch  # noqa: E402
from core.evidence_startpruefung import EvidenceStartpruefung     # noqa: E402
from core.evidence_startpruefung_fehler import (                  # noqa: E402
    EvidenceStartpruefungFehler)
from core.startfehlerseite import Startfehlerseite                # noqa: E402
from core.startup_checks import StartupChecker, StartupCheckError  # noqa: E402
from db.reparatur.hilfen import sha256                            # noqa: E402
from management.db_vorfall.melde_ergebnis import EINGETRAGEN, GEPUFFERT  # noqa: E402


class Konfig:
    """config.get(key, default) wie ConfigLoader."""

    def __init__(self, werte):
        self._w = dict(werte)

    def get(self, key, default=None):
        return self._w.get(key, default)


class _Welt(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.daten = os.path.join(self.tmp, "data", "evidence")
        os.makedirs(self.daten)
        self.ev = os.path.join(self.daten, "evidence_4711.db")
        self.coord = os.path.join(self.tmp, "coordinator.db")
        baue_coordinator(self.coord)
        self.dest = os.path.join(self.tmp, "sicherung")
        self.defekt = os.path.join(self.dest, "defekt")
        self.cfg = Konfig({"backup.dest_dir": self.dest})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ctx(self, mode="cli", coord=None):
        return SimpleNamespace(evidence_db=Path(self.ev), mode=mode,
                               subject_id=4711, investigator_id=2,
                               coordinator_db=Path(coord or self.coord))

    def pruefung(self, **kw):
        kw.setdefault("timeout", 0.3)
        ctx = kw.pop("ctx", None) or self.ctx()
        cfg = kw.pop("cfg", None) or self.cfg
        kw.setdefault("zeitstempel", "20261014_190000")
        return EvidenceStartpruefung(ctx, cfg, **kw)

    def register(self):
        con = sqlite3.connect(self.coord)
        try:
            return con.execute(
                "SELECT ergebnis, befund_json, subject_id, person_id, status, "
                "nachgetragen FROM db_vorfall ORDER BY id").fetchall()
        finally:
            con.close()


class AblaufTests(_Welt):

    def test_es01_unversehrt(self):
        T.bau_evidence(self.ev)
        vorher = sha256(self.ev)
        self.assertIsNone(self.pruefung().ausfuehren())
        self.assertEqual(sha256(self.ev), vorher)
        self.assertEqual(self.register(), [])
        self.assertFalse(os.path.exists(self.defekt))

    def test_es02_anhaengetabelle_freigegeben(self):
        T.bau_evidence(self.ev)
        vorlage = T.inhalt(self.ev)
        T.abschneiden(self.ev, "viewport_events")
        defekt_sha = sha256(self.ev)
        self.assertEqual(EvidenceStartpruefung.pruefen(self.ev).art, "defekt")

        erg = self.pruefung().ausfuehren()
        self.assertEqual(erg.ausgang, EINGETRAGEN)
        self.assertTrue(EvidenceStartpruefung.pruefen(self.ev).ok)
        self.assertEqual(T.inhalt(self.ev), vorlage)
        sicherung = os.path.join(self.defekt,
                                 "evidence_4711_defekt_20261014_190000.db")
        self.assertEqual(sha256(sicherung), defekt_sha)
        self.assertEqual([f for f in os.listdir(self.daten)], ["evidence_4711.db"])
        (ergebnis, befund, sid, pid, status, nach), = self.register()
        self.assertEqual((ergebnis, sid, pid, status, nach),
                         ("repariert_freigegeben", 4711, 2, "offen", 0))
        b = json.loads(befund)
        self.assertEqual(b["erkennung"]["art"], "defekt")
        self.assertEqual(b["reparatur"]["status"], "freigegeben")
        self.assertEqual(b["austausch"]["original_sha256"], defekt_sha)
        self.assertEqual(b["austausch"]["eingesetzt_sha256"], sha256(self.ev))
        self.assertEqual(b["nachpruefung"]["art"], "ok")
        with open(b["reparatur"]["protokoll_txt"], encoding="utf-8") as fh:
            prot = fh.read()
        self.assertIn("AUSTAUSCH durch die Startpruefung", prot)
        self.assertIn("Registereintrag:", prot)

    def test_es03_annotations_nicht_freigegeben_trotzdem_getauscht(self):
        T.bau_evidence(self.ev)
        T.abschneiden(self.ev, "annotations", zaehler_senken=True)
        defekt_sha = sha256(self.ev)
        erg = self.pruefung().ausfuehren()           # wirft NICHT
        self.assertEqual(erg.ausgang, EINGETRAGEN)
        self.assertNotEqual(sha256(self.ev), defekt_sha)
        self.assertTrue(EvidenceStartpruefung.pruefen(self.ev).ok)
        (ergebnis, befund, *_r), = self.register()
        self.assertEqual(ergebnis, "repariert_nicht_freigegeben")
        b = json.loads(befund)
        self.assertIn("annotations", b["reparatur"]["sperren"])
        self.assertGreater(b["reparatur"]["verloren"].get("annotations", 0), 0)

    def test_es04_heisses_journal(self):
        quelle = os.path.join(self.tmp, "quelle.db")
        T.bau_evidence(quelle)
        vorlage = T.inhalt(quelle)
        T.heisses_journal(quelle, self.ev)
        self.assertTrue(os.path.exists(self.ev + "-journal"))
        self.assertEqual(EvidenceStartpruefung.pruefen(self.ev).art,
                         "heisses_journal")
        sha_db, sha_j = sha256(self.ev), sha256(self.ev + "-journal")
        erg = self.pruefung().ausfuehren()
        self.assertEqual(erg.ausgang, EINGETRAGEN)
        self.assertFalse(os.path.exists(self.ev + "-journal"))
        self.assertEqual(T.inhalt(self.ev), vorlage)
        s = os.path.join(self.defekt, "evidence_4711_vor_zurueckrollen_defekt_"
                         "20261014_190000.db")
        self.assertEqual(sha256(s), sha_db)
        self.assertEqual(sha256(s + "-journal"), sha_j)
        (ergebnis, befund, *_r), = self.register()
        self.assertEqual(ergebnis, "journal_zurueckgerollt")
        b = json.loads(befund)
        self.assertEqual(b["erkennung"]["art"], "heisses_journal")
        self.assertEqual(b["nach_zurueckrollen"]["art"], "ok")
        self.assertEqual(b["sicherung_vor_zurueckrollen"]["begleit"],
                         {"-journal": sha_j})

    def test_es05_supportmodus(self):
        T.bau_evidence(self.ev)
        T.abschneiden(self.ev, "viewport_events")
        vorher = sha256(self.ev)
        with self.assertRaises(EvidenceStartpruefungFehler) as ctx:
            self.pruefung(ctx=self.ctx(mode="support")).ausfuehren()
        self.assertIn("Supportmodus", str(ctx.exception))
        self.assertTrue(ctx.exception.hilfe)
        self.assertEqual(ctx.exception.melde_ergebnis.ausgang, EINGETRAGEN)
        self.assertEqual(sha256(self.ev), vorher)
        self.assertFalse(os.path.exists(self.defekt))
        (ergebnis, befund, *_r), = self.register()
        self.assertEqual(ergebnis, "start_verweigert")
        self.assertIn("Supportmodus", json.loads(befund)["grund"])

    def test_es06_gesperrt(self):
        T.bau_evidence(self.ev)
        vorher = sha256(self.ev)
        sperr = sqlite3.connect(self.ev, isolation_level=None)
        sperr.execute("BEGIN EXCLUSIVE")
        try:
            with self.assertRaises(EvidenceStartpruefungFehler) as ctx:
                self.pruefung().ausfuehren()
        finally:
            sperr.execute("ROLLBACK")
            sperr.close()
        self.assertIn("gesperrt", str(ctx.exception))
        # Festlegung: auch eine gesperrte Datei ist ein Eintrag (Befund der
        # unabhaengigen Durchsicht, Build 778 — der erste Stand dieses Tests
        # behauptete das Gegenteil der Vorgabe).
        self.assertEqual(ctx.exception.melde_ergebnis.ausgang, EINGETRAGEN)
        (ergebnis, befund, *_r), = self.register()
        self.assertEqual(ergebnis, "start_verweigert")
        self.assertIn("nichts veraendert", json.loads(befund)["grund"])
        self.assertEqual(sha256(self.ev), vorher)
        self.assertFalse(os.path.exists(self.defekt))

    def test_es07_austausch_scheitert_an_offener_datei(self):
        T.bau_evidence(self.ev)
        T.abschneiden(self.ev, "viewport_events")
        # Eine (nicht heisse) Begleitdatei liegt daneben: sie muss beim
        # Abbruch zurueckverschoben werden.
        with open(self.ev + "-shm", "wb") as fh:
            fh.write(b"\x00" * 16)
        vorher, shm = sha256(self.ev), sha256(self.ev + "-shm")
        with mock.patch("core.evidence_austausch.os.replace",
                        side_effect=PermissionError("Datei wird verwendet")):
            with self.assertRaises(EvidenceStartpruefungFehler) as ctx:
                self.pruefung().ausfuehren()
        self.assertIn("Datei wird verwendet", str(ctx.exception))
        self.assertEqual(sha256(self.ev), vorher)
        self.assertEqual(sha256(self.ev + "-shm"), shm)
        self.assertFalse(os.path.exists(self.ev + EvidenceAustausch.TMP_ENDUNG))
        (ergebnis, befund, *_r), = self.register()
        self.assertEqual(ergebnis, "start_verweigert")
        self.assertIn("Austausch", json.loads(befund)["grund"])

    def test_es08_puffer_und_nachtrag(self):
        T.bau_evidence(self.ev)
        T.abschneiden(self.ev, "viewport_events")
        fehlt = os.path.join(self.tmp, "nicht_da", "coordinator.db")
        erg = self.pruefung(ctx=self.ctx(coord=fehlt)).ausfuehren()
        self.assertEqual(erg.ausgang, GEPUFFERT)
        self.assertTrue(os.path.isfile(erg.puffer_pfad))
        self.assertEqual(self.register(), [])
        # Naechster Start, Datei jetzt unversehrt, coordinator.db erreichbar.
        self.assertIsNone(self.pruefung().ausfuehren())
        (ergebnis, _b, _s, _p, _st, nach), = self.register()
        self.assertEqual((ergebnis, nach), ("repariert_freigegeben", 1))
        self.assertFalse(os.path.exists(erg.puffer_pfad))

    def test_es10_ohne_sicherungsordner(self):
        T.bau_evidence(self.ev)
        T.abschneiden(self.ev, "viewport_events")
        vorher = sha256(self.ev)
        with self.assertRaises(EvidenceStartpruefungFehler):
            self.pruefung(cfg=Konfig({})).ausfuehren()
        self.assertEqual(sha256(self.ev), vorher)
        (ergebnis, befund, *_r), = self.register()
        self.assertEqual(ergebnis, "start_verweigert")
        self.assertIn("backup.dest_dir", json.loads(befund)["grund"])

    def test_es13_unerwarteter_fehler(self):
        T.bau_evidence(self.ev)
        T.abschneiden(self.ev, "viewport_events")
        vorher = sha256(self.ev)
        with mock.patch("db.reparatur.evidence_reparierer.EvidenceReparierer."
                        "ausfuehren", side_effect=RuntimeError("Platte voll")):
            with self.assertRaises(EvidenceStartpruefungFehler) as ctx:
                self.pruefung().ausfuehren()
        self.assertIn("Platte voll", str(ctx.exception))
        self.assertEqual(sha256(self.ev), vorher)
        (ergebnis, befund, *_r), = self.register()
        b = json.loads(befund)
        self.assertEqual(ergebnis, "start_verweigert")
        self.assertIn("RuntimeError", b["traceback"])

    def test_es15_nachpruefung_nach_dem_austausch(self):
        """Besteht die eingesetzte Datei die erneute Pruefung nicht, wird der
        Start verweigert (Gegenprobe P12)."""
        from core.integritaets_befund import IntegritaetsBefund
        T.bau_evidence(self.ev)
        T.abschneiden(self.ev, "viewport_events")
        echt = EvidenceStartpruefung.pruefen
        aufrufe = []

        def pruefen(pfad, timeout=10.0):
            aufrufe.append(pfad)
            if len(aufrufe) == 1:
                return echt(pfad, timeout)
            return IntegritaetsBefund(art="defekt", zeilen=["kuenstlich"])
        with mock.patch.object(EvidenceStartpruefung, "pruefen",
                               staticmethod(pruefen)):
            with self.assertRaises(EvidenceStartpruefungFehler) as ctx:
                self.pruefung().ausfuehren()
        self.assertEqual(len(aufrufe), 2)
        self.assertIn("besteht die Pruefung nicht", str(ctx.exception))
        (ergebnis, befund, *_r), = self.register()
        self.assertEqual(ergebnis, "start_verweigert")
        self.assertEqual(json.loads(befund)["nachpruefung"]["art"], "defekt")

    def test_es18_abbruch_nach_dem_austausch_wird_nachgetragen(self):
        """Endet der Prozess zwischen Austausch und Eintrag, traegt der
        naechste Start die Vormerkung nach (Befund der Durchsicht)."""
        T.bau_evidence(self.ev)
        T.abschneiden(self.ev, "viewport_events")
        echt = EvidenceStartpruefung.pruefen
        aufrufe = []

        def pruefen(pfad, timeout=10.0):
            aufrufe.append(pfad)
            if len(aufrufe) == 2:                 # Nachpruefung -> "Absturz"
                raise KeyboardInterrupt("Prozess beendet")
            return echt(pfad, timeout)
        with mock.patch.object(EvidenceStartpruefung, "pruefen",
                               staticmethod(pruefen)):
            with self.assertRaises(KeyboardInterrupt):
                self.pruefung().ausfuehren()
        self.assertEqual(self.register(), [])
        vormerkung = os.listdir(os.path.join(self.defekt, "ausstehende_vorfaelle"))
        self.assertEqual(len(vormerkung), 1)
        self.assertTrue(EvidenceStartpruefung.pruefen(self.ev).ok)  # ersetzt
        self.assertIsNone(self.pruefung(zeitstempel="20261014_191000")
                          .ausfuehren())
        (ergebnis, befund, _s, _p, _st, nach), = self.register()
        self.assertEqual((ergebnis, nach), ("repariert_freigegeben", 1))
        self.assertIn("nicht bestaetigt", json.loads(befund)["vorlaeufig"])
        self.assertEqual(os.listdir(os.path.join(self.defekt,
                                                 "ausstehende_vorfaelle")), [])

    def test_es18b_vormerkung_wird_durch_die_meldung_ersetzt(self):
        T.bau_evidence(self.ev)
        T.abschneiden(self.ev, "viewport_events")
        self.pruefung().ausfuehren()
        self.assertEqual(os.listdir(os.path.join(self.defekt,
                                                 "ausstehende_vorfaelle")), [])
        (ergebnis, befund, *_r), = self.register()
        self.assertNotIn("vorlaeufig", json.loads(befund))
        self.assertEqual(json.loads(befund)["datei_veraendert"], "ersetzt")

    def test_es19_journal_und_danach_noch_defekt(self):
        """Zwei Staende, zwei Sicherungen — keine ueberdeckt die andere."""
        quelle = os.path.join(self.tmp, "quelle.db")
        T.bau_evidence(quelle)
        T.abschneiden(quelle, "page_visits")
        T.heisses_journal(quelle, self.ev)
        sha_db, sha_j = sha256(self.ev), sha256(self.ev + "-journal")
        erg = self.pruefung().ausfuehren()
        self.assertEqual(erg.ausgang, EINGETRAGEN)
        vor = os.path.join(self.defekt, "evidence_4711_vor_zurueckrollen_"
                           "defekt_20261014_190000.db")
        self.assertEqual(sha256(vor), sha_db)
        self.assertEqual(sha256(vor + "-journal"), sha_j)
        nach = os.path.join(self.defekt, "evidence_4711_defekt_20261014_190000.db")
        self.assertTrue(os.path.isfile(nach))
        self.assertFalse(os.path.exists(nach + "-journal"))
        self.assertNotEqual(sha256(nach), sha_db)
        (ergebnis, befund, *_r), = self.register()
        b = json.loads(befund)
        self.assertEqual(ergebnis, "repariert_freigegeben")
        self.assertEqual(b["nach_zurueckrollen"]["art"], "defekt")
        self.assertEqual(b["sicherung_vor_zurueckrollen"]["datei"], vor)
        self.assertEqual(b["reparatur"]["sicherung"]["datei"], nach)

    def test_es20_einordnung_nach_fehlername(self):
        def fehler(klasse, name, text="x"):
            e = klasse(text)
            e.sqlite_errorname = name
            return e
        E, O = sqlite3.DatabaseError, sqlite3.OperationalError
        ein = EvidenceStartpruefung.einordnen
        T.bau_evidence(self.ev)
        self.assertEqual(ein(fehler(O, "SQLITE_READONLY_ROLLBACK"), self.ev),
                         "unklar")             # ohne -journal kein heisses
        with open(self.ev + "-journal", "wb") as fh:
            fh.write(b"j")
        self.assertEqual(ein(fehler(O, "SQLITE_READONLY_ROLLBACK"), self.ev),
                         "heisses_journal")
        self.assertEqual(ein(fehler(O, "SQLITE_BUSY"), self.ev), "gesperrt")
        self.assertEqual(ein(fehler(O, "SQLITE_CANTOPEN"), self.ev), "gesperrt")
        self.assertEqual(ein(fehler(E, "SQLITE_CORRUPT"), self.ev), "defekt")
        self.assertEqual(ein(fehler(E, "SQLITE_NOTADB"), self.ev), "defekt")
        self.assertEqual(ein(fehler(O, "SQLITE_IOERR_READ", "disk I/O error"),
                             self.ev), "unklar")
        # Echte Fehler: Datei fehlt (Ordner fehlt) -> gesperrt; Unsinn -> defekt
        self.assertEqual(EvidenceStartpruefung.pruefen(
            os.path.join(self.tmp, "nix", "x.db")).art, "gesperrt")
        unsinn = os.path.join(self.tmp, "unsinn.db")
        with open(unsinn, "wb") as fh:
            fh.write(b"keine Datenbank " * 300)
        self.assertEqual(EvidenceStartpruefung.pruefen(unsinn).art, "defekt")

    def test_es20b_unklar_greift_nicht_ein(self):
        T.bau_evidence(self.ev)
        vorher = sha256(self.ev)
        from core.integritaets_befund import IntegritaetsBefund
        with mock.patch.object(EvidenceStartpruefung, "pruefen", staticmethod(
                lambda p, t=10.0: IntegritaetsBefund(
                    art="unklar", zeilen=["disk I/O error"]))):
            with self.assertRaises(EvidenceStartpruefungFehler) as ctx:
                self.pruefung().ausfuehren()
        self.assertIn("Ursache unklar", str(ctx.exception))
        self.assertEqual(sha256(self.ev), vorher)
        self.assertFalse(os.path.exists(self.defekt))
        (ergebnis, *_r), = self.register()
        self.assertEqual(ergebnis, "start_verweigert")

    def test_es21_text_nach_zustand_der_datei(self):
        """'unveraendert' nur, wenn es stimmt (Befund der Durchsicht)."""
        T.bau_evidence(self.ev)
        T.abschneiden(self.ev, "viewport_events")
        echt = EvidenceStartpruefung.pruefen
        aufrufe = []
        from core.integritaets_befund import IntegritaetsBefund

        def pruefen(pfad, timeout=10.0):
            aufrufe.append(pfad)
            if len(aufrufe) == 1:
                return echt(pfad, timeout)
            return IntegritaetsBefund(art="defekt", zeilen=["kuenstlich"])
        with mock.patch.object(EvidenceStartpruefung, "pruefen",
                               staticmethod(pruefen)):
            with self.assertRaises(EvidenceStartpruefungFehler) as ctx:
                self.pruefung().ausfuehren()
        self.assertIn("ersetzt", str(ctx.exception))
        self.assertNotIn("unveraendert.", str(ctx.exception).split("\n")[0])
        self.assertIn("bereits durch eine reparierte Fassung ersetzt",
                      ctx.exception.hilfe[0])


class AustauschTests(_Welt):

    def test_es09_original_veraendert(self):
        from db.reparatur import EvidenceReparierer
        T.bau_evidence(self.ev)
        T.abschneiden(self.ev, "viewport_events")
        erg = EvidenceReparierer(self.ev, self.defekt,
                                 zeitstempel="20261014_190000").ausfuehren()
        self.assertTrue(erg.neue_datei_gut)
        with open(self.ev, "ab") as fh:              # jemand schreibt weiter
            fh.write(b"x")
        vorher = sha256(self.ev)
        with self.assertRaises(AustauschFehler) as ctx:
            EvidenceAustausch(self.ev, self.defekt, "20261014_190000").ausfuehren(erg)
        self.assertIn("veraendert", str(ctx.exception))
        self.assertEqual(sha256(self.ev), vorher)
        self.assertFalse(os.path.exists(self.ev + EvidenceAustausch.TMP_ENDUNG))
        # Begleitdatei, die von der Sicherung abweicht -> Abbruch, zurueck.
        with open(self.ev, "rb+") as fh:
            fh.truncate(os.path.getsize(self.ev) - 1)
        with open(self.ev + "-journal", "wb") as fh:
            fh.write(b"neu")
        with self.assertRaises(AustauschFehler) as ctx:
            EvidenceAustausch(self.ev, self.defekt, "20261014_190000").ausfuehren(erg)
        self.assertIn("Begleitdatei", str(ctx.exception))
        self.assertTrue(os.path.exists(self.ev + "-journal"))
        self.assertEqual(sha256(self.ev), erg.sicherung.sha256)
        os.remove(self.ev + "-journal")
        # Platte voll beim Kopieren: halbe .tmp wird entfernt (Durchsicht).
        def halb(quelle, ziel):
            with open(ziel, "wb") as fh:
                fh.write(b"halb")
            raise OSError(28, "No space left on device")
        with mock.patch("core.evidence_austausch.shutil.copyfile", halb):
            with self.assertRaises(AustauschFehler) as ctx:
                EvidenceAustausch(self.ev, self.defekt,
                                  "20261014_190000").ausfuehren(erg)
        self.assertIn("No space", str(ctx.exception))
        self.assertFalse(ctx.exception.ersetzt)
        self.assertFalse(os.path.exists(self.ev + EvidenceAustausch.TMP_ENDUNG))
        self.assertEqual(sha256(self.ev), erg.sicherung.sha256)

    def test_es22_sicherung_wird_nie_ueberschrieben(self):
        from db.reparatur.defekt_sicherung import DefektSicherung
        T.bau_evidence(self.ev)
        ds = DefektSicherung(self.defekt)
        a = ds.sichern(self.ev, "evidence_4711", "20261014_190000")
        with open(self.ev + "-journal", "wb") as fh:
            fh.write(b"j")
        b = ds.sichern(self.ev, "evidence_4711", "20261014_190000")
        self.assertTrue(b.neu_angelegt)
        self.assertNotEqual(a.pfad, b.pfad)
        self.assertTrue(b.pfad.endswith("_20261014_190000_2.db"))
        self.assertFalse(os.path.exists(a.pfad + "-journal"))
        self.assertEqual(sha256(a.pfad), a.sha256)
        c = ds.sichern(self.ev, "evidence_4711", "20261014_190000")
        self.assertFalse(c.neu_angelegt)          # identisch -> wiederverwendet
        self.assertEqual(c.pfad, b.pfad)


class StartupCheckerTests(_Welt):

    def test_es11_forensic_keine_sqlite_datei(self):
        forensic = Path(self.tmp) / "forensic_4711.db"
        forensic.write_bytes(b"Dies ist keine SQLite-Datenbank. " * 200)
        ctx = SimpleNamespace(forensic_db=forensic, evidence_db=Path(self.ev),
                              mode="cli", subject_id=4711)
        checker = StartupChecker(ctx, self.cfg)
        for methode in (checker._check_forensic_db_schema_version,
                        checker._check_forensic_db_integrity,
                        checker._check_forensic_db_readonly):
            with self.assertRaises(StartupCheckError, msg=methode.__name__) as c:
                methode()
            self.assertIn("beschädigt oder keine SQLite-Datenbank",
                          str(c.exception))
            self.assertIn("DatabaseError", str(c.exception))

    def test_es14_evidence_zuletzt(self):
        reihenfolge = []
        stub = SimpleNamespace(ausfuehren=lambda: reihenfolge.append("evidence")
                               or "MELDUNG")
        checker = StartupChecker(SimpleNamespace(), self.cfg,
                                 evidence_pruefung=stub)
        namen = ("_check_forensic_db_exists", "_check_default_db_exists",
                 "_check_coordinator_db_exists", "_check_journal_stamps",
                 "_check_forensic_db_schema_version",
                 "_check_forensic_db_integrity", "_check_forensic_db_readonly")
        with mock.patch.multiple(StartupChecker, **{
                n: (lambda n=n: (lambda self: reihenfolge.append(n)))()
                for n in namen}):
            checker.run_all()
        self.assertEqual(reihenfolge, list(namen) + ["evidence"])
        self.assertEqual(checker.evidence_meldung, "MELDUNG")


class FehlerseiteTests(_Welt):

    def test_es12_fehlerseite(self):
        melde = SimpleNamespace(klartext=lambda: "Vorfall X im Register <ok>.")
        fehler = EvidenceStartpruefungFehler(
            "Datei <script>alert(1)</script> kaputt",
            hilfe=["Erst A & dann B."], melde_ergebnis=melde)
        seite = Startfehlerseite(self.tmp)
        text = seite.html(fehler, logdatei="C:\\logs\\x.log", zeit="jetzt")
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;script&gt;", text)
        self.assertIn("Erst A &amp; dann B.", text)
        self.assertIn("Vorfall X im Register &lt;ok&gt;.", text)
        self.assertIn("C:\\logs\\x.log", text)
        self.assertNotIn("<script", text.lower())
        allg = seite.html(StartupCheckError("forensic kaputt"))
        self.assertIn("Schließen Sie andere Fenster", allg)
        pfad = seite.schreiben(fehler)
        self.assertTrue(pfad.startswith(self.tmp))
        with open(pfad, encoding="utf-8") as fh:
            self.assertEqual(fh.read().count("Erst A &amp; dann B."), 1)
        # Protokollordner ist eine DATEI -> Ausweichen in den temp-Ordner.
        blocker = os.path.join(self.tmp, "blocker")
        with open(blocker, "w") as fh:
            fh.write("x")
        pfad2 = Startfehlerseite(os.path.join(blocker, "logs")).schreiben(fehler)
        try:
            self.assertTrue(pfad2.startswith(tempfile.gettempdir()))
        finally:
            os.remove(pfad2)
        self.assertEqual(Startfehlerseite.aus_konfiguration(Konfig({
            "logging.logfile": os.path.join(self.tmp, "l", "s.log")})).verzeichnis,
            os.path.join(self.tmp, "l"))

    def test_es16_anzeigen_oeffnet_und_wirft_nie(self):
        geoeffnet = []
        launcher = SimpleNamespace(open=lambda url: geoeffnet.append(url))
        cfg = Konfig({"logging.logfile": os.path.join(self.tmp, "lg", "s.log")})
        pfad = Startfehlerseite.anzeigen(cfg, StartupCheckError("x"),
                                         launcher=launcher)
        self.assertTrue(os.path.isfile(pfad))
        self.assertEqual(geoeffnet, [Path(pfad).resolve().as_uri()])
        self.assertTrue(geoeffnet[0].startswith("file:"))
        kaputt = SimpleNamespace(open=mock.Mock(side_effect=OSError("kein Browser")))
        from core.logger import get_logger
        with self.assertLogs(get_logger("core.startfehlerseite").name,
                             level="WARNING"):
            self.assertIsNone(Startfehlerseite.anzeigen(
                cfg, StartupCheckError("x"), launcher=kaputt))

    def test_es17_main_zeigt_die_seite_bei_jedem_abbruch_von_schritt_6(self):
        """main.py: BEIDE Abfangzweige der Startpruefung (StartupCheckError
        und unerwartete Ausnahme) rufen _start_verweigert vor sys.exit(1)."""
        import ast
        baum = ast.parse((WURZEL / "main.py").read_text(encoding="utf-8"))
        zweige = []
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.Try) and any(
                    isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "run_all"
                    for c in ast.walk(ast.Module(body=knoten.body, type_ignores=[]))):
                zweige = knoten.handlers
        self.assertEqual(len(zweige), 2)
        for h in zweige:
            aufrufe = [getattr(c.func, "id", getattr(c.func, "attr", ""))
                       for c in ast.walk(h) if isinstance(c, ast.Call)]
            self.assertIn("_start_verweigert", aufrufe)
            self.assertLess(aufrufe.index("_start_verweigert"),
                            aufrufe.index("exit"))


if __name__ == "__main__":
    unittest.main()
