# =============================================================================
# tests/test_person_sichtbarkeit.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Ruhestand von Hand
# =============================================================================
# Testsuite fuer management/person/person_sichtbarkeit.py (Build 701,
# Ticket 95139d2a).
#
# WORAUF DIESE SUITE ZIELT: Der Filter entscheidet, was ein Ermittler NICHT zu
# sehen bekommt. Jeder Fehler darin ist deshalb per Bauart still — genau die
# Sorte Fehler, die Grundregel 1 verbietet. Die Faelle sind entsprechend
# ausgewaehlt: nicht "blendet es aus?", sondern "blendet es das FALSCHE aus,
# und sagt es Bescheid?".
#
# PSI01 — ohne M020-Spalten: keine Aussage moeglich -> nichts ausgeblendet.
# PSI02 — inaktive() liest genau die inaktiven Zeilen samt Grund/Zeitpunkt.
# PSI03 — offene_faelle(): nur open/in_progress zaehlen, approved/closed nicht;
#         unzugewiesene Faelle (assigned_to IS NULL) zaehlen nirgends mit.
# PSI04 — fuer_auswahl entfernt ALLE Inaktiven, auch die mit offenen Faellen,
#         und fuehrt darueber Buch (Zahl + Kennungen).
# PSI05 — fuer_grundmenge BEHAELT die Inaktiven mit offenen Faellen und nennt
#         sie; die uebrigen Inaktiven fallen heraus.
# PSI06 — fuer_grundmenge(inaktive_zeigen=True) blendet nichts aus und sagt
#         das im Befund ('gezeigt').
# PSI07 — fehlt die Tabelle 'cases', wird NICHTS ausgeblendet und der Grund
#         steht im Hinweis (konservativ statt still).
# PSI08 — die Zeilenform ist gleichgueltig (dict, sqlite3.Row, dataclass,
#         Tupel); eine Zeile ohne lesbare Kennung wird BEHALTEN, nie entfernt.
# PSI09 — 'ausnahmen': eine referenzierte inaktive Person bleibt stehen und
#         wird als 'behalten_referenziert' benannt.
#
# Version: v0.8.701 · Build: 701 · 2026-08-12
# =============================================================================

import sqlite3
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.person.person_sichtbarkeit import (   # noqa: E402
    OFFENE_STATUS, PersonSichtbarkeit,
)

# Minimalschema: nur, was der Filter anfasst. Ein vollstaendiges
# coordinator.db-Schema waere hier Ballast und wuerde die Aussage der Faelle
# verwaessern — geprueft wird die Entscheidungslogik, nicht das Schema.
_PERSON_M020 = """
CREATE TABLE person (
    id INTEGER PRIMARY KEY,
    system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0,
    is_support INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    deactivated_at INTEGER,
    deactivated_reason TEXT
)
"""

_PERSON_VOR_M020 = """
CREATE TABLE person (
    id INTEGER PRIMARY KEY,
    system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0,
    is_support INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
)
"""

_CASES = """
CREATE TABLE cases (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    status TEXT NOT NULL,
    assigned_to INTEGER
)
"""


@dataclass(frozen=True)
class _Last:
    """Zeilenform wie InvestigatorLoad — frozen dataclass mit anderem Feldnamen."""
    investigator_id: int
    system_username: str


class PersonSichtbarkeitTests(unittest.TestCase):

    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.execute(_PERSON_M020)
        self.con.execute(_CASES)
        # 1 aktiv, 2 inaktiv OHNE offene Faelle, 3 inaktiv MIT offenen Faellen.
        self.con.executemany(
            "INSERT INTO person (id, system_username, display_name, "
            "created_at, is_active, deactivated_at, deactivated_reason) "
            "VALUES (?,?,?,?,?,?,?)",
            [
                (1, "h0aktiv", "Aktiv", 1000, 1, None, None),
                (2, "h0weg", "Weg", 1000, 0, 1700000000, "ausgeschieden"),
                (3, "h0weg2", "Weg mit Arbeit", 1000, 0, 1700000001, "Umzug"),
            ])

    def tearDown(self):
        self.con.close()

    def _faelle(self, *zeilen):
        self.con.executemany(
            "INSERT INTO cases (id, username, status, assigned_to) "
            "VALUES (?,?,?,?)", zeilen)

    @staticmethod
    def _zeilen():
        return [{"id": 1, "n": "a"}, {"id": 2, "n": "b"}, {"id": 3, "n": "c"}]

    # PSI01 ------------------------------------------------------------------
    def test_psi01_ohne_m020_wird_nichts_ausgeblendet(self):
        """
        Auf einem Bestand vor M020 gibt es den Zustand 'inaktiv' ueberhaupt
        nicht. Jede Ausblendung waere dort eine Erfindung — und die Sicht
        wuerde Zeilen unterschlagen, fuer die es keinen Grund gibt.
        """
        con = sqlite3.connect(":memory:")
        try:
            con.execute(_PERSON_VOR_M020)
            con.execute(_CASES)
            con.execute("INSERT INTO person (id, system_username, "
                        "display_name, created_at) VALUES (1,'a','A',1)")
            s = PersonSichtbarkeit(con)
            self.assertFalse(s.hat_m020())
            self.assertEqual(s.inaktive(), {})
            b = s.fuer_auswahl([{"id": 1}])
            self.assertEqual(len(b.zeilen), 1)
            self.assertEqual(b.ausgeblendet, 0)
        finally:
            con.close()

    # PSI02 ------------------------------------------------------------------
    def test_psi02_inaktive_mit_grund_und_zeitpunkt(self):
        s = PersonSichtbarkeit(self.con)
        inaktive = s.inaktive()
        self.assertEqual(sorted(inaktive), [2, 3])
        self.assertEqual(inaktive[2]["system_username"], "h0weg")
        self.assertEqual(inaktive[2]["deactivated_reason"], "ausgeschieden")
        self.assertEqual(inaktive[2]["deactivated_at"], 1700000000)
        # Die aktive Person taucht NICHT auf — sonst waere die Menge sinnlos.
        self.assertNotIn(1, inaktive)

    # PSI03 ------------------------------------------------------------------
    def test_psi03_offene_faelle_zaehlt_nur_offene(self):
        """
        'offen' ist NICHT frei gewaehlt: es ist die aktive Last aus
        workload_repo (_LoadAccumulator.active == open + in_progress).
        approved und closed sind dort 'done' und zaehlen hier deshalb nicht.
        """
        self.assertEqual(OFFENE_STATUS, ("open", "in_progress"))
        self._faelle(
            (1, "u1", "open", 3),
            (2, "u2", "in_progress", 3),
            (3, "u3", "approved", 3),       # zaehlt NICHT
            (4, "u4", "closed", 3),         # zaehlt NICHT
            (5, "u5", "open", None),        # unzugewiesen — gehoert niemandem
            (6, "u6", "open", 1),
        )
        s = PersonSichtbarkeit(self.con)
        self.assertEqual(s.offene_faelle_von(3), 2)
        self.assertEqual(s.offene_faelle_von(1), 1)
        self.assertEqual(s.offene_faelle_von(2), 0)
        self.assertIsNone(s.offene_hinweis())

    # PSI04 ------------------------------------------------------------------
    def test_psi04_auswahl_entfernt_alle_inaktiven(self):
        """
        In einer AUSWAHLLISTE hilft die Ausnahme 'traegt noch Faelle' nicht:
        wer ausgeschieden ist, darf keinen NEUEN Fall bekommen. Genau das
        Zuweisen ist der Fehler, den die Ausblendung verhindern soll.
        """
        self._faelle((1, "u1", "open", 3))
        b = PersonSichtbarkeit(self.con).fuer_auswahl(self._zeilen())
        self.assertEqual([z["id"] for z in b.zeilen], [1])
        self.assertEqual(b.ausgeblendet, 2)
        self.assertEqual(b.ausgeblendete_kennungen, ("h0weg", "h0weg2"))
        self.assertEqual(b.behalten_mit_arbeit, ())
        self.assertFalse(b.inaktive_gezeigt)
        self.assertIsNone(b.hinweis)
        # Der Rechenschaftsblock traegt genau diese Angaben ins JSON.
        d = b.to_dict()
        self.assertEqual(d["ausgeblendet"], 2)
        self.assertEqual(d["ausgeblendete_kennungen"], ["h0weg", "h0weg2"])

    # PSI05 ------------------------------------------------------------------
    def test_psi05_grundmenge_behaelt_wer_noch_arbeit_traegt(self):
        """
        DER KERNFALL DES TICKETS. Verschwaende die Zeile eines Ausgeschiedenen
        aus der Arbeitslast, verschwaende mit ihr die offene Arbeit — aus
        genau der Sicht, in der sie auffallen muss.
        """
        self._faelle((1, "u1", "open", 3), (2, "u2", "closed", 2))
        b = PersonSichtbarkeit(self.con).fuer_grundmenge(self._zeilen())
        self.assertEqual([z["id"] for z in b.zeilen], [1, 3])
        self.assertEqual(b.ausgeblendet, 1)
        self.assertEqual(b.ausgeblendete_kennungen, ("h0weg",))
        # Und die stehengebliebene Person wird BENANNT — sonst waere ihre
        # Zeile von der einer aktiven nicht zu unterscheiden.
        self.assertEqual(b.behalten_mit_arbeit, ("h0weg2",))

    # PSI06 ------------------------------------------------------------------
    def test_psi06_umschalter_zeigt_alle(self):
        self._faelle((1, "u1", "open", 3))
        b = PersonSichtbarkeit(self.con).fuer_grundmenge(
            self._zeilen(), inaktive_zeigen=True)
        self.assertEqual([z["id"] for z in b.zeilen], [1, 2, 3])
        self.assertEqual(b.ausgeblendet, 0)
        self.assertTrue(b.inaktive_gezeigt)
        self.assertTrue(b.to_dict()["gezeigt"])

    # PSI07 ------------------------------------------------------------------
    def test_psi07_ohne_cases_wird_nichts_ausgeblendet_aber_benannt(self):
        """
        Ist die Fallzahl nicht feststellbar, ist die Ausnahme aus PSI05 nicht
        entscheidbar. Ein Filter, der im Zweifel ausblendet, verschweigt im
        Zweifel Belege — also blendet er nichts aus UND sagt warum.
        """
        con = sqlite3.connect(":memory:")
        try:
            con.execute(_PERSON_M020)
            con.execute("INSERT INTO person (id, system_username, "
                        "display_name, created_at, is_active) "
                        "VALUES (2,'h0weg','Weg',1,0)")
            s = PersonSichtbarkeit(con)          # KEINE Tabelle 'cases'
            b = s.fuer_grundmenge([{"id": 2}])
            self.assertEqual(len(b.zeilen), 1)   # nichts ausgeblendet
            self.assertEqual(b.ausgeblendet, 0)
            self.assertIsNotNone(b.hinweis)
            self.assertIn("nicht feststellbar", b.hinweis)
            self.assertIsNotNone(s.offene_hinweis())
        finally:
            con.close()

    # PSI08 ------------------------------------------------------------------
    def test_psi08_zeilenformen_und_unlesbare_kennung(self):
        s = PersonSichtbarkeit(self.con)
        self._faelle()

        # dict
        self.assertEqual(len(s.fuer_auswahl([{"id": 2}]).zeilen), 0)
        # frozen dataclass mit eigenem Feldnamen
        b = s.fuer_auswahl([_Last(2, "h0weg"), _Last(1, "h0aktiv")],
                           id_feld="investigator_id")
        self.assertEqual([z.investigator_id for z in b.zeilen], [1])
        # sqlite3.Row
        con = self.con
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT id, system_username FROM person ORDER BY id").fetchall()
        b = PersonSichtbarkeit(con).fuer_auswahl(rows)
        self.assertEqual([r["id"] for r in b.zeilen], [1])
        con.row_factory = None
        # Tupel (id an erster Stelle — die Form der SELECTs im Server)
        b = PersonSichtbarkeit(self.con).fuer_auswahl([(1, "a"), (2, "b")])
        self.assertEqual([z[0] for z in b.zeilen], [1])

        # KEINE lesbare Kennung -> die Zeile bleibt. Was nicht zugeordnet
        # werden kann, wird nicht still entfernt.
        b = PersonSichtbarkeit(self.con).fuer_auswahl(
            [{"kein_id_feld": 7}, {"id": None}, {"id": "krumm"}])
        self.assertEqual(len(b.zeilen), 3)
        self.assertEqual(b.ausgeblendet, 0)

    # PSI09 ------------------------------------------------------------------
    def test_psi09_ausnahmen_bleiben_stehen_und_werden_benannt(self):
        """
        Eine Auswahlliste ohne den aktuell gewaehlten Eintrag laesst dessen
        Zuordnung beim naechsten Speichern still fallen. Deshalb bleiben
        referenzierte Inaktive stehen — mit eigenem, unterscheidbarem Grund.
        """
        self._faelle()
        b = PersonSichtbarkeit(self.con).fuer_auswahl(
            self._zeilen(), ausnahmen={3})
        self.assertEqual([z["id"] for z in b.zeilen], [1, 3])
        self.assertEqual(b.ausgeblendet, 1)
        self.assertEqual(b.behalten_referenziert, ("h0weg2",))
        # NICHT mit dem anderen Behalte-Grund vermischt.
        self.assertEqual(b.behalten_mit_arbeit, ())
        self.assertEqual(b.to_dict()["behalten_referenziert"], ["h0weg2"])


if __name__ == "__main__":                                # pragma: no cover
    unittest.main()
