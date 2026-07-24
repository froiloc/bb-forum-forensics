# =============================================================================
# tests/test_subject_alias_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Identitaet (AP-2A)
# =============================================================================
# Testsuite fuer Build 504: SubjectAliasRepo (globaler Alias-Katalog, M022).
#
# AL01 — add() legt an; list() liefert den Eintrag mit Art-Label; audit_seq und
#        created_audit_seq sind mit der echten Beleg-seq nachgetragen.
# AL02 — ci-NORMALISIERUNG mit NICHT-ASCII (kyrillisch/griechisch/Umlaut/'ss'):
#        casefold() faltet korrekt — der Kern der Kollations-Leitlinie.
# AL03 — Duplikat (aktiv, gleiche Normform am selben Konto) -> CrossrefError,
#        auch bei abweichender Gross-/Kleinschreibung.
# AL04 — retract() ist SOFT: Zeile bleibt, is_active=0, Grund gespeichert.
# AL05 — retract() ohne Grund -> CrossrefError (kein stilles Aussortieren).
# AL06 — nach Widerruf ist die Neuvergabe desselben Namens erlaubt
#        (partieller UNIQUE-Index).
# AL07 — reinstate() kollidiert mit einem inzwischen aktiven Duplikat -> Fehler.
# AL08 — search(): Rueckwaertssuche ueber die Normform, inkl. LIKE-Entschaerfung
#        und leerem Begriff (-> leere Liste, KEIN Gesamtabzug).
# AL09 — counts(): total/aktiv/widerrufen/subjects.
# AL10 — SENSIBILITAET: Klartext (alias/basis/note/Grund) taucht NICHT im rohen
#        audit_log auf; die Laengen jedoch schon.
#
# Version: v0.8.504 · Build: 504 · 2026-07-24
# =============================================================================

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
from management.crossref.identified_subject_repo import CrossrefError
from management.crossref.subject_alias_repo import ALIAS_KINDS, SubjectAliasRepo
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover

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


class SubjectAliasRepoTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        now = int(time.time())
        con.execute(_PERSON)
        con.execute(
            "INSERT INTO person (id, system_username, display_name, created_at) "
            "VALUES (1, 'h001', 'Ermittler Eins', ?)", (now,))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con
        self.now = now
        self.repo = SubjectAliasRepo(con, CoordinatorWriter(con, AuditLog(con)))
        self.ro = SubjectAliasRepo(con)

    def tearDown(self):
        try:
            self.con.close()
        finally:
            for fn in os.listdir(self._tmp):
                try:
                    os.remove(os.path.join(self._tmp, fn))
                except OSError:
                    pass
            os.rmdir(self._tmp)

    def _raw_audit(self):
        """
        Roher audit_log-Text — die Pruefflaeche der Sensibilitaetsregel.
        Gelesen werden die EINGEFROREN benannten Spalten 'content' (Payload)
        und 'meta'; beide gehen in die Hash-Kette ein und sind damit genau die
        Stellen, an denen sensibler Klartext dauerhaft haengen bliebe.
        """
        rows = self.con.execute(
            "SELECT event_type, content, meta FROM audit_log").fetchall()
        return "\n".join("%s %s %s" % (r["event_type"], r["content"], r["meta"])
                         for r in rows)

    # AL01 -------------------------------------------------------------------
    def test_al01_add_und_list(self):
        res = self.repo.add(subject_id=4711, alias="Panther",
                            kind_code="forenname", basis="Signatur in Post 12",
                            actor_id=1)
        self.assertGreater(res["audit_seq"], 0)
        self.assertGreater(res["alias_id"], 0)

        rows = self.ro.list()
        self.assertEqual(len(rows), 1)
        e = rows[0]
        self.assertEqual(e["subject_id"], 4711)
        self.assertEqual(e["alias"], "Panther")          # Original erhalten
        self.assertEqual(e["alias_norm"], "panther")     # Normform
        self.assertEqual(e["kind_code"], "forenname")
        self.assertEqual(e["kind_label"], ALIAS_KINDS["forenname"])
        self.assertTrue(e["is_active"])
        self.assertIsNone(e["retracted_reason"])
        # audit_seq-Backfill: beide Felder tragen die echte Beleg-seq.
        self.assertEqual(e["audit_seq"], res["audit_seq"])
        self.assertEqual(e["created_audit_seq"], res["audit_seq"])

    # AL02 -------------------------------------------------------------------
    def test_al02_ci_normalisierung_nicht_ascii(self):
        """
        Der Kern der Kollations-Leitlinie: das Forum ist multilingual, und
        ASCII-NOCASE haette hier still zwei Eintraege erzeugt.
        """
        self.assertEqual(SubjectAliasRepo.normalize("Ярослав"),
                         SubjectAliasRepo.normalize("ЯРОСЛАВ"))
        self.assertEqual(SubjectAliasRepo.normalize("Σοφία"),
                         SubjectAliasRepo.normalize("ΣΟΦΊΑ"))
        self.assertEqual(SubjectAliasRepo.normalize("Grüße"),
                         SubjectAliasRepo.normalize("GRÜSSE"))
        # Randstriche werden entfernt, der Originaltext bleibt davon unberuehrt.
        self.assertEqual(SubjectAliasRepo.normalize("  Panther  "), "panther")

        # ... und die DB-Ebene zieht mit: Anlage kyrillisch, Duplikat in
        # Grossbuchstaben wird abgelehnt.
        self.repo.add(subject_id=1, alias="Ярослав", kind_code="forenname",
                      actor_id=1)
        with self.assertRaises(CrossrefError):
            self.repo.add(subject_id=1, alias="ЯРОСЛАВ",
                          kind_code="forenname", actor_id=1)

    # AL03 -------------------------------------------------------------------
    def test_al03_duplikat_aktiv(self):
        self.repo.add(subject_id=1, alias="Panther", kind_code="forenname",
                      actor_id=1)
        with self.assertRaises(CrossrefError) as cm:
            self.repo.add(subject_id=1, alias="pANTHER",
                          kind_code="handle", actor_id=1)
        self.assertIn("bereits aktiv erfasst", str(cm.exception))
        # Am ANDEREN Konto ist derselbe Name selbstverstaendlich erlaubt —
        # das ist ja gerade der interessante Befund.
        self.repo.add(subject_id=2, alias="Panther", kind_code="forenname",
                      actor_id=1)
        self.assertEqual(len(self.ro.list()), 2)

    # AL04 -------------------------------------------------------------------
    def test_al04_retract_ist_soft(self):
        r = self.repo.add(subject_id=1, alias="Panther",
                          kind_code="forenname", actor_id=1)
        self.repo.retract(alias_id=r["alias_id"],
                          reason="Verwechslung mit Konto 99", actor_id=1)
        # Ohne include_retracted unsichtbar ...
        self.assertEqual(self.ro.list(), [])
        # ... die Zeile existiert aber weiter, mit Grund.
        rows = self.ro.list(include_retracted=True)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["is_active"])
        self.assertEqual(rows[0]["retracted_reason"],
                         "Verwechslung mit Konto 99")
        # NIE geloescht:
        n = self.con.execute("SELECT COUNT(*) FROM subject_alias").fetchone()[0]
        self.assertEqual(n, 1)

    # AL05 -------------------------------------------------------------------
    def test_al05_retract_ohne_grund(self):
        r = self.repo.add(subject_id=1, alias="Panther",
                          kind_code="forenname", actor_id=1)
        for bad in ("", "   ", None):
            with self.assertRaises(CrossrefError):
                self.repo.retract(alias_id=r["alias_id"], reason=bad,
                                  actor_id=1)
        # Der Eintrag ist unveraendert aktiv geblieben.
        self.assertTrue(self.ro.list()[0]["is_active"])

    # AL06 -------------------------------------------------------------------
    def test_al06_neuvergabe_nach_widerruf(self):
        r = self.repo.add(subject_id=1, alias="Panther",
                          kind_code="forenname", actor_id=1)
        self.repo.retract(alias_id=r["alias_id"], reason="Irrtum", actor_id=1)
        # Der partielle UNIQUE-Index laesst die Neuvergabe zu.
        r2 = self.repo.add(subject_id=1, alias="Panther",
                           kind_code="handle", basis="neuer Fund", actor_id=1)
        self.assertNotEqual(r2["alias_id"], r["alias_id"])
        aktive = self.ro.list()
        self.assertEqual(len(aktive), 1)
        self.assertEqual(aktive[0]["kind_code"], "handle")
        self.assertEqual(len(self.ro.list(include_retracted=True)), 2)

    # AL07 -------------------------------------------------------------------
    def test_al07_reinstate_kollision(self):
        r1 = self.repo.add(subject_id=1, alias="Panther",
                           kind_code="forenname", actor_id=1)
        self.repo.retract(alias_id=r1["alias_id"], reason="Irrtum", actor_id=1)
        self.repo.add(subject_id=1, alias="PANTHER", kind_code="handle",
                      actor_id=1)
        with self.assertRaises(CrossrefError) as cm:
            self.repo.reinstate(alias_id=r1["alias_id"], actor_id=1)
        self.assertIn("erneut aktiv erfasst", str(cm.exception))
        # Ohne Kollision klappt die Zuruecknahme.
        r3 = self.repo.add(subject_id=2, alias="Luchs",
                           kind_code="forenname", actor_id=1)
        self.repo.retract(alias_id=r3["alias_id"], reason="Zweifel", actor_id=1)
        self.repo.reinstate(alias_id=r3["alias_id"], actor_id=1)
        wieder = [e for e in self.ro.list() if e["id"] == r3["alias_id"]]
        self.assertEqual(len(wieder), 1)
        self.assertIsNone(wieder[0]["retracted_reason"])

    # AL08 -------------------------------------------------------------------
    def test_al08_search(self):
        self.repo.add(subject_id=1, alias="Panther", kind_code="forenname",
                      actor_id=1)
        self.repo.add(subject_id=2, alias="PantherKing",
                      kind_code="handle", actor_id=1)
        self.repo.add(subject_id=3, alias="Luchs", kind_code="forenname",
                      actor_id=1)

        treffer = self.ro.search("panther")
        self.assertEqual(sorted(t["subject_id"] for t in treffer), [1, 2])
        # Gross-/Kleinschreibung des SUCHBEGRIFFS ist ebenso egal.
        self.assertEqual(len(self.ro.search("PANTH")), 2)
        # Leerer Begriff -> kein stiller Gesamtabzug.
        self.assertEqual(self.ro.search(""), [])
        self.assertEqual(self.ro.search("   "), [])
        # LIKE-Sonderzeichen wirken NICHT als Platzhalter.
        self.assertEqual(self.ro.search("%"), [])
        self.assertEqual(self.ro.search("_"), [])

    # AL09 -------------------------------------------------------------------
    def test_al09_counts(self):
        a = self.repo.add(subject_id=1, alias="A", kind_code="forenname",
                          actor_id=1)
        self.repo.add(subject_id=1, alias="B", kind_code="handle", actor_id=1)
        self.repo.add(subject_id=2, alias="C", kind_code="handle", actor_id=1)
        self.repo.retract(alias_id=a["alias_id"], reason="Irrtum", actor_id=1)

        c = self.ro.counts()
        self.assertEqual(c["total"], 3)
        self.assertEqual(c["aktiv"], 2)
        self.assertEqual(c["widerrufen"], 1)
        self.assertEqual(c["subjects"], 2)

    # AL10 -------------------------------------------------------------------
    def test_al10_sensibilitaet(self):
        """
        Der sensible Freitext darf im Beleg NICHT auftauchen — nur Fakten und
        Textlaengen. Das ist die Regel, die den audit_log pruefbar haelt, ohne
        die PII zu spiegeln.
        """
        geheim_alias = "KlarnameMuellerXY"
        geheim_basis = "IP 203.0.113.9 aus Bestandsauskunft"
        geheim_note = "Hinweis von VP 7"
        geheim_grund = "Bestandsauskunft war fehlerhaft"

        r = self.repo.add(subject_id=1, alias=geheim_alias,
                          kind_code="forenname", basis=geheim_basis,
                          note=geheim_note, actor_id=1)
        self.repo.update(alias_id=r["alias_id"], basis="korrigiert",
                         actor_id=1)
        self.repo.retract(alias_id=r["alias_id"], reason=geheim_grund,
                          actor_id=1)
        self.repo.reinstate(alias_id=r["alias_id"], actor_id=1)

        raw = self._raw_audit()
        for geheim in (geheim_alias, geheim_basis, geheim_note, geheim_grund):
            self.assertNotIn(geheim, raw,
                             "Sensibler Klartext %r steht im audit_log!"
                             % geheim)
        # Die FAKTEN stehen sehr wohl drin — der Beleg bleibt pruefbar.
        self.assertIn("subject_alias_added", raw)
        self.assertIn("subject_alias_updated", raw)
        self.assertIn("subject_alias_retracted", raw)
        self.assertIn("subject_alias_reinstated", raw)
        add_row = self.con.execute(
            "SELECT content FROM audit_log "
            "WHERE event_type='subject_alias_added'").fetchone()
        payload = json.loads(add_row["content"])
        self.assertEqual(payload["alias_len"], len(geheim_alias))
        self.assertEqual(payload["basis_len"], len(geheim_basis))
        self.assertEqual(payload["note_len"], len(geheim_note))
        self.assertEqual(payload["subject_id"], 1)
        self.assertEqual(payload["kind_code"], "forenname")

    # Zusatz: Schutzregeln, die sonst leicht durchrutschen ------------------
    def test_al11_schutzregeln(self):
        # Ungueltige Art wird vom Repo abgefangen, bevor die DDL-CHECK greift.
        with self.assertRaises(CrossrefError):
            self.repo.add(subject_id=1, alias="X", kind_code="quatsch",
                          actor_id=1)
        # Leerer Alias.
        with self.assertRaises(CrossrefError):
            self.repo.add(subject_id=1, alias="   ", kind_code="forenname",
                          actor_id=1)
        # No-Op-Update wirft und erzeugt keinen irrefuehrenden Beleg.
        r = self.repo.add(subject_id=1, alias="Panther",
                          kind_code="forenname", basis="b", actor_id=1)
        with self.assertRaises(CrossrefError):
            self.repo.update(alias_id=r["alias_id"], kind_code="forenname",
                             basis="b", actor_id=1)
        # Schreiben ohne Writer ist kein unauditierter Schleichweg.
        with self.assertRaises(CrossrefError):
            self.ro.add(subject_id=9, alias="Y", kind_code="forenname")


if __name__ == "__main__":
    unittest.main()
