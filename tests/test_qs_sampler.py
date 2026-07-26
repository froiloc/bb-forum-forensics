# =============================================================================
# tests/test_qs_sampler.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3C
# =============================================================================
# Testsuite fuer Build 540: das Vokabular der QS-Stichprobe, die reine Ziehung
# und die Migration M034.
#
# DIE ZIEHUNG IST OHNE DATENBANK PRUEFBAR, und das ist der Grund fuer diesen
# Schnitt: bei einer Zahl, die darueber entscheidet, WESSEN Arbeit geprueft
# wird, ist die Nachrechenbarkeit ohne Vorrichtung keine Bequemlichkeit,
# sondern Voraussetzung. Dasselbe Muster wie urgency_matrix (Build 536).
#
# VOKABULAR:
#   QV01 — Die Zweckbindung steht im Code, ist nicht leer und nennt
#          ausdruecklich, dass es KEIN Bewertungsinstrument ist.
#   QV02 — 'ergebnis' ist KEINE Note: es gibt kein 'mangelhaft', keinen
#          Punktwert und keine Rangfolge — aber 'nicht_beurteilbar'.
#   QV03 — Ein unbekannter Code wird BENANNT und nicht auf einen bekannten
#          abgebildet.
#
# ZIEHUNG (rein, ohne Datenbank):
#   QS01 — Jeder gezogene Fall stammt aus der Grundgesamtheit; keiner doppelt.
#   QS02 — REPRODUZIERBARKEIT: derselbe Keim ueber derselben Grundgesamtheit
#          liefert dieselbe FOLGE. Das ist der Kern des ganzen Pakets.
#   QS03 — Ein anderer Keim liefert (praktisch sicher) eine andere Auswahl —
#          sonst wuerde QS02 auch eine kaputte Ziehung bestaetigen.
#   QS04 — DIE REIHENFOLGE DER EINGABE IST EGAL: dieselbe Menge in anderer
#          Reihenfolge ergibt dieselbe Ziehung (es wird vor dem Ziehen
#          sortiert). Ohne das haenge der Beleg an der Zeilenreihenfolge der
#          Datenbank.
#   QS05 — GESCHICHTET: die blinden Flecken sind ueberproportional vertreten.
#   QS06 — Eine Schicht mit weniger Faellen als ihrem Anteil gibt die Reste
#          zurueck — die Stichprobe wird NICHT stillschweigend kleiner.
#   QS07 — Eine nicht leere Schicht, aus der nichts gezogen wurde, wird
#          BENANNT.
#   QS08 — Die Groesse ist min(ceil(anteil*n), hoechstens), mindestens 1: eine
#          Ziehung ueber einer nicht leeren Grundgesamtheit zieht nie 0.
#   QS09 — Leere Grundgesamtheit: 0 Prueflinge, und der Leerbefund wird als
#          solcher benannt (KEINE Aussage ueber die Qualitaet).
#   QS10 — Unbrauchbare Vorgaben werden VERWEIGERT, nicht repariert.
#   QS11 — schicht_von: fehlende Abdeckung gilt als 'nie_bewertet' und NICHT
#          als 'rest' — im Zweifel wird MEHR geprueft, nicht weniger.
#   QS12 — filter_json enthaelt alles, was zum Nachziehen noetig ist, und ist
#          gueltiges JSON.
#   QS13 — nachziehen_stimmt() erkennt eine geaenderte Grundgesamtheit UND
#          eine abweichende Auswahl, jeweils im Klartext.
#   QS14 — Die Antwort traegt die Zweckbindung und die beiden Zusicherungen
#          mit.
#
# MIGRATION M034:
#   QM01 — Die drei Tabellen, die drei Indizes und die zwei Rechte entstehen.
#   QM02 — DIE CHECKS GREIFEN: leere Begruendung, unbekanntes Ergebnis,
#          unbekanntes Verfahren, Stichprobe > Grundgesamtheit.
#   QM03 — Der Ergebnis-CHECK der Migration deckt sich mit ERGEBNIS_CODES
#          (eingefrorene Kopie gegen die Wahrheitsquelle gehalten).
#   QM04 — Idempotent: zweimal anwenden ist ein No-op.
#   QM05 — Eine gleichnamige Tabelle mit ANDEREN Spalten wird NICHT
#          ueberschrieben, sondern gemeldet.
#   QM06 — 'seed' ist NOT NULL — eine Ziehung ohne Keim kann im Schema nicht
#          entstehen.
#
# Version: v0.8.540 · Build: 540 · 2026-07-26
# =============================================================================

import json
import re
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.migrations.coordinator import m034_qs_stichprobe as M034  # noqa: E402
from management.qs import qs_vokabular as V                              # noqa: E402
from management.qs.qs_sampler import (                                   # noqa: E402
    QsSamplerError,
    nachziehen_stimmt,
    schicht_von,
    ziehe,
)

_WURZEL = Path(__file__).resolve().parent.parent


def F(sid, *, nie=False, abdeckung=0.9):
    """Ein Fall der Grundgesamtheit (Form: CoverageRepo)."""
    return {"subject_id": sid, "nie_bewertet": nie, "abdeckung": abdeckung}


class TestVokabular(unittest.TestCase):
    """QV01-QV03."""

    def test_QV01_zweckbindung(self):
        self.assertTrue(V.ZWECKBINDUNG.strip())
        self.assertIn("KEIN MITARBEITER-BEWERTUNGSINSTRUMENT", V.ZWECKBINDUNG)
        self.assertIn("keine Rangfolge", V.ZWECKBINDUNG)

    def test_QV02_ergebnis_ist_keine_note(self):
        for verboten in ("mangelhaft", "ungenuegend", "schlecht", "note"):
            self.assertNotIn(
                verboten, " ".join(V.ERGEBNIS_CODES),
                "Ein Notenbegriff im Ergebnisvokabular macht die Sicht zum "
                "Bewertungsinstrument.")
        self.assertIn("nicht_beurteilbar", V.ERGEBNIS_CODES,
                      "Ohne diesen Code wuerde ein unklarer Fall in eine der "
                      "anderen Kategorien gedrueckt.")
        # Jeder Code hat Label UND Bedeutung — ein Code ohne Erklaerung waere
        # in einem Vermerk nicht verwertbar.
        for c in V.ERGEBNIS_CODES:
            self.assertTrue(V.ERGEBNIS_LABEL.get(c))
            self.assertTrue(V.ERGEBNIS_BEDEUTUNG.get(c))
        self.assertIn("NICHT 'in Ordnung'",
                      V.ERGEBNIS_BEDEUTUNG["nicht_beurteilbar"])

    def test_QV03_unbekannter_code_wird_benannt(self):
        self.assertIn("gibtsnicht", V.ergebnis_label("gibtsnicht"))
        self.assertIn("unbekannt", V.ergebnis_label("gibtsnicht"))
        self.assertIn("gibtsnicht", V.schicht_label("gibtsnicht"))
        self.assertFalse(V.ergebnis_gueltig("mangelhaft"))
        self.assertTrue(V.ergebnis_gueltig("in_ordnung"))


class TestZiehung(unittest.TestCase):
    """QS01-QS14 — ohne Datenbank."""

    def setUp(self):
        # 20 Faelle: 4 nie bewertet, 4 unter der Schwelle, 12 darueber.
        self.g = (
            [F(100 + i, nie=True, abdeckung=None) for i in range(4)]
            + [F(200 + i, abdeckung=0.2) for i in range(4)]
            + [F(300 + i, abdeckung=0.9) for i in range(12)]
        )

    # ===================================================================== QS01
    def test_QS01_nur_echte_faelle_und_keiner_doppelt(self):
        z = ziehe(self.g, seed=7, anteil=0.5, hoechstens=10)
        alle = {f["subject_id"] for f in self.g}
        self.assertTrue(set(z.subject_ids) <= alle)
        self.assertEqual(len(set(z.subject_ids)), len(z.subject_ids))
        self.assertEqual(z.stichprobe_n, len(z.subject_ids))
        self.assertEqual(z.grundgesamtheit_n, 20)

    # ===================================================================== QS02
    def test_QS02_reproduzierbar(self):
        a = ziehe(self.g, seed=4711, anteil=0.5, hoechstens=10)
        b = ziehe(self.g, seed=4711, anteil=0.5, hoechstens=10)
        self.assertEqual(a.subject_ids, b.subject_ids,
                         "Dieselbe Ziehung muss dieselbe FOLGE liefern — "
                         "sonst ist der mitgeschriebene Keim wertlos.")

    # ===================================================================== QS03
    def test_QS03_anderer_keim_andere_auswahl(self):
        a = ziehe(self.g, seed=1, anteil=0.5, hoechstens=10)
        b = ziehe(self.g, seed=2, anteil=0.5, hoechstens=10)
        self.assertNotEqual(
            a.subject_ids, b.subject_ids,
            "Waeren die Ziehungen keimunabhaengig, wuerde QS02 auch eine "
            "kaputte Ziehung bestaetigen.")

    # ===================================================================== QS04
    def test_QS04_eingabereihenfolge_ist_egal(self):
        gedreht = list(reversed(self.g))
        a = ziehe(self.g, seed=99, anteil=0.5, hoechstens=10)
        b = ziehe(gedreht, seed=99, anteil=0.5, hoechstens=10)
        self.assertEqual(a.subject_ids, b.subject_ids,
                         "Ohne Sortierung vor dem Ziehen haenge der Beleg an "
                         "der Zeilenreihenfolge der Datenbank.")

    # ===================================================================== QS05
    def test_QS05_blinde_flecken_ueberproportional(self):
        # 8 von 20 Faellen (40 %) sind blinde Flecken. Bei 10 Prueflingen
        # muessen sie deutlich haeufiger vertreten sein als 40 %.
        z = ziehe(self.g, seed=5, anteil=1.0, hoechstens=10)
        blind = {f["subject_id"] for f in self.g
                 if f["nie_bewertet"] or (f["abdeckung"] or 0) < 0.5}
        getroffen = len(blind & set(z.subject_ids))
        self.assertEqual(z.stichprobe_n, 10)
        # PROPORTIONAL waeren es 4 von 10 (die blinden Flecken sind 40 % der
        # Grundgesamtheit). Genau diese Zahl darf NICHT herauskommen — sonst
        # leistete 'geschichtet' dasselbe wie 'einfach', und der Aufwand waere
        # Zierrat. Mit SCHICHT_GEWICHT 3/2/1 sind es 7.
        self.assertGreater(
            getroffen, 4,
            "Proportional gezogen waeren es 4 — die Schichtung haette dann "
            "keine Wirkung; getroffen: %d" % getroffen)
        self.assertGreaterEqual(
            getroffen, 7,
            "Die Schichtung soll die blinden Flecken ueberproportional "
            "pruefen; getroffen: %d" % getroffen)
        # Und die Schichtangaben sind vollstaendig.
        codes = [s["code"] for s in z.schichten]
        self.assertEqual(codes, list(V.SCHICHT_CODES))
        self.assertEqual(sum(s["gezogen_n"] for s in z.schichten), 10)

    # ===================================================================== QS06
    def test_QS06_reste_werden_aufgefuellt(self):
        # Nur eine einzige Schicht ist besetzt: die Zielgroesse muss trotzdem
        # erreicht werden.
        g = [F(400 + i, abdeckung=0.9) for i in range(10)]
        z = ziehe(g, seed=3, anteil=1.0, hoechstens=5)
        self.assertEqual(z.stichprobe_n, 5,
                         "Ohne Auffuellen waere die Stichprobe stillschweigend "
                         "kleiner als angefordert.")

    # ===================================================================== QS07
    def test_QS07_leere_ziehung_aus_besetzter_schicht_wird_benannt(self):
        # 1 Pruefling bei 20 Faellen -> zwei Schichten bleiben unbeobachtet.
        z = ziehe(self.g, seed=8, anteil=0.01, hoechstens=1)
        self.assertEqual(z.stichprobe_n, 1)
        self.assertTrue(any("unbeobachtet" in h for h in z.hinweise),
                        z.hinweise)

    # ===================================================================== QS08
    def test_QS08_groesse(self):
        # 5 % von 20 = 1 (aufgerundet), Hoechstgrenze greift nicht.
        self.assertEqual(ziehe(self.g, seed=1, anteil=0.05,
                               hoechstens=10).stichprobe_n, 1)
        # 50 % von 20 = 10, Hoechstgrenze 3 greift.
        self.assertEqual(ziehe(self.g, seed=1, anteil=0.5,
                               hoechstens=3).stichprobe_n, 3)
        # Sehr kleiner Anteil -> trotzdem mindestens 1.
        self.assertEqual(ziehe(self.g, seed=1, anteil=0.0001,
                               hoechstens=10).stichprobe_n, 1)
        # Vollpruefung wird als solche benannt.
        z = ziehe(self.g, seed=1, anteil=1.0, hoechstens=999)
        self.assertEqual(z.stichprobe_n, 20)
        self.assertTrue(any("Vollpruefung" in h for h in z.hinweise))

    # ===================================================================== QS09
    def test_QS09_leere_grundgesamtheit(self):
        z = ziehe([], seed=1)
        self.assertEqual(z.stichprobe_n, 0)
        self.assertEqual(z.subject_ids, ())
        self.assertTrue(any("Leerbefund" in h for h in z.hinweise), z.hinweise)
        self.assertTrue(any("keine aussage" in h.lower() for h in z.hinweise))

    # ===================================================================== QS10
    def test_QS10_unbrauchbare_vorgaben_werden_verweigert(self):
        for kwargs in ({"verfahren": "wuerfeln"}, {"anteil": 0.0},
                       {"anteil": 1.5}, {"anteil": -0.1}, {"hoechstens": 0}):
            with self.assertRaises(QsSamplerError, msg=repr(kwargs)):
                ziehe(self.g, seed=1, **kwargs)
        # Ein Eintrag ohne subject_id ist ein Fehler, kein Grenzfall.
        with self.assertRaises(QsSamplerError):
            ziehe([{"abdeckung": 0.5}], seed=1)

    # ===================================================================== QS11
    def test_QS11_fehlende_abdeckung_gilt_als_nie_bewertet(self):
        self.assertEqual(schicht_von({"abdeckung": None}), "nie_bewertet")
        self.assertEqual(schicht_von({"nie_bewertet": True,
                                      "abdeckung": 1.0}), "nie_bewertet")
        self.assertEqual(schicht_von({"abdeckung": 0.49}), "abdeckung_niedrig")
        self.assertEqual(schicht_von({"abdeckung": 0.5}), "rest")

    # ===================================================================== QS12
    def test_QS12_filter_json_traegt_alles_zum_nachziehen(self):
        z = ziehe(self.g, seed=13, anteil=0.5, hoechstens=10)
        d = json.loads(z.filter_json())
        for k in ("verfahren", "anteil", "hoechstens", "abdeckung_schwelle",
                  "schichten"):
            self.assertIn(k, d)
        self.assertEqual(d["verfahren"], "geschichtet")
        self.assertEqual(len(d["schichten"]), len(V.SCHICHT_CODES))

    # ===================================================================== QS13
    def test_QS13_nachziehen_erkennt_abweichungen(self):
        z = ziehe(self.g, seed=21, anteil=0.5, hoechstens=10)
        ok, ab = nachziehen_stimmt(z, self.g)
        self.assertTrue(ok, ab)
        self.assertEqual(ab, [])

        # Geaenderte Grundgesamtheit -> benannt.
        ok2, ab2 = nachziehen_stimmt(z, self.g + [F(999, abdeckung=0.9)])
        self.assertFalse(ok2)
        self.assertTrue(any("Grundgesamtheit hat sich geaendert" in t
                            for t in ab2), ab2)

        # Gleiche Groesse, andere Faelle -> die Auswahl weicht ab.
        anders = [F(500 + i, abdeckung=0.9) for i in range(20)]
        ok3, ab3 = nachziehen_stimmt(z, anders)
        self.assertFalse(ok3)
        self.assertTrue(any("weichen ab" in t for t in ab3), ab3)

    # ===================================================================== QS14
    def test_QS14_antwort_traegt_die_zweckbindung(self):
        d = ziehe(self.g, seed=1, anteil=0.5, hoechstens=10).to_dict()
        self.assertEqual(d["zweckbindung"], V.ZWECKBINDUNG)
        self.assertTrue(d["ist_kein_bewertungsinstrument"])
        self.assertTrue(d["prueflinge_sind_vorschlag"])


class TestMigrationM034(unittest.TestCase):
    """QM01-QM06."""

    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.isolation_level = None
        self.con.executescript("""
            CREATE TABLE person (id INTEGER PRIMARY KEY AUTOINCREMENT,
                system_username TEXT NOT NULL UNIQUE, created_at INTEGER);
            CREATE TABLE cases (subject_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL);
            CREATE TABLE audit_log (seq INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT);
            CREATE TABLE rbac_capability (code TEXT PRIMARY KEY, label TEXT,
                description TEXT, created_at INTEGER);
        """)
        self.con.execute("INSERT INTO person (system_username) VALUES ('a')")
        self.con.execute("INSERT INTO cases VALUES (101, 'x')")
        self.con.execute("INSERT INTO audit_log (event_type) VALUES ('g')")

    def tearDown(self):
        self.con.close()

    # ===================================================================== QM01
    def test_QM01_tabellen_indizes_rechte(self):
        M034.up(self.con)
        namen = {r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master").fetchall()}
        for t in ("qs_sample", "qs_sample_item", "qs_review",
                  "ix_qs_item_sample", "ix_qs_review_sample",
                  "ix_qs_review_subject"):
            self.assertIn(t, namen)
        caps = {r[0] for r in self.con.execute(
            "SELECT code FROM rbac_capability").fetchall()}
        self.assertEqual(caps, {"qs.view", "qs.edit"})
        # Die Probe hat NICHTS hinterlassen (SAVEPOINT + ROLLBACK).
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM qs_sample").fetchone()[0], 0)

    # ===================================================================== QM02
    def test_QM02_die_checks_greifen(self):
        M034.up(self.con)
        cur = self.con.execute(
            "INSERT INTO qs_sample (gezogen_von, gezogen_at, verfahren, "
            "grundgesamtheit_n, stichprobe_n, seed, filter_json, audit_seq) "
            "VALUES (1, 0, 'einfach', 5, 1, 42, '{}', 1)")
        sid = int(cur.lastrowid)

        faelle = [
            ("leere Begruendung",
             "INSERT INTO qs_review (sample_id, subject_id, geprueft_von, "
             "geprueft_at, ergebnis, begruendung, audit_seq) "
             "VALUES (?,101,1,0,'in_ordnung','  ',1)", (sid,)),
            ("unbekanntes Ergebnis",
             "INSERT INTO qs_review (sample_id, subject_id, geprueft_von, "
             "geprueft_at, ergebnis, begruendung, audit_seq) "
             "VALUES (?,101,1,0,'mangelhaft','x',1)", (sid,)),
            ("unbekanntes Verfahren",
             "INSERT INTO qs_sample (gezogen_von, gezogen_at, verfahren, "
             "grundgesamtheit_n, stichprobe_n, seed, filter_json, audit_seq) "
             "VALUES (1,0,'wuerfeln',5,1,1,'{}',1)", ()),
            ("Stichprobe groesser als Grundgesamtheit",
             "INSERT INTO qs_sample (gezogen_von, gezogen_at, verfahren, "
             "grundgesamtheit_n, stichprobe_n, seed, filter_json, audit_seq) "
             "VALUES (1,0,'einfach',3,4,1,'{}',1)", ()),
            ("zwei Ergebnisse zu demselben Fall derselben Ziehung",
             None, None),
        ]
        for was, sql, args in faelle[:-1]:
            with self.assertRaises(sqlite3.IntegrityError, msg=was):
                self.con.execute(sql, args)

        # Der UNIQUE-Schutz: ein Fall wird je Ziehung EINMAL geprueft.
        self.con.execute(
            "INSERT INTO qs_review (sample_id, subject_id, geprueft_von, "
            "geprueft_at, ergebnis, begruendung, audit_seq) "
            "VALUES (?,101,1,0,'in_ordnung','traegt',1)", (sid,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO qs_review (sample_id, subject_id, geprueft_von, "
                "geprueft_at, ergebnis, begruendung, audit_seq) "
                "VALUES (?,101,1,0,'nachzuarbeiten','doch nicht',1)", (sid,))

    # ===================================================================== QM03
    def test_QM03_eingefrorene_kopie_deckt_sich_mit_dem_vokabular(self):
        """
        Die Migration fuehrt eine EINGEFRORENE Kopie der Codes (m005-Prinzip).
        Genau deshalb muss ein Test beide gegeneinander halten — sonst
        divergieren sie unbemerkt, und die Datenbank liesse etwas zu (oder
        verboete etwas), was das Vokabular anders sieht.
        """
        self.assertEqual(set(M034._ERGEBNIS_CODES), set(V.ERGEBNIS_CODES))
        self.assertEqual(set(M034._VERFAHREN_CODES), set(V.VERFAHREN_CODES))
        # Und die Codes stehen wirklich im DDL-CHECK.
        for c in V.ERGEBNIS_CODES:
            self.assertIn("'%s'" % c, M034._DDL_REVIEW)
        for c in V.VERFAHREN_CODES:
            self.assertIn("'%s'" % c, M034._DDL_SAMPLE)

    # ===================================================================== QM04
    def test_QM04_idempotent(self):
        M034.up(self.con)
        M034.up(self.con)          # darf nicht werfen
        self.assertEqual(
            self.con.execute(
                "SELECT COUNT(*) FROM rbac_capability").fetchone()[0], 2)

    # ===================================================================== QM05
    def test_QM05_fremde_gleichnamige_tabelle_wird_nicht_ueberschrieben(self):
        self.con.execute("CREATE TABLE qs_review (id INTEGER, was TEXT)")
        with self.assertRaises(RuntimeError) as ctx:
            M034.up(self.con)
        self.assertIn("ABWEICHENDEN Spalten", str(ctx.exception))
        # Und die fremde Tabelle steht unveraendert da.
        spalten = {r[1] for r in self.con.execute(
            'PRAGMA table_info("qs_review")').fetchall()}
        self.assertEqual(spalten, {"id", "was"})

    # ===================================================================== QM06
    def test_QM06_seed_ist_pflicht(self):
        M034.up(self.con)
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO qs_sample (gezogen_von, gezogen_at, verfahren, "
                "grundgesamtheit_n, stichprobe_n, seed, filter_json, "
                "audit_seq) VALUES (1,0,'einfach',5,1,NULL,'{}',1)")

    def test_QM07_migration_nutzt_kein_executescript(self):
        """
        executescript() committet implizit und nimmt dem Runner den ROLLBACK
        (Lehre aus M019). Die Datei darf es deshalb nicht enthalten.
        """
        quelle = (_WURZEL / "management" / "migrations" / "coordinator"
                  / "m034_qs_stichprobe.py").read_text(encoding="utf-8")
        # Nur CODE-Zeilen, keine Kommentare: im Kopf STEHT das Wort, weil dort
        # begruendet wird, warum es nicht benutzt wird.
        code = [z for z in quelle.splitlines()
                if not z.lstrip().startswith("#")]
        self.assertIsNone(re.search(r"\bexecutescript\s*\(", "\n".join(code)))


if __name__ == "__main__":
    unittest.main()
