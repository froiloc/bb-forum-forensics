# =============================================================================
# tests/test_forensic_index_upgrade.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7
# =============================================================================
# Testsuite fuer Build 531: das Index-Upgrade auf bestehenden
# forensic_<uid>.db (management/maintenance/forensic_index_upgrade.py).
#
# Diese Suite prueft ein Werkzeug, das BEWEISMITTELDATEIEN VERAENDERT. Der
# Schwerpunkt liegt deshalb nicht auf 'der Index ist da', sondern auf den
# Zusicherungen drumherum:
#
#   FI01 — Der TROCKENLAUF ist die Vorgabe: ohne ausfuehren=True wird KEIN
#          Index angelegt, und die Datei aendert sich BYTEWEISE nicht.
#   FI02 — Die Kandidatenliste wird aus ZEITQUELLEN abgeleitet, nicht gepflegt:
#          eine bereits indizierte Zeitquelle ist kein Kandidat, eine nicht
#          indizierte schon.
#   FI03 — Ein Index, dessen erste Spalte eine ANDERE ist, zaehlt NICHT als
#          vorhanden (fuer MIN/MAX nutzt SQLite nur den Indexanfang).
#   FI04 — Der Lauf legt die Indizes an, benennt sie mit dem Praefix 'aiw_' und
#          meldet 'geaendert'.
#   FI05 — DER KERN: der INHALT bleibt nachweislich gleich (Inhaltshash und
#          Zeilenzahlen vorher = nachher), waehrend sich die DATEI-Pruefsumme
#          aendert. Genau diese Unterscheidung ist der Zweck des Werkzeugs.
#   FI06 — Der zweite Lauf meldet 'aktuell' und schreibt nichts mehr
#          (Wiederholbarkeit ohne Nebenwirkung).
#   FI07 — Der Inhaltshash ist INDEXUNABHAENGIG: derselbe Wert vor und nach dem
#          Anlegen, in BEIDEN Pruestiefen.
#   FI08 — Eine WAL-gestempelte Datei wird UEBERSPRUNGEN und nicht umgestellt
#          (WAL-Verbot Build 499) — mit Begruendung und Verweis auf das
#          zustaendige Werkzeug.
#   FI09 — Eine kaputte/fremde Datei wird zu 'fehler' und bricht den Lauf NICHT
#          ab; die uebrigen Dateien werden trotzdem behandelt (Grundregel 1).
#   FI10 — Fehlende Tabelle bzw. fehlende Spalte sind KEIN Fehler und KEIN
#          Kandidat (nicht jede Falldatenbank fuehrt jede Tabelle).
#   FI11 — 'grenze' begrenzt den Lauf, und die Zahl der NICHT betrachteten
#          Dateien steht im Protokoll (keine stille Begrenzung).
#   FI12 — Das Protokoll ist vollstaendig und JSON-faehig; es nennt Prueftiefe,
#          Kandidaten und Praefix.
#   FI13 — Eine unbekannte Prueftiefe ist ein harter Fehler, kein Rueckfall.
#   FI14 — Der Index wird von SQLite auch BENUTZT (EXPLAIN QUERY PLAN) — sonst
#          waere die ganze Aenderung wirkungslos und das Werkzeug ein
#          Selbstzweck.
# =============================================================================

import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.deadlines.limitation_repo import ZEITQUELLEN        # noqa: E402
from management.maintenance.forensic_index_upgrade import (         # noqa: E402
    INDEX_PRAEFIX,
    ForensicIndexUpgrade,
    ForensicIndexUpgradeError,
    index_name,
)


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _fdb(pfad: Path, *, posts=(), pms=(), mit_pms=True,
         posts_index=False) -> None:
    """
    Eine minimale forensic_<uid>.db mit dem ECHTEN Schema.

    BELEG: forensic_uid.db.schema.sql (mc, 2026-07-25). Die Indexlage ist
    ebenfalls aus dem DDL uebernommen: uid_posts wird dort auf topic_id,
    forum_id und active indiziert — NICHT auf posted_ts. Genau diese Luecke
    schliesst das Werkzeug.
    """
    con = sqlite3.connect(str(pfad))
    try:
        con.execute(
            'CREATE TABLE "uid_posts" ("post_id" INTEGER, "topic_id" INTEGER '
            'NOT NULL, "forum_id" INTEGER NOT NULL, "posted_ts" INTEGER, '
            '"active" INTEGER NOT NULL DEFAULT 0, PRIMARY KEY("post_id"))')
        con.execute('CREATE INDEX "uid_posts_topic_idx" ON "uid_posts" '
                    '("topic_id")')
        con.execute('CREATE INDEX "uid_posts_active_idx" ON "uid_posts" '
                    '("active")')
        if posts_index:
            # Der Zustand NACH einer Prepper-Anpassung: die Zeitspalte hat
            # bereits einen Index, nur unter anderem Namen.
            con.execute('CREATE INDEX "uid_posts_ts_idx" ON "uid_posts" '
                        '("posted_ts")')
        for i, t in enumerate(posts):
            con.execute("INSERT INTO uid_posts (post_id, topic_id, forum_id, "
                        "posted_ts) VALUES (?,?,?,?)", (i + 1, 10, 20, t))
        if mit_pms:
            con.execute(
                'CREATE TABLE "uid_pms_posts" ("pm_post_id" INTEGER, '
                '"pm_topic_id" INTEGER NOT NULL, "posted_ts" INTEGER, '
                '"active" INTEGER NOT NULL DEFAULT 0, '
                'PRIMARY KEY("pm_post_id"))')
            con.execute('CREATE INDEX "uid_pms_posts_topic_idx" ON '
                        '"uid_pms_posts" ("pm_topic_id")')
            for i, t in enumerate(pms):
                con.execute("INSERT INTO uid_pms_posts (pm_post_id, "
                            "pm_topic_id, posted_ts) VALUES (?,?,?)",
                            (500 + i, 7, t))
        con.commit()
    finally:
        con.close()


class TestForensicIndexUpgrade(unittest.TestCase):

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _werk(self, tiefe="fingerabdruck"):
        return ForensicIndexUpgrade(self.dir, prueftiefe=tiefe)

    # -- Trockenlauf und Kandidatenbildung -----------------------------------

    def test_FI01_trockenlauf_ist_die_vorgabe(self):
        p = self.dir / "forensic_11.db"
        _fdb(p, posts=[1600000000, 1700000000])
        vorher = _md5(p)

        pr = self._werk().lauf()                      # ausfuehren fehlt
        self.assertFalse(pr.ausgefuehrt)
        self.assertEqual(pr.zaehler.get("geplant"), 1)
        self.assertNotIn("geaendert", pr.zaehler)
        b = pr.befunde[0]
        self.assertEqual(b.zustand, "geplant")
        self.assertEqual(b.angelegt, ())
        self.assertIn("TROCKENLAUF", b.grund)
        # DIE eigentliche Zusicherung: die Datei ist byteweise unberuehrt.
        self.assertEqual(_md5(p), vorher)

    def test_FI02_kandidaten_kommen_aus_ZEITQUELLEN(self):
        p = self.dir / "forensic_12.db"
        _fdb(p, posts=[1600000000])
        werk = self._werk()
        # Die Kandidatenliste des Werkzeugs IST die Zeitquellenliste.
        self.assertEqual(list(werk._kandidaten),
                         [(q[0], q[1]) for q in ZEITQUELLEN])
        con = sqlite3.connect("file:%s?mode=ro" % p, uri=True)
        try:
            fehlt = werk.fehlende_indizes(con)
        finally:
            con.close()
        namen = {f[0] for f in fehlt}
        self.assertIn(index_name("uid_posts", "posted_ts"), namen)
        self.assertIn(index_name("uid_pms_posts", "posted_ts"), namen)

        # Ist die Spalte bereits indiziert (unter FREMDEM Namen), ist sie
        # KEIN Kandidat — das Werkzeug legt keinen zweiten Index an.
        p2 = self.dir / "forensic_13.db"
        _fdb(p2, posts=[1600000000], posts_index=True, mit_pms=False)
        con = sqlite3.connect("file:%s?mode=ro" % p2, uri=True)
        try:
            fehlt2 = werk.fehlende_indizes(con)
        finally:
            con.close()
        self.assertEqual(fehlt2, [])

    def test_FI03_index_mit_anderer_erster_spalte_zaehlt_nicht(self):
        """
        Fuer MIN/MAX nutzt SQLite einen Index nur, wenn die gesuchte Spalte an
        dessen ANFANG steht. Ein Index (topic_id, posted_ts) hilft also nicht —
        und darf hier nicht als 'vorhanden' durchgehen.
        """
        p = self.dir / "forensic_14.db"
        _fdb(p, posts=[1600000000], mit_pms=False)
        con = sqlite3.connect(str(p))
        con.execute('CREATE INDEX "kombi_idx" ON "uid_posts" '
                    '("topic_id", "posted_ts")')
        con.commit()
        con.close()
        con = sqlite3.connect("file:%s?mode=ro" % p, uri=True)
        try:
            fehlt = self._werk().fehlende_indizes(con)
        finally:
            con.close()
        self.assertEqual([f[0] for f in fehlt],
                         [index_name("uid_posts", "posted_ts")])

    # -- Der Schreiblauf ------------------------------------------------------

    def test_FI04_lauf_legt_die_indizes_an(self):
        p = self.dir / "forensic_15.db"
        _fdb(p, posts=[1600000000, 1700000000], pms=[1650000000])
        pr = self._werk().lauf(ausfuehren=True)
        self.assertTrue(pr.ausgefuehrt)
        b = pr.befunde[0]
        self.assertEqual(b.zustand, "geaendert", b.grund)
        self.assertEqual(set(b.angelegt),
                         {index_name("uid_posts", "posted_ts"),
                          index_name("uid_pms_posts", "posted_ts")})
        for name in b.angelegt:
            self.assertTrue(name.startswith(INDEX_PRAEFIX), name)
        con = sqlite3.connect("file:%s?mode=ro" % p, uri=True)
        try:
            da = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='index'")}
        finally:
            con.close()
        self.assertTrue(set(b.angelegt).issubset(da))

    def test_FI05_datei_aendert_sich_inhalt_nicht(self):
        """
        DER KERN DES WERKZEUGS. mc am 2026-07-25 ging davon aus, ein Index sei
        'keine den Hashwert veraendernde Anpassung'. Das stimmt fuer den
        INHALT und nicht fuer die DATEI — genau diese Unterscheidung wird hier
        festgehalten, damit sie nicht wieder verloren geht.
        """
        p = self.dir / "forensic_16.db"
        _fdb(p, posts=list(range(1600000000, 1600000200)),
             pms=[1650000000, 1650000001])
        datei_vorher = _md5(p)
        pr = self._werk().lauf(ausfuehren=True)
        b = pr.befunde[0]
        self.assertEqual(b.zustand, "geaendert", b.grund)

        # Der INHALT ist nachweislich derselbe ...
        self.assertTrue(b.unveraendert)
        self.assertEqual(b.inhalt_vorher, b.inhalt_nachher)
        self.assertEqual(b.zeilen_vorher, b.zeilen_nachher)
        self.assertEqual(b.integritaet_vorher, "ok")
        self.assertEqual(b.integritaet_nachher, "ok")
        # ... die DATEI aber nicht. Beides gehoert zur Aussage.
        self.assertNotEqual(_md5(p), datei_vorher)

    def test_FI06_zweiter_lauf_ist_folgenlos(self):
        p = self.dir / "forensic_17.db"
        _fdb(p, posts=[1600000000])
        self._werk().lauf(ausfuehren=True)
        nach_erstem = _md5(p)
        pr2 = self._werk().lauf(ausfuehren=True)
        self.assertEqual(pr2.befunde[0].zustand, "aktuell")
        self.assertEqual(pr2.befunde[0].angelegt, ())
        self.assertEqual(_md5(p), nach_erstem)

    def test_FI07_inhaltshash_ist_indexunabhaengig(self):
        for tiefe in ("fingerabdruck", "voll"):
            with self.subTest(tiefe=tiefe):
                d = Path(tempfile.mkdtemp())
                try:
                    p = d / "forensic_18.db"
                    _fdb(p, posts=[1600000000, 1700000000], pms=[1650000000])
                    werk = ForensicIndexUpgrade(d, prueftiefe=tiefe)
                    con = sqlite3.connect("file:%s?mode=ro" % p, uri=True)
                    try:
                        vorher = werk.inhaltshash(con)
                    finally:
                        con.close()
                    werk.lauf(ausfuehren=True)
                    con = sqlite3.connect("file:%s?mode=ro" % p, uri=True)
                    try:
                        nachher = werk.inhaltshash(con)
                    finally:
                        con.close()
                    self.assertEqual(vorher, nachher)
                    # Und er reagiert auf eine ECHTE Aenderung — sonst waere er
                    # als Beleg wertlos.
                    con = sqlite3.connect(str(p))
                    con.execute("INSERT INTO uid_posts (post_id, topic_id, "
                                "forum_id, posted_ts) VALUES (999,1,1,1)")
                    con.commit()
                    con.close()
                    con = sqlite3.connect("file:%s?mode=ro" % p, uri=True)
                    try:
                        self.assertNotEqual(werk.inhaltshash(con), nachher)
                    finally:
                        con.close()
                finally:
                    shutil.rmtree(d, ignore_errors=True)

    # -- Die Sicherheitsnetze -------------------------------------------------

    def test_FI08_wal_datei_wird_uebersprungen(self):
        p = self.dir / "forensic_19.db"
        _fdb(p, posts=[1600000000], mit_pms=False)
        con = sqlite3.connect(str(p))
        con.execute("PRAGMA journal_mode=WAL")
        con.close()
        vorher = _md5(p)
        pr = self._werk().lauf(ausfuehren=True)
        b = pr.befunde[0]
        self.assertEqual(b.zustand, "uebersprungen", b.grund)
        self.assertIn("WAL", b.grund)
        self.assertIn("convert_journal_mode", b.grund)
        # Der Journalmodus wird NICHT nebenbei umgestellt.
        self.assertEqual(_md5(p), vorher)

    def test_FI09_fehlerhafte_datei_bricht_den_lauf_nicht_ab(self):
        kaputt = self.dir / "forensic_20.db"
        kaputt.write_bytes(b"das ist keine sqlite-datei")
        gut = self.dir / "forensic_21.db"
        _fdb(gut, posts=[1600000000], mit_pms=False)

        pr = self._werk().lauf(ausfuehren=True)
        self.assertEqual(pr.dateien_gesamt, 2)
        zustaende = {Path(b.pfad).name: b.zustand for b in pr.befunde}
        self.assertEqual(zustaende["forensic_20.db"], "fehler")
        # DIE ZUSICHERUNG: die zweite Datei wurde trotzdem behandelt.
        self.assertEqual(zustaende["forensic_21.db"], "geaendert")
        self.assertEqual(pr.zaehler.get("fehler"), 1)

    def test_FI10_fehlende_tabelle_oder_spalte_ist_kein_fehler(self):
        p = self.dir / "forensic_22.db"
        con = sqlite3.connect(str(p))
        # uid_posts OHNE Zeitspalte, uid_pms_posts gar nicht vorhanden.
        con.execute('CREATE TABLE "uid_posts" ("post_id" INTEGER PRIMARY KEY, '
                    '"topic_id" INTEGER)')
        con.commit()
        con.close()
        pr = self._werk().lauf(ausfuehren=True)
        b = pr.befunde[0]
        self.assertEqual(b.zustand, "aktuell", b.grund)
        self.assertEqual(b.angelegt, ())

    def test_FI11_grenze_wird_ausgewiesen(self):
        for uid in (30, 31, 32):
            _fdb(self.dir / ("forensic_%d.db" % uid), posts=[1600000000],
                 mit_pms=False)
        pr = self._werk().lauf(grenze=1)
        self.assertEqual(pr.dateien_gesamt, 3)
        self.assertEqual(len(pr.befunde), 1)
        # KEINE stille Begrenzung: die ausgelassenen Dateien werden gezaehlt.
        self.assertEqual(pr.zaehler.get("nicht_betrachtet"), 2)

    def test_FI12_protokoll_ist_vollstaendig_und_json_faehig(self):
        p = self.dir / "forensic_33.db"
        _fdb(p, posts=[1600000000], mit_pms=False)
        pr = self._werk().lauf(ausfuehren=True)
        d = json.loads(json.dumps(pr.to_dict(), ensure_ascii=False))
        for key in ("verzeichnis", "ausgefuehrt", "prueftiefe", "kandidaten",
                    "index_praefix", "dateien_gesamt", "zaehler", "befunde",
                    "dauer_ms"):
            self.assertIn(key, d)
        self.assertEqual(d["index_praefix"], INDEX_PRAEFIX)
        b = d["befunde"][0]
        for key in ("pfad", "zustand", "grund", "angelegt", "inhalt_vorher",
                    "inhalt_nachher", "inhalt_unveraendert",
                    "integritaet_vorher", "integritaet_nachher"):
            self.assertIn(key, b)
        self.assertTrue(b["inhalt_unveraendert"])

    def test_FI13_unbekannte_prueftiefe_ist_ein_fehler(self):
        with self.assertRaises(ForensicIndexUpgradeError):
            ForensicIndexUpgrade(self.dir, prueftiefe="ungefaehr")
        with self.assertRaises(ForensicIndexUpgradeError):
            ForensicIndexUpgrade(self.dir / "gibt_es_nicht").lauf()

    def test_FI14_sqlite_benutzt_den_index_auch(self):
        """
        Ohne diesen Test waere das Werkzeug ein Selbstzweck: ein Index, den der
        Abfrageplaner nicht heranzieht, kostet Platz und bringt nichts.
        """
        p = self.dir / "forensic_34.db"
        _fdb(p, posts=list(range(1600000000, 1600001000)), mit_pms=False)
        con = sqlite3.connect("file:%s?mode=ro" % p, uri=True)
        try:
            plan_vorher = " ".join(str(r) for r in con.execute(
                "EXPLAIN QUERY PLAN SELECT MIN(posted_ts), MAX(posted_ts) "
                "FROM uid_posts"))
        finally:
            con.close()
        self.assertNotIn("INDEX", plan_vorher.upper())

        self._werk().lauf(ausfuehren=True)

        con = sqlite3.connect("file:%s?mode=ro" % p, uri=True)
        try:
            plan_nachher = " ".join(str(r) for r in con.execute(
                "EXPLAIN QUERY PLAN SELECT MIN(posted_ts), MAX(posted_ts) "
                "FROM uid_posts"))
        finally:
            con.close()
        self.assertIn(index_name("uid_posts", "posted_ts"), plan_nachher)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
