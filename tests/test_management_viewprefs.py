# =============================================================================
# tests/test_management_viewprefs.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3G
# =============================================================================
# Testsuite fuer Build 545: die persoenliche Ansichtseinstellung
# (person_view_pref, M037) — Katalog, Repository und die drei Endpunkte.
#
# KATALOG:
#   VP01 — Der Sichten-Katalog deckt sich mit VIEW_CATALOG aus cockpit.js.
#          Ohne diesen Test faellt eine kuenftige neue Sicht STILL aus der
#          Steuerung heraus — dieselbe Luecke, die VE08 fuer den Export
#          schliesst.
#   VP02 — ARTEN im Katalog und der CHECK in M037 sind zeichengleich (die
#          Migration fuehrt eine eingefrorene Kopie, m005-Prinzip).
#   VP03 — Jede Kachel nennt eine Faehigkeit, die es im RBAC-Katalog gibt,
#          und einen Endpunkt, den dispatch() kennt. Eine Kachel mit
#          erfundenem Recht waere dauerhaft unsichtbar, eine mit erfundenem
#          Pfad dauerhaft leer — beides ohne Fehlermeldung.
#   VP04 — Die Werkseinstellung ist GENAU die Fall-Uebersicht. Damit sieht
#          der Ueberblick ohne gespeicherte Vorliebe aus wie bisher.
#
# REPOSITORY:
#   VP05 — Speichern legt die Zeilen in LISTENFOLGE an (Position 0..n-1).
#   VP06 — Ein Speichervorgang ersetzt eine Art VOLLSTAENDIG; die nicht
#          genannte Art bleibt unberuehrt.
#   VP07 — Ausgeblendete Elemente BEHALTEN ihre Position. Sonst rutschte
#          beim Wiedereinblenden die ganze uebrige Ordnung.
#   VP08 — Ein Audit-Beleg JE ART, und sein Payload traegt den
#          VOLLSTAENDIGEN Zustand (reihenfolge + ausgeblendet), kein Delta.
#   VP09 — Unbekannter Schluessel -> Fehler, der ihn NENNT; es wird NICHTS
#          gespeichert (keine stille Teilverarbeitung).
#   VP10 — Doppelter Schluessel -> Fehler.
#   VP11 — Ein Fehler in der ZWEITEN Art laesst auch die erste nicht
#          zurueck (eine Transaktion, Rollback beider).
#   VP12 — actor_id != person_id -> Fehler. Es gibt keine Vertretung.
#   VP13 — Ohne CoordinatorWriter gibt es KEINEN Schreibweg.
#   VP14 — lade() weist gespeicherte Schluessel, die der Katalog nicht mehr
#          kennt, in 'unbekannt' AUS, statt sie zu uebergehen.
#   VP15 — zuruecksetzen() loescht, schreibt einen EIGENEN Beleg und trifft
#          nur die genannte Art.
#
# ENDPUNKTE:
#   VP16 — GET /api/viewprefs -> 200 mit Katalog; 'erlaubt' je Kachel folgt
#          den TATSAECHLICHEN Rechten der Person.
#   VP17 — GET fuer eine unbekannte Person -> 404.
#   VP18 — POST speichert, ein erneutes GET liefert es zurueck.
#   VP19 — POST ohne beide Felder -> 400.
#   VP20 — POST mit unbekanntem Schluessel -> 400, der ihn nennt.
#   VP21 — GET schreibt NICHTS (Audit-Spitze unveraendert).
#   VP22 — POST /api/viewprefs/reset -> 200, danach ist nichts gespeichert.
#   VP24 — Build 571: JEDES Feld von WidgetSpec kommt im Browser an
#          (Anlass: 'api_path' fehlte, alle acht Kacheln 404).
#   VP23 — M037 seedet KEIN Recht (AP-3G braucht keines).
#
# KATALOG GEGEN FRONTEND (Build 547):
#   VP24 — Zu JEDER Kachel des Katalogs gibt es im Browser einen Reduzierer,
#          und umgekehrt. Eine Kachel ohne Reduzierer waere dauerhaft leer,
#          ein Reduzierer ohne Kachel toter Code — beides ohne Fehlermeldung.
#   VP25 — 'viewprefs' ist nicht steuerbar und traegt einen Grund; die
#          Einstellsicht darf sich nicht selbst wegstellen.
#
# Version: v0.8.545 · Build: 545 · 2026-07-26
# =============================================================================

import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations  # noqa: E402
from management.audit.audit_log import AuditLog                     # noqa: E402
from management.audit.event_types import EventType                  # noqa: E402
from management.gateway.coordinator_writer import CoordinatorWriter  # noqa: E402
from management.migrations.runner import MigrationRunner, discover  # noqa: E402
from management.rbac.catalog import capability_codes                # noqa: E402
from management.rbac.rbac_repo import RbacRepo                      # noqa: E402
from management.server.management_app import ManagementApp          # noqa: E402
from management.viewprefs import viewpref_katalog as kat            # noqa: E402
from management.viewprefs.viewpref_repo import (                    # noqa: E402
    ViewPrefFehler,
    ViewPrefRepo,
)

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


class _Basis(unittest.TestCase):
    """
    coordinator.db mit zwei Personen.

    Person 1 = Chefin (dashboard.view + caseoverview.view +
    escalation.view + ops.view),
    Person 2 = Ermittler ohne jedes Recht. Der Unterschied traegt VP16.
    """

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.forensic = Path(self._tmp) / "forensic"
        self.evidence = Path(self._tmp) / "evidence"
        self.forensic.mkdir()
        self.evidence.mkdir()

        con = sqlite3.connect(self.db_path)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.executescript(_PERSON)
        con.executescript(_OLD_SCRAPE_JOBS)
        now = int(time.time())
        for uname, dname, inv, sup in (
                ("NRW\\chefin", "Chef-Ermittlerin", 0, 1),
                ("NRW\\ermittler", "Ermittler", 1, 0)):
            con.execute(
                "INSERT INTO person (system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?,?,?,?,0,?)", (uname, dname, inv, sup, now))

        self.audit = AuditLog(con)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="tester").run()
        self.writer = CoordinatorWriter(con, self.audit)

        rbac = RbacRepo(con, self.writer)
        # Build 698 (Vorgang 60fe72fb): 'caseoverview.view' ergaenzt - die
        # Kachel 'fallampel' haengt seither daran und nicht mehr am Recht
        # des Kachel-Dashboards.
        for cap in ("dashboard.view", "caseoverview.view",
                    "escalation.view", "ops.view"):
            rbac.grant("supervisor", cap, scope="alle", actor_id=1)
        rbac.assign_role(1, "supervisor", actor_id=1)
        # Person 2 bekommt bewusst nichts.

        self.con = con
        self.app = ManagementApp(self.db_path,
                                 forensic_dir=str(self.forensic),
                                 evidence_dir=str(self.evidence))

    def tearDown(self):
        try:
            self.con.close()
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)

    # ------------------------------------------------------------------ Hilfen
    def _repo(self):
        return ViewPrefRepo(self.con, self.writer)

    def _zeilen(self, person_id=1, art=None):
        sql = ("SELECT art, element_key, position, sichtbar, audit_seq "
               "FROM person_view_pref WHERE person_id = ?")
        args = [person_id]
        if art is not None:
            sql += " AND art = ?"
            args.append(art)
        sql += " ORDER BY art, position"
        return [dict(r) for r in self.con.execute(sql, args).fetchall()]

    def _spitze(self):
        return self.con.execute("SELECT MAX(seq) FROM audit_log").fetchone()[0]

    def _payload(self, seq):
        row = self.con.execute(
            "SELECT content FROM audit_log WHERE seq = ?", (seq,)).fetchone()
        return json.loads(row[0]) if row and row[0] else {}

    def _typ(self, seq):
        return self.con.execute(
            "SELECT event_type FROM audit_log WHERE seq = ?",
            (seq,)).fetchone()[0]


class TestKatalog(unittest.TestCase):
    """VP01-VP04 — der Katalog, ohne Datenbank."""

    # ===================================================================== VP01
    def test_VP01_katalog_deckt_cockpit_view_catalog(self):
        """
        Konsistenz gegen die WAHRHEITSQUELLE cockpit.js. Verfahren wie VE08
        in tests/test_view_export_api.py: sonst faellt eine kuenftige neue
        Sicht STILL aus der Steuerung, und niemand merkt es, weil eine
        fehlende Sicht in einer Auswahlliste wie eine Entscheidung aussieht.
        """
        js = Path("management/server/static/cockpit.js").read_text(
            encoding="utf-8")
        block = js.split("VIEW_CATALOG", 1)[1].split("];", 1)[0]
        # BEFUND Build 559: der Ausdruck lautete [a-z]+ und haette eine
        # Sicht-Kennung MIT UNTERSTRICH gar nicht erst gefunden. Der
        # Test waere gruen geblieben, waehrend die neue Sicht weder
        # steuerbar noch ausdruecklich ausgenommen gewesen waere —
        # also genau die stille Luecke, die er verhindern soll. Bis
        # Build 558 trug keine Kennung einen Unterstrich; der Fehler
        # war latent. 'capacity_pflege' ist die erste.
        cockpit_ids = set(re.findall(r"\{\s*id:\s*'([a-z_]+)'", block))
        self.assertGreater(len(cockpit_ids), 25, "VIEW_CATALOG nicht erkannt")

        steuerbar = set(kat.STEUERBARE_SICHTEN)
        ausgenommen = set(kat.NICHT_STEUERBAR)

        # (a) Der Katalog nennt keine Sicht, die es nicht gibt.
        verwaist = (steuerbar | ausgenommen) - cockpit_ids
        self.assertEqual(verwaist, set(),
                         "Der Steuerungs-Katalog nennt Sichten, die es im "
                         "Cockpit nicht gibt: %r" % verwaist)

        # (b) Jede Cockpit-Sicht ist steuerbar ODER ausdruecklich ausgenommen.
        unversorgt = cockpit_ids - steuerbar - ausgenommen
        self.assertEqual(unversorgt, set(),
                         "Sichten ohne Steuerbarkeit und ohne Begruendung: %r"
                         % unversorgt)

        # (c) Keine Sicht ist beides zugleich.
        self.assertEqual(steuerbar & ausgenommen, set())

        # (d) Jede Ausnahme traegt einen Grund im Klartext.
        for vid, grund in kat.NICHT_STEUERBAR.items():
            self.assertTrue(grund and grund.strip(),
                            "Ausnahme '%s' ohne Begruendung" % vid)

    # ===================================================================== VP02
    def test_VP02_arten_deckungsgleich_mit_migration(self):
        """
        M037 fuehrt die Arten als EINGEFRORENE Kopie (m005-Prinzip: eine
        angewandte Migration darf ihr Verhalten nie aendern). Damit die Kopie
        nicht abdriftet, wird sie hier gegen das Original gehalten — gegen
        BEIDES: die Konstante und den tatsaechlichen CHECK im DDL.
        """
        from management.migrations.coordinator import m037_view_pref as m037
        self.assertEqual(tuple(m037._ARTEN), tuple(kat.ARTEN))
        for art in kat.ARTEN:
            self.assertIn("'%s'" % art, m037._DDL,
                          "Art '%s' fehlt im CHECK der Migration" % art)

    # ===================================================================== VP03
    def test_VP03_kacheln_nennen_echte_rechte_und_echte_endpunkte(self):
        """
        Eine Kachel mit erfundenem Recht waere fuer JEDE Person dauerhaft
        unsichtbar; eine mit erfundenem Pfad dauerhaft leer. Beides ohne
        Fehlermeldung — genau die Art stiller Ausfall, die Grundregel 1 meint.
        """
        bekannte_rechte = capability_codes()
        quelle = Path("management/server/management_app.py").read_text(
            encoding="utf-8")
        for w in kat.WIDGETS:
            self.assertIn(w.cap, bekannte_rechte,
                          "Kachel '%s' nennt ein Recht, das der RBAC-Katalog "
                          "nicht kennt: %s" % (w.key, w.cap))
            self.assertIn('path == "%s"' % w.api_path, quelle,
                          "Kachel '%s' nennt einen Endpunkt, den dispatch() "
                          "nicht kennt: %s" % (w.key, w.api_path))
            self.assertTrue(w.label.strip(), w.key)
            self.assertTrue(w.beschreibung.strip(), w.key)
        # Die Schluessel sind eindeutig — sie stehen in der Datenbank.
        keys = [w.key for w in kat.WIDGETS]
        self.assertEqual(len(keys), len(set(keys)))

    # ===================================================================== VP04
    def test_VP04_werkseinstellung_ist_die_fallübersicht(self):
        """
        Ohne gespeicherte Vorliebe muss der Ueberblick aussehen wie bisher.
        Eine Aenderung, die allen im Produktivbetrieb die gewohnte
        Oberflaeche umbaut, waere der falsche Weg.
        """
        self.assertEqual(kat.standard_widgets(), ("fallampel",))
        self.assertEqual(kat.widget_spec("fallampel").api_path,
                         "/api/overview")
        self.assertIsNone(kat.widget_spec("gibtsnicht"))
        self.assertFalse(kat.ist_bekannt("unfug", "fallampel"))
        self.assertEqual(kat.bekannte_schluessel("unfug"), ())


class TestRepo(_Basis):
    """VP05-VP15."""

    # ===================================================================== VP05
    def test_VP05_listenfolge_ist_die_reihenfolge(self):
        self._repo().speichern(person_id=1, actor_id=1,
                               sichten=["escalation", "dashboard", "audit"])
        z = self._zeilen(art="sicht")
        self.assertEqual([r["position"] for r in z], [0, 1, 2])
        self.assertEqual([r["element_key"] for r in z],
                         ["escalation", "dashboard", "audit"])
        self.assertTrue(all(r["sichtbar"] == 1 for r in z))
        # Jede Zeile traegt die seq ihres Belegs — nicht die 0 aus dem Insert.
        self.assertTrue(all(r["audit_seq"] > 0 for r in z))

    # ===================================================================== VP06
    def test_VP06_vollstaendiges_ersetzen_je_art(self):
        r = self._repo()
        r.speichern(person_id=1, actor_id=1,
                    sichten=["dashboard", "escalation"],
                    widgets=["fallampel"])
        # Zweiter Lauf: nur die Sichten, und kuerzer.
        r.speichern(person_id=1, actor_id=1, sichten=["audit"])
        sichten = self._zeilen(art="sicht")
        self.assertEqual([x["element_key"] for x in sichten], ["audit"],
                         "Die alten Sicht-Eintraege muessen weg sein.")
        # Die NICHT genannte Art bleibt unberuehrt — das ist der Punkt.
        widgets = self._zeilen(art="widget")
        self.assertEqual([x["element_key"] for x in widgets], ["fallampel"])

    # ===================================================================== VP07
    def test_VP07_ausgeblendete_behalten_ihre_position(self):
        self._repo().speichern(person_id=1, actor_id=1, sichten=[
            {"key": "dashboard", "sichtbar": True},
            {"key": "escalation", "sichtbar": False},
            {"key": "audit", "sichtbar": True},
        ])
        z = {r["element_key"]: r for r in self._zeilen(art="sicht")}
        self.assertEqual(z["escalation"]["position"], 1,
                         "Eine ausgeblendete Sicht behaelt ihren Platz.")
        self.assertEqual(z["escalation"]["sichtbar"], 0)
        self.assertEqual(z["audit"]["position"], 2)

    # ===================================================================== VP08
    def test_VP08_ein_beleg_je_art_mit_vollstaendigem_zustand(self):
        vor = self._spitze()
        res = self._repo().speichern(
            person_id=1, actor_id=1,
            sichten=[{"key": "dashboard", "sichtbar": True},
                     {"key": "escalation", "sichtbar": False}],
            widgets=["fallampel"])
        # Genau zwei Belege — einer je Art, nicht einer je Zeile.
        self.assertEqual(self._spitze() - vor, 2)
        self.assertEqual(set(res["audit_seqs"]), {"sicht", "widget"})

        seq = res["audit_seqs"]["sicht"]
        self.assertEqual(self._typ(seq), EventType.VIEW_PREF_SET)
        p = self._payload(seq)
        self.assertEqual(p["art"], "sicht")
        self.assertEqual(p["anzahl"], 2)
        # DER VOLLSTAENDIGE ZUSTAND, kein Delta: aus diesem einen Beleg muss
        # rekonstruierbar sein, wie die Oberflaeche eingerichtet war.
        self.assertEqual(p["reihenfolge"], ["dashboard", "escalation"])
        self.assertEqual(p["ausgeblendet"], ["escalation"])
        # Kein Fallbezug im Beleg — die Einstellung kann konstruktiv keinen
        # tragen, und das wird hier festgehalten.
        for verboten in ("subject_id", "username", "case_id"):
            self.assertNotIn(verboten, p)

    # ===================================================================== VP09
    def test_VP09_unbekannter_schluessel_wird_benannt_und_nichts_gespeichert(self):
        with self.assertRaises(ViewPrefFehler) as ctx:
            self._repo().speichern(person_id=1, actor_id=1,
                                   sichten=["dashboard", "gibtsnicht"])
        self.assertIn("gibtsnicht", str(ctx.exception))
        # Keine stille Teilverarbeitung: auch 'dashboard' darf nicht liegen.
        self.assertEqual(self._zeilen(), [])

    # ===================================================================== VP10
    def test_VP10_doppelter_schluessel(self):
        with self.assertRaises(ViewPrefFehler) as ctx:
            self._repo().speichern(person_id=1, actor_id=1,
                                   sichten=["dashboard", "dashboard"])
        self.assertIn("mehrfach", str(ctx.exception))
        self.assertEqual(self._zeilen(), [])

    # ===================================================================== VP11
    def test_VP11_fehler_in_zweiter_art_laesst_erste_nicht_zurueck(self):
        """
        Die Pruefung laeuft VOR dem Schreiben, also faellt hier schon die
        Eingabepruefung. Der Test haelt trotzdem fest, was gelten muss:
        nach einem Fehlschlag steht NICHTS in der Tabelle — auch nicht die
        Art, die fuer sich genommen in Ordnung war.
        """
        vor = self._spitze()
        with self.assertRaises(ViewPrefFehler):
            self._repo().speichern(person_id=1, actor_id=1,
                                   sichten=["dashboard"],
                                   widgets=["fallampel", "gibtsnicht"])
        self.assertEqual(self._zeilen(), [])
        self.assertEqual(self._spitze(), vor, "Kein Beleg ohne Write.")

    # ===================================================================== VP12
    def test_VP12_keine_vertretung(self):
        """
        Wer die Oberflaeche einer anderen Person umbauen koennte, koennte ihr
        die Eskalationssicht wegnehmen. Das soll niemand koennen ausser ihr
        selbst.
        """
        with self.assertRaises(ViewPrefFehler) as ctx:
            self._repo().speichern(person_id=2, actor_id=1,
                                   sichten=["dashboard"])
        self.assertIn("selbst", str(ctx.exception))
        with self.assertRaises(ViewPrefFehler):
            self._repo().zuruecksetzen(person_id=2, actor_id=1)
        self.assertEqual(self._zeilen(person_id=2), [])

    # ===================================================================== VP13
    def test_VP13_ohne_writer_kein_schreibweg(self):
        nur_lesend = ViewPrefRepo(self.con)
        with self.assertRaises(ViewPrefFehler) as ctx:
            nur_lesend.speichern(person_id=1, actor_id=1, sichten=["audit"])
        self.assertIn("CoordinatorWriter", str(ctx.exception))
        with self.assertRaises(ViewPrefFehler):
            nur_lesend.zuruecksetzen(person_id=1, actor_id=1)
        # Lesen geht ohne Writer sehr wohl.
        self.assertEqual(nur_lesend.lade(1)["sichten"], [])

    # ===================================================================== VP14
    def test_VP14_unbekannte_gespeicherte_schluessel_werden_ausgewiesen(self):
        """
        Faellt eine Sicht spaeter aus dem Cockpit, zeigen gespeicherte Zeilen
        ins Leere. Sie werden BENANNT statt uebergangen — wer sie loescht,
        soll das entscheiden und nicht die Ladefunktion.
        """
        self._repo().speichern(person_id=1, actor_id=1, sichten=["dashboard"])
        # Am Repo vorbei, wie es eine spaetere Katalogaenderung hinterliesse.
        self.con.execute(
            "INSERT INTO person_view_pref (person_id, art, element_key, "
            "position, sichtbar, geaendert_at, audit_seq) "
            "VALUES (1,'sicht','abgeschaffte_sicht',7,1,0,1)")
        geladen = self._repo().lade(1)
        self.assertEqual([s["key"] for s in geladen["sichten"]], ["dashboard"])
        self.assertEqual(len(geladen["unbekannt"]), 1)
        self.assertEqual(geladen["unbekannt"][0]["key"], "abgeschaffte_sicht")
        self.assertEqual(geladen["unbekannt"][0]["art"], "sicht")

    # ===================================================================== VP15
    def test_VP15_zuruecksetzen_mit_eigenem_beleg_und_je_art(self):
        r = self._repo()
        r.speichern(person_id=1, actor_id=1, sichten=["dashboard"],
                    widgets=["fallampel"])
        res = r.zuruecksetzen(person_id=1, art="sicht", actor_id=1)
        self.assertEqual(res["geloescht"], 1)
        self.assertEqual(self._typ(res["audit_seq"]),
                         EventType.VIEW_PREF_RESET)
        self.assertEqual(self._zeilen(art="sicht"), [])
        # Die andere Art bleibt stehen.
        self.assertEqual(len(self._zeilen(art="widget")), 1)

        res2 = r.zuruecksetzen(person_id=1, actor_id=1)   # 'alle'
        self.assertEqual(res2["arten"], list(kat.ARTEN))
        self.assertEqual(self._zeilen(), [])
        # Ein Zuruecksetzen ohne Bestand ist kein Fehler, aber es wird
        # trotzdem belegt — sonst waere der Vorgang unsichtbar.
        res3 = r.zuruecksetzen(person_id=1, actor_id=1)
        self.assertEqual(res3["geloescht"], 0)
        self.assertGreater(res3["audit_seq"], res2["audit_seq"])


class TestEndpunkte(_Basis):
    """VP16-VP23."""

    def _get(self, person_id, pfad="/api/viewprefs", query=None):
        return self.app.dispatch(person_id, pfad, query or {})

    def _post(self, person_id, pfad, payload):
        return self.app.dispatch_write(person_id, pfad, payload)

    # ===================================================================== VP16
    def test_VP16_get_liefert_katalog_und_echte_rechtelage(self):
        r = self._get(1)
        self.assertEqual(r.status, 200)
        b = json.loads(r.body)
        self.assertEqual(b["person_id"], 1)
        self.assertEqual(b["katalog"]["sichten"],
                         list(kat.STEUERBARE_SICHTEN))
        self.assertEqual(b["katalog"]["standard_widgets"], ["fallampel"])

        erlaubt = {w["key"]: w["erlaubt"] for w in b["katalog"]["widgets"]}
        # Person 1 hat dashboard.view/caseoverview.view/escalation.view/
        # ops.view.
        self.assertTrue(erlaubt["fallampel"])
        self.assertTrue(erlaubt["eskalationen"])
        self.assertTrue(erlaubt["kettenzustand"])
        # ... und sonst nichts.
        self.assertFalse(erlaubt["lastverteilung"])
        self.assertFalse(erlaubt["fristen"])

        # Person 2 hat gar nichts — die Kacheln erscheinen im Katalog, aber
        # ALLE als nicht erlaubt. Der Rechtefilter ist die Auskunft des
        # Servers, nicht eine Ableitung des Browsers.
        b2 = json.loads(self._get(2).body)
        self.assertTrue(all(not w["erlaubt"]
                            for w in b2["katalog"]["widgets"]))

    # ===================================================================== VP24
    #
    # BUILD 571: KEIN FELD DES KACHELKATALOGS DARF UNTERWEGS VERLORENGEHEN.
    #
    # Anlass ist ein Fehler aus dem Betrieb: 'api_path' fehlte in der Antwort.
    # Der Browser holt die Daten jeder Kachel selbst (loadOverview:
    # fetchJson(w.api_path)); ohne das Feld war es dort 'undefined', fetch
    # holte die relative Adresse "undefined", und ALLE ACHT Kacheln meldeten
    # "Nicht abrufbar: HTTP 404 bei undefined". Kein Routing-, kein
    # Rechtefehler - ein nicht transportiertes Feld.
    #
    # Diese Pruefung liest die Felder von WidgetSpec und verlangt sie in der
    # Antwort. Wer ein Feld ABSICHTLICH nicht ausliefern will, traegt es unten
    # MIT GRUND ein - eine wortlose Ausnahmeliste waere eine Hintertuer.
    NICHT_TRANSPORTIERT = {
        # (derzeit leer: alles, was WidgetSpec fuehrt, gehoert in den Browser)
    }

    def test_VP24_kachelkatalog_transportiert_jedes_feld(self):
        from dataclasses import fields as _fields
        r = self._get(1)
        self.assertEqual(r.status, 200)
        b = json.loads(r.body)
        widgets = b["katalog"]["widgets"]
        self.assertEqual(len(widgets), len(kat.WIDGETS))

        soll = {f.name for f in _fields(kat.WidgetSpec)}
        soll -= set(self.NICHT_TRANSPORTIERT)
        for w in widgets:
            fehlt = sorted(soll - set(w.keys()))
            self.assertEqual(
                fehlt, [],
                "Kachel %r: Feld(er) %s kommen nicht im Browser an."
                % (w.get("key"), fehlt))

        # Und der Pfad ist nicht nur DA, sondern auch RICHTIG - ein leerer
        # oder falscher Pfad waere derselbe Ausfall in neuer Verkleidung.
        erwartet = {x.key: x.api_path for x in kat.WIDGETS}
        for w in widgets:
            self.assertEqual(w["api_path"], erwartet[w["key"]])
            self.assertTrue(str(w["api_path"]).startswith("/api/"),
                            "Kachel %r hat keinen brauchbaren Pfad: %r"
                            % (w["key"], w["api_path"]))

    # ===================================================================== VP17
    def test_VP17_unbekannte_person_404(self):
        r = self._get(999)
        self.assertEqual(r.status, 404)
        self.assertEqual(json.loads(r.body)["error"], "unknown_person")

    # ===================================================================== VP18
    def test_VP18_post_speichert_und_get_liefert_zurueck(self):
        r = self._post(1, "/api/viewprefs", {
            "sichten": [{"key": "escalation", "sichtbar": True},
                        {"key": "dashboard", "sichtbar": False}],
            "widgets": ["fallampel", "eskalationen"]})
        self.assertEqual(r.status, 200)
        b = json.loads(r.body)
        self.assertEqual(b["gespeichert"], {"sicht": 2, "widget": 2})

        g = json.loads(self._get(1).body)
        self.assertEqual([s["key"] for s in g["sichten"]],
                         ["escalation", "dashboard"])
        self.assertFalse(g["sichten"][1]["sichtbar"])
        self.assertEqual([w["key"] for w in g["widgets"]],
                         ["fallampel", "eskalationen"])
        self.assertEqual(g["unbekannt"], [])

    # ===================================================================== VP19
    def test_VP19_post_ohne_beide_felder_400(self):
        r = self._post(1, "/api/viewprefs", {})
        self.assertEqual(r.status, 400)
        self.assertIn("sichten", json.loads(r.body)["detail"])

    # ===================================================================== VP20
    def test_VP20_post_mit_unbekanntem_schluessel_400(self):
        r = self._post(1, "/api/viewprefs", {"sichten": ["gibtsnicht"]})
        self.assertEqual(r.status, 400)
        self.assertIn("gibtsnicht", json.loads(r.body)["detail"])
        self.assertEqual(self._zeilen(), [])

    # ===================================================================== VP21
    def test_VP21_get_schreibt_nichts(self):
        vor = self._spitze()
        self._get(1)
        self._get(1)
        self.assertEqual(self._spitze(), vor,
                         "Ein GET darf die Kette nicht bewegen.")

    # ===================================================================== VP22
    def test_VP22_reset_endpunkt(self):
        self._post(1, "/api/viewprefs", {"sichten": ["dashboard"]})
        r = self._post(1, "/api/viewprefs/reset", {"art": "alle"})
        self.assertEqual(r.status, 200)
        self.assertEqual(json.loads(r.body)["geloescht"], 1)
        self.assertEqual(json.loads(self._get(1).body)["sichten"], [])
        # Unbekannte Art -> 400 mit Klartext, nicht stillschweigend 'alle'.
        r2 = self._post(1, "/api/viewprefs/reset", {"art": "unfug"})
        self.assertEqual(r2.status, 400)
        self.assertIn("unfug", json.loads(r2.body)["detail"])

    # ===================================================================== VP23
    def test_VP23_m037_seedet_kein_recht(self):
        """
        AP-3G braucht kein neues Recht (Bauplan Welle 3 §4). Der Test haelt
        das fest, damit es nicht spaeter unbemerkt eines wird.
        """
        n = self.con.execute(
            "SELECT COUNT(*) FROM rbac_capability").fetchone()[0]
        self.assertEqual(n, len(capability_codes()),
                         "Die Migrationskette hat mehr oder weniger Rechte "
                         "geseedet, als der Katalog kennt.")
        from management.migrations.coordinator import m037_view_pref as m037
        quelle = Path(m037.__file__).read_text(encoding="utf-8")
        self.assertNotIn("rbac_capability", quelle,
                         "M037 fasst rbac_capability an — AP-3G soll kein "
                         "Recht anlegen.")


class TestKatalogGegenFrontend(unittest.TestCase):
    """VP24-VP25 — Build 547. Ohne Datenbank."""

    # ===================================================================== VP24
    def test_VP24_jede_kachel_hat_einen_reduzierer(self):
        """
        Der Kachel-Katalog steht im Server, die Darstellung im Browser. Ohne
        diesen Abgleich faellt beides irgendwann auseinander, UND ZWAR
        LAUTLOS: eine Kachel ohne Reduzierer bliebe dauerhaft leer (sie
        bekaeme nur einen Fehlertext, den niemand als Bauversehen erkennt),
        ein Reduzierer ohne Kachel waere toter Code. Verfahren wie VP01/VE08.
        """
        js = Path("management/server/static/cockpit_dashboard.js").read_text(
            encoding="utf-8")
        block = js.split("var REDUZIERER = {", 1)[1].split("};", 1)[0]
        reduzierer = set(re.findall(r"^\s*([a-z_]+):", block, re.MULTILINE))
        self.assertGreater(len(reduzierer), 5, "REDUZIERER nicht erkannt")

        katalog = {w.key for w in kat.WIDGETS}
        self.assertEqual(
            katalog - reduzierer, set(),
            "Kacheln ohne Reduzierer (waeren dauerhaft leer): %r"
            % sorted(katalog - reduzierer))
        self.assertEqual(
            reduzierer - katalog, set(),
            "Reduzierer ohne Kachel (toter Code): %r"
            % sorted(reduzierer - katalog))

        # KEIN ENDPUNKT ALS ZEICHENKETTE IM MODUL. Die Pfade holt die Shell
        # aus dem Katalog des Servers (w.api_path); staenden sie zusaetzlich
        # als Literal im Browser, gaebe es zwei Listen von Pfaden und damit
        # zwei Wahrheiten.
        #
        # Geprueft wird auf ZITIERTE Vorkommen. Die Pfade stehen im Modul
        # sehr wohl in KOMMENTAREN (je Reduzierer die Quellenangabe) — das
        # ist Dokumentation und ausdruecklich erwuenscht. Die erste Fassung
        # dieses Tests hat beides verwechselt und ist daran gescheitert.
        literale = set(re.findall(r"['\"](/api/[a-z_/-]+)['\"]", js))
        self.assertEqual(
            literale, set(),
            "cockpit_dashboard.js nennt Endpunkte als Zeichenkette: %r "
            "— die Pfade gehoeren allein in viewpref_katalog.WIDGETS."
            % sorted(literale))

    # ===================================================================== VP25
    def test_VP25_einstellsicht_ist_nicht_steuerbar(self):
        self.assertIn("viewprefs", kat.NICHT_STEUERBAR)
        self.assertNotIn("viewprefs", kat.STEUERBARE_SICHTEN)
        self.assertTrue(kat.NICHT_STEUERBAR["viewprefs"].strip())
        self.assertFalse(kat.ist_bekannt(kat.ART_SICHT, "viewprefs"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
