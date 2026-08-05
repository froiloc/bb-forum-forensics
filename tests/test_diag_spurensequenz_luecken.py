# =============================================================================
# tests/test_diag_spurensequenz_luecken.py
# IT-Forensisches Ermittlungswerkzeug — Regression zu tools/diag_spurensequenz_luecken.py
# =============================================================================
# Was hier bewacht wird (Vorgang 2f1044b9):
#
#   SL01 - Die Selbstprobe des Werkzeugs besteht. Sie ist der Grund, dem
#          Ergebnis zu trauen; faellt sie, darf kein Ergebnis ausgewiesen
#          werden.
#   SL02 - Gegen einen Wegwerf-Bestand mit BEKANNTER Luecke findet das
#          Werkzeug genau diese Luecke und meldet Rueckgabewert 1.
#   SL03 - Gegen einen Bestand OHNE Luecke meldet es 0 und keine Luecke.
#          Ein Waechter, der immer anschlaegt, ist keiner.
#   SL04 - DER WICHTIGSTE FALL: die Datenbankdatei ist nach dem Lauf
#          BYTEGLEICH. Das Werkzeug wird auf Bestaende losgelassen, die
#          Beweismittel sind; die Zusicherung 'nur lesend' muss gemessen
#          werden und nicht nur behauptet.
#   SL05 - Die TYPE_MAP im Werkzeug stimmt mit der in db/forensic_db.py
#          ueberein. Das Werkzeug misst, was der Produktivcode TUT. Weicht
#          die Abschrift ab, misst es etwas anderes - und niemand merkt es.
#
# Version: v0.8.671 - Build: 671 - 2026-08-05
# =============================================================================

from __future__ import annotations

import ast
import hashlib
import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_WURZEL = Path(__file__).resolve().parent.parent
_WERKZEUG = _WURZEL / "tools" / "diag_spurensequenz_luecken.py"


def _lade_werkzeug():
    """Laedt das Werkzeug als Modul, ohne es als Skript auszufuehren."""
    spec = importlib.util.spec_from_file_location(
        "diag_spurensequenz_luecken", _WERKZEUG)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["diag_spurensequenz_luecken"] = modul
    spec.loader.exec_module(modul)
    return modul


def _baue_bestand(pfad: Path, seiten: list[str], ziele: list[tuple]) -> None:
    """
    Legt einen Wegwerf-Bestand in der Form von forensic_<uid>.db an.

    ziele: (url_type, topic_id, actor_user_id)
    """
    con = sqlite3.connect(pfad)
    con.executescript("""
        CREATE TABLE forensic_meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO forensic_meta VALUES ('protocol','http'),
                                         ('domainname','alice.onion');
        CREATE TABLE pages (id INTEGER PRIMARY KEY, url_canonical TEXT,
                            html BLOB, title TEXT);
        CREATE TABLE page_aliases (page_id INTEGER, url_raw TEXT);
        CREATE TABLE scrape_targets (
            id INTEGER PRIMARY KEY, scrape_context TEXT, url_type TEXT,
            forum_id INTEGER, topic_id INTEGER, post_id INTEGER,
            pm_topic_id INTEGER, pm_post_id INTEGER, thanks_post_id INTEGER,
            poll_topic_id INTEGER, actor_user_id INTEGER,
            actor_username TEXT, static_url TEXT, source_tables TEXT);
    """)
    for i, u in enumerate(seiten, 1):
        con.execute("INSERT INTO pages VALUES (?,?,NULL,?)",
                    (i, "http://alice.onion" + u, "Titel %d" % i))
    for i, (typ, topic, actor) in enumerate(ziele, 1):
        con.execute(
            "INSERT INTO scrape_targets "
            "(id, scrape_context, url_type, topic_id, actor_user_id, "
            " source_tables) VALUES (?,'user',?,?,?,'probe')",
            (i, typ, topic, actor))
    con.commit()
    con.close()


class DiagSpurensequenzTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.modul = _lade_werkzeug()

    def setUp(self):
        # Das Werkzeug sammelt seine Ausgabe in einer Modulvariablen. Ohne
        # Leeren wuechse sie ueber die Faelle hinweg und die Protokolldatei
        # eines Falls enthielte die Zeilen des vorigen.
        self.modul.LOGLINES.clear()

    # -- SL01 -----------------------------------------------------------------
    def test_sl01_selbstprobe_besteht(self):
        ok, begruendung = self.modul.selbstprobe()
        self.assertTrue(ok, "Selbstprobe fehlgeschlagen: %s" % begruendung)
        self.assertIn("4 bekannte Luecken", begruendung)

    # -- SL02 -----------------------------------------------------------------
    def test_sl02_bekannte_luecke_wird_gefunden(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "forensic_probe.db"
            _baue_bestand(
                db,
                seiten=[
                    "/forum/viewtopic.php?id=500",
                    "/forum/viewtopic.php?id=500&p=2",
                    "/forum/viewtopic.php?id=500&p=3",
                ],
                ziele=[("viewtopic", 500, None)],
            )
            con = self.modul.oeffne_lesend(db)
            basis = self.modul.basis_url(con)
            erg = self.modul.messe(self.modul.lade_urls(con, basis),
                                   self.modul.lade_ziele(con))
            con.close()

        self.assertEqual(1, len(erg["sequenz"]),
                         "die Sequenz fuehrt heute genau eine Seite je Thema")
        luecke = sorted(e["url"] for e in erg["luecke"])
        self.assertEqual(
            ["/forum/viewtopic.php?id=500&p=2",
             "/forum/viewtopic.php?id=500&p=3"], luecke,
            "genau die beiden Folgeseiten muessen als uebergangen gelten")

    # -- SL03 -----------------------------------------------------------------
    def test_sl03_ohne_luecke_kein_befund(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "forensic_probe.db"
            _baue_bestand(
                db,
                seiten=["/forum/viewtopic.php?id=500"],
                ziele=[("viewtopic", 500, None)],
            )
            con = self.modul.oeffne_lesend(db)
            basis = self.modul.basis_url(con)
            erg = self.modul.messe(self.modul.lade_urls(con, basis),
                                   self.modul.lade_ziele(con))
            con.close()
        self.assertEqual([], erg["luecke"],
                         "ein Waechter, der immer anschlaegt, ist keiner")
        self.assertEqual(1, len(erg["sequenz"]))

    # -- SL04 -----------------------------------------------------------------
    def test_sl04_datenbank_bleibt_bytegleich(self):
        """
        Die Zusicherung 'nur lesend' wird gemessen, nicht geglaubt.

        Geprueft wird die Pruefsumme der Datei UND die Abwesenheit von
        Journal-Nebendateien: ein '-wal' oder '-journal' waere der Beleg, dass
        eine Schreibabsicht bestand, selbst wenn die Hauptdatei gleich bliebe.
        """
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "forensic_probe.db"
            _baue_bestand(
                db,
                seiten=["/forum/viewtopic.php?id=500",
                        "/forum/viewtopic.php?id=500&p=2"],
                ziele=[("viewtopic", 500, None)],
            )
            vorher = hashlib.md5(db.read_bytes()).hexdigest()

            con = self.modul.oeffne_lesend(db)
            basis = self.modul.basis_url(con)
            self.modul.messe(self.modul.lade_urls(con, basis),
                             self.modul.lade_ziele(con))
            con.close()

            nachher = hashlib.md5(db.read_bytes()).hexdigest()
            self.assertEqual(vorher, nachher,
                             "die Datenbankdatei wurde veraendert")
            for anhang in ("-wal", "-shm", "-journal"):
                self.assertFalse(
                    Path(str(db) + anhang).exists(),
                    "Nebendatei '%s' entstanden - es gab eine Schreibabsicht"
                    % anhang)

    # -- SL05 -----------------------------------------------------------------
    def test_sl05_type_map_ist_wortgleiche_abschrift(self):
        """
        Vergleicht die TYPE_MAP des Werkzeugs mit der in
        db/forensic_db.py, get_trace_sequence().

        Gelesen wird ueber den Syntaxbaum, nicht ueber einen Import: das
        Modul zieht den halben Serverunterbau nach, und dieser Fall soll
        auch dann noch laufen, wenn dort etwas klemmt.
        """
        quelle = (_WURZEL / "db" / "forensic_db.py").read_text(encoding="utf-8")
        baum = ast.parse(quelle)

        gefunden = None
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Assign):
                continue
            ziele = [z.id for z in knoten.targets if isinstance(z, ast.Name)]
            if "TYPE_MAP" not in ziele:
                continue
            try:
                gefunden = ast.literal_eval(knoten.value)
            except ValueError:                     # pragma: no cover
                continue
            break

        self.assertIsNotNone(
            gefunden, "TYPE_MAP in db/forensic_db.py nicht auffindbar - "
                      "wurde sie umbenannt? Dann ist die Abschrift im "
                      "Werkzeug ungeprueft.")
        self.assertEqual(
            gefunden, self.modul.TYPE_MAP,
            "Die Abschrift im Diagnosewerkzeug weicht vom Produktivcode ab. "
            "Das Werkzeug misst dann etwas anderes als das, was laeuft.")


if __name__ == "__main__":
    unittest.main()
