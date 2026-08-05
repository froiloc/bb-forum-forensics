# =============================================================================
# tests/test_pruefe_profilerfassung.py
# IT-Forensisches Ermittlungswerkzeug - Regression zu tools/pruefe_profilerfassung.py
# =============================================================================
# Vorgang 90e7c214. Was hier bewacht wird:
#
#   PP01 - Ein Fall, dem Profilseiten fehlen, wird als BETROFFEN erkannt, und
#          die fehlenden Kennungen werden genau benannt.
#   PP02 - Ein vollstaendiger Fall wird NICHT gemeldet. Ein Waechter, der
#          immer anschlaegt, ist keiner.
#   PP03 - DIE ZWEITE URL-FORM. Im Bestand steht die Kennung nicht immer
#          direkt hinter 'profile.php?':
#             /forum/profile.php?id=1488
#             /forum/profile.php?section=essentials&edit&id=1488
#          Wer nur die erste Form sucht, haelt die zweite fuer nicht vorhanden
#          und meldet eine Fehlmenge, die es nicht gibt. Beide Formen wurden
#          am 05.08.2026 im echten Bestand gemessen.
#   PP04 - Zweitadressen aus page_aliases zaehlen mit. Eine Profilseite, die
#          nur unter '/forum/beginner/...' gefuehrt wird, ist vorhanden.
#   PP05 - Die Datenbankdatei ist nach dem Lauf BYTEGLEICH und es entsteht
#          keine Journal-Nebendatei. Das Werkzeug laeuft ueber Bestaende, die
#          Beweismittel sind.
#
# Version: v0.8.675 - Build: 675 - 2026-08-05
# =============================================================================

from __future__ import annotations

import hashlib
import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_WURZEL = Path(__file__).resolve().parent.parent
_WERKZEUG = _WURZEL / "tools" / "pruefe_profilerfassung.py"

BASIS = "http://alice.onion"


def _lade_werkzeug():
    spec = importlib.util.spec_from_file_location(
        "pruefe_profilerfassung", _WERKZEUG)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["pruefe_profilerfassung"] = modul
    spec.loader.exec_module(modul)
    return modul


def _baue_fall(pfad: Path, *, benutzer: str, ziel_ids: list[int],
               seiten: list[str], aliasse: list[tuple[int, str]] = ()) -> None:
    """Legt einen Wegwerf-Fall in der Form von forensic_<uid>.db an."""
    con = sqlite3.connect(pfad)
    con.executescript("""
        CREATE TABLE forensic_meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE pages (id INTEGER PRIMARY KEY, url_canonical TEXT,
                            html BLOB, title TEXT);
        CREATE TABLE page_aliases (page_id INTEGER, url_raw TEXT);
        CREATE TABLE scrape_targets (
            id INTEGER PRIMARY KEY, scrape_context TEXT, url_type TEXT,
            forum_id INTEGER, topic_id INTEGER, post_id INTEGER,
            pm_topic_id INTEGER, actor_user_id INTEGER, source_tables TEXT);
    """)
    con.execute("INSERT INTO forensic_meta VALUES ('username', ?)", (benutzer,))
    con.execute("INSERT INTO forensic_meta VALUES ('user_id', '4711')")
    con.execute("INSERT INTO forensic_meta VALUES ('protocol', 'http')")
    con.execute("INSERT INTO forensic_meta VALUES ('domainname', 'alice.onion')")
    for i, u in enumerate(seiten, 1):
        con.execute("INSERT INTO pages VALUES (?,?,NULL,?)",
                    (i, BASIS + u, "Seite %d" % i))
    for page_id, u in aliasse:
        con.execute("INSERT INTO page_aliases VALUES (?,?)", (page_id, BASIS + u))
    for i, uid in enumerate(ziel_ids, 1):
        con.execute(
            "INSERT INTO scrape_targets (id, scrape_context, url_type, "
            "actor_user_id, source_tables) VALUES (?,'user','other_profile',?,'p')",
            (i, uid))
    con.commit()
    con.close()


class PruefeProfilerfassungTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.modul = _lade_werkzeug()

    def setUp(self):
        self.modul.LOGLINES.clear()

    # -- PP01 -----------------------------------------------------------------
    def test_pp01_fehlende_profilseiten_werden_benannt(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "forensic_4711.db"
            _baue_fall(db, benutzer="AliceX", ziel_ids=[1488, 2000, 3000],
                       seiten=["/forum/profile.php?id=1488"])
            e = self.modul.pruefe_fall(db)

        self.assertIsNone(e["fehler"])
        self.assertEqual("4711", e["subject_id"])
        self.assertEqual("AliceX", e["benutzername"])
        self.assertEqual(3, e["ziele"])
        self.assertEqual(1, e["vorhanden"])
        self.assertEqual(2, e["fehlend"])
        self.assertEqual(["2000", "3000"], e["fehlende_kennungen"])

    # -- PP02 -----------------------------------------------------------------
    def test_pp02_vollstaendiger_fall_wird_nicht_gemeldet(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "forensic_4711.db"
            _baue_fall(db, benutzer="AliceX", ziel_ids=[1488, 2000],
                       seiten=["/forum/profile.php?id=1488",
                               "/forum/profile.php?id=2000"])
            e = self.modul.pruefe_fall(db)
        self.assertEqual(0, e["fehlend"],
                         "Ein Waechter, der immer anschlaegt, ist keiner.")
        self.assertEqual(2, e["vorhanden"])

    # -- PP03 -----------------------------------------------------------------
    def test_pp03_kennung_auch_hinter_weiteren_parametern(self):
        """
        Beide Formen wurden am 05.08.2026 im echten Bestand gemessen. Wer nur
        'profile.php?id=' sucht, meldet eine Fehlmenge, die es nicht gibt.
        """
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "forensic_4711.db"
            _baue_fall(
                db, benutzer="AliceX", ziel_ids=[1488, 2000, 3000],
                seiten=["/forum/profile.php?section=essentials&edit&id=1488",
                        "/forum/profile.php?menu=preferences&section=language"
                        "&edit&id=2000",
                        "/forum/profile.php?section=PGP&edit&id=3000"])
            e = self.modul.pruefe_fall(db)
        self.assertEqual(
            0, e["fehlend"],
            "Die Kennung hinter weiteren Parametern wurde nicht erkannt - "
            "gemeldet als fehlend: %s" % e["fehlende_kennungen"])

    # -- PP04 -----------------------------------------------------------------
    def test_pp04_zweitadressen_zaehlen_mit(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "forensic_4711.db"
            _baue_fall(db, benutzer="AliceX", ziel_ids=[1488],
                       seiten=["/forum/index.php"],
                       aliasse=[(1, "/forum/beginner/profile.php?id=1488")])
            e = self.modul.pruefe_fall(db)
        self.assertEqual(
            0, e["fehlend"],
            "Eine Profilseite, die nur als Zweitadresse gefuehrt wird, ist "
            "trotzdem vorhanden.")

    # -- PP05 -----------------------------------------------------------------
    def test_pp05_datenbank_bleibt_bytegleich(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "forensic_4711.db"
            _baue_fall(db, benutzer="AliceX", ziel_ids=[1488, 2000],
                       seiten=["/forum/profile.php?id=1488"])
            vorher = hashlib.md5(db.read_bytes()).hexdigest()
            self.modul.pruefe_fall(db)
            self.assertEqual(vorher, hashlib.md5(db.read_bytes()).hexdigest(),
                             "die Datenbankdatei wurde veraendert")
            for anhang in ("-wal", "-shm", "-journal"):
                self.assertFalse(
                    Path(str(db) + anhang).exists(),
                    "Nebendatei '%s' entstanden - es gab eine Schreibabsicht"
                    % anhang)


if __name__ == "__main__":
    unittest.main()
