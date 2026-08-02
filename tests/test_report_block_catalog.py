# =============================================================================
# tests/test_report_block_catalog.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Build 659 — Vorgang 317481d3 (Lektorat: Kommentare verankern)
# =============================================================================
# Deckt ab:
#   (A) den reinen Umwandler management/reports/report_block_catalog.py und
#   (B) den Endpunkt GET /api/report/blocks sowie
#   (C) die verschaerfte Ankerpruefung in POST /api/report/comment.
#
#   BK01 — Katalog: Ordnungszahlen 1..n in AUSGABEREIHENFOLGE; block_id, Typ
#          und deutsche Typbezeichnung stehen richtig.
#   BK02 — Auszug wird gekuerzt, am Wortende geschnitten und als 'truncated'
#          GEMELDET (die Kuerzung ist ein Befund, kein Detail).
#   BK03 — Ein ZEHNTER, unbekannter Blocktyp bleibt in der Liste, wird als
#          unbekannt benannt UND bekommt trotzdem einen Textauszug
#          (Auffangstufe). Grundregel 1: nicht stumm auslassen.
#   BK04 — Block ganz ohne Text bekommt '(ohne Text)' statt einer leeren,
#          nicht waehlbaren Zeile.
#   BK05 — Kommentarzaehlung je block_id; ANKERLOSE Kommentare werden nicht
#          mitgezaehlt, aber getrennt gezaehlt statt zu verschwinden.
#   BK06 — Editor.js-Inline-HTML steht NICHT im Auszug ('<b>' waere im
#          Auswahlfeld sichtbar gewesen).
#   BK07 — Mehrbyte-Zeichen: gekuerzt wird nach ZEICHEN, nicht nach Bytes
#          (Fallerkenntnis 2 — multilinguales Forum).
#   BK08 — Endpunkt: 200; die Reihenfolge der Bloecke ist DIESELBE wie die der
#          Vorschau /api/report/render (nicht nur "auch sortiert").
#   BK09 — Endpunkt: ohne reports.review/approve -> 403.
#   BK10 — Endpunkt: unbekannte uid -> 404; fehlender subject_id -> 400.
#   BK11 — Endpunkt: READ-ONLY-Integritaet, MD5 der evidence_<uid>.db vor==nach.
#   BK12 — GEGENPROBE ZU BUILD 658: Kommentar OHNE block_id -> 400
#          'block_id_required'. Bis Build 658 gab es hier 200 und einen
#          Kommentar, der auf nichts zeigte.
#   BK13 — GEGENPROBE ZU BUILD 658: Kommentar mit UNBEKANNTEM block_id -> 400
#          'block_unknown', der abgewiesene Wert wird MITGENANNT, und es wurde
#          NICHTS gespeichert. Bis Build 658: 200 mit block_sha256=NULL.
#   BK14 — DREI WERTE, NICHT ZWEI: fehlt die evidence-Datei, kommt 503
#          'block_uncheckable' — NICHT dasselbe 400 wie beim Vertipper. Die
#          Ununterscheidbarkeit dieser beiden Lagen war der Kern des Fehlers.
#   BK15 — Der gueltige Weg bleibt heil: gewaehlter Block -> 200 + Blockhash.
#
# Version: v0.8.659 · Build: 659 · 2026-08-02
# =============================================================================

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations
from management.audit.audit_log import AuditLog
from management.migrations.runner import MigrationRunner, discover
from management.gateway.coordinator_writer import CoordinatorWriter
from management.rbac.rbac_repo import RbacRepo
from management.cases.cases_repo import CasesRepo
from management.server.management_app import ManagementApp
from management.reports.report_block_catalog import (
    ReportBlockCatalog, AUSZUG_LEER,
)
from db.evidence_db import EvidenceDb
from db.review_addendum_db import addendum_path

_PERSON = """
CREATE TABLE person (
    id INTEGER PRIMARY KEY AUTOINCREMENT, system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL, is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0, is_support INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
)
"""

_OLD_SCRAPE_JOBS = """
CREATE TABLE scrape_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','running','done','failed')),
    manifest_path TEXT, output_path TEXT, worker_id TEXT,
    created_at INTEGER NOT NULL, started_at INTEGER, finished_at INTEGER,
    error_message TEXT, assigned_to INTEGER, note TEXT,
    FOREIGN KEY(assigned_to) REFERENCES person(id)
)
"""


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


class _Blk:
    """Stellvertreter fuer RenderedBlock — der Umwandler liest nur Attribute."""

    def __init__(self, block_id, block_type, plain="", data=None, known=True):
        self.block_id = block_id
        self.block_type = block_type
        self.resolved_text_plain = plain
        self.data = data if data is not None else {}
        self.is_known_type = known


class _Doc:
    """Stellvertreter fuer ReportDocument."""

    def __init__(self, blocks):
        self.blocks = blocks
        self.report_id = 1


# =============================================================================
# (A) Der reine Umwandler — ohne Datei, ohne Server.
# =============================================================================
class ReportBlockCatalogTests(unittest.TestCase):

    # BK01 -------------------------------------------------------------------
    def test_bk01_reihenfolge_und_felder(self):
        doc = _Doc([
            _Blk("b1", "paragraph", plain="Erster Absatz."),
            _Blk("b2", "header", plain="Zwischenüberschrift"),
            _Blk("b3", "quote", plain="Ein Zitat."),
        ])
        items = ReportBlockCatalog().bauen(doc)
        self.assertEqual([i["ordinal"] for i in items], [1, 2, 3])
        self.assertEqual([i["block_id"] for i in items], ["b1", "b2", "b3"])
        self.assertEqual([i["type_label"] for i in items],
                         ["Absatz", "Überschrift", "Zitat"])
        self.assertEqual(items[0]["excerpt"], "Erster Absatz.")
        self.assertFalse(items[0]["truncated"])
        self.assertEqual(items[0]["comment_count"], 0)

    # BK02 -------------------------------------------------------------------
    def test_bk02_kuerzung_wird_gemeldet(self):
        lang = ("Der Beschuldigte meldete sich am vierzehnten Maerz "
                "zweitausendvierundzwanzig um zweiundzwanzig Uhr an.")
        items = ReportBlockCatalog(auszug_laenge=40).bauen(
            _Doc([_Blk("b1", "paragraph", plain=lang)]))
        auszug = items[0]["excerpt"]
        self.assertTrue(items[0]["truncated"],
                        "Die Kuerzung MUSS gemeldet werden, nicht nur geschehen.")
        self.assertTrue(auszug.endswith("…"), auszug)
        # Am Wortende geschnitten: kein angebrochenes Wort vor dem Anhang.
        self.assertTrue(lang.startswith(auszug.replace(" …", "")), auszug)
        self.assertNotIn("  ", auszug)

    # BK03 -------------------------------------------------------------------
    def test_bk03_zehnter_blocktyp_bleibt_sichtbar(self):
        """Ein unbekannter Typ darf nicht als leere Zeile enden — sonst waere
        er in der Auswahl unauffindbar und der Kommentar unmoeglich (GR1)."""
        doc = _Doc([_Blk("bx", "zeitleiste",
                         data={"eintraege": ["14.03.2024 Anmeldung"]},
                         known=False)])
        items = ReportBlockCatalog().bauen(doc)
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0]["is_known_type"])
        self.assertIn("zeitleiste", items[0]["type_label"])
        # Auffangstufe: der Text steht trotzdem da.
        self.assertIn("Anmeldung", items[0]["excerpt"])

    # BK04 -------------------------------------------------------------------
    def test_bk04_block_ohne_text(self):
        items = ReportBlockCatalog().bauen(_Doc([_Blk("b1", "delimiter")]))
        self.assertEqual(items[0]["excerpt"], AUSZUG_LEER)
        self.assertEqual(items[0]["type_label"], "Trennlinie")
        self.assertFalse(items[0]["truncated"])

    # BK05 -------------------------------------------------------------------
    def test_bk05_kommentarzaehlung(self):
        kommentare = [
            {"block_id": "b1"}, {"block_id": "b1"}, {"block_id": "b2"},
            {"block_id": None},          # ankerlos
            {"block_id": ""},            # ankerlos (leerer String)
        ]
        kat = ReportBlockCatalog()
        zahlen = kat.zaehle_kommentare(kommentare)
        self.assertEqual(zahlen, {"b1": 2, "b2": 1})
        # Die ankerlosen verschwinden NICHT in der Differenz.
        self.assertEqual(kat.zaehle_ankerlose(kommentare), 2)

        items = kat.bauen(
            _Doc([_Blk("b1", "paragraph", plain="A"),
                  _Blk("b2", "paragraph", plain="B"),
                  _Blk("b3", "paragraph", plain="C")]), zahlen)
        self.assertEqual([i["comment_count"] for i in items], [2, 1, 0])

    # BK06 -------------------------------------------------------------------
    def test_bk06_inline_html_nicht_im_auszug(self):
        items = ReportBlockCatalog().bauen(_Doc([
            _Blk("b1", "paragraph",
                 plain='Der <b>Beschuldigte</b> war <mark>anwesend</mark>.')]))
        auszug = items[0]["excerpt"]
        self.assertNotIn("<", auszug)
        self.assertIn("Beschuldigte", auszug)
        # Tag wurde durch EIN Leerzeichen ersetzt, nicht durch nichts:
        # 'Der Beschuldigte' darf nicht zu 'DerBeschuldigte' verkleben.
        self.assertIn("Der Beschuldigte", auszug)

    # BK07 -------------------------------------------------------------------
    def test_bk07_kuerzung_zaehlt_zeichen_nicht_bytes(self):
        """Das Forum ist multilingual (Fallerkenntnis 2). Eine Byte-Grenze
        zerschnitte Mehrbyte-Zeichen und erzeugte ungueltiges UTF-8."""
        text = "Москва" * 20            # 120 Zeichen, 240 Bytes in UTF-8
        items = ReportBlockCatalog(auszug_laenge=10).bauen(
            _Doc([_Blk("b1", "paragraph", plain=text)]))
        auszug = items[0]["excerpt"]
        self.assertTrue(items[0]["truncated"])
        # Der Auszug ohne Anhang ist hoechstens 10 ZEICHEN lang ...
        kern = auszug.replace(" …", "")
        self.assertLessEqual(len(kern), 10)
        # ... und laesst sich verlustfrei nach UTF-8 und zurueck wandeln.
        self.assertEqual(auszug.encode("utf-8").decode("utf-8"), auszug)

    # Randfall: auszug_laenge < 1 ist ein Programmierfehler und wird gemeldet.
    def test_bk07b_ungueltige_laenge(self):
        with self.assertRaises(ValueError):
            ReportBlockCatalog(auszug_laenge=0)


# =============================================================================
# (B)+(C) Endpunkt und Ankerpruefung — echte evidence_<uid>.db, KEIN Mock.
# =============================================================================
_BLOCK1 = json.dumps({"text": "Der Beschuldigte meldete sich an."})
_BLOCK2 = json.dumps({"text": "Die Auswertung ergab Folgendes."})


def _seed_evidence(path: Path) -> None:
    con = sqlite3.connect(str(path))
    try:
        EvidenceDb(con, db_path=str(path))
        con.execute(
            "INSERT INTO reports (id, report_type, sequence_nr, title, "
            "created_by, created_at, status) "
            "VALUES (1,'final',1,'Hauptbericht','inv',1000,'submitted')")
        # ABSICHT: b2 traegt sort_index 0, b1 traegt 1 — die Ausgabereihenfolge
        # ist damit NICHT die Einfuegereihenfolge. Nur so kann BK08 zeigen,
        # dass die Ordnungszahl der Vorschau folgt und nicht der Tabelle.
        for bid, bt, bd in (("b1", "paragraph", _BLOCK1),
                            ("b2", "header", _BLOCK2)):
            con.execute(
                "INSERT INTO report_blocks (block_id, report_id, author, "
                "created_at, updated_at, block_type, block_data, "
                "placeholder_values_json, module_id) "
                "VALUES (?,1,'inv',1000,1000,?,?,NULL,NULL)", (bid, bt, bd))
        con.execute(
            "INSERT INTO report_block_order (block_id, sort_index, "
            "last_modified_by, last_modified_at) VALUES ('b2', 0, 'inv', 1000)")
        con.execute(
            "INSERT INTO report_block_order (block_id, sort_index, "
            "last_modified_by, last_modified_at) VALUES ('b1', 1, 'inv', 1000)")
        con.commit()
    finally:
        con.close()


class ReportBlocksApiTests(unittest.TestCase):

    _PATH = "/api/report/blocks"

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=delete")
        con.execute(_PERSON)
        now = int(time.time())
        for pid, un, disp in ((1, "h001", "Lektor"), (2, "h002", "Fremd")):
            con.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?, ?, ?, 1, 0, 0, ?)", (pid, un, disp, now))
        con.execute(_OLD_SCRAPE_JOBS)
        con.execute("INSERT INTO scrape_jobs (user_id, username, created_at) "
                    "VALUES (700, 'b700', ?)", (now,))
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con

        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        self.rbac = RbacRepo(self.con, self.writer)
        self.cases = CasesRepo(self.con, self.writer)
        self.rbac.grant("lector", "reports.review", scope="alle", actor_id=1)
        self.rbac.assign_role(1, "lector", actor_id=1)
        self.cases.create_case(700, "b700", actor_id=1)

        self._evidence_dir = os.path.join(self._tmp, "evidence")
        self._forensic_dir = os.path.join(self._tmp, "forensic")
        self._assets_dir = os.path.join(self._tmp, "assets")
        for d in (self._evidence_dir, self._forensic_dir, self._assets_dir):
            os.makedirs(d, exist_ok=True)
        self._templates_db = os.path.join(self._tmp, "templates.db")
        self._ev700 = Path(self._evidence_dir) / "evidence_700.db"
        _seed_evidence(self._ev700)

    def tearDown(self):
        try:
            self.con.close()
        except Exception:
            pass
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    def _app(self) -> ManagementApp:
        return ManagementApp(
            self._db,
            evidence_dir=self._evidence_dir,
            forensic_dir=self._forensic_dir,
            assets_dir=self._assets_dir,
            templates_db=self._templates_db,
            default_db=os.path.join(self._tmp, "default.db"))

    def _blocks(self, person=1, uid="700"):
        r = self._app().dispatch(person, self._PATH, {"subject_id": [uid]})
        return r, (json.loads(r.body.decode("utf-8")) if r.body else {})

    def _create(self, person=1, **kw):
        body = {"subject_id": 700, "report_id": 1}
        body.update(kw)
        return self._app().dispatch_write(person, "/api/report/comment", body)

    # BK08 -------------------------------------------------------------------
    def test_bk08_reihenfolge_gleich_der_vorschau(self):
        r, d = self._blocks()
        self.assertEqual(r.status, 200)
        self.assertEqual(d["count"], 2)
        # b2 steht laut report_block_order VOR b1 — die Ordnungszahl folgt der
        # Ausgabereihenfolge und nicht der Einfuegereihenfolge.
        self.assertEqual([b["block_id"] for b in d["blocks"]], ["b2", "b1"])
        self.assertEqual([b["ordinal"] for b in d["blocks"]], [1, 2])
        self.assertEqual(d["blocks"][0]["type_label"], "Überschrift")
        self.assertEqual(d["unanchored_comments"], 0)

        # GEGENPROBE: dieselbe Reihenfolge wie im gerenderten Vorschau-HTML.
        rr = self._app().dispatch(1, "/api/report/render",
                                  {"subject_id": ["700"]})
        self.assertEqual(rr.status, 200)
        html = rr.body.decode("utf-8")
        self.assertLess(html.index("Die Auswertung"), html.index("Der Beschuldigte"),
                        "Katalog und Vorschau muessen dieselbe Reihenfolge zeigen.")

    # BK09 -------------------------------------------------------------------
    def test_bk09_ohne_recht_403(self):
        r, _ = self._blocks(person=2)
        self.assertEqual(r.status, 403)

    # BK10 -------------------------------------------------------------------
    def test_bk10_fehleingaben(self):
        r, d = self._blocks(uid="999")
        self.assertEqual(r.status, 404)
        self.assertEqual(d["error"], "evidence_not_found")
        r2 = self._app().dispatch(1, self._PATH, {})
        self.assertEqual(r2.status, 400)

    # BK11 -------------------------------------------------------------------
    def test_bk11_read_only(self):
        vorher = _md5(self._ev700)
        r, d = self._blocks()
        # WIRKUNGSPRUEFUNG, NICHT VAKUUM: Erst festhalten, dass der Aufruf
        # ueberhaupt etwas getan hat. Ohne diese beiden Zeilen waere der Test
        # auch dann gruen, wenn es den Endpunkt gar nicht gaebe (404 aendert
        # naturgemaess keine Datei) — derselbe Fehler wie in Vorgang 9d4b6f80
        # ("gruen-aber-tot").
        self.assertEqual(r.status, 200)
        self.assertEqual(d["count"], 2)
        self.assertEqual(_md5(self._ev700), vorher,
                         "Der Katalog darf die Beweismitteldatenbank nicht "
                         "veraendern (Migrationsvorbehalt).")

    # BK12 -------------------------------------------------------------------
    def test_bk12_kommentar_ohne_anker_abgewiesen(self):
        """GEGENPROBE ZU BUILD 658: dort lieferte dieser Aufruf 200 und legte
        einen Kommentar an, der auf nichts zeigte."""
        r = self._create(comment_text="Passt so nicht.")
        self.assertEqual(r.status, 400)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["error"], "block_id_required")
        # Es darf auch keine Addendum-Datei entstanden sein.
        self.assertFalse(addendum_path(self._evidence_dir, 700, 1).exists())

    # BK13 -------------------------------------------------------------------
    def test_bk13_unbekannter_anker_abgewiesen_und_genannt(self):
        r = self._create(block_id="b-tippfehler", comment_text="Hier fehlt was.")
        self.assertEqual(r.status, 400)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["error"], "block_unknown")
        # Der abgewiesene Wert wird MITGENANNT — sonst raet die Anwenderin.
        self.assertEqual(d["block_id"], "b-tippfehler")
        self.assertTrue(d.get("detail"))
        self.assertFalse(addendum_path(self._evidence_dir, 700, 1).exists(),
                         "Ein abgewiesener Kommentar darf nichts hinterlassen.")

    # BK14 -------------------------------------------------------------------
    def test_bk14_unpruefbar_ist_nicht_unbekannt(self):
        """DREI WERTE, NICHT ZWEI. 'Ich konnte nicht nachsehen' ist etwas
        anderes als 'diesen Block gibt es nicht' — bis Build 658 fuehrte
        beides zu demselben stillen Schreibvorgang mit block_sha256=NULL."""
        os.remove(self._ev700)
        r = self._create(block_id="b1", comment_text="Hier fehlt was.")
        self.assertEqual(r.status, 503,
                         "Fehlende Beweismitteldatenbank ist ein Betriebs"
                         "befund (503), kein Eingabefehler (400).")
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["error"], "block_uncheckable")
        self.assertIn("evidence_700.db", d.get("detail", ""))

    # BK15 -------------------------------------------------------------------
    def test_bk15_gueltiger_weg_bleibt_heil(self):
        r = self._create(block_id="b1", comment_text="Bitte praezisieren.")
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["block_id"], "b1")
        p = addendum_path(self._evidence_dir, 700, 1)
        self.assertTrue(p.exists())
        c = sqlite3.connect("file:%s?mode=ro" % p.resolve(), uri=True)
        try:
            row = c.execute("SELECT block_sha256 FROM review_comments "
                            "WHERE comment_id = ?", (d["comment_id"],)).fetchone()
        finally:
            c.close()
        self.assertEqual(row[0],
                         hashlib.sha256(_BLOCK1.encode("utf-8")).hexdigest())

        # Und der Katalog zaehlt den frischen Kommentar an b1 mit.
        _, cat = self._blocks()
        zahlen = {b["block_id"]: b["comment_count"] for b in cat["blocks"]}
        self.assertEqual(zahlen, {"b1": 1, "b2": 0})


if __name__ == "__main__":
    unittest.main()
