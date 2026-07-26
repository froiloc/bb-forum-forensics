# =============================================================================
# tests/test_limitation_tatzeit.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A)
# =============================================================================
# Testsuite fuer Build 535: die FESTGESTELLTE Tatzeit im Fristenmonitor.
#
# Bis Build 534 stand in limitation_repo.compute() fest 'festgestellt=False'.
# Diese Suite prueft die Umschaltung — und vor allem die Faelle, in denen sie
# still das Falsche tun koennte.
#
#   TA01 — RELEVANTE_KATEGORIEN sind gueltige Kategorien (faengt Tippfehler:
#          ein falscher Code wuerde NICHTS finden und wie 'nichts festgestellt'
#          aussehen).
#   TA02 — DIE QUERPROBE ZWISCHEN OBERFLAECHE UND RECHNUNG: die Liste ist
#          wortgleich mit MAHN_KATEGORIEN in toolbar/tatzeit_panel.js. Liefen
#          sie auseinander, mahnte die Maske dort, wo nichts gerechnet wird —
#          oder schwiege dort, wo es zaehlt.
#   TA03 — Eine harte Angabe: Befund 'festgestellt', frueheste == spaeteste,
#          nicht mehrdeutig.
#   TA04 — MEHRERE Angaben: die FRUEHESTE Beendigung verankert, die spaeteste
#          faehrt mit, 'mehrdeutig' ist gesetzt (Entscheidung mc 2026-07-26).
#   TA05 — Fehlt das Ende, gilt der Beginn (COALESCE(bis_ts, von_ts)).
#   TA06 — Unscharfe Angaben werden GEZAEHLT, aber nicht gerechnet.
#   TA07 — Angaben in anderen Kategorien werden GEZAEHLT, aber nicht gerechnet.
#   TA08 — Eine zurueckgenommene Angabe (deleted_at) rechnet nicht mehr.
#   TA09 — Eine BEARBEITETE Annotation: die Tatzeit folgt der neuen Fassung
#          ueber annotation_local_id. Die alte Fassung traegt deleted_at, und
#          das heisst hier 'geaendert', nicht 'geloescht'.
#   TA10 — WIRD DIE KATEGORIE AUF 176 GEAENDERT, rechnet die Tatzeit ab sofort
#          mit; wird sie weggeaendert, hoert sie auf. Die Kategorie wird von
#          der AKTUELLEN Fassung gelesen, nicht von der, an der die Tatzeit
#          haengt.
#   TA11 — Wird die Annotation GELOESCHT, verankert ihre Tatzeit nichts mehr.
#   TA12 — Fehlt 'annotation_tatzeit' (m002 nicht angewandt), ist der Befund
#          'ohne_tabelle' und NICHT 'nichts festgestellt'.
#   TA13 — Fehlt die Datei, ist der Befund 'ohne_evidence_db'.
#   TA14 — DIE UMSCHALTUNG: compute() liefert anker_art='tatzeit',
#          feststellung='festgestellt' und zitierfaehig=True.
#   TA15 — DIE RANGFOLGE: eine festgestellte Tatzeit schlaegt eine SPAETERE
#          belegte Tathandlung. Der Aktivitaetsbefund bleibt daneben stehen.
#   TA16 — OHNE evidence_dir wird NICHT still weitergerechnet: jede Zeile traegt
#          'nicht_geprueft', und der Bericht sagt es an erster Stelle.
#   TA17 — Der Bericht weist die Gegenrichtung zu den Aktivitaetsdaten
#          AUSDRUECKLICH aus — sonst liest jemand zwei Zeilen nebeneinander und
#          haelt sie fuer nach derselben Regel gerechnet.
#
# Version: v0.8.535 · Build: 535 · 2026-07-26
# =============================================================================

import re
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import date, datetime, time as dtime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.evidence as evidence_migrations        # noqa: E402
from db.evidence_db import VALID_CATEGORIES                          # noqa: E402
from management.deadlines.limitation import ANKER_ARTEN              # noqa: E402
from management.deadlines.limitation_params import load_params       # noqa: E402
from management.deadlines.limitation_repo import LimitationRepo      # noqa: E402
from management.deadlines.tatzeit_anker import (                     # noqa: E402
    RELEVANTE_KATEGORIEN, TATZEIT_BEFUNDE, read_tatzeit_anker,
)
from management.migrations.runner import MigrationRunner, discover   # noqa: E402

_WURZEL = Path(__file__).resolve().parent.parent

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

_CASES = """
CREATE TABLE cases (
    subject_id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
);
"""


def _ts(tag: str) -> int:
    return int(datetime.combine(date.fromisoformat(tag), dtime(0, 0),
                                tzinfo=timezone.utc).timestamp())


class _Evidence:
    """Kleine Vorrichtung: eine evidence_<uid>.db mit echtem m002-Schema."""

    def __init__(self, pfad: Path, mit_tatzeit_tabelle: bool = True):
        self.pfad = pfad
        self.con = sqlite3.connect(str(pfad))
        self.con.executescript(_ANNOTATIONS)
        self.con.commit()
        if mit_tatzeit_tabelle:
            # DIE ECHTE MIGRATION, nicht ein nachgebautes CREATE TABLE. Sonst
            # pruefte die Suite eine Welt, die der Code erwartet — genau der
            # Fehler, den Build 527 aufgedeckt hat.
            MigrationRunner(
                self.con,
                [m for m in discover(evidence_migrations) if m.VERSION <= 2]
            ).run()

    def annotation(self, *, kategorie="CAT_176", local_id=None,
                   deleted_at=None, prev_id=None, version_nr=1) -> int:
        cur = self.con.execute(
            'INSERT INTO "annotations" (page_url, category, text, ts, '
            'investigator_id, local_id, version_nr, prev_id, deleted_at) '
            'VALUES (?,?,?,?,?,?,?,?,?)',
            ("/viewtopic.php?id=1", kategorie, "t", 1700000000, 3, local_id,
             version_nr, prev_id, deleted_at))
        self.con.commit()
        return int(cur.lastrowid)

    def tatzeit(self, annotation_id, *, local_id=None, art="hart",
                von=None, bis=None, genauigkeit="tag",
                angabe_schluessel=None, angabe_wert=None,
                quelle="beitragstext", deleted_at=None) -> int:
        cur = self.con.execute(
            'INSERT INTO "annotation_tatzeit" (annotation_id, '
            'annotation_local_id, art, von_ts, bis_ts, genauigkeit, '
            'angabe_schluessel, angabe_wert, quelle, erfasst_von, '
            'erfasst_at, deleted_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (annotation_id, local_id, art, von, bis, genauigkeit,
             angabe_schluessel, angabe_wert, quelle, 7, 1700000100,
             deleted_at))
        self.con.commit()
        return int(cur.lastrowid)

    def close(self):
        try:
            self.con.close()
        except sqlite3.Error:
            pass


class TestTatzeitAnkerLeser(unittest.TestCase):
    """TA01-TA13: der Leser aus management/deadlines/tatzeit_anker.py."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.pfad = self.dir / "evidence_101.db"
        self.ev = _Evidence(self.pfad)

    def tearDown(self):
        self.ev.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def _lies(self):
        return read_tatzeit_anker(self.pfad, 101)

    # ===================================================================== TA01
    def test_TA01_kategorien_sind_gueltig(self):
        for code in RELEVANTE_KATEGORIEN:
            self.assertIn(
                code, VALID_CATEGORIES,
                "'%s' ist keine gueltige Annotationskategorie — der JOIN "
                "faende NICHTS, und das saehe aus wie 'nichts festgestellt'."
                % code)
        self.assertIn("tatzeit", ANKER_ARTEN)
        self.assertIn("festgestellt", TATZEIT_BEFUNDE)
        self.assertIn("nicht_geprueft", TATZEIT_BEFUNDE)

    # ===================================================================== TA02
    def test_TA02_oberflaeche_und_rechnung_mahnen_dasselbe(self):
        """
        Die Querprobe zwischen zwei Sprachen. toolbar/tatzeit_panel.js mahnt
        eine fehlende Tatzeit an; dieses Modul rechnet sie. Waeren die Listen
        verschieden, entstuende genau der Widerspruch, den niemand bemerkt:
        eine Warnung ohne Wirkung oder eine Wirkung ohne Warnung.
        """
        quelle = (_WURZEL / "toolbar" / "tatzeit_panel.js").read_text(
            encoding="utf-8")
        m = re.search(r"var MAHN_KATEGORIEN\s*=\s*\[([^\]]*)\]", quelle)
        self.assertIsNotNone(
            m, "MAHN_KATEGORIEN in tatzeit_panel.js nicht gefunden — der "
               "Abgleich zwischen Maske und Monitor ist damit unmoeglich.")
        js = tuple(re.findall(r"'([^']+)'", m.group(1)))
        self.assertEqual(
            js, RELEVANTE_KATEGORIEN,
            "Die Maske mahnt %r an, gerechnet wird mit %r." % (js,
                                                               RELEVANTE_KATEGORIEN))

    # ===================================================================== TA03
    def test_TA03_eine_harte_angabe(self):
        a = self.ev.annotation(local_id="abc")
        self.ev.tatzeit(a, local_id="abc", von=_ts("2020-03-01"),
                        bis=_ts("2020-03-05"))
        r = self._lies()
        self.assertEqual(r.befund, "festgestellt")
        self.assertTrue(r.hat_anker)
        self.assertEqual(r.anzahl_hart, 1)
        self.assertEqual(r.frueheste_beendigung, _ts("2020-03-05"))
        self.assertEqual(r.spaeteste_beendigung, _ts("2020-03-05"))
        self.assertFalse(r.mehrdeutig,
                         "Bei EINER Angabe ist nichts auszuwaehlen.")

    # ===================================================================== TA04
    def test_TA04_mehrere_angaben_die_fruehste_verankert(self):
        """
        DIE ENTSCHEIDUNG VON mc (2026-07-26). Sie ist die Gegenrichtung zur
        Regel fuer Aktivitaetsdaten, und genau deshalb wird sie hier
        festgehalten: wer sie spaeter 'vereinheitlicht', bricht diesen Test.
        """
        a1 = self.ev.annotation(local_id="a1")
        a2 = self.ev.annotation(local_id="a2")
        self.ev.tatzeit(a1, local_id="a1", von=_ts("2019-01-01"),
                        bis=_ts("2019-06-30"))
        self.ev.tatzeit(a2, local_id="a2", von=_ts("2022-01-01"),
                        bis=_ts("2022-12-31"))

        r = self._lies()
        self.assertEqual(r.anzahl_hart, 2)
        self.assertEqual(r.frueheste_beendigung, _ts("2019-06-30"),
                         "Verankern muss die FRUEHESTE Beendigung.")
        self.assertEqual(r.spaeteste_beendigung, _ts("2022-12-31"),
                         "Die spaeteste muss AUSGEWIESEN werden — sonst waere "
                         "die uebergangene Zahl unsichtbar.")
        self.assertTrue(r.mehrdeutig)

    # ===================================================================== TA05
    def test_TA05_ohne_ende_gilt_der_beginn(self):
        a = self.ev.annotation(local_id="abc")
        self.ev.tatzeit(a, local_id="abc", von=_ts("2021-05-05"), bis=None)
        r = self._lies()
        self.assertEqual(r.frueheste_beendigung, _ts("2021-05-05"))

        # Und umgekehrt: nur ein Ende, kein Beginn.
        b = self.ev.annotation(local_id="zzz")
        self.ev.tatzeit(b, local_id="zzz", von=None, bis=_ts("2019-02-02"))
        r2 = self._lies()
        self.assertEqual(r2.frueheste_beendigung, _ts("2019-02-02"))
        self.assertEqual(r2.spaeteste_beendigung, _ts("2021-05-05"))

    # ===================================================================== TA06
    def test_TA06_unscharfe_angaben_zaehlen_aber_rechnen_nicht(self):
        a = self.ev.annotation(local_id="abc")
        self.ev.tatzeit(a, local_id="abc", art="weich", genauigkeit="unbestimmt",
                        angabe_schluessel="markierung",
                        angabe_wert="vor zwei Jahren")
        r = self._lies()
        self.assertEqual(r.befund, "ohne_feststellung")
        self.assertFalse(r.hat_anker)
        self.assertEqual(r.anzahl_weich, 1)
        # Und sie wird BENANNT — nicht bloss weggelassen.
        self.assertIn("unscharfe", r.detail)

    # ===================================================================== TA07
    def test_TA07_fremde_kategorien_zaehlen_aber_rechnen_nicht(self):
        a = self.ev.annotation(kategorie="CAT_PERSON", local_id="p1")
        self.ev.tatzeit(a, local_id="p1", von=_ts("2020-01-01"))
        r = self._lies()
        self.assertEqual(r.befund, "ohne_feststellung")
        self.assertEqual(r.anzahl_fremde_kategorie, 1)
        self.assertIn("anderen Kategorien", r.detail)

    # ===================================================================== TA08
    def test_TA08_zurueckgenommene_angabe_rechnet_nicht(self):
        a = self.ev.annotation(local_id="abc")
        tz = self.ev.tatzeit(a, local_id="abc", von=_ts("2020-01-01"))
        self.assertTrue(self._lies().hat_anker)

        self.ev.con.execute(
            'UPDATE "annotation_tatzeit" SET deleted_at = 1700009999 '
            'WHERE id = ?', (tz,))
        self.ev.con.commit()
        r = self._lies()
        self.assertFalse(r.hat_anker)
        self.assertEqual(r.befund, "ohne_feststellung")

    # ===================================================================== TA09
    def test_TA09_tatzeit_folgt_der_bearbeiteten_annotation(self):
        """
        'annotations' ist append-only: eine Bearbeitung markiert die alte
        Fassung mit deleted_at und legt eine neue an. Das heisst hier
        'geaendert', NICHT 'geloescht' (db/evidence_db.py:886-891). Die
        Tatzeit haengt an der ALTEN Fassung und muss trotzdem weiterrechnen —
        aufgeloest ueber annotation_local_id.
        """
        alt = self.ev.annotation(local_id="abc")
        self.ev.tatzeit(alt, local_id="abc", von=_ts("2020-01-01"))
        self.assertTrue(self._lies().hat_anker)

        # Bearbeiten: alte Fassung markieren, neue anlegen.
        self.ev.con.execute(
            'UPDATE "annotations" SET deleted_at = 1700005000 WHERE id = ?',
            (alt,))
        self.ev.con.commit()
        self.ev.annotation(local_id="abc", prev_id=alt, version_nr=2)

        r = self._lies()
        self.assertTrue(
            r.hat_anker,
            "Nach dem Bearbeiten der Annotation ist die Tatzeit verloren — "
            "die Aufloesung ueber annotation_local_id greift nicht.")
        self.assertEqual(r.frueheste_beendigung, _ts("2020-01-01"))

    # ===================================================================== TA10
    def test_TA10_kategoriewechsel_wirkt_sofort(self):
        """
        Die Kategorie wird von der AKTUELLEN Fassung gelesen. Wer eine
        Annotation von 176 auf PERSON umstellt, nimmt ihre Tatzeit aus der
        Rechnung — und umgekehrt. Wuerde stattdessen die Fassung gelesen, an
        der die Tatzeit haengt, bliebe eine laengst umgewidmete Annotation
        fristbestimmend.
        """
        alt = self.ev.annotation(kategorie="CAT_176", local_id="abc")
        self.ev.tatzeit(alt, local_id="abc", von=_ts("2020-01-01"))
        self.assertTrue(self._lies().hat_anker)

        # Neue Fassung mit anderer Kategorie.
        self.ev.con.execute(
            'UPDATE "annotations" SET deleted_at = 1700005000 WHERE id = ?',
            (alt,))
        self.ev.con.commit()
        neu = self.ev.annotation(kategorie="CAT_PERSON", local_id="abc",
                                 prev_id=alt, version_nr=2)
        r = self._lies()
        self.assertFalse(r.hat_anker,
                         "Die Tatzeit rechnet weiter, obwohl die Annotation "
                         "nicht mehr §§ 176/184 betrifft.")
        self.assertEqual(r.anzahl_fremde_kategorie, 1)

        # Und wieder zurueck auf 184 — sie rechnet erneut mit.
        self.ev.con.execute(
            'UPDATE "annotations" SET deleted_at = 1700006000 WHERE id = ?',
            (neu,))
        self.ev.con.commit()
        self.ev.annotation(kategorie="CAT_184", local_id="abc", prev_id=neu,
                           version_nr=3)
        self.assertTrue(self._lies().hat_anker)

    # ===================================================================== TA11
    def test_TA11_geloeschte_annotation_verankert_nichts(self):
        a = self.ev.annotation(local_id="abc")
        self.ev.tatzeit(a, local_id="abc", von=_ts("2020-01-01"))
        # Loeschen = deleted_at OHNE Nachfolger.
        self.ev.con.execute(
            'UPDATE "annotations" SET deleted_at = 1700005000 WHERE id = ?',
            (a,))
        self.ev.con.commit()
        r = self._lies()
        self.assertFalse(r.hat_anker)
        # Die Tatzeitzeile bleibt in der Datenbank stehen — sie ist
        # Beweismittel und wird nie entfernt.
        self.assertEqual(
            self.ev.con.execute(
                'SELECT COUNT(*) FROM "annotation_tatzeit"').fetchone()[0], 1)

    # ===================================================================== TA12
    def test_TA12_fehlende_tabelle_wird_benannt(self):
        pfad = self.dir / "evidence_202.db"
        ev = _Evidence(pfad, mit_tatzeit_tabelle=False)
        try:
            r = read_tatzeit_anker(pfad, 202)
            self.assertEqual(r.befund, "ohne_tabelle")
            self.assertFalse(r.hat_anker)
            # Der entscheidende Satz: nicht "nichts festgestellt".
            self.assertIn("NICHT gesagt", r.detail)
            self.assertIn("m002", r.detail)
        finally:
            ev.close()

    # ===================================================================== TA13
    def test_TA13_fehlende_datei_ist_kein_fehler(self):
        r = read_tatzeit_anker(self.dir / "evidence_999.db", 999)
        self.assertEqual(r.befund, "ohne_evidence_db")
        self.assertFalse(r.hat_anker)
        self.assertEqual(r.fehler, ())


class TestLimitationMitTatzeit(unittest.TestCase):
    """TA14-TA17: die Umschaltung in LimitationRepo.compute()."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.forensic = self.dir / "forensic"
        self.evidence = self.dir / "evidence"
        self.forensic.mkdir()
        self.evidence.mkdir()

        self.cdb = self.dir / "coordinator.db"
        con = sqlite3.connect(str(self.cdb))
        con.executescript(_CASES)
        con.execute("INSERT INTO cases (subject_id, username) VALUES (?,?)",
                    (101, "beschuldigter"))
        con.commit()
        con.close()

        # Aktivitaetsdaten: SPAETESTE Handlung 2023-01-01.
        fcon = sqlite3.connect(str(self.forensic / "forensic_101.db"))
        fcon.execute("CREATE TABLE uid_posts (post_id INTEGER PRIMARY KEY, "
                     "topic_id INTEGER, forum_id INTEGER, posted_ts INTEGER)")
        for i, t in enumerate((_ts("2020-01-01"), _ts("2023-01-01"))):
            fcon.execute("INSERT INTO uid_posts (post_id, topic_id, forum_id, "
                         "posted_ts) VALUES (?,?,?,?)", (i + 1, 1, 1, t))
        fcon.commit()
        fcon.close()

        self.ev = _Evidence(self.evidence / "evidence_101.db")
        self.params = load_params()

    def tearDown(self):
        self.ev.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def _bericht(self, *, mit_evidence=True):
        con = sqlite3.connect("file:%s?mode=ro" % self.cdb, uri=True)
        con.row_factory = sqlite3.Row
        try:
            repo = LimitationRepo(
                con, self.forensic,
                self.evidence if mit_evidence else None)
            return repo.compute(params=self.params, now_ts=_ts("2026-07-26"))
        finally:
            con.close()

    # ===================================================================== TA14
    def test_TA14_umschaltung_auf_festgestellt(self):
        a = self.ev.annotation(local_id="abc")
        self.ev.tatzeit(a, local_id="abc", von=_ts("2021-05-01"),
                        bis=_ts("2021-05-02"))

        b = self._bericht()
        self.assertEqual(len(b.rows), 1)
        zeile = b.rows[0]
        self.assertEqual(zeile.assessment.anker_art, "tatzeit")
        self.assertEqual(zeile.assessment.feststellung, "festgestellt")
        self.assertEqual(zeile.assessment.tatzeit_ts, _ts("2021-05-02"))

        d = zeile.to_dict()
        self.assertTrue(d["zitierfaehig"],
                        "Eine FESTGESTELLTE Tatzeit muss zitierfaehig sein — "
                        "sonst haette die ganze Achse keinen Zweck.")
        self.assertTrue(d["anker_art_stimmig"],
                        "Tatzeitteil und Rechenschicht fuehren verschiedene "
                        "Anker — die Verdrahtung ist falsch.")
        self.assertEqual(d["tatzeit_feststellung_befund"], "festgestellt")
        self.assertEqual(b.anker_verteilung.get("tatzeit"), 1)
        self.assertEqual(b.feststellung_verteilung.get("festgestellt"), 1)
        self.assertEqual(b.tatzeit_befunde.get("festgestellt"), 1)

    # ===================================================================== TA15
    def test_TA15_feststellung_schlaegt_spaetere_aktivitaet(self):
        """
        Die Rangfolge. Die spaeteste belegte Tathandlung liegt 2023-01-01, die
        festgestellte Tatzeit endet 2021-05-02 — also FRUEHER. Trotzdem
        verankert die Feststellung: was ein Mensch festgestellt hat, wiegt
        schwerer als was aus Aktivitaetsdaten abgeleitet wurde.
        """
        ohne = self._bericht()
        self.assertEqual(ohne.rows[0].assessment.anker_art, "aktivitaet")
        self.assertEqual(ohne.rows[0].assessment.tatzeit_ts, _ts("2023-01-01"))
        self.assertEqual(ohne.rows[0].assessment.feststellung, "vorlaeufig")

        a = self.ev.annotation(local_id="abc")
        self.ev.tatzeit(a, local_id="abc", von=_ts("2021-05-01"),
                        bis=_ts("2021-05-02"))

        mit = self._bericht()
        self.assertEqual(mit.rows[0].assessment.tatzeit_ts, _ts("2021-05-02"))
        # Der AKTIVITAETSbefund bleibt daneben stehen — die beiden Achsen
        # werden nicht vermischt.
        self.assertEqual(mit.rows[0].tatzeit.befund, "belegt")
        self.assertEqual(mit.rows[0].tatzeit.spaeteste_ts, _ts("2023-01-01"))

    # ===================================================================== TA16
    def test_TA16_ohne_evidence_dir_wird_es_gesagt(self):
        a = self.ev.annotation(local_id="abc")
        self.ev.tatzeit(a, local_id="abc", von=_ts("2021-05-01"))

        b = self._bericht(mit_evidence=False)
        self.assertEqual(b.tatzeit_befunde.get("nicht_geprueft"), 1)
        self.assertEqual(b.rows[0].assessment.anker_art, "aktivitaet")
        self.assertEqual(b.rows[0].assessment.feststellung, "vorlaeufig")
        # Und es steht GANZ OBEN in den Hinweisen: eine Liste, die aussieht wie
        # ausgewertet, es aber nicht ist, waere der gefaehrlichste Beleg.
        self.assertIn("NICHT GEPRUEFT", b.hinweise[0])
        self.assertIn("VORLAEUFIG", b.hinweise[0])

    # ===================================================================== TA17
    def test_TA17_die_gegenrichtung_wird_ausgewiesen(self):
        a1 = self.ev.annotation(local_id="a1")
        a2 = self.ev.annotation(local_id="a2")
        self.ev.tatzeit(a1, local_id="a1", von=_ts("2019-01-01"),
                        bis=_ts("2019-06-30"))
        self.ev.tatzeit(a2, local_id="a2", von=_ts("2022-01-01"),
                        bis=_ts("2022-12-31"))

        b = self._bericht()
        self.assertEqual(b.faelle_mehrdeutig, 1)
        text = " ".join(b.hinweise)
        self.assertIn("FRUEHESTE", text)
        self.assertIn("Gegenrichtung", text,
                      "Der Bericht sagt nicht, dass hier anders gerechnet wird "
                      "als bei den Aktivitaetsdaten — dann liest jemand zwei "
                      "Zeilen nebeneinander und haelt sie fuer gleich.")
        self.assertIn("MEHRERE festgestellte", text)

        d = b.rows[0].to_dict()
        self.assertEqual(d["tatzeit_frueheste_beendigung"], _ts("2019-06-30"))
        self.assertEqual(d["tatzeit_spaeteste_beendigung"], _ts("2022-12-31"))
        self.assertTrue(d["tatzeit_mehrdeutig"])
        # Gerechnet wird mit der FRUEHESTEN.
        self.assertEqual(b.rows[0].assessment.tatzeit_ts, _ts("2019-06-30"))


if __name__ == "__main__":
    unittest.main()
