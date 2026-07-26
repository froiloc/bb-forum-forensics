# =============================================================================
# tests/test_tatzeit_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A)
# =============================================================================
# Testsuite fuer Build 533: TatzeitRepo — der Schreib- und Lesepfad zu
# 'annotation_tatzeit' in evidence_<uid>.db.
#
#   TR01 — Ersterfassung: Fachzeile UND Beleg liegen vor, version_nr=1,
#          prev_id IS NULL, und die Kette verifiziert.
#   TR02 — Korrektur ist eine NEUE VERSION, kein UPDATE: version_nr=2,
#          prev_id zeigt auf die Vorgaengerin, die Vorgaengerin traegt
#          deleted_at UND hat einen Nachfolger.
#   TR03 — Ruecknahme ist etwas ANDERES als eine Korrektur: deleted_at gesetzt,
#          KEIN Nachfolger, eigener Ereignistyp TATZEIT_CLEARED.
#   TR04 — DIE UNTERSCHEIDUNG, DIE MAN VERWECHSELN KANN: 'deleted_at' auf einer
#          Zeile mit Nachfolger heisst "geaendert", ohne Nachfolger "zurueck-
#          genommen" (db/evidence_db.py:886-891). Wer das verwechselt, zaehlt
#          jede Korrektur als Ruecknahme.
#   TR05 — Aufloesung ueber annotation_local_id (die Tatzeit FOLGT einer
#          bearbeiteten Annotation) mit Rueckfall auf annotation_id.
#   TR06 — Quellen-Vokabular: 'sonstiges' verlangt Freitext, jeder andere Code
#          verbietet ihn, unbekannte Codes werden abgewiesen.
#   TR07 — Harte und weiche Angaben schliessen sich aus, in beide Richtungen.
#   TR08 — WIRKUNGSPROBE GEGEN DIE DATENBANK: jede Eingabe, die das Repository
#          ablehnt, wird auch von einem CHECK abgelehnt. Beide Ebenen sind
#          sich einig — die eine liefert den lesbaren Satz, die andere ist die
#          letzte Verteidigung.
#   TR09 — Der Plausibilitaetsrahmen im Laufzeitcode ist derselbe wie die
#          FROZEN COPY im CHECK von m002. Laufen sie auseinander, faellt es
#          hier auf und nicht erst als IntegrityError bei einer Ermittlerin.
#   TR10 — SENSIBILITAETSREGEL: der Beleg traegt KEINEN Wortlaut und KEINEN
#          Freitext, nur Fakten und Textlaengen.
#   TR11 — Eine bereits ersetzte oder zurueckgenommene Zeile kann nicht noch
#          einmal ersetzt werden — sonst entstuenden zwei Aeste und keiner
#          waere "der aktuelle".
#   TR12 — Ohne EvidenceWriter sind die Schreibmethoden GESPERRT (nicht still
#          wirkungslos).
#
# Version: v0.8.533 · Build: 533 · 2026-07-26
# =============================================================================

import re
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.evidence as evidence_migrations        # noqa: E402
from db.tatzeit_repo import TatzeitError, TatzeitRepo               # noqa: E402
from management.audit.evidence_audit_log import EvidenceAuditLog    # noqa: E402
from management.audit.event_types import EventType                  # noqa: E402
from management.deadlines.limitation_repo import (                  # noqa: E402
    PLAUSIBEL_BIS, PLAUSIBEL_VON,
)
from management.gateway.evidence_writer import EvidenceWriter       # noqa: E402
from management.migrations.evidence import (                        # noqa: E402
    m002_annotation_tatzeit as M002,
)
from management.migrations.runner import MigrationRunner, discover  # noqa: E402

_ANNOTATIONS = """
CREATE TABLE "annotations" (
    "id"              INTEGER,
    "page_url"        TEXT NOT NULL,
    "element_id"      TEXT,
    "category"        TEXT NOT NULL,
    "text"            TEXT NOT NULL DEFAULT '',
    "ts"              INTEGER NOT NULL,
    "investigator_id" INTEGER,
    "local_id"        TEXT DEFAULT NULL,
    "version_nr"      INTEGER NOT NULL DEFAULT 1,
    "prev_id"         INTEGER DEFAULT NULL,
    "deleted_at"      INTEGER DEFAULT NULL,
    PRIMARY KEY("id" AUTOINCREMENT)
);
"""

_VON = 1600000000        # 2020-09-13
_BIS = 1600086400        # 2020-09-14
_ACTOR = 7


class TestTatzeitRepo(unittest.TestCase):

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.pfad = self.dir / "evidence_4711.db"
        con = sqlite3.connect(str(self.pfad))
        con.row_factory = sqlite3.Row
        con.executescript(_ANNOTATIONS)
        con.execute(
            'INSERT INTO "annotations" (page_url, category, text, ts, '
            'investigator_id, local_id) VALUES (?,?,?,?,?,?)',
            ("/viewtopic.php?id=1", "§ 184b", "Er schrieb: das war 2020",
             1700000000, 3, "abc-123"))
        con.execute(
            'INSERT INTO "annotations" (page_url, category, text, ts, '
            'investigator_id, local_id) VALUES (?,?,?,?,?,?)',
            ("/viewtopic.php?id=2", "Sonstiges", "anonyme Einmal-Annotation",
             1700000100, 3, None))
        con.commit()
        MigrationRunner(con, discover(evidence_migrations)).run()
        self.con = con
        self.repo = TatzeitRepo(con, EvidenceWriter(con))
        self.nur_lesen = TatzeitRepo(con)

    def tearDown(self):
        try:
            self.con.close()
        except sqlite3.Error:
            pass
        shutil.rmtree(self.dir, ignore_errors=True)

    # ------------------------------------------------------------------ Hilfen
    def _setzen(self, **kwargs):
        args = dict(annotation_id=1, annotation_local_id="abc-123",
                    art="hart", quelle_code="beitragstext", actor_id=_ACTOR,
                    von_ts=_VON, bis_ts=_BIS, genauigkeit="tag")
        args.update(kwargs)
        return self.repo.setzen(**args)

    def _belege(self, event_type=None):
        sql = "SELECT seq, event_type, actor_id, target_type, target_id, " \
              "content FROM evidence_audit_log"
        args = ()
        if event_type:
            sql += " WHERE event_type = ?"
            args = (event_type,)
        return self.con.execute(sql + " ORDER BY seq", args).fetchall()

    # ===================================================================== TR01
    def test_TR01_ersterfassung(self):
        res = self._setzen()
        self.assertEqual(res["version_nr"], 1)
        self.assertIsNone(res["prev_id"])

        zeile = self.repo.eine(res["tatzeit_id"])
        self.assertEqual(zeile["annotation_id"], 1)
        self.assertEqual(zeile["annotation_local_id"], "abc-123")
        self.assertEqual(zeile["art"], "hart")
        self.assertEqual(zeile["von_ts"], _VON)
        self.assertEqual(zeile["bis_ts"], _BIS)
        self.assertEqual(zeile["quelle"], "beitragstext")
        self.assertEqual(zeile["quelle_code"], "beitragstext")
        self.assertIsNone(zeile["quelle_freitext"])
        self.assertEqual(zeile["erfasst_von"], _ACTOR)
        self.assertIsNone(zeile["deleted_at"])

        belege = self._belege(EventType.TATZEIT_SET)
        self.assertEqual(len(belege), 1)
        self.assertEqual(int(belege[0]["actor_id"]), _ACTOR)
        self.assertEqual(belege[0]["target_type"], "annotation")
        self.assertEqual(belege[0]["target_id"], "1")
        self.assertTrue(EvidenceAuditLog(self.con).verify_chain().ok)

    # ===================================================================== TR02
    def test_TR02_korrektur_ist_eine_neue_version(self):
        erst = self._setzen()
        zweit = self._setzen(von_ts=_VON + 86400, bis_ts=None,
                             ersetzt_id=erst["tatzeit_id"])

        self.assertEqual(zweit["version_nr"], 2)
        self.assertEqual(zweit["prev_id"], erst["tatzeit_id"])

        alt = self.repo.eine(erst["tatzeit_id"])
        neu = self.repo.eine(zweit["tatzeit_id"])
        self.assertIsNotNone(alt["deleted_at"],
                             "Die Vorgaengerin muss markiert sein.")
        self.assertIsNone(neu["deleted_at"])
        # Der Inhalt der Vorgaengerin ist UNVERAENDERT — append-only.
        self.assertEqual(alt["von_ts"], _VON)
        self.assertEqual(neu["von_ts"], _VON + 86400)

        aktiv = self.repo.liste(annotation_local_id="abc-123")
        self.assertEqual([z["id"] for z in aktiv], [zweit["tatzeit_id"]])
        self.assertEqual(len(self._belege(EventType.TATZEIT_SET)), 2)

    # ===================================================================== TR03
    def test_TR03_ruecknahme_ist_ein_eigener_vorgang(self):
        erst = self._setzen()
        res = self.repo.zuruecknehmen(tatzeit_id=erst["tatzeit_id"],
                                      actor_id=_ACTOR, grund="Irrtum")

        zeile = self.repo.eine(erst["tatzeit_id"])
        self.assertIsNotNone(zeile["deleted_at"])
        self.assertFalse(self.repo.hat_nachfolger(erst["tatzeit_id"]))
        self.assertEqual(self.repo.liste(annotation_id=1), [])

        belege = self._belege(EventType.TATZEIT_CLEARED)
        self.assertEqual(len(belege), 1)
        self.assertEqual(belege[0]["seq"], res["audit_seq"])
        self.assertTrue(EvidenceAuditLog(self.con).verify_chain().ok)

    # ===================================================================== TR04
    def test_TR04_geaendert_und_zurueckgenommen_sind_unterscheidbar(self):
        """
        Beide Faelle setzen 'deleted_at'. Unterschieden werden sie ALLEIN ueber
        den Nachfolger — genau wie bei 'annotations' selbst
        (db/evidence_db.py:886-891). Wer das verwechselt, zaehlt jede Korrektur
        als Ruecknahme und der Fristenmonitor saehe eine festgestellte Tatzeit,
        die es nicht mehr gibt (oder umgekehrt).
        """
        a = self._setzen()
        b = self._setzen(ersetzt_id=a["tatzeit_id"], von_ts=_VON + 100)
        c = self._setzen(annotation_id=2, annotation_local_id=None)
        self.repo.zuruecknehmen(tatzeit_id=c["tatzeit_id"], actor_id=_ACTOR)

        # a: deleted_at gesetzt, ABER mit Nachfolger -> geaendert
        self.assertIsNotNone(self.repo.eine(a["tatzeit_id"])["deleted_at"])
        self.assertTrue(self.repo.hat_nachfolger(a["tatzeit_id"]))
        # c: deleted_at gesetzt, OHNE Nachfolger -> zurueckgenommen
        self.assertIsNotNone(self.repo.eine(c["tatzeit_id"])["deleted_at"])
        self.assertFalse(self.repo.hat_nachfolger(c["tatzeit_id"]))
        # b ist die aktive Version
        self.assertIsNone(self.repo.eine(b["tatzeit_id"])["deleted_at"])

    # ===================================================================== TR05
    def test_TR05_aufloesung_ueber_local_id_mit_rueckfall(self):
        self._setzen()
        # Annotation 2 hat KEINE local_id ("anonyme Einmal-Annotation",
        # db/evidence_db.py:871) — dort greift der Rueckfall.
        zweit = self._setzen(annotation_id=2, annotation_local_id=None)

        ueber_local = self.repo.liste(annotation_local_id="abc-123")
        self.assertEqual(len(ueber_local), 1)
        self.assertEqual(ueber_local[0]["annotation_id"], 1)

        ueber_ann = self.repo.liste(annotation_id=2)
        self.assertEqual([z["id"] for z in ueber_ann], [zweit["tatzeit_id"]])
        self.assertIsNone(ueber_ann[0]["annotation_local_id"])

        with self.assertRaises(TatzeitError):
            self.repo.liste()

        # Historie liefert auch die ersetzten Zeilen.
        self._setzen(ersetzt_id=ueber_local[0]["id"], von_ts=_VON + 7)
        self.assertEqual(len(self.repo.liste(annotation_local_id="abc-123")), 1)
        self.assertEqual(
            len(self.repo.liste(annotation_local_id="abc-123",
                                mit_historie=True)), 2)

    # ===================================================================== TR06
    def test_TR06_quellen_vokabular(self):
        with self.assertRaises(TatzeitError) as ctx:
            self._setzen(quelle_code="sonstiges")
        self.assertIn("Freitext", str(ctx.exception))

        with self.assertRaises(TatzeitError):
            self._setzen(quelle_code="beitragstext", quelle_freitext="egal")

        with self.assertRaises(TatzeitError):
            self._setzen(quelle_code="erfunden")

        res = self._setzen(quelle_code="sonstiges",
                           quelle_freitext="Zitat in geloeschtem Beitrag")
        zeile = self.repo.eine(res["tatzeit_id"])
        self.assertEqual(zeile["quelle"],
                         "sonstiges:Zitat in geloeschtem Beitrag")
        self.assertEqual(zeile["quelle_code"], "sonstiges")
        self.assertEqual(zeile["quelle_freitext"],
                         "Zitat in geloeschtem Beitrag")

    # ===================================================================== TR07
    def test_TR07_harte_und_weiche_angaben_schliessen_sich_aus(self):
        # hart ohne jeden Zeitwert
        with self.assertRaises(TatzeitError):
            self._setzen(von_ts=None, bis_ts=None)
        # hart mit weichen Feldern
        with self.assertRaises(TatzeitError):
            self._setzen(angabe_schluessel="markierung", angabe_wert="x")
        # weich ohne Schluessel
        with self.assertRaises(TatzeitError):
            self._setzen(art="weich", von_ts=None, bis_ts=None,
                         genauigkeit=None)
        # weich mit Zeitwerten
        with self.assertRaises(TatzeitError):
            self._setzen(art="weich", angabe_schluessel="markierung",
                         angabe_wert="vor zwei Jahren", genauigkeit=None)
        # Ende vor Beginn
        with self.assertRaises(TatzeitError):
            self._setzen(von_ts=_BIS, bis_ts=_VON)

        # Der zulaessige weiche Fall (Entscheidung mc: als Markierung um den
        # Text festhalten, Verarbeitung spaeter).
        res = self._setzen(art="weich", von_ts=None, bis_ts=None,
                           genauigkeit="unbestimmt",
                           angabe_schluessel="markierung",
                           angabe_wert="vor zwei Jahren",
                           wortlaut="das war so vor zwei Jahren")
        zeile = self.repo.eine(res["tatzeit_id"])
        self.assertEqual(zeile["art"], "weich")
        self.assertIsNone(zeile["von_ts"])
        self.assertEqual(zeile["angabe_wert"], "vor zwei Jahren")

    # ===================================================================== TR08
    def test_TR08_repository_und_datenbank_sind_sich_einig(self):
        """
        Wirkungsprobe. Fuer jede Eingabe, die das Repository ablehnt, wird
        DIESELBE Eingabe roh in die Tabelle geschrieben — der CHECK muss sie
        ebenfalls ablehnen. Waere eine der beiden Ebenen laxer, gaebe es einen
        Weg an ihr vorbei.

        AUSDRUECKLICH NICHT ABGEDECKT: die Quellen-Codes. Der CHECK in m002:222
        verlangt nur, dass 'quelle' NICHT LEER ist — das Vokabular ist eine
        reine Anwendungsregel. Das ist so gewollt (eine Codeliste in einen
        eingefrorenen CHECK zu giessen hiesse, sie nie wieder erweitern zu
        koennen), aber es soll hier stehen und nicht stillschweigend fehlen.
        """
        faelle = (
            ("Art unbekannt",
             dict(art="mittel", von_ts=_VON, bis_ts=None),
             ("mittel", _VON, None, None, None, None)),
            ("Genauigkeit unbekannt",
             dict(genauigkeit="stunde"),
             ("hart", _VON, _BIS, "stunde", None, None)),
            ("hart ohne Zeitwert",
             dict(von_ts=None, bis_ts=None),
             ("hart", None, None, "tag", None, None)),
            ("weich ohne Schluessel",
             dict(art="weich", von_ts=None, bis_ts=None, genauigkeit=None),
             ("weich", None, None, None, None, None)),
            ("hart mit weichen Feldern",
             dict(angabe_schluessel="markierung", angabe_wert="x"),
             ("hart", _VON, _BIS, "tag", "markierung", "x")),
            ("Ende vor Beginn",
             dict(von_ts=_BIS, bis_ts=_VON),
             ("hart", _BIS, _VON, "tag", None, None)),
            ("vor dem Plausibilitaetsrahmen",
             dict(von_ts=PLAUSIBEL_VON - 1, bis_ts=None),
             ("hart", PLAUSIBEL_VON - 1, None, "tag", None, None)),
            ("nach dem Plausibilitaetsrahmen",
             dict(von_ts=None, bis_ts=PLAUSIBEL_BIS + 1),
             ("hart", None, PLAUSIBEL_BIS + 1, "tag", None, None)),
        )
        for name, kwargs, roh in faelle:
            with self.subTest(fall=name):
                with self.assertRaises(TatzeitError,
                                       msg="Repository liess %r durch" % name):
                    self._setzen(**kwargs)
                with self.assertRaises(sqlite3.IntegrityError,
                                       msg="CHECK liess %r durch" % name):
                    self.con.execute(
                        'INSERT INTO "annotation_tatzeit" '
                        '(annotation_id, art, von_ts, bis_ts, genauigkeit, '
                        ' angabe_schluessel, angabe_wert, quelle, '
                        ' erfasst_von, erfasst_at) '
                        'VALUES (1,?,?,?,?,?,?,?,?,?)',
                        roh + ("beitragstext", _ACTOR, 1700000000))
                self.con.rollback()

        # Kein Rueckstand aus den abgelehnten Versuchen.
        self.assertEqual(
            self.con.execute(
                'SELECT COUNT(*) AS c FROM "annotation_tatzeit"'
            ).fetchone()["c"], 0)

    # ===================================================================== TR09
    def test_TR09_plausibilitaetsrahmen_stimmt_mit_der_frozen_copy(self):
        """
        m002 traegt den Rahmen als FROZEN COPY im CHECK — richtig, denn eine
        angewandte Migration darf ihre Bedeutung nicht nachtraeglich aendern.
        Der Laufzeitcode importiert dagegen die Konstanten. Laufen beide je
        auseinander, ist das hier zu sehen und nicht erst als IntegrityError
        aus der Tiefe der Datenbank.
        """
        quelle = Path(M002.__file__).read_text(encoding="utf-8")
        zahlen = {int(z) for z in re.findall(r'"von_ts" >= (\d+)', quelle)}
        zahlen |= {int(z) for z in re.findall(r'"bis_ts" >= (\d+)', quelle)}
        bis = {int(z) for z in re.findall(r'"von_ts" <= (\d+)', quelle)}
        bis |= {int(z) for z in re.findall(r'"bis_ts" <= (\d+)', quelle)}

        self.assertEqual(zahlen, {PLAUSIBEL_VON},
                         "Untergrenze im CHECK weicht von PLAUSIBEL_VON ab.")
        self.assertEqual(bis, {PLAUSIBEL_BIS},
                         "Obergrenze im CHECK weicht von PLAUSIBEL_BIS ab.")

    # ===================================================================== TR10
    def test_TR10_beleg_traegt_keinen_wortlaut(self):
        """
        Sensibilitaetsregel wie M018/M022: der Beleg haelt FAKTEN fest, nicht
        den Text. Sonst waende der Wortlaut einer Annotation in einer zweiten
        Struktur — und die Loeschung der Annotation liesse ihn dort stehen.
        """
        geheim = "Er nannte die Grundschule Lindenweg"
        res = self._setzen(art="weich", von_ts=None, bis_ts=None,
                           genauigkeit=None,
                           angabe_schluessel="markierung",
                           angabe_wert=geheim, wortlaut=geheim,
                           quelle_code="sonstiges",
                           quelle_freitext="Zitat aus Beitrag 4711")

        beleg = self._belege(EventType.TATZEIT_SET)[0]
        inhalt = beleg["content"]
        self.assertNotIn(geheim, inhalt,
                         "Der Wortlaut steht im Beleg — Sensibilitaetsregel "
                         "verletzt.")
        self.assertNotIn("Zitat aus Beitrag 4711", inhalt,
                         "Der Quellen-Freitext steht im Beleg.")
        # Die Fakten sind aber da, inklusive der Laengen als Nachweis, DASS
        # etwas eingetragen war.
        self.assertIn('"quelle_code":"sonstiges"', inhalt)
        self.assertIn('"wortlaut_len":%d' % len(geheim), inhalt)
        self.assertIn('"quelle_freitext_len":22', inhalt)
        self.assertIn('"tatzeit_id":%d' % res["tatzeit_id"], inhalt)

    # ===================================================================== TR11
    def test_TR11_nicht_mehr_aktive_zeile_ist_nicht_ersetzbar(self):
        a = self._setzen()
        self._setzen(ersetzt_id=a["tatzeit_id"], von_ts=_VON + 10)

        with self.assertRaises(TatzeitError) as ctx:
            self._setzen(ersetzt_id=a["tatzeit_id"], von_ts=_VON + 20)
        self.assertIn("nicht mehr aktiv", str(ctx.exception))

        # Auch eine zurueckgenommene Zeile nicht.
        c = self._setzen(annotation_id=2, annotation_local_id=None)
        self.repo.zuruecknehmen(tatzeit_id=c["tatzeit_id"], actor_id=_ACTOR)
        with self.assertRaises(TatzeitError):
            self._setzen(annotation_id=2, annotation_local_id=None,
                         ersetzt_id=c["tatzeit_id"])
        with self.assertRaises(TatzeitError):
            self.repo.zuruecknehmen(tatzeit_id=c["tatzeit_id"],
                                    actor_id=_ACTOR)

        # Und eine fremde Annotation laesst sich nicht unterschieben.
        d = self._setzen()
        with self.assertRaises(TatzeitError) as ctx2:
            self.repo.setzen(annotation_id=2, annotation_local_id=None,
                             art="hart", quelle_code="beitragstext",
                             actor_id=_ACTOR, von_ts=_VON,
                             ersetzt_id=d["tatzeit_id"])
        self.assertIn("gehoert zu Annotation", str(ctx2.exception))

    # ===================================================================== TR12
    def test_TR12_ohne_writer_sind_schreibwege_gesperrt(self):
        with self.assertRaises(TatzeitError) as ctx:
            self.nur_lesen.setzen(annotation_id=1, annotation_local_id=None,
                                  art="hart", quelle_code="beitragstext",
                                  actor_id=_ACTOR, von_ts=_VON)
        self.assertIn("ohne Schreibpfad", str(ctx.exception))

        with self.assertRaises(TatzeitError):
            self.nur_lesen.zuruecknehmen(tatzeit_id=1, actor_id=_ACTOR)

        self.assertEqual(
            self.con.execute(
                'SELECT COUNT(*) AS c FROM "annotation_tatzeit"'
            ).fetchone()["c"], 0)

        # Und ohne Handelnden ebenfalls nicht.
        with self.assertRaises(TatzeitError):
            self.repo.setzen(annotation_id=1, annotation_local_id=None,
                             art="hart", quelle_code="beitragstext",
                             actor_id=None, von_ts=_VON)


if __name__ == "__main__":
    unittest.main()
