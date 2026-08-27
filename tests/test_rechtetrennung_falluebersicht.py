# =============================================================================
# tests/test_rechtetrennung_falluebersicht.py
# IT-Forensisches Ermittlungswerkzeug — Regression zu Vorgang 60fe72fb
# =============================================================================
# DER ANLASS (Alex, 31.07.2026): Mit dem Umbau des Dashboards auf das
# Kachelsystem ergibt es keinen Sinn mehr, 'dashboard.view' an die
# Falluebersicht zu koppeln. Das Recht wird auf das Kachel-Dashboard
# beschraenkt; die Sicht 'Fallübersicht' und die Kachel 'Fall-Übersicht
# (Ampel)' bekommen 'caseoverview.view'.
#
# WAS DARAN MEHR IST ALS EINE UMBENENNUNG: Die Kachel war die EINZIGE ohne
# eigenes Recht - sie lief auf dem Recht des Rahmens mit, waehrend jede andere
# Kachel ihr eigenes fuehrt. Wer den Ueberblick oeffnen durfte, bekam damit die
# vollstaendige Fallliste mit den Beschuldigten-Kontonamen ungefragt dazu.
#
# Testfaelle:
#   RB01 - M038 seedet 'caseoverview.view' und vergibt dabei KEINEN Grant.
#   RB02 - M038 berichtigt den Text von 'dashboard.view' - aber nur, wenn er
#          unveraendert der aus M006 ist. Eine fremde Fassung bleibt stehen.
#   RB03 - M038 ist idempotent (zweiter Lauf aendert nichts).
#   RB04 - Kachelkatalog und Sichtenkatalog der Hilfe nennen das neue Recht,
#          und der Sichtenkatalog stimmt mit dem VIEW_CATALOG in cockpit.js
#          ueberein.
#   RB05 - /api/overview verlangt 'caseoverview.view' - mit 'dashboard.view'
#          allein antwortet er 403 und NENNT das fehlende Recht.
#   RB06 - /api/search (Kommandopalette) verlangt dasselbe Recht. Sonst waere
#          sie ein zweiter Zugang zu denselben Falldaten.
#   RB07 - 'rbac_admin migrate-grants' uebernimmt aktive Grants samt Umfang,
#          schreibt je Grant einen Beleg und laesst das Quellrecht stehen.
#   RB08 - Der Probelauf schreibt NICHTS und sagt das.
#   RB09 - Ein zweiter Lauf vergibt nichts doppelt und BENENNT, was er
#          uebergeht (Grundregel 1).
#   RB10 - Die Hilfe erklaert die Umstellung, statt nur das Recht zu tauschen.
#
# NACHTRAG BUILD 711 (Vorgang 9c4e17b2) - DER SPERRRIEGEL:
#   Wer 'migrate-grants' VOR M038 fuhr, bekam einen ordentlich belegten Grant
#   auf ein Recht, das der Katalog der Datenbank noch nicht kannte. M038 zaehlte
#   danach den BESTAND statt des ZUWACHSES, brach ab und rollte zurueck - die
#   Faehigkeit entstand nie, das Management verweigerte den Start, und selbst
#   der saubere Rueckweg (Soft-Revoke) half nicht, weil die Zaehlung
#   'revoked_at' nicht filterte. Es blieb allein ein DELETE auf eine belegte
#   Zeile.
#
#   RB11 - Ein VORGEFUNDENER Grant haelt M038 nicht mehr auf: die Migration
#          laeuft durch, laesst ihn unveraendert und BENENNT ihn samt Beleg-seq.
#   RB12 - Der Waechter ist damit nicht zahnlos: ein waehrend des Laufs
#          ENTSTANDENER Grant bricht weiterhin ab, und der Rollback greift.
#   RB13 - 'migrate-grants' weist den zu fruehen Lauf jetzt ab, nennt den
#          fehlenden Schritt und schreibt NICHTS.
#
# Version: v0.8.698 - Build: 698 - 2026-08-11
#   erweitert v0.8.711 - Build: 711 - 2026-08-13 (RB11-RB13)
# =============================================================================

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import management.migrations.coordinator as coordinator_migrations  # noqa: E402
from management.audit.audit_log import AuditLog                     # noqa: E402
from management.gateway.coordinator_writer import CoordinatorWriter  # noqa: E402
from management.help import sicht_katalog                            # noqa: E402
from management.migrations.coordinator import m038_caseoverview_rbac  # noqa: E402
from management.migrations.runner import MigrationRunner, discover    # noqa: E402
from management.rbac import catalog                                   # noqa: E402
from management.rbac.rbac_repo import RbacRepo                        # noqa: E402
from management.viewprefs import viewpref_katalog                     # noqa: E402

_WURZEL = Path(__file__).resolve().parent.parent
_NEUES_RECHT = "caseoverview.view"
_ALTES_RECHT = "dashboard.view"


class _MitDatenbank(unittest.TestCase):
    """Eine frisch migrierte coordinator.db je Testfall."""

    #: None = die ganze Kette. Eine Zahl haelt sie nach dieser Version an
    #  (Build 711, fuer die Ausgangslage vor M038).
    _BIS_VERSION = None

    #: Die Personentabelle ist AELTER als die Migrationskette (M001 schreibt
    #  seinen Genesis-Beleg gegen sie). Sie wird deshalb hier angelegt - wie in
    #  tests/test_management_server.py.
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

    #: M002 zaehlt vor dem Umbau die alten Auftragszeilen - ohne diese Tabelle
    #  bricht die Kette bei M002 ab. Ebenfalls uebernommen aus
    #  tests/test_management_server.py.
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

    def setUp(self):
        import time
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.con.executescript(self._PERSON)
        self.con.executescript(self._OLD_SCRAPE_JOBS)
        jetzt = int(time.time())
        for uname, dname, inv, sup in (("h001", "Chefin", 0, 1),
                                       ("h002", "Ermittler", 1, 0)):
            self.con.execute(
                "INSERT INTO person (system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?,?,?,?,0,?)", (uname, dname, inv, sup, jetzt))
        self.audit = AuditLog(self.con)
        # Build 711: Unterklassen koennen die Kette VOR M038 anhalten
        # (_BIS_VERSION). Nur so laesst sich die Ausgangslage des Vorgangs
        # 9c4e17b2 nachstellen - ein Grant, der vor der Migration entsteht.
        migrationen = discover(coordinator_migrations)
        if self._BIS_VERSION is not None:
            migrationen = [m for m in migrationen
                           if m.VERSION <= self._BIS_VERSION]
        MigrationRunner(self.con, migrationen,
                        audit=self.audit, deployed_by="tester").run()
        self.writer = CoordinatorWriter(self.con, self.audit)
        self.repo = RbacRepo(self.con, self.writer)

    def tearDown(self):
        self.con.close()

    def _cap(self, code):
        return self.con.execute(
            "SELECT code, label, description FROM rbac_capability WHERE code=?",
            (code,)).fetchone()


class MigrationTests(_MitDatenbank):

    # -- RB01 -----------------------------------------------------------------
    def test_rb01_seed_ohne_grant(self):
        row = self._cap(_NEUES_RECHT)
        self.assertIsNotNone(row, "'%s' fehlt nach M038." % _NEUES_RECHT)
        self.assertEqual(row["label"], "Falluebersicht sehen")

        # KEIN Grant. Das ist der Punkt, an dem die Migration bewusst
        # aufhoert: rbac_grant.audit_seq ist NOT NULL, eine Migration hat
        # weder Akteur noch Beleg. Ein von ihr geschriebener Grant waere ein
        # Zugang, den niemand vergeben hat.
        n = self.con.execute(
            "SELECT COUNT(*) FROM rbac_grant WHERE capability_code=?",
            (_NEUES_RECHT,)).fetchone()[0]
        self.assertEqual(0, n)

        # Und der Katalog im Code fuehrt dasselbe Recht - sonst schlaegt der
        # Start-Check verify_catalog_present() zu.
        self.assertIn(_NEUES_RECHT, catalog.CAPABILITY_CODES)

    # -- RB02 -----------------------------------------------------------------
    def test_rb02_text_berichtigt_aber_fremde_fassung_bleibt(self):
        row = self._cap(_ALTES_RECHT)
        self.assertEqual(row["label"], "Kachel-Dashboard sehen")
        self.assertIn("RAHMEN", row["description"])

        # Die Gegenprobe: eine von Hand geaenderte Fassung darf NICHT
        # ueberschrieben werden. Eine Migration, die fremde Aenderungen
        # plaettet, macht aus einer Berichtigung einen Datenverlust.
        self.con.execute(
            "UPDATE rbac_capability SET label=?, description=? WHERE code=?",
            ("Eigene Beschriftung", "Eigener Text.", _ALTES_RECHT))
        with self.assertLogs("management.migrations.coordinator."
                             "m038_caseoverview_rbac", level="WARNING") as log:
            m038_caseoverview_rbac.up(self.con)
        self.assertTrue(any("fremden Text" in z for z in log.output),
                        "Die fremde Fassung wird nicht benannt: %s" % log.output)
        row = self._cap(_ALTES_RECHT)
        self.assertEqual(row["label"], "Eigene Beschriftung")

    # -- RB03 -----------------------------------------------------------------
    def test_rb03_idempotent(self):
        vorher = dict(self._cap(_NEUES_RECHT))
        m038_caseoverview_rbac.up(self.con)      # zweiter Lauf
        self.assertEqual(vorher, dict(self._cap(_NEUES_RECHT)))
        n = self.con.execute(
            "SELECT COUNT(*) FROM rbac_capability WHERE code=?",
            (_NEUES_RECHT,)).fetchone()[0]
        self.assertEqual(1, n)


class KatalogTests(unittest.TestCase):

    # -- RB04 -----------------------------------------------------------------
    def test_rb04_kachel_und_sichtkatalog(self):
        kachel = viewpref_katalog.widget_spec("fallampel")
        self.assertIsNotNone(kachel)
        self.assertEqual(_NEUES_RECHT, kachel.cap)
        # Die Kachel bleibt Werkseinstellung: was jemand sehen WOLLTE und was
        # er sehen DARF, sind zwei Fragen. Der Rechtefilter laeuft zuletzt.
        self.assertTrue(kachel.standard)

        sicht = sicht_katalog.sicht("faelle")
        self.assertIsNotNone(sicht)
        self.assertEqual((_NEUES_RECHT,), sicht.rechte())
        self.assertEqual((_ALTES_RECHT,),
                         sicht_katalog.sicht("dashboard").rechte())

        # Der Sichtenkatalog ist der SPIEGEL des VIEW_CATALOG in cockpit.js.
        # Ein Spiegel, der etwas anderes zeigt, macht die Hilfe genau dort
        # falsch, wo jemand nachschlaegt, warum er eine Sicht nicht sieht.
        quelle = (_WURZEL / "management" / "server" / "static"
                  / "cockpit.js").read_text(encoding="utf-8")
        self.assertIn("{ id: 'faelle',     cap: 'caseoverview.view',", quelle)
        self.assertIn("{ id: 'dashboard',  cap: 'dashboard.view',", quelle)

    # -- RB10 -----------------------------------------------------------------
    def test_rb10_hilfe_erklaert_die_umstellung(self):
        """
        Das Recht zu tauschen genuegt nicht. Wer die Sicht ploetzlich nicht
        mehr hat, sucht den Grund - und muss ihn in der Hilfe finden, sonst
        meldet er einen Ausfall, den es nicht gibt.
        """
        from management.help.inhalt import fallsteuerung, ueberblick

        faelle_rechte = " ".join(
            t for a in fallsteuerung.FAELLE.abschnitte if a.anker == "rechte"
            for t in a.absaetze)
        self.assertIn(_NEUES_RECHT, fallsteuerung.FAELLE.recht_klartext)
        self.assertIn(_NEUES_RECHT, faelle_rechte)
        self.assertIn(_ALTES_RECHT, faelle_rechte,
                      "Die Umstellung wird nicht erklaert - der alte "
                      "Rechtename kommt gar nicht mehr vor.")

        dash_rechte = " ".join(
            t for a in ueberblick.DASHBOARD.abschnitte if a.anker == "rechte"
            for t in a.absaetze)
        self.assertIn(_NEUES_RECHT, dash_rechte)
        self.assertIn("Rahmen", dash_rechte)

        kontext = {k.schluessel: k.text for k in ueberblick.DASHBOARD.kontext}
        self.assertIn(_NEUES_RECHT, kontext["dashboard.kachel.fallampel"])


class EndpunktTests(_MitDatenbank):
    """Die beiden Endpunkte, die den Fallbestand ausliefern."""

    def setUp(self):
        super().setUp()
        from management.server.management_app import ManagementApp
        self.repo.assign_role(1, "supervisor", actor_id=1)
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.app = ManagementApp(self.db_path)

    def _get(self, pfad, query=None):
        return self.app.dispatch(1, pfad, query)

    # -- RB05 / RB06 ----------------------------------------------------------
    def test_rb05_rb06_endpunkte_verlangen_das_neue_recht(self):
        import json

        # Nur das ALTE Recht: beide Endpunkte muessen schliessen - und sagen,
        # welches Recht fehlt. Ein 403 ohne Nennung waere fuer die Betroffenen
        # nicht von einem Ausfall zu unterscheiden.
        endpunkte = (("/api/overview", None),
                     ("/api/search", {"q": ["taeter"]}))

        self.repo.grant("supervisor", _ALTES_RECHT, scope="alle", actor_id=1)
        for pfad, query in endpunkte:
            with self.subTest(pfad=pfad, recht="nur alt"):
                r = self._get(pfad, query)
                self.assertEqual(403, r.status)
                self.assertEqual(_NEUES_RECHT,
                                 json.loads(r.body)["capability"])

        # Mit dem neuen Recht gehen beide auf.
        self.repo.grant("supervisor", _NEUES_RECHT, scope="alle", actor_id=1)
        for pfad, query in endpunkte:
            with self.subTest(pfad=pfad, recht="neu"):
                self.assertEqual(200, self._get(pfad, query).status)


class MigrateGrantsTests(_MitDatenbank):
    """Der auditierte Uebernahmelauf."""

    def setUp(self):
        super().setUp()
        # Zwei Rollen mit VERSCHIEDENEM Umfang - genau daran zeigt sich, ob
        # der Umfang 1:1 mitwandert oder unterwegs vereinheitlicht wird.
        self.repo.grant("supervisor", _ALTES_RECHT, scope="alle", actor_id=1)
        self.repo.grant("investigator", _ALTES_RECHT, scope="eigene",
                        actor_id=1)

    def _lauf(self, *args):
        from management.rbac import rbac_admin
        return rbac_admin.main(
            ["migrate-grants", "--from", _ALTES_RECHT, "--to", _NEUES_RECHT,
             "--coordinator-db", self.db_path] + list(args))

    def _aktive(self, cap):
        return {g["role_code"]: g["scope"]
                for g in self.repo.list_grants(active_only=True)
                if g["capability_code"] == cap}

    # -- RB07 -----------------------------------------------------------------
    def test_rb07_uebernimmt_umfang_und_belegt_jeden_grant(self):
        spitze_vorher = self.con.execute(
            "SELECT MAX(seq) FROM audit_log").fetchone()[0]

        self.assertEqual(0, self._lauf("--actor", "h001"))

        self.con.close()
        self.con = sqlite3.connect(self.db_path)
        self.con.row_factory = sqlite3.Row
        self.repo = RbacRepo(self.con, CoordinatorWriter(
            self.con, AuditLog(self.con)))

        self.assertEqual({"supervisor": "alle", "investigator": "eigene"},
                         self._aktive(_NEUES_RECHT))
        # Das Quellrecht bleibt unangetastet - ob es einer Rolle erhalten
        # bleibt, ist eine fachliche Entscheidung je Rolle.
        self.assertEqual({"supervisor": "alle", "investigator": "eigene"},
                         self._aktive(_ALTES_RECHT))

        # Je uebernommenem Grant ein eigener Beleg, und die Zeile zeigt darauf.
        for g in self.repo.list_grants(active_only=True):
            if g["capability_code"] != _NEUES_RECHT:
                continue
            self.assertGreater(g["audit_seq"], spitze_vorher)
            self.assertIn("Uebernahme aus", g["note"] or "")
        self.assertTrue(AuditLog(self.con).verify_chain().ok,
                        "Audit-Kette nach der Uebernahme nicht intakt")

    # -- RB08 -----------------------------------------------------------------
    def test_rb08_probelauf_schreibt_nichts(self):
        spitze = self.con.execute(
            "SELECT MAX(seq) FROM audit_log").fetchone()[0]

        self.assertEqual(0, self._lauf("--probe"))

        self.con.close()
        self.con = sqlite3.connect(self.db_path)
        self.con.row_factory = sqlite3.Row
        self.repo = RbacRepo(self.con, CoordinatorWriter(
            self.con, AuditLog(self.con)))
        self.assertEqual({}, self._aktive(_NEUES_RECHT))
        self.assertEqual(
            spitze,
            self.con.execute("SELECT MAX(seq) FROM audit_log").fetchone()[0],
            "Der Probelauf hat in das Belegbuch geschrieben.")

    # -- RB09 -----------------------------------------------------------------
    def test_rb09_zweiter_lauf_vergibt_nichts_doppelt(self):
        import io
        from contextlib import redirect_stdout

        self.assertEqual(0, self._lauf("--actor", "h001"))
        puffer = io.StringIO()
        with redirect_stdout(puffer):
            self.assertEqual(0, self._lauf("--actor", "h001"))
        ausgabe = puffer.getvalue()

        # Grundregel 1: was uebergangen wird, wird BENANNT. Ein Lauf, der nur
        # meldet, was er getan hat, laesst offen, ob der Rest vergessen wurde.
        self.assertIn("BEREITS DA", ausgabe)
        self.assertIn("supervisor", ausgabe)
        self.assertIn("investigator", ausgabe)

        self.con.close()
        self.con = sqlite3.connect(self.db_path)
        self.con.row_factory = sqlite3.Row
        self.repo = RbacRepo(self.con, CoordinatorWriter(
            self.con, AuditLog(self.con)))
        aktiv = [g for g in self.repo.list_grants(active_only=True)
                 if g["capability_code"] == _NEUES_RECHT]
        self.assertEqual(2, len(aktiv), "Grants doppelt vergeben.")


class SperrriegelTests(_MitDatenbank):
    """
    Vorgang 9c4e17b2 — die Ausgangslage, die den Bestand verriegelte.

    Die Kette haelt VOR M038 an. Damit ist genau der Zustand hergestellt, in
    dem am 12.08.2026 der Uebernahmelauf gefahren wurde: das Recht steht im
    Katalog des CODES (sonst wiese RbacRepo es ab), aber noch nicht in der
    Datenbank.
    """

    _BIS_VERSION = 37

    def _kette_zuende(self):
        """Die restliche Kette (also M038) nachfahren."""
        MigrationRunner(self.con, discover(coordinator_migrations),
                        audit=AuditLog(self.con), deployed_by="tester").run()

    def _grant_zeile(self):
        return self.con.execute(
            "SELECT id, audit_seq, scope, revoked_at FROM rbac_grant "
            "WHERE capability_code=?", (_NEUES_RECHT,)).fetchone()

    # -- RB11 -----------------------------------------------------------------
    def test_rb11_vorgefundener_grant_haelt_m038_nicht_auf(self):
        # Die Ausgangslage muss echt sein, sonst prueft der Test nichts:
        # die Faehigkeit darf in der DATENBANK noch nicht stehen.
        self.assertIsNone(self._cap(_NEUES_RECHT),
                          "Die Kette haelt nicht vor M038 an.")

        # db_katalog_pruefen=False (Build 716, Vorgang 1b7d55ae): seit dem
        # zweiten Waechter in RbacRepo.grant weist der auditierte Weg genau
        # diesen Grant ab - das ist der Zweck des Waechters. Die Nachstellung
        # braucht die Waise aber als AUSGANGSLAGE. Rohes SQL scheidet aus:
        # (c) unten prueft die Beleg-seq, der Grant muss also ein ordentlich
        # belegter sein. Der uebergangene Waechter vermerkt sich seinerseits
        # in der audit_log-Nutzlast; RB13 haelt das fest.
        self.repo.grant("supervisor", _NEUES_RECHT, scope="alle", actor_id=1,
                        db_katalog_pruefen=False)
        vorher = dict(self._grant_zeile())

        with self.assertLogs("management.migrations.coordinator."
                             "m038_caseoverview_rbac", level="WARNING") as log:
            self._kette_zuende()

        # (a) Die Migration ist durch - das ist der eigentliche Befund.
        self.assertIsNotNone(self._cap(_NEUES_RECHT),
                             "M038 hat die Faehigkeit nicht angelegt.")
        # Build 725: NICHT mehr gegen die feste Zahl 38 pruefen. Die Aussage
        # dieses Tests ist "die Kette ist zuende gefahren, M038 eingeschlossen"
        # - nicht "38 ist die letzte Migration, die es je geben wird". Mit
        # M039 (person.first_name/last_name/rank) fiel die feste Zahl, obwohl
        # an der geprueften Sache nichts anders war. Geprueft wird deshalb
        # gegen den HOECHSTSTAND DER AUSGELIEFERTEN MODULE; kommt eine
        # Migration dazu, haelt der Test weiter, bleibt aber scharf, wenn die
        # Kette vorzeitig stehenbleibt.
        hoechste = max(m.VERSION for m in discover(coordinator_migrations))
        angewandt = self.con.execute(
            "SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        self.assertEqual(hoechste, angewandt,
                         "Die Migrationskette ist nicht zuende gefahren.")
        self.assertGreaterEqual(angewandt, 38, "M038 ist nicht angewandt.")

        # (b) Der vorgefundene Grant ist UNANGETASTET. Eine Migration, die
        #     fremde, belegte Zeilen zurechtruecken wuerde, waere schlimmer
        #     als die, die daran scheiterte.
        self.assertEqual(vorher, dict(self._grant_zeile()))

        # (c) Und er wird BENANNT (Grundregel 1), mit dem Beleg, ueber den
        #     sich seine Herkunft klaeren laesst.
        text = "\n".join(log.output)
        self.assertIn("Grant #%d" % vorher["id"], text)
        self.assertIn("Beleg-seq=%d" % vorher["audit_seq"], text)
        self.assertIn("supervisor", text)

        # (d) Die Belegkette haelt.
        self.assertTrue(AuditLog(self.con).verify_chain().ok,
                        "Audit-Kette nach M038 nicht intakt.")

    # -- RB11b ----------------------------------------------------------------
    def test_rb11b_auch_ein_zurueckgenommener_grant_haelt_nicht_auf(self):
        """
        Die Gegenprobe zur alten Zaehlung: sie filterte 'revoked_at' nicht,
        also half selbst der vorgesehene Rueckweg nicht mehr aus der Sackgasse
        heraus. Genau dieser Fall wird hier festgehalten.
        """
        # Notausgang wie in RB11 - dieselbe Ausgangslage, dieselbe Begruendung.
        self.repo.grant("supervisor", _NEUES_RECHT, scope="alle", actor_id=1,
                        db_katalog_pruefen=False)
        gid = self._grant_zeile()["id"]
        self.repo.revoke_grant(gid, actor_id=1, note="Gegenprobe RB11b")
        self.assertIsNotNone(self._grant_zeile()["revoked_at"])

        self._kette_zuende()
        self.assertIsNotNone(self._cap(_NEUES_RECHT))

    # -- RB12 -----------------------------------------------------------------
    def test_rb12_ein_zuwachs_waehrend_des_laufs_bricht_weiterhin_ab(self):
        """
        Der Waechter darf durch die Berichtigung nicht zahnlos werden. Sein
        Zweck ist unveraendert: diese Migration soll KEINEN Grant erzeugen.

        Nachgestellt wird das mit einem Trigger, der beim Anlegen der
        Faehigkeit eine Grant-Zeile mitschreibt - also einem Zuwachs, der
        WAEHREND up() entsteht. Kein Mock: gemessen wird die echte Funktion an
        einer echten Datenbank.
        """
        self.con.executescript(
            "CREATE TRIGGER t_rb12_zuwachs AFTER INSERT ON rbac_capability "
            "WHEN NEW.code = '%s' BEGIN "
            "INSERT INTO rbac_grant (role_code, capability_code, scope, "
            "audit_seq, granted_at) VALUES ('supervisor', '%s', 'alle', 1, 0);"
            " END;" % (_NEUES_RECHT, _NEUES_RECHT))

        with self.assertRaises(RuntimeError) as ctx:
            self._kette_zuende()
        self.assertIn("hinzubekommen", str(ctx.exception))

        # Und der Rollback greift: kein Teilzustand, keine Registry-Zeile.
        self.assertIsNone(self._cap(_NEUES_RECHT))
        self.assertEqual(37, self.con.execute(
            "SELECT MAX(version) FROM schema_migrations").fetchone()[0])
        self.con.executescript("DROP TRIGGER t_rb12_zuwachs")

    # -- RB13 -----------------------------------------------------------------
    def test_rb13_migrate_grants_weist_den_zu_fruehen_lauf_ab(self):
        """
        Die Vorbeugung: das Werkzeug, mit dem der Fehlgriff geschah, laesst
        ihn nicht mehr zu.
        """
        import io
        from contextlib import redirect_stderr
        from management.rbac import rbac_admin

        self.repo.grant("supervisor", _ALTES_RECHT, scope="alle", actor_id=1)
        spitze = self.con.execute(
            "SELECT MAX(seq) FROM audit_log").fetchone()[0]

        puffer = io.StringIO()
        with redirect_stderr(puffer):
            rc = rbac_admin.main(
                ["migrate-grants", "--from", _ALTES_RECHT, "--to",
                 _NEUES_RECHT, "--coordinator-db", self.db_path,
                 "--actor", "h001"])
        ausgabe = puffer.getvalue()

        self.assertEqual(1, rc, "Der zu fruehe Lauf wurde nicht abgewiesen.")
        # Die Meldung muss den FEHLENDEN SCHRITT nennen, nicht nur das
        # Scheitern - sonst sucht der Betroffene an der falschen Stelle.
        self.assertIn(_NEUES_RECHT, ausgabe)
        self.assertIn("management.migrate", ausgabe)

        # Es wurde NICHTS geschrieben - weder ein Grant noch ein Beleg.
        self.con.close()
        self.con = sqlite3.connect(self.db_path)
        self.con.row_factory = sqlite3.Row
        self.assertIsNone(self.con.execute(
            "SELECT 1 FROM rbac_grant WHERE capability_code=?",
            (_NEUES_RECHT,)).fetchone())
        self.assertEqual(spitze, self.con.execute(
            "SELECT MAX(seq) FROM audit_log").fetchone()[0],
            "Der abgewiesene Lauf hat in das Belegbuch geschrieben.")


if __name__ == "__main__":
    unittest.main()
