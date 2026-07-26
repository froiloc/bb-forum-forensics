# =============================================================================
# tests/test_evidence_m002_tatzeit.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7
# =============================================================================
# Testsuite fuer Build 532: die Evidence-Migration m002 (annotation_tatzeit).
#
# Diese Suite prueft eine Migration auf einer Datenbank, in der ab dem
# 01.07.2026 ERMITTLERDATEN liegen. Der Schwerpunkt liegt deshalb nicht auf
# "die Tabelle ist da", sondern auf den Zusicherungen drumherum:
#
#   TZ01 — Die Migration laeuft ueber die ECHTE Migrationskette und wird in
#          'schema_migrations' als Version 2 / 'additive' registriert.
#   TZ02 — Die Spalten stimmen mit ERWARTETE_SPALTEN ueberein, in der
#          Reihenfolge. Die Liste im Migrationsmodul ist die Wahrheit.
#   TZ03 — Alle vier Indizes sind angelegt.
#   TZ04 — DIE WICHTIGSTE ZUSICHERUNG: 'annotations' ist INHALTLICH unberuehrt.
#          Kein UPDATE, kein ALTER TABLE, keine Zeile mehr oder weniger.
#   TZ05 — KEIN RUECKSTAND: die Tabelle ist leer, und 'sqlite_sequence' traegt
#          keinen Eintrag — die erste ECHTE Zeile bekommt id=1. Die
#          Selbstpruefung der Migration darf sich nicht bemerkbar machen.
#   TZ06 — Jeder CHECK GREIFT auch. Ein geschriebener, aber unwirksamer CHECK
#          waere schlimmer als keiner, weil man sich auf ihn verlaesst.
#   TZ07 — Zweiter Lauf: nichts anzuwenden, kein Fehler (Wiederholbarkeit).
#   TZ08 — Fehlt 'annotations', bricht die Migration ab und legt NICHTS an.
#   TZ09 — Existiert 'annotation_tatzeit' bereits mit ANDEREM Aufbau, bricht
#          die Migration ab statt ihn stillschweigend zu uebernehmen.
#   TZ10 — Der Index wird von SQLite fuer MAX(von_ts) auch BENUTZT — genau die
#          Abfrage, die der Fristenmonitor spaeter braucht. Dieser Test hat im
#          ersten Entwurf einen echten Fehler gefunden (partielle Zeitindizes
#          werden fuer MAX/MIN nicht herangezogen).
#   TZ11 — Beide Schluessel sind speicherbar, und 'annotation_local_id' darf
#          NULL sein (anonyme Einmal-Annotation, db/evidence_db.py:871).
#   TZ12 — Das Modul benutzt KEIN executescript(). Pythons sqlite3 committet
#          davor implizit und wuerde damit die Transaktion des Runners
#          beenden; die Tabelle waere angelegt, die Registrierung aber nicht
#          erfolgt. Der Test haelt den Quelltext fest, damit das nicht durch
#          spaeteres 'Aufraeumen' wieder hineinkommt.
# =============================================================================

import hashlib
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.evidence as evidence_migrations        # noqa: E402
from management.migrations.evidence import m002_annotation_tatzeit as M002  # noqa: E402
from management.migrations.runner import MigrationRunner, discover  # noqa: E402

#: Der Aufbau von 'annotations' — aus db/evidence_db.py:258-275 uebernommen
#  (die fuer diesen Test wesentlichen Spalten). Bewusst nicht der ganze DDL:
#  m002 fasst die Tabelle nicht an und braucht sie nur als Nachweis, dass es
#  sich um eine evidence-DB handelt.
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

#: Gueltige Zeitwerte innerhalb des Plausibilitaetsrahmens der Migration
#  (2018-01-01 .. 2027-01-01).
_VON = 1600000000        # 2020-09-13
_BIS = 1600086400        # 2020-09-14


def _annotations_fingerabdruck(con) -> str:
    """
    Inhaltshash der Tabelle 'annotations' — indexunabhaengig, nach rowid.

    Er ist der Beleg fuer TZ04. Ein Vergleich der DATEI-Pruefsumme waere hier
    untauglich: die Datei aendert sich zwangslaeufig, weil eine Tabelle
    hinzukommt. Was gleich bleiben MUSS, ist der Inhalt der Bestandstabelle.
    """
    h = hashlib.sha256()
    spalten = [str(r[1]) for r in con.execute('PRAGMA table_info("annotations")')]
    h.update((",".join(spalten)).encode("utf-8"))
    liste = ", ".join('"%s"' % s for s in spalten)
    for zeile in con.execute(
            'SELECT %s FROM "annotations" ORDER BY rowid' % liste):
        h.update(repr(tuple(zeile)).encode("utf-8", "surrogatepass"))
    return h.hexdigest()


class TestEvidenceM002Tatzeit(unittest.TestCase):

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.pfad = self.dir / "evidence_4711.db"
        self.con = sqlite3.connect(str(self.pfad))
        self.con.executescript(_ANNOTATIONS)
        # Zwei Bestandszeilen: ohne sie waere TZ04 ein Leerbefund.
        self.con.execute(
            'INSERT INTO "annotations" (page_url, category, text, ts, '
            'investigator_id, local_id) VALUES (?,?,?,?,?,?)',
            ("/viewtopic.php?id=1", "§ 184b", "Verweis auf Material",
             1700000000, 3, "abc-123"))
        self.con.execute(
            'INSERT INTO "annotations" (page_url, category, text, ts, '
            'investigator_id, local_id) VALUES (?,?,?,?,?,?)',
            ("/viewtopic.php?id=2", "Sonstiges", "Zeitangabe im Text",
             1700000100, 3, None))
        self.con.commit()
        self.mods = discover(evidence_migrations)

    def tearDown(self):
        try:
            self.con.close()
        except sqlite3.Error:
            pass
        shutil.rmtree(self.dir, ignore_errors=True)

    def _lauf(self, con=None):
        return MigrationRunner(con or self.con, self.mods).run()

    def _indizes(self):
        return {str(r[0]) for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND tbl_name='annotation_tatzeit'")}

    # -- Anwenden und Aufbau --------------------------------------------------

    def test_TZ01_migration_wird_registriert(self):
        angewandt = self._lauf()
        self.assertIn(2, angewandt)
        row = self.con.execute(
            "SELECT version, name, kind FROM schema_migrations "
            "WHERE version = 2").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[2], "additive")
        self.assertIn("annotation_tatzeit", row[1])

    def test_TZ02_spalten_stimmen_und_in_reihenfolge(self):
        self._lauf()
        spalten = tuple(str(r[1]) for r in self.con.execute(
            'PRAGMA table_info("annotation_tatzeit")'))
        # Die Liste im MIGRATIONSMODUL ist die Wahrheit — sie wird hier nicht
        # abgeschrieben, sondern importiert (Muster LV08/LV20).
        self.assertEqual(spalten, M002.ERWARTETE_SPALTEN)

    def test_TZ03_alle_indizes_angelegt(self):
        self._lauf()
        self.assertTrue(set(M002.ERWARTETE_INDIZES).issubset(self._indizes()),
                        "fehlend: %s" % (set(M002.ERWARTETE_INDIZES)
                                         - self._indizes()))

    def test_TZ04_annotations_bleibt_inhaltlich_unberuehrt(self):
        """
        DIE wichtigste Zusicherung dieser Migration. 'annotations' ist die
        Tabelle, in der ab 01.07.2026 Ermittlerdaten liegen — sie darf von
        dieser Migration nicht angefasst werden, und zwar nachweislich.
        """
        vorher = _annotations_fingerabdruck(self.con)
        anzahl_vorher = self.con.execute(
            'SELECT COUNT(*) FROM "annotations"').fetchone()[0]
        aufbau_vorher = self.con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND name='annotations'").fetchone()[0]

        self._lauf()

        self.assertEqual(_annotations_fingerabdruck(self.con), vorher)
        self.assertEqual(self.con.execute(
            'SELECT COUNT(*) FROM "annotations"').fetchone()[0], anzahl_vorher)
        # Auch der AUFBAU ist unveraendert — kein heimliches ALTER TABLE.
        self.assertEqual(self.con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND name='annotations'").fetchone()[0], aufbau_vorher)

    def test_TZ05_kein_rueckstand_aus_der_selbstpruefung(self):
        """
        Die Migration fuegt zur Pruefung ihrer CHECKs Probezeilen ein und rollt
        sie zurueck. Bliebe davon etwas stehen — sei es eine Zeile oder nur der
        AUTOINCREMENT-Zaehler —, wuerde die erste echte Erfassung nicht bei 1
        beginnen. Das wuerde in einer Akte zu Recht Fragen aufwerfen.
        """
        self._lauf()
        self.assertEqual(self.con.execute(
            'SELECT COUNT(*) FROM "annotation_tatzeit"').fetchone()[0], 0)
        seq = self.con.execute(
            "SELECT seq FROM sqlite_sequence WHERE name='annotation_tatzeit'"
        ).fetchone()
        self.assertIsNone(seq, "sqlite_sequence traegt einen Rueckstand: %r"
                               % (seq,))
        self.con.execute(
            'INSERT INTO "annotation_tatzeit" (annotation_id, art, von_ts, '
            'quelle, erfasst_von, erfasst_at) VALUES (?,?,?,?,?,?)',
            (1, "hart", _VON, "Angabe im Beitrag", 3, 1700000000))
        self.assertEqual(self.con.execute(
            'SELECT id FROM "annotation_tatzeit"').fetchone()[0], 1)

    # -- Die CHECKs -----------------------------------------------------------

    def _einfuegen(self, spalten, werte):
        platz = ", ".join("?" * len(werte))
        self.con.execute(
            'INSERT INTO "annotation_tatzeit" (%s) VALUES (%s)'
            % (spalten, platz), werte)

    def test_TZ06_jeder_check_greift(self):
        self._lauf()
        BASIS = "annotation_id, art, quelle, erfasst_von, erfasst_at"
        gueltig = (
            ("harte Angabe mit Zeitraum",
             BASIS + ", von_ts, bis_ts, genauigkeit",
             (1, "hart", "Angabe im Beitrag", 3, 1700000000,
              _VON, _BIS, "tag")),
            ("harte Angabe nur mit Beginn (Ende unbekannt)",
             BASIS + ", von_ts",
             (1, "hart", "Angabe im Beitrag", 3, 1700000000, _VON)),
            ("harte Angabe nur mit Ende",
             BASIS + ", bis_ts",
             (1, "hart", "Angabe im Beitrag", 3, 1700000000, _BIS)),
            ("weiche Angabe",
             BASIS + ", angabe_schluessel, angabe_wert, wortlaut",
             (1, "weich", "Angabe im Beitrag", 3, 1700000000,
              "relativ_jahre", "vor zwei Jahren", "das war vor zwei Jahren")),
            ("Zeitraum mit gleichem Beginn und Ende (ein Tag)",
             BASIS + ", von_ts, bis_ts",
             (1, "hart", "Angabe im Beitrag", 3, 1700000000, _VON, _VON)),
        )
        ungueltig = (
            ("unbekannte Art", BASIS + ", von_ts",
             (1, "irgendwas", "q", 3, 1, _VON)),
            ("harte Angabe ohne jeden Zeitwert", BASIS,
             (1, "hart", "q", 3, 1)),
            ("weiche Angabe ohne Schluessel", BASIS,
             (1, "weich", "q", 3, 1)),
            ("harte Angabe MIT weichen Feldern",
             BASIS + ", von_ts, angabe_schluessel",
             (1, "hart", "q", 3, 1, _VON, "relativ_jahre")),
            ("weiche Angabe MIT Zeitwert",
             BASIS + ", angabe_schluessel, von_ts",
             (1, "weich", "q", 3, 1, "relativ_jahre", _VON)),
            ("Ende vor Beginn", BASIS + ", von_ts, bis_ts",
             (1, "hart", "q", 3, 1, _BIS, _VON)),
            ("Beginn ausserhalb des Rahmens (Epoch 0)", BASIS + ", von_ts",
             (1, "hart", "q", 3, 1, 0)),
            ("Ende ausserhalb des Rahmens (Millisekunden)", BASIS + ", bis_ts",
             (1, "hart", "q", 3, 1, 1700000000000)),
            ("leere Quelle", BASIS + ", von_ts",
             (1, "hart", "   ", 3, 1, _VON)),
            ("unbekannte Genauigkeit", BASIS + ", von_ts, genauigkeit",
             (1, "hart", "q", 3, 1, _VON, "ungefaehr")),
            ("annotation_id fehlt", "art, quelle, erfasst_von, erfasst_at, von_ts",
             ("hart", "q", 3, 1, _VON)),
            ("erfasst_von fehlt", "annotation_id, art, quelle, erfasst_at, von_ts",
             (1, "hart", "q", 1, _VON)),
        )
        for beschreibung, spalten, werte in gueltig:
            with self.subTest(gueltig=beschreibung):
                self._einfuegen(spalten, werte)
        for beschreibung, spalten, werte in ungueltig:
            with self.subTest(ungueltig=beschreibung):
                with self.assertRaises(sqlite3.IntegrityError):
                    self._einfuegen(spalten, werte)

    # -- Wiederholbarkeit und Abbruchbedingungen ------------------------------

    def test_TZ07_zweiter_lauf_ist_folgenlos(self):
        self._lauf()
        self.assertEqual(self._lauf(), [])

    def test_TZ08_ohne_annotations_bricht_die_migration_ab(self):
        pfad = self.dir / "evidence_fremd.db"
        con = sqlite3.connect(str(pfad))
        con.execute("CREATE TABLE irgendwas (id INTEGER PRIMARY KEY)")
        con.commit()
        try:
            with self.assertRaises(Exception):
                MigrationRunner(con, self.mods).run()
            # UND es wurde nichts angelegt — kein Teilzustand.
            self.assertIsNone(con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='annotation_tatzeit'").fetchone())
        finally:
            con.close()

    def test_TZ09_abweichender_bestand_wird_nicht_uebernommen(self):
        """
        Existiert die Tabelle schon — etwa aus einem Versuch mit 'CREATE TABLE
        IF NOT EXISTS' —, darf sie nicht stillschweigend als geprueft gelten.
        Sonst waere ab diesem Lauf ein fremder Aufbau der offiziell bestaetigte.
        """
        self.con.execute(
            'CREATE TABLE "annotation_tatzeit" (id INTEGER PRIMARY KEY, '
            'annotation_id INTEGER, zeit TEXT)')
        self.con.commit()
        with self.assertRaises(Exception) as ctx:
            self._lauf()
        self.assertIn("anderem Aufbau", str(ctx.exception))
        # Der alte Aufbau steht unveraendert da; nichts wurde repariert.
        spalten = [str(r[1]) for r in self.con.execute(
            'PRAGMA table_info("annotation_tatzeit")')]
        self.assertEqual(spalten, ["id", "annotation_id", "zeit"])

    # -- Wirksamkeit und Bauweise --------------------------------------------

    def test_TZ10_index_wird_fuer_MAX_benutzt(self):
        """
        Genau die Abfrage, die der Fristenmonitor spaeter braucht.

        DIESER TEST HAT EINEN ECHTEN FEHLER GEFUNDEN (2026-07-26): Der erste
        Entwurf der Migration legte die Zeitindizes PARTIELL an ('WHERE von_ts
        IS NOT NULL'). SQLite zieht einen partiellen Index fuer
        'SELECT MAX(von_ts)' NICHT heran — nur wenn die Abfrage dieselbe
        WHERE-Bedingung wiederholt. Der Index war also vorhanden und wirkungslos.
        Ohne diese Pruefung waere das erst bei der naechsten Laufzeitmessung
        aufgefallen, und dann als 'unerklaerlich langsam'.

        Der Test prueft deshalb NICHT, dass ein Index existiert, sondern dass
        SQLite ihn BENUTZT. Das ist der Unterschied zwischen 'gebaut' und
        'wirksam'.
        """
        self._lauf()
        plan = " ".join(str(r) for r in self.con.execute(
            "EXPLAIN QUERY PLAN SELECT MAX(von_ts) FROM annotation_tatzeit"))
        self.assertIn("tatzeit_von_idx", plan, plan)
        plan_bis = " ".join(str(r) for r in self.con.execute(
            "EXPLAIN QUERY PLAN SELECT MIN(bis_ts) FROM annotation_tatzeit"))
        self.assertIn("tatzeit_bis_idx", plan_bis, plan_bis)

    def test_TZ11_beide_schluessel_und_local_id_darf_fehlen(self):
        self._lauf()
        # Mit beiden Schluesseln.
        self._einfuegen(
            "annotation_id, annotation_local_id, art, von_ts, quelle, "
            "erfasst_von, erfasst_at",
            (1, "abc-123", "hart", _VON, "Angabe im Beitrag", 3, 1700000000))
        # Ohne local_id — 'anonyme Einmal-Annotation' hat keine.
        self._einfuegen(
            "annotation_id, art, von_ts, quelle, erfasst_von, erfasst_at",
            (2, "hart", _VON, "Angabe im Beitrag", 3, 1700000000))
        rows = self.con.execute(
            'SELECT annotation_id, annotation_local_id FROM '
            '"annotation_tatzeit" ORDER BY id').fetchall()
        self.assertEqual(rows, [(1, "abc-123"), (2, None)])

    def test_TZ12_kein_executescript_im_migrationsmodul(self):
        """
        Pythons sqlite3 committet vor einem executescript() implizit. Innerhalb
        der Transaktion des Runners beendet das die Transaktion; die Tabelle
        waere angelegt, die Registrierung in 'schema_migrations' aber nicht —
        die Datei traege eine Struktur, von der sie selbst nichts weiss.
        Genau dieser Fehler ist beim ersten Probelauf aufgetreten.
        """
        quelltext = Path(M002.__file__).read_text(encoding="utf-8")
        # In einem Kommentar darf das Wort stehen (dort ist die Begruendung).
        code = "\n".join(z for z in quelltext.splitlines()
                         if not z.lstrip().startswith("#"))
        self.assertNotIn("executescript", code)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
