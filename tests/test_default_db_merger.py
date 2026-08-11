# =============================================================================
# tests/test_default_db_merger.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management/Wartung
# =============================================================================
# Testsuite für management.maintenance.DefaultDbMerger
# (verlustfreie Konsolidierung mehrerer default.db).
#
# M01 — Basis-Merge zweier Quellen: Zeilen vereinigt, Bericht ausgeglichen
# M02 — asset_id-Remap korrekt: gleiche Quell-id in verschiedenen Quellen
#       zeigt NICHT auf dasselbe Ziel-Asset (kein Cross-Wiring); FK sauber
# M03 — content_hash-Dedup über Quellen hinweg -> genau ein Asset
# M04 — dieselbe URL zeigt in Quelle B auf anderes Asset -> Konflikt,
#       neueste Quelle gewinnt, protokolliert
# M05 — known_aliases: (user_id, name)-Dedup, alias_id neu vergeben
# M06 — default_meta stabiler Key divergiert -> MergeError (Abbruch)
# M07 — default_meta Lauf-Key divergiert -> neueste Quelle gewinnt
# M08 — Invariante: keine Zeile still verworfen (balanced == True je Tabelle)
# M09 — unbekannte Tabelle in Quelle -> MergeError (fail loud)
# M10 — Ziel == Quelle bzw. Ziel existiert ohne --overwrite -> MergeError
# M11 — Quellen bleiben unverändert (read-only); provenance geschrieben
#
# NACHTRAG BUILD 694 — Vorgang 1400b31f: ERST BAUEN, DANN TAUSCHEN.
# Bis Build 690 loeschte _open_target() die vorhandene Ziel-Datei VOR dem
# BEGIN und legte an ihrem Platz die neue an. Ein Abbruch danach hinterliess
# deshalb eine LEERE, syntaktisch einwandfreie default.db — und das ohne
# Zutun von '--overwrite' auch beim Erstlauf. Eine fehlende Datei schreit,
# eine leere gueltige schweigt: der Auswertungsdienst oeffnet sie anstandslos
# und findet nur keine Vorlagen.
#
# M12 — Abbruch mit --overwrite: der Altbestand bleibt Zeile fuer Zeile
# M13 — Abbruch beim Erstlauf: es entsteht GAR KEINE Ziel-Datei
# M14 — nach einem Abbruch bleibt keine Arbeitsdatei liegen
# M15 — nach einem erfolgreichen Lauf ebenso wenig
# M16 — waehrend des Laufs ist der Altbestand noch vollstaendig da
# M17 — ein Rest aus einem frueheren Lauf blockiert den naechsten nicht
# M18 — scheitert der Tausch, bleibt das FERTIGE Ergebnis erhalten und wird
#       benannt (der Windows-Fall: die Zieldatei ist von jemandem offen)
# M19 — Beidateien neben der Arbeitsdatei verhindern den Tausch
#
# Version: v0.8.694 · Build: 694 · 2026-08-11
# =============================================================================

import hashlib
import os
import sqlite3
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.maintenance.default_db_merger import (
    _CANONICAL_DDL,
    DefaultDbMerger,
    MergeError,
)


def _new_source(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(_CANONICAL_DDL)
    con.commit()
    return con


def _add_asset(con, content: bytes, note="found", mime="image/png") -> int:
    ch = hashlib.md5(content).hexdigest()
    cur = con.execute(
        "INSERT INTO default_assets "
        "(content_hash, data, mime_type, file_size, source_note, fetched_at) "
        "VALUES (?,?,?,?,?,?)",
        (ch, content, mime, len(content), note, 1000),
    )
    return cur.lastrowid


def _add_url(con, url, asset_id, ctx="img"):
    con.execute(
        "INSERT INTO default_urls "
        "(url, url_hash, asset_id, url_context, http_status, added_at) "
        "VALUES (?,?,?,?,?,?)",
        (url, hashlib.md5(url.encode()).hexdigest()[:16], asset_id, ctx, 200, 1000),
    )


def _set_meta(con, key, value):
    con.execute(
        "INSERT OR REPLACE INTO default_meta (key, value) VALUES (?, ?)",
        (key, str(value)),
    )


class DefaultDbMergerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.target = self.root / "central" / "default.db"

    def tearDown(self):
        self._tmp.cleanup()

    # --------------------------------------------------------------- helpers
    def _run(self, sources, **kw):
        merger = DefaultDbMerger(
            target_path=self.target,
            source_paths=sources,
            **kw,
        )
        return merger.run()

    def _target_urls(self):
        """{url: content_hash} über den JOIN im Ziel — prüft den FK-Remap."""
        con = sqlite3.connect(self.target)
        try:
            rows = con.execute(
                "SELECT du.url AS url, da.content_hash AS ch "
                "FROM default_urls du LEFT JOIN default_assets da "
                "ON da.id = du.asset_id"
            ).fetchall()
            return {r[0]: r[1] for r in rows}
        finally:
            con.close()

    # ----------------------------------------------------------------- tests
    def test_m01_basic_merge_balanced(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        b = self.root / "b" / "default.db"; b.parent.mkdir(parents=True)
        ca = _new_source(a)
        _set_meta(ca, "last_run_ts", 100)
        ca.execute("INSERT INTO known_users (user_id, username) VALUES (5,'alice')")
        ca.commit(); ca.close()
        cb = _new_source(b)
        _set_meta(cb, "last_run_ts", 200)
        cb.execute("INSERT INTO known_users (user_id, username) VALUES (6,'bob')")
        cb.commit(); cb.close()

        report = self._run([a, b])
        con = sqlite3.connect(self.target)
        n = con.execute("SELECT COUNT(*) FROM known_users").fetchone()[0]
        con.close()
        self.assertEqual(n, 2)
        for st in report.tables.values():
            self.assertTrue(st.balanced)
        self.assertTrue(report.fk_check_ok)

    def test_m02_asset_id_remap_no_crosswire(self):
        # Quelle A: id1=hashA (/x), id2=hashB (/y)
        # Quelle B: id1=hashC (/z)  -> gleiche Quell-id 1, anderer Inhalt
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        b = self.root / "b" / "default.db"; b.parent.mkdir(parents=True)
        ca = _new_source(a); _set_meta(ca, "last_run_ts", 100)
        id1 = _add_asset(ca, b"AAAA"); id2 = _add_asset(ca, b"BBBB")
        _add_url(ca, "/x", id1); _add_url(ca, "/y", id2)
        ca.commit(); ca.close()
        cb = _new_source(b); _set_meta(cb, "last_run_ts", 200)
        idb = _add_asset(cb, b"CCCC")  # in B ebenfalls id=1
        _add_url(cb, "/z", idb)
        cb.commit(); cb.close()

        self._run([a, b])
        urls = self._target_urls()
        self.assertEqual(urls["/x"], hashlib.md5(b"AAAA").hexdigest())
        self.assertEqual(urls["/y"], hashlib.md5(b"BBBB").hexdigest())
        # KERN: /z darf NICHT auf hashA zeigen, obwohl beide Quell-id 1 hatten
        self.assertEqual(urls["/z"], hashlib.md5(b"CCCC").hexdigest())

    def test_m03_content_hash_dedup(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        b = self.root / "b" / "default.db"; b.parent.mkdir(parents=True)
        ca = _new_source(a); _set_meta(ca, "last_run_ts", 100)
        _add_url(ca, "/x", _add_asset(ca, b"SAME")); ca.commit(); ca.close()
        cb = _new_source(b); _set_meta(cb, "last_run_ts", 200)
        _add_url(cb, "/y", _add_asset(cb, b"SAME")); cb.commit(); cb.close()

        self._run([a, b])
        con = sqlite3.connect(self.target)
        n = con.execute("SELECT COUNT(*) FROM default_assets").fetchone()[0]
        con.close()
        self.assertEqual(n, 1)  # identischer Inhalt -> genau ein Asset

    def test_m04_url_conflict_newest_wins(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        b = self.root / "b" / "default.db"; b.parent.mkdir(parents=True)
        ca = _new_source(a); _set_meta(ca, "last_run_ts", 100)
        _add_url(ca, "/logo.png", _add_asset(ca, b"OLD")); ca.commit(); ca.close()
        cb = _new_source(b); _set_meta(cb, "last_run_ts", 200)
        _add_url(cb, "/logo.png", _add_asset(cb, b"NEW")); cb.commit(); cb.close()

        report = self._run([a, b])
        urls = self._target_urls()
        # neueste Quelle (ts=200) gewinnt
        self.assertEqual(urls["/logo.png"], hashlib.md5(b"NEW").hexdigest())
        self.assertTrue(any(c.table == "default_urls" for c in report.conflicts))

    def test_m05_known_aliases_composite_dedup(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        b = self.root / "b" / "default.db"; b.parent.mkdir(parents=True)
        ca = _new_source(a); _set_meta(ca, "last_run_ts", 100)
        ca.execute("INSERT INTO known_aliases (user_id, name) VALUES (5,'nick')")
        ca.commit(); ca.close()
        cb = _new_source(b); _set_meta(cb, "last_run_ts", 200)
        cb.execute("INSERT INTO known_aliases (user_id, name) VALUES (5,'nick')")
        cb.execute("INSERT INTO known_aliases (user_id, name) VALUES (5,'other')")
        cb.commit(); cb.close()

        self._run([a, b])
        con = sqlite3.connect(self.target)
        rows = con.execute(
            "SELECT user_id, name FROM known_aliases ORDER BY name"
        ).fetchall()
        con.close()
        self.assertEqual([(r[0], r[1]) for r in rows], [(5, "nick"), (5, "other")])

    def test_m06_meta_stable_key_mismatch_aborts(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        b = self.root / "b" / "default.db"; b.parent.mkdir(parents=True)
        ca = _new_source(a); _set_meta(ca, "domainname", "forumA.onion"); ca.commit(); ca.close()
        cb = _new_source(b); _set_meta(cb, "domainname", "forumB.onion"); cb.commit(); cb.close()
        with self.assertRaises(MergeError):
            self._run([a, b])

    def test_m06b_meta_stable_key_mismatch_override(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        b = self.root / "b" / "default.db"; b.parent.mkdir(parents=True)
        ca = _new_source(a); _set_meta(ca, "last_run_ts", 100)
        _set_meta(ca, "domainname", "forumA.onion"); ca.commit(); ca.close()
        cb = _new_source(b); _set_meta(cb, "last_run_ts", 200)
        _set_meta(cb, "domainname", "forumB.onion"); cb.commit(); cb.close()
        report = self._run([a, b], allow_host_mismatch=True)
        con = sqlite3.connect(self.target)
        v = con.execute(
            "SELECT value FROM default_meta WHERE key='domainname'"
        ).fetchone()[0]
        con.close()
        self.assertEqual(v, "forumB.onion")  # neueste gewinnt
        self.assertTrue(report.fk_check_ok)

    def test_m07_meta_run_key_newest_wins(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        b = self.root / "b" / "default.db"; b.parent.mkdir(parents=True)
        ca = _new_source(a); _set_meta(ca, "last_run_ts", 100)
        _set_meta(ca, "last_run_stats", "old"); ca.commit(); ca.close()
        cb = _new_source(b); _set_meta(cb, "last_run_ts", 200)
        _set_meta(cb, "last_run_stats", "new"); cb.commit(); cb.close()
        self._run([a, b])
        con = sqlite3.connect(self.target)
        v = con.execute(
            "SELECT value FROM default_meta WHERE key='last_run_stats'"
        ).fetchone()[0]
        con.close()
        self.assertEqual(v, "new")

    def test_m09_unknown_table_aborts(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        ca = _new_source(a)
        ca.execute("CREATE TABLE bogus (x INTEGER)")
        ca.commit(); ca.close()
        with self.assertRaises(MergeError):
            self._run([a])

    def test_m10_target_is_source_aborts(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        ca = _new_source(a); ca.commit(); ca.close()
        merger = DefaultDbMerger(target_path=a, source_paths=[a])
        with self.assertRaises(MergeError):
            merger.run()

    def test_m10b_target_exists_without_overwrite_aborts(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        ca = _new_source(a); ca.commit(); ca.close()
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_bytes(b"exists")
        with self.assertRaises(MergeError):
            self._run([a])
        # mit --overwrite geht es
        report = self._run([a], overwrite=True)
        self.assertTrue(report.fk_check_ok)

    def test_m11_sources_unchanged_and_provenance(self):
        a = self.root / "a" / "default.db"; a.parent.mkdir(parents=True)
        ca = _new_source(a); _set_meta(ca, "last_run_ts", 100)
        _add_url(ca, "/x", _add_asset(ca, b"DATA")); ca.commit(); ca.close()
        before = hashlib.md5(a.read_bytes()).hexdigest()

        self._run([a])
        after = hashlib.md5(a.read_bytes()).hexdigest()
        self.assertEqual(before, after)  # Quelle unangetastet

        con = sqlite3.connect(self.target)
        prov = con.execute(
            "SELECT value FROM default_meta WHERE key='merge_provenance'"
        ).fetchone()
        con.close()
        self.assertIsNotNone(prov)


# =============================================================================
# M12-M19 — Vorgang 1400b31f: erst bauen, dann tauschen (Build 694)
# =============================================================================

class MergerTauschTest(unittest.TestCase):
    """
    Die Waechter zum Vorgang 1400b31f.

    GEMESSEN WIRD DER ZUSTAND AUF DER PLATTE, nicht der Ablauf im Speicher.
    Ein Test, der prueft, ob os.replace() aufgerufen wurde, waere gruen
    geblieben, waehrend am Zielort eine leere Datenbank liegt — und genau
    darum geht es hier.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.target = self.root / "central" / "default.db"
        self.target.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._tmp.cleanup()

    # ----------------------------------------------------------- Hilfsmittel
    def _quelle(self, name, url):
        pfad = self.root / name / "default.db"
        pfad.parent.mkdir(parents=True, exist_ok=True)
        con = _new_source(pfad)
        _add_url(con, url, _add_asset(con, b"DATA-" + url.encode()))
        _set_meta(con, "last_run_ts", 100)
        con.commit()
        con.close()
        return pfad

    def _altbestand(self, url="http://alt/bestand.png"):
        """Eine vorhandene Ziel-default.db mit einer erkennbaren Zeile."""
        con = _new_source(self.target)
        _add_url(con, url, _add_asset(con, b"ALTBESTAND"))
        con.commit()
        con.close()
        return url

    def _urls(self, pfad=None):
        con = sqlite3.connect(pfad or self.target)
        try:
            return {r[0] for r in con.execute("SELECT url FROM default_urls")}
        finally:
            con.close()

    def _arbeitsdateien(self):
        return sorted(p.name for p in self.target.parent.glob("*merge-tmp*"))

    def _merger_mit_abbruch(self, quellen, **kw):
        """
        Ein Merger, der in der ZWEITEN Quelle abbricht.

        So sieht ein Plattenfehler aus, ein Schemafehler in einer spaeten
        Quelle oder ein Strg-C: mittendrin, nachdem schon geschrieben wurde.
        """
        merger = DefaultDbMerger(target_path=self.target,
                                 source_paths=quellen, **kw)
        echt = merger._merge_one_source
        zaehler = {"n": 0}

        def kaputt(src):
            zaehler["n"] += 1
            if zaehler["n"] == 2:
                raise MergeError("Wegwerf-Abbruch in der zweiten Quelle")
            return echt(src)

        merger._merge_one_source = kaputt
        return merger

    # ------------------------------------------------------------------ M12
    def test_m12_abbruch_mit_overwrite_laesst_den_altbestand_stehen(self):
        """
        M12 — DER TICKETFALL.

        GEMESSEN vor der Berichtigung: aus 'assets=1 urls=1' wurde
        'assets=0 urls=0' — die Datei war noch da, aber leer.
        """
        alt = self._altbestand()
        quellen = [self._quelle("a", "/neu-a"), self._quelle("b", "/neu-b")]

        with self.assertRaises(MergeError):
            self._merger_mit_abbruch(quellen, overwrite=True).run()

        self.assertTrue(self.target.exists(),
                        "Die vorhandene default.db ist verschwunden.")
        self.assertEqual({alt}, self._urls(),
                         "Der Altbestand wurde durch den abgebrochenen Lauf "
                         "veraendert.")

    # ------------------------------------------------------------------ M13
    def test_m13_abbruch_beim_erstlauf_hinterlaesst_keine_datei(self):
        """
        M13 — DER BEFUND, DER NICHT IM VORGANG STAND.

        Ohne '--overwrite', mit fehlendem Ziel: bis Build 690 lag danach eine
        LEERE default.db am Zielort. Der naechste Versuch scheiterte dann an
        'Ziel existiert bereits' — einer Meldung, die auf eine ganz andere
        Ursache zeigt.
        """
        quellen = [self._quelle("a", "/neu-a"), self._quelle("b", "/neu-b")]

        with self.assertRaises(MergeError):
            self._merger_mit_abbruch(quellen).run()

        # Die Meldung wird VOR der Zusicherung gebaut und darf die Lage
        # nicht veraendern: sqlite3.connect() auf einen fehlenden Pfad wuerde
        # die Datei anlegen und damit genau das herstellen, was hier
        # ausgeschlossen werden soll.
        lage = (("existiert mit %s" % self._urls())
                if self.target.exists() else "existiert nicht")
        self.assertFalse(self.target.exists(),
                         "Nach dem Abbruch liegt eine Ziel-Datei da, die nie "
                         "fertig geworden ist (%s)." % lage)

    # ------------------------------------------------------------ M14 / M15
    def test_m14_nach_abbruch_bleibt_keine_arbeitsdatei_liegen(self):
        """
        M14 — eine liegengebliebene '.merge-tmp-<pid>' waere eine Datei mit
        ungeklaertem Inhalt neben einer, die als gueltig gilt.
        """
        quellen = [self._quelle("a", "/neu-a"), self._quelle("b", "/neu-b")]
        with self.assertRaises(MergeError):
            self._merger_mit_abbruch(quellen).run()
        self.assertEqual([], self._arbeitsdateien())

    def test_m15_nach_erfolg_bleibt_keine_arbeitsdatei_liegen(self):
        """M15 — die Gegenrichtung zu M14."""
        quellen = [self._quelle("a", "/neu-a"), self._quelle("b", "/neu-b")]
        bericht = DefaultDbMerger(target_path=self.target,
                                  source_paths=quellen).run()
        self.assertTrue(bericht.fk_check_ok)
        self.assertEqual([], self._arbeitsdateien())
        self.assertEqual({"/neu-a", "/neu-b"}, self._urls())

    # ------------------------------------------------------------------ M16
    def test_m16_waehrend_des_laufs_ist_der_altbestand_noch_da(self):
        """
        M16 — der Kern der Berichtigung, an der Platte gemessen.

        Nicht "am Ende steht das Richtige da", sondern: ZU KEINEM ZEITPUNKT
        ist der Altbestand weg. Gemessen wird MITTEN im Lauf, waehrend die
        zweite Quelle verarbeitet wird.
        """
        alt = self._altbestand()
        quellen = [self._quelle("a", "/neu-a"), self._quelle("b", "/neu-b")]
        merger = DefaultDbMerger(target_path=self.target,
                                 source_paths=quellen, overwrite=True)
        echt = merger._merge_one_source
        gesehen = []

        def beobachte(src):
            gesehen.append(self._urls() if self.target.exists() else None)
            return echt(src)

        merger._merge_one_source = beobachte
        merger.run()

        self.assertTrue(gesehen, "Es wurde keine Quelle verarbeitet.")
        for stand in gesehen:
            self.assertEqual({alt}, stand,
                             "Waehrend des Laufs war der Altbestand nicht "
                             "mehr vollstaendig: %s" % (stand,))
        self.assertEqual({"/neu-a", "/neu-b"}, self._urls())

    # ------------------------------------------------------------------ M17
    def test_m17_ein_rest_aus_einem_frueheren_lauf_blockiert_nicht(self):
        """
        M17 — nach einem Absturz kann derselbe Prozess erneut anlaufen.

        Ein Rest unter '.merge-tmp-<pid>' ist per Bauart nie ein Ergebnis —
        ein Ergebnis waere getauscht worden. Er wird deshalb entfernt, und
        das steht im Protokoll. Ein Abbruch an dieser Stelle haette Arbeit
        blockiert, ohne etwas zu schuetzen.
        """
        rest = self.target.with_name("%s.merge-tmp-%d"
                                     % (self.target.name, os.getpid()))
        rest.write_bytes(b"Rest eines abgestuerzten Laufs")

        quellen = [self._quelle("a", "/neu-a")]
        DefaultDbMerger(target_path=self.target, source_paths=quellen).run()

        self.assertEqual({"/neu-a"}, self._urls())
        self.assertEqual([], self._arbeitsdateien())

    # ------------------------------------------------------------------ M18
    def test_m18_scheitert_der_tausch_bleibt_das_ergebnis_erhalten(self):
        """
        M18 — DER WINDOWS-FALL, und die Entscheidung dazu (Alex, 2026-08-11).

        Unter Windows schlaegt os.replace() fehl, solange eine andere
        Anwendung die Zieldatei offen haelt — und der Auswertungsdienst haelt
        die default.db lesend offen. Der Wartungsvorbehalt verlangt Ruhe,
        aber zwischen seiner Pruefung und dem Tausch bleibt ein Restfenster.

        Dann wird die FERTIGE Zusammenfuehrung nicht weggeworfen: sie bleibt
        unter ihrem Nebennamen liegen, und die Meldung nennt Pfad UND
        Handgriff. Aus dem Verlust einer langen Zusammenfuehrung wird ein
        Zwischenstand, den man von Hand einsammeln kann.

        Nachgestellt wird der Fehlschlag ueber os.replace selbst — der
        Windows-Fall laesst sich unter Linux nicht echt herstellen, und ihn
        zu behaupten waere schlechter, als ihn zu bauen.
        """
        alt = self._altbestand()
        quellen = [self._quelle("a", "/neu-a")]
        merger = DefaultDbMerger(target_path=self.target,
                                 source_paths=quellen, overwrite=True)

        def verweigert(*_a, **_kw):
            raise PermissionError(13, "Zugriff verweigert (nachgestellt)")

        with unittest.mock.patch("management.maintenance.default_db_merger."
                                 "os.replace", verweigert):
            with self.assertRaises(MergeError) as fall:
                merger.run()

        meldung = str(fall.exception)
        reste = self._arbeitsdateien()
        self.assertEqual(1, len(reste),
                         "Das fertige Ergebnis wurde weggeworfen: %s" % reste)
        self.assertIn(reste[0], meldung,
                      "Die Meldung nennt den Pfad des Ergebnisses nicht.")
        self.assertIn("UNBERUEHRT", meldung)

        # Der Altbestand steht unveraendert an seinem Platz ...
        self.assertEqual({alt}, self._urls())
        # ... und das Ergebnis daneben ist vollstaendig und benutzbar.
        fertig = self.target.parent / reste[0]
        self.assertEqual({"/neu-a"}, self._urls(fertig))

    # ------------------------------------------------------------------ M19
    def test_m19_beidateien_verhindern_den_tausch(self):
        """
        M19 — eine Annahme, die ausgesprochen und geprueft wird.

        Das Werkzeug arbeitet im Journalmodus 'delete'; nach dem Schliessen
        bleibt keine Beidatei zurueck (gemessen 2026-08-11). Stellt jemand
        das spaeter um, laege Inhalt in einer '-wal' — und die Hauptdatei
        allein zu verschieben wuerde ihn verlieren, lautlos. Dann bricht der
        Tausch lieber ab und sagt, warum.
        """
        alt = self._altbestand()
        quellen = [self._quelle("a", "/neu-a")]
        merger = DefaultDbMerger(target_path=self.target,
                                 source_paths=quellen, overwrite=True)
        echt = merger._tausche_ein

        def mit_beidatei():
            Path(str(merger._bau_pfad) + "-wal").write_bytes(b"WAL")
            return echt()

        merger._tausche_ein = mit_beidatei
        with self.assertRaises(MergeError) as fall:
            merger.run()

        self.assertIn("Beidateien", str(fall.exception))
        self.assertEqual({alt}, self._urls(),
                         "Trotz Beidatei wurde getauscht.")


if __name__ == "__main__":
    unittest.main()
