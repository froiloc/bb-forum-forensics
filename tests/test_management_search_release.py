# =============================================================================
# tests/test_management_search_release.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Volltextsuche (AP-3E, B561)
# =============================================================================
# Testsuite fuer Build 561: Migration M040 (fulltext_zweck, fulltext_release),
# Zweckcode-Vokabular, Recht 'fulltext.release', EventTypes und der auditierte
# Schreibpfad der Inhaltsfreigabe (Modell B, Stufe 2).
#
# VOLLSTAENDIG automatisiert, NUR synthetische Daten — KEIN reales
# Beweismaterial.
#
# LEITLINIE (Lehre aus den Builds 533/535, Uebergabe §4): Wirkungspruefungen
#   statt Existenzpruefungen. FR04/FR05 pruefen nicht, dass ein CHECK bzw. ein
#   Fremdschluessel im DDL STEHT, sondern dass die DATENBANK den falschen
#   Wert ABLEHNT — auch dann, wenn man am Repository vorbeischreibt.
#
# FR01 — M040 legt beide Tabellen, drei Indizes und die Faehigkeit an;
#        zweiter Lauf ist ein No-op (Idempotenz)
# FR02 — QUERPROBE M040-SEED <-> zweck_vokabular.py: Codes, Labels und
#        Freitextpflicht stimmen ueberein. Liefen sie auseinander, boete die
#        Sicht etwas an, das der Fremdschluessel ablehnt
# FR03 — pruefe(): unbekannter Code, fehlender Pflichtfreitext und Freitext
#        ohne Pflicht werden abgelehnt — hart, nicht nachsichtig
# FR04 — WIRKUNG des CHECK: 'sonstiges' ohne Freitext und ein anderer Code MIT
#        Freitext werden von der DATENBANK abgelehnt (am Repo vorbei)
# FR05 — WIRKUNG des Fremdschluessels: unbekannter zweck_code wird abgelehnt
# FR06 — erteile(): Zeile + Beleg in EINER Transaktion, audit_seq gesetzt
# FR07 — zweite gueltige Freigabe je (Fall, Person) -> Fachfehler mit Klartext
# FR08 — WIRKUNG des partiellen UNIQUE-Index: auch am Repo vorbei kein
#        zweiter aktiver Satz — aber widerrufene Zeilen behindern nicht
# FR09 — widerrufe(): is_active kippt, die ZEILE BLEIBT, revoke_audit_seq
#        gesetzt; zweiter Widerruf -> Fachfehler
# FR10 — nach Widerruf ist eine erneute Freigabe moeglich
# FR11 — darf_inhalt_sehen(): eigener_fall / freigabe / gesperrt /
#        unbekannt_wer sind VIER unterscheidbare Befunde
# FR12 — Vorrang: der eigene Fall schlaegt eine vorhandene Freigabe (der
#        Beleg soll den richtigen Grund tragen)
# FR13 — SENSIBILITAET: im Audit-Payload steht KEIN Freitext, nur Fakten,
#        der Zweckcode und Textlaengen
# FR14 — ohne Gateway und ohne Handelnden wird NICHTS geschrieben
# FR15 — Rollback: schlaegt der Fachwrite fehl, bleibt weder Zeile noch Beleg
# FR16 — die drei neuen EventTypes sind gueltig und in ALL
# FR17 — zweck_katalog() liefert die DB-Liste; ohne M040 leer statt Absturz
#
# Version: v0.8.561 · Build: 561 · 2026-07-26
# =============================================================================

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations
from management.audit.audit_log import AuditLog
from management.audit.event_types import EventType
from management.cases.cases_repo import CasesRepo
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.rbac import catalog
from management.rbac.rbac_repo import RbacRepo
from management.search import zweck_vokabular as zv
from management.search.release_repo import (
    GRUND_EIGENER_FALL,
    GRUND_FREIGABE,
    GRUND_GESPERRT,
    GRUND_UNBEKANNT_WER,
    FulltextReleaseFehler,
    FulltextReleaseRepo,
)

_PERSON = """
CREATE TABLE person (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0,
    is_support INTEGER NOT NULL DEFAULT 0,
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

#: Die Migration dieses Builds. Die Nummer ist VORLAEUFIG (Sperrvermerk im
#  Dateikopf von m040_fulltext_release.py) — wird sie geaendert, aendert sie
#  sich HIER MIT, und der Test findet sie ueber das Modul statt ueber die Zahl.
_M040 = next(m for m in discover(coordinator_migrations)
             if m.__name__.endswith("m040_fulltext_release"))


class ReleaseTestBasis(unittest.TestCase):
    """Coordinator-DB mit vollem Migrationslauf, drei Personen, RBAC, Cases."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="aiw_release_")
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row

        self.NOW = int(time.time())
        self.con.execute(_PERSON)
        self.con.executemany(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(1, "h001", "Chefin, Alpha", 1, 1, 0, self.NOW),
             (2, "h002", "Beta", 1, 0, 0, self.NOW),
             (3, "h003", "Gamma", 1, 0, 0, self.NOW)])
        self.con.execute(_OLD_SCRAPE_JOBS)

        self.audit = AuditLog(self.con)
        self.mods = discover(coordinator_migrations)
        self.applied = MigrationRunner(self.con, self.mods, audit=self.audit,
                                       deployed_by="tester").run()

        self.writer = CoordinatorWriter(self.con, self.audit)
        self.rbac = RbacRepo(self.con, self.writer)
        self.rbac.grant("supervisor", "fulltext.release", scope="alle",
                        actor_id=1)
        self.rbac.assign_role(1, "supervisor", actor_id=1)

        self.cases = CasesRepo(self.con, self.writer)
        # Fall 5023 ist Person 2 zugewiesen, Fall 6114 niemandem.
        self.cases.create_case(5023, "birnenmus", actor_id=1)
        self.cases.assign(5023, 2, actor_id=1)
        self.cases.create_case(6114, "apfelsaft", actor_id=1)

        self.repo = FulltextReleaseRepo(self.con, self.writer)

    def tearDown(self):
        try:
            self.con.close()
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)

    # ------------------------------------------------------------- Helfer
    def _erteile(self, subject_id=6114, person_id=3,
                 zweck_code="kreuzbezug_nickname", zweck_freitext=None,
                 begruendung="Kreuzbezug zu Fall 5023 erforderlich.",
                 actor_id=1):
        return self.repo.erteile(
            subject_id=subject_id, person_id=person_id,
            zweck_code=zweck_code, zweck_freitext=zweck_freitext,
            begruendung=begruendung, actor_id=actor_id)

    def _zeile(self, release_id):
        return self.con.execute(
            "SELECT * FROM fulltext_release WHERE id = ?",
            (int(release_id),)).fetchone()

    def _beleg(self, seq):
        return self.con.execute(
            "SELECT * FROM audit_log WHERE seq = ?", (int(seq),)).fetchone()


# ====================================================== FR01 · FR02 · FR16
class TestMigrationUndVokabular(ReleaseTestBasis):

    def test_fr01_m040_legt_alles_an_und_ist_idempotent(self):
        for tabelle in ("fulltext_zweck", "fulltext_release"):
            self.assertIsNotNone(self.con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (tabelle,)).fetchone(), "Tabelle fehlt: %s" % tabelle)
        for index in ("ux_fulltext_release_aktiv",
                      "ix_fulltext_release_person",
                      "ix_fulltext_release_fall"):
            self.assertIsNotNone(self.con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
                (index,)).fetchone(), "Index fehlt: %s" % index)
        self.assertIsNotNone(self.con.execute(
            "SELECT 1 FROM rbac_capability WHERE code='fulltext.release'"
        ).fetchone())
        self.assertIn("fulltext.release", catalog.capability_codes())

        # Idempotenz: ein zweiter up()-Lauf darf nichts kaputtmachen.
        vorher = self.con.execute(
            "SELECT COUNT(*) FROM fulltext_zweck").fetchone()[0]
        _M040.up(self.con)
        self.assertEqual(vorher, self.con.execute(
            "SELECT COUNT(*) FROM fulltext_zweck").fetchone()[0])

    def test_fr02_seed_deckt_sich_mit_dem_vokabular(self):
        """
        Der Seed in M040 ist eine EINGEFRORENE Kopie (m005-Prinzip) — die
        Migration importiert zweck_vokabular.py absichtlich NICHT. Diese
        Bruecke haelt beide zur BAUZEIT zusammen. Liefen sie auseinander,
        boete die Auswahlliste der Sicht einen Code an, den der
        Fremdschluessel ablehnt: ein Fehler, der erst beim Schreiben auffiele.
        """
        aus_db = {r["code"]: (r["label"], r["beschreibung"],
                              bool(r["freitext_pflicht"]))
                  for r in self.con.execute("SELECT * FROM fulltext_zweck")}
        aus_code = {z.code: (z.label, z.beschreibung, z.freitext_pflicht)
                    for z in zv.ZWECKE}
        self.assertEqual(aus_code, aus_db,
                         "M040-Seed und zweck_vokabular.py sind auseinander "
                         "gelaufen.")

    def test_fr16_eventtypes(self):
        for wert in ("fulltext_searched", "fulltext_release_granted",
                     "fulltext_release_revoked"):
            self.assertTrue(EventType.is_valid(wert), wert)
            self.assertIn(wert, EventType.ALL)


# ======================================================= FR03 · FR04 · FR05
class TestZweckangabe(ReleaseTestBasis):

    def test_fr03_pruefe_ist_hart(self):
        self.assertEqual(("kreuzbezug_nickname", None),
                         zv.pruefe("kreuzbezug_nickname"))
        self.assertEqual(("sonstiges", "Amtshilfe LKA"),
                         zv.pruefe("sonstiges", "  Amtshilfe LKA  "))
        with self.assertRaises(zv.ZweckFehler):
            zv.pruefe("gibt_es_nicht")
        with self.assertRaises(zv.ZweckFehler):
            zv.pruefe("sonstiges", "   ")
        with self.assertRaises(zv.ZweckFehler):
            zv.pruefe("wiedervorlage", "unerwarteter Freitext")

    def test_fr04_check_wirkt_auch_am_repo_vorbei(self):
        """
        Die Regel 'Freitext genau dann, wenn der Code ihn verlangt' steht als
        CHECK in der TABELLE. Eine Regel, die nur die Anwendung kennt, gilt
        genau so lange, wie alle Schreibpfade durch die Anwendung laufen —
        hier wird bewusst daran vorbeigeschrieben.
        """
        basis = ("INSERT INTO fulltext_release (subject_id, person_id, "
                 "zweck_code, zweck_freitext, begruendung, granted_by, "
                 "granted_at, audit_seq, is_active) VALUES (?,?,?,?,?,?,?,?,1)")
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(basis, (6114, 3, "sonstiges", None, "x", 1,
                                     self.NOW, 1))
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(basis, (6114, 3, "sonstiges", "   ", "x", 1,
                                     self.NOW, 1))
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(basis, (6114, 3, "wiedervorlage", "Text", "x", 1,
                                     self.NOW, 1))
        # Die zulaessigen Formen gehen durch.
        self.con.execute(basis, (6114, 3, "sonstiges", "Amtshilfe", "x", 1,
                                 self.NOW, 1))
        self.con.execute(basis, (6114, 2, "wiedervorlage", None, "x", 1,
                                 self.NOW, 1))

    def test_fr05_fremdschluessel_wirkt(self):
        """
        Der Fremdschluessel auf fulltext_zweck ist der eigentliche Grund fuer
        die Katalogtabelle: ein Tippfehler im Code wird von der DATENBANK
        abgelehnt. SQLite erzwingt Fremdschluessel nur bei eingeschaltetem
        PRAGMA — das wird hier ausdruecklich gesetzt, weil der Test genau
        diese Wirkung belegt und nicht die Voreinstellung der Verbindung.
        """
        self.con.execute("PRAGMA foreign_keys=ON")
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                self.con.execute(
                    "INSERT INTO fulltext_release (subject_id, person_id, "
                    "zweck_code, zweck_freitext, begruendung, granted_by, "
                    "granted_at, audit_seq, is_active) "
                    "VALUES (6114, 3, 'tippfehler', NULL, 'x', 1, ?, 1, 1)",
                    (self.NOW,))
        finally:
            self.con.execute("PRAGMA foreign_keys=OFF")


# ============================================ FR06 · FR07 · FR08 · FR13-FR15
class TestErteilen(ReleaseTestBasis):

    def test_fr06_erteile_schreibt_zeile_und_beleg(self):
        r = self._erteile()
        zeile = self._zeile(r["release_id"])
        self.assertIsNotNone(zeile)
        self.assertEqual(6114, zeile["subject_id"])
        self.assertEqual(3, zeile["person_id"])
        self.assertEqual("kreuzbezug_nickname", zeile["zweck_code"])
        self.assertIsNone(zeile["zweck_freitext"])
        self.assertEqual(1, zeile["is_active"])
        # Der Beleg traegt die Zeile, und die Zeile traegt den Beleg.
        self.assertEqual(r["audit_seq"], zeile["audit_seq"])
        beleg = self._beleg(r["audit_seq"])
        self.assertEqual(EventType.FULLTEXT_RELEASE_GRANTED,
                         beleg["event_type"])

    def test_fr07_zweite_gueltige_freigabe_wird_abgelehnt(self):
        self._erteile()
        with self.assertRaises(FulltextReleaseFehler) as ctx:
            self._erteile()
        self.assertIn("bereits eine gueltige Freigabe", str(ctx.exception))

    def test_fr08_unique_index_wirkt_auch_am_repo_vorbei(self):
        """
        E-1 verlangt EINE Freigabe je Fall und Person. Der partielle
        UNIQUE-Index setzt das in der Datenbank durch — hier wird bewusst am
        Repository vorbeigeschrieben. Widerrufene Zeilen duerfen dabei NICHT
        stoeren, sonst waere eine erneute Freigabe unmoeglich (FR10).
        """
        r = self._erteile()
        basis = ("INSERT INTO fulltext_release (subject_id, person_id, "
                 "zweck_code, zweck_freitext, begruendung, granted_by, "
                 "granted_at, audit_seq, is_active) "
                 "VALUES (6114, 3, 'wiedervorlage', NULL, 'x', 1, ?, 1, ?)")
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(basis, (self.NOW, 1))
        # Eine INAKTIVE Zeile ist zulaessig — der Index ist partiell.
        self.con.execute(basis, (self.NOW, 0))
        self.assertEqual(1, self.con.execute(
            "SELECT COUNT(*) FROM fulltext_release WHERE is_active = 1"
        ).fetchone()[0])
        self.assertIsNotNone(self._zeile(r["release_id"]))

    def test_fr13_kein_freitext_im_beleg(self):
        """
        SENSIBILITAETSREGEL (Muster M018/M022/M027): der Payload traegt
        FAKTEN, den ZWECKCODE und TEXTLAENGEN — niemals den Wortlaut. Die
        Begruendung einer Freigabe kann benennen, worum es in einem fremden
        Verfahren geht; sie gehoert in die Tabelle, nicht in die Kette.
        """
        geheim = "Klarname Mustermann, Hinweis aus Fall 5023"
        r = self._erteile(zweck_code="sonstiges", zweck_freitext=geheim,
                          begruendung=geheim)
        beleg = self._beleg(r["audit_seq"])
        roh = json.dumps({k: beleg[k] for k in beleg.keys()},
                         ensure_ascii=False, default=str)
        self.assertNotIn("Mustermann", roh)
        self.assertNotIn(geheim, roh)
        # Der Payload liegt in der Spalte 'content' (audit_log,
        # kanonisch serialisiert durch AuditLog.append).
        nutz = json.loads(beleg["content"])
        self.assertEqual("sonstiges", nutz["zweck_code"])
        self.assertEqual(len(geheim), nutz["begruendung_len"])
        self.assertEqual(len(geheim), nutz["zweck_freitext_len"])
        # Der Wortlaut steht dort, wo er hingehoert: in der Tabelle.
        self.assertEqual(geheim, self._zeile(r["release_id"])["begruendung"])

    def test_fr14_ohne_gateway_und_ohne_handelnden_wird_nichts_geschrieben(self):
        ohne = FulltextReleaseRepo(self.con, None)
        with self.assertRaises(FulltextReleaseFehler):
            ohne.erteile(subject_id=6114, person_id=3,
                         zweck_code="wiedervorlage",
                         begruendung="x", actor_id=1)
        with self.assertRaises(FulltextReleaseFehler):
            self._erteile(actor_id=None)
        with self.assertRaises(FulltextReleaseFehler):
            self._erteile(begruendung="   ")
        self.assertEqual(0, self.con.execute(
            "SELECT COUNT(*) FROM fulltext_release").fetchone()[0])

    def test_fr15_rollback_laesst_weder_zeile_noch_beleg(self):
        """
        Der Fachwrite und sein Beleg committen gemeinsam oder gar nicht.
        Geprueft wird an der Kollision aus FR07: sie wirft INNERHALB der
        Transaktion, nachdem die erste Freigabe bereits steht.
        """
        self._erteile()
        vorher_zeilen = self.con.execute(
            "SELECT COUNT(*) FROM fulltext_release").fetchone()[0]
        vorher_belege = self.con.execute(
            "SELECT COUNT(*) FROM audit_log").fetchone()[0]
        with self.assertRaises(FulltextReleaseFehler):
            self._erteile()
        self.assertEqual(vorher_zeilen, self.con.execute(
            "SELECT COUNT(*) FROM fulltext_release").fetchone()[0])
        self.assertEqual(vorher_belege, self.con.execute(
            "SELECT COUNT(*) FROM audit_log").fetchone()[0])


# =============================================================== FR09 · FR10
class TestWiderruf(ReleaseTestBasis):

    def test_fr09_widerruf_laesst_die_zeile_stehen(self):
        r = self._erteile()
        w = self.repo.widerrufe(release_id=r["release_id"],
                                reason="Kreuzbezug erledigt.", actor_id=1)
        zeile = self._zeile(r["release_id"])
        self.assertIsNotNone(zeile, "Die Zeile wurde geloescht statt "
                                    "widerrufen — stiller Beweisverlust.")
        self.assertEqual(0, zeile["is_active"])
        self.assertEqual(1, zeile["revoked_by"])
        self.assertEqual("Kreuzbezug erledigt.", zeile["revoke_reason"])
        self.assertEqual(w["audit_seq"], zeile["revoke_audit_seq"])
        self.assertEqual(EventType.FULLTEXT_RELEASE_REVOKED,
                         self._beleg(w["audit_seq"])["event_type"])

        with self.assertRaises(FulltextReleaseFehler):
            self.repo.widerrufe(release_id=r["release_id"], reason="nochmal",
                                actor_id=1)
        with self.assertRaises(FulltextReleaseFehler):
            self.repo.widerrufe(release_id=999999, reason="x", actor_id=1)

    def test_fr09b_widerruf_ohne_grund_wird_abgelehnt(self):
        r = self._erteile()
        with self.assertRaises(FulltextReleaseFehler):
            self.repo.widerrufe(release_id=r["release_id"], reason="  ",
                                actor_id=1)
        self.assertEqual(1, self._zeile(r["release_id"])["is_active"])

    def test_fr10_nach_widerruf_erneut_freigeben(self):
        r1 = self._erteile()
        self.repo.widerrufe(release_id=r1["release_id"], reason="erledigt",
                            actor_id=1)
        r2 = self._erteile()
        self.assertNotEqual(r1["release_id"], r2["release_id"])
        # Beide Zeilen stehen: die alte als Beleg, die neue als Befugnis.
        self.assertEqual(2, self.con.execute(
            "SELECT COUNT(*) FROM fulltext_release").fetchone()[0])
        self.assertEqual(0, self._zeile(r1["release_id"])["is_active"])
        self.assertEqual(1, self._zeile(r2["release_id"])["is_active"])


# =============================================================== FR11 · FR12
class TestSichtbarkeit(ReleaseTestBasis):

    def test_fr11_vier_unterscheidbare_befunde(self):
        # Person 2 hat Fall 5023 zugewiesen bekommen.
        eigen = self.repo.darf_inhalt_sehen(subject_id=5023, person_id=2)
        self.assertTrue(eigen["erlaubt"])
        self.assertEqual(GRUND_EIGENER_FALL, eigen["grund"])

        # Person 3 hat nichts — gesperrt, mit Klartext statt blossem False.
        gesperrt = self.repo.darf_inhalt_sehen(subject_id=6114, person_id=3)
        self.assertFalse(gesperrt["erlaubt"])
        self.assertEqual(GRUND_GESPERRT, gesperrt["grund"])
        self.assertIn("Anfrage", gesperrt["klartext"])

        # Nach der Freigabe: erlaubt, und der Grund nennt sie samt Herkunft.
        r = self._erteile(subject_id=6114, person_id=3)
        frei = self.repo.darf_inhalt_sehen(subject_id=6114, person_id=3)
        self.assertTrue(frei["erlaubt"])
        self.assertEqual(GRUND_FREIGABE, frei["grund"])
        self.assertEqual(r["release_id"], frei["release_id"])
        self.assertEqual(1, frei["freigegeben_von"])

        # Nach dem Widerruf wieder gesperrt.
        self.repo.widerrufe(release_id=r["release_id"], reason="erledigt",
                            actor_id=1)
        self.assertEqual(GRUND_GESPERRT, self.repo.darf_inhalt_sehen(
            subject_id=6114, person_id=3)["grund"])

        # Ohne Handelnden: EIGENER Befund, nicht 'gesperrt'. Ein
        # Konfigurationsfehler darf nicht wie eine Zugriffsentscheidung
        # aussehen.
        ohne = self.repo.darf_inhalt_sehen(subject_id=6114, person_id=None)
        self.assertFalse(ohne["erlaubt"])
        self.assertEqual(GRUND_UNBEKANNT_WER, ohne["grund"])

    def test_fr12_eigener_fall_schlaegt_freigabe(self):
        """
        Wer den Fall bearbeitet, sieht seinen Inhalt aus EIGENEM Recht, nicht
        aus geliehenem. Waere die Reihenfolge umgekehrt, truege der Beleg bei
        einer zufaellig vorhandenen Freigabe einen falschen Grund.
        """
        self._erteile(subject_id=5023, person_id=2)
        befund = self.repo.darf_inhalt_sehen(subject_id=5023, person_id=2)
        self.assertTrue(befund["erlaubt"])
        self.assertEqual(GRUND_EIGENER_FALL, befund["grund"])
        self.assertIsNone(befund["release_id"])

    def test_listen_beide_richtungen(self):
        self._erteile(subject_id=6114, person_id=3)
        self.assertEqual(1, len(self.repo.fuer_person(3)))
        self.assertEqual(1, len(self.repo.fuer_fall(6114)))
        self.assertEqual([], self.repo.fuer_person(2))
        # Der Klartext der Zweckangabe kommt mit — die Sicht soll den Code
        # nicht selbst uebersetzen muessen.
        self.assertIn("Kreuzbezug",
                      self.repo.fuer_person(3)[0]["zweck_klartext"])


# ======================================================================= FR17
class TestOhneMigration(unittest.TestCase):

    def test_fr17_ohne_m040_leer_statt_absturz(self):
        """
        'Keine Freigaben' und 'die Tabelle gibt es noch nicht' duerfen sich
        unterscheiden lassen — das zweite ist ein Betriebsbefund (Migration
        fehlt), kein Sachverhalt. Die Lesewege liefern leer statt zu werfen;
        table_exists() sagt, welcher der beiden Faelle vorliegt.
        """
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute("CREATE TABLE cases (subject_id INTEGER, assigned_to "
                    "INTEGER)")
        repo = FulltextReleaseRepo(con, None)
        self.assertFalse(FulltextReleaseRepo.table_exists(con))
        self.assertEqual([], repo.zweck_katalog())
        self.assertEqual([], repo.fuer_person(3))
        self.assertEqual([], repo.fuer_fall(6114))
        self.assertEqual(GRUND_GESPERRT, repo.darf_inhalt_sehen(
            subject_id=6114, person_id=3)["grund"])
        con.close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
