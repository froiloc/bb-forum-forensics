# =============================================================================
# tests/test_urgency_matrix.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3B
# =============================================================================
# Testsuite fuer Build 536: der Rechenkern der Dringlichkeits-/Erkenntnislage-
# Matrix und seine Gewichtungs-Ladeschicht.
#
# Die Suite laeuft VOLLSTAENDIG OHNE DATENBANK — das war der Grund fuer diesen
# Build-Schnitt. Jede Aussage der Matrix ist damit ohne Vorrichtung
# nachrechenbar, und das ist bei einer Zahl, die die Arbeitsverteilung einer
# Dienststelle beeinflusst, keine Bequemlichkeit, sondern Voraussetzung.
#
# --- Ladeschicht -------------------------------------------------------------
#   MW01 — Der ausgelieferte Gewichtungssatz laedt und traegt Zweckbindung und
#          Vorbehalte.
#   MW02 — Die Hoechstwerte werden RICHTIG gebildet: 'frist_knapp' und
#          'frist_mittel' schliessen einander aus, es zaehlt nur der groessere.
#          Sie zu addieren waere ein Rechenfehler, der die Quadrantengrenze
#          verschoebe, ohne dass es auffiele.
#   MW03 — Unbekannte schema_version -> Verweigerung, keine Reparatur.
#   MW04 — Negatives Gewicht -> Verweigerung (vermutlich ein Vorzeichenfehler).
#   MW05 — Fehlende Zweckbindung -> Verweigerung. Sie faehrt in JEDER Antwort
#          mit; ohne sie waere die Matrix eine Zahl ohne Aussage darueber, was
#          sie NICHT sagt.
#   MW06 — Tagesgrenzen nicht aufsteigend -> Verweigerung (sonst waere die
#          mittlere Stufe toter Code).
#   MW07 — DIE QUERPROBE GEGEN DEN KATALOG: die Konfidenztabelle deckt jeden
#          Code des Seeds ab. Bricht dieser Test, wurde der Katalog erweitert
#          und der Gewichtungssatz nicht nachgezogen — dann ist eine FACHLICHE
#          Entscheidung faellig, keine Codeanpassung.
#
# --- Achse X (Dringlichkeit) --------------------------------------------------
#   UM01 — Die vier Beitraege ohne Frist summieren sich richtig.
#   UM02 — Fristschwellen: <= 365 Tage -> 40, <= 1095 -> 20, darueber 0.
#   UM03 — M-1: DIE BELASTBARKEIT WIRD NICHT EINGERECHNET. Zwei Faelle mit
#          gleicher Restlaufzeit, einer festgestellt, einer auf Ersatzanker,
#          haben DIESELBE Punktzahl — und verschiedene 'belastbarkeit'.
#   UM04 — M-1: 'ohne_tatzeit' ergibt KEINE 0, sondern das fuenfte Feld.
#   UM05 — M-1: die uebrigen Punkte gehen dabei NICHT verloren
#          ('dringlichkeit_mindestens').
#   UM06 — Die Positivliste greift auch fuer 'ruht', 'ohne_fassung' und
#          'keine_aussage' — alles Nichtaussagen.
#   UM07 — Eine nicht geladene Fristkomponente ist NICHT dasselbe wie eine
#          fehlende Frist; der Grund unterscheidet die beiden.
#   UM08 — WIDERSPRUCH IM DATENSATZ: Ampel verspricht eine Restlaufzeit, es
#          kommt keine -> wird benannt, nicht geglaettet.
#   UM09 — Quittierte Eskalationen zaehlen MIT (M027: eine Quittierung ist kein
#          Erledigen). Mehrere Meldungen erhoehen den Punktwert NICHT.
#
# --- Achse Y (Erkenntnislage) -------------------------------------------------
#   UM10 — M-3: 'identification' geht NICHT in die Abdeckung ein; gerechnet
#          wird ueber neun statt zehn Kriterien.
#   UM11 — M-3: die Identitaet ist ABGESTUFT — 'verdacht' und 'gesichert'
#          ergeben verschiedene Werte.
#   UM12 — M-2: ein unbekannter Konfidenzcode ergibt NICHT 0, sondern macht den
#          Fall 'nicht bestimmbar' und wird benannt.
#   UM13 — M-2: dasselbe fuer einen unbekannten Identitaets-Code.
#   UM14 — 'kein_anhalt' (0 Punkte) ist NICHT dasselbe wie 'nie bewertet': der
#          eine hat eine Abdeckung, der andere nicht.
#
# --- Quadranten und Sortierung ------------------------------------------------
#   UM15 — Die vier Quadranten werden an den Schwellen richtig getroffen.
#   UM16 — Ist EINE Achse nicht bestimmbar, ist es das fuenfte Feld — auch wenn
#          die andere hoch ist.
#   UM17 — SORTIERUNG: 'nicht_bestimmbar' steht GANZ OBEN. Ungepruefes darf
#          nicht unter Unverdaechtiges rutschen.
#   UM18 — Jede Zelle traegt ihre Beitraege mit; eine nackte Zahl gaebe es nie.
#
# Version: v0.8.536 · Build: 536 · 2026-07-26
# =============================================================================

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.results.matrix_weights import (                     # noqa: E402
    MatrixWeightsError, load_weights,
)
from management.results.urgency_matrix import (                     # noqa: E402
    AMPEL_MIT_FRIST, QUADRANTEN, UrgencyMatrix,
)

_WURZEL = Path(__file__).resolve().parent.parent
_JSON = _WURZEL / "management" / "results" / "matrix_weights.json"

#: Die zehn Kriterien des Seeds (m011_investigation_results.py:307-318).
_KRITERIEN = [
    "identification", "location_identification", "victim_identification",
    "abuser", "cp_possession", "cp_distribution", "cp_production",
    "jp_possession", "jp_distribution", "jp_production",
]


def _bewertung(code, conf, ordinal, extrem="schwerste"):
    return {"criterion_code": code, "extrem": extrem,
            "confidence_code": conf, "confidence_ordinal": ordinal}


def _fall(**over):
    f = {
        "subject_id": 101, "username": "beschuldigter",
        "limitation": None,
        "wiedervorlage_ueberfaellig": False,
        "eskalationen": 0,
        "tage_ohne_ereignis": None,
        "unzugewiesen": False,
        "alle_kriterien": list(_KRITERIEN),
        "bewertungen": [],
        "identitaet_konfidenz": None,
    }
    f.update(over)
    return f


def _lim(ampel="offen", rest=2000, feststellung="vorlaeufig",
         anker="aktivitaet"):
    return {"ampel": ampel, "restlaufzeit_tage": rest,
            "feststellung": feststellung, "anker_art": anker}


class TestMatrixWeights(unittest.TestCase):
    """MW01-MW07: die Ladeschicht."""

    def setUp(self):
        self.roh = json.loads(_JSON.read_text(encoding="utf-8"))
        self.dir = Path(tempfile.mkdtemp())

    def _mit(self, aenderung):
        d = json.loads(json.dumps(self.roh))
        aenderung(d)
        p = self.dir / "w.json"
        p.write_text(json.dumps(d), encoding="utf-8")
        return p

    # ===================================================================== MW01
    def test_MW01_ausgelieferter_satz_laedt(self):
        g = load_weights()
        self.assertTrue(g.zweckbindung)
        self.assertIn("261", g.zweckbindung)
        self.assertGreaterEqual(len(g.vorbehalte), 1)
        self.assertEqual(g.ausgeschlossene_kriterien, ("identification",))

    # ===================================================================== MW02
    def test_MW02_hoechstwerte_addieren_die_fristsstufen_nicht(self):
        g = load_weights()
        # 40 (die groessere der beiden Fristsstufen) + 15 + 15 + 10 + 10
        self.assertEqual(g.dringlichkeit_max, 90)
        self.assertNotEqual(
            g.dringlichkeit_max,
            g.frist_knapp + g.frist_mittel + g.wiedervorlage_ueberfaellig
            + g.eskalation_aktiv + g.liegezeit + g.unzugewiesen,
            "Die beiden Fristsstufen wurden addiert — sie schliessen einander "
            "aber aus. Die Quadrantengrenze laege dann zu hoch.")
        self.assertEqual(g.erkenntnislage_max, 100)   # 40 + 40 + 20
        self.assertEqual(g.schwelle_dringlichkeit, 45.0)
        self.assertEqual(g.schwelle_erkenntnislage, 50.0)

    # ===================================================================== MW03
    def test_MW03_unbekannte_schema_version(self):
        p = self._mit(lambda d: d.update(schema_version=99))
        with self.assertRaises(MatrixWeightsError) as ctx:
            load_weights(p)
        self.assertIn("schema_version", str(ctx.exception))

    # ===================================================================== MW04
    def test_MW04_negatives_gewicht(self):
        p = self._mit(lambda d: d["dringlichkeit"].update(unzugewiesen=-5))
        with self.assertRaises(MatrixWeightsError) as ctx:
            load_weights(p)
        self.assertIn("negativ", str(ctx.exception))

    # ===================================================================== MW05
    def test_MW05_ohne_zweckbindung_keine_matrix(self):
        p = self._mit(lambda d: d.update(zweckbindung=""))
        with self.assertRaises(MatrixWeightsError) as ctx:
            load_weights(p)
        self.assertIn("Zweckbindung", str(ctx.exception))

        p2 = self._mit(lambda d: d.update(vorbehalte=[]))
        with self.assertRaises(MatrixWeightsError):
            load_weights(p2)

    # ===================================================================== MW06
    def test_MW06_tagesgrenzen_muessen_aufsteigen(self):
        p = self._mit(lambda d: d["dringlichkeit"].update(
            frist_knapp_tage_bis=1095, frist_mittel_tage_bis=365))
        with self.assertRaises(MatrixWeightsError) as ctx:
            load_weights(p)
        self.assertIn("GROESSER", str(ctx.exception))

    # ===================================================================== MW07
    def test_MW07_konfidenztabelle_deckt_den_katalog_ab(self):
        """
        DIE QUERPROBE (Entscheidung M-2). Die Skala ist Daten und im Betrieb
        aenderbar; mc hat sich fuer eine feste Punktetabelle entschieden. Damit
        eine Katalogerweiterung nicht STILL dazu fuehrt, dass Faelle absinken,
        haelt dieser Test die Tabelle gegen den Seed.

        BRICHT ER, IST KEINE CODEANPASSUNG FAELLIG, SONDERN EINE FACHLICHE
        ENTSCHEIDUNG: jemand muss festlegen, wie viele Punkte die neue Stufe
        traegt.
        """
        import re
        seed = (_WURZEL / "management" / "migrations" / "coordinator"
                / "m011_investigation_results.py").read_text(encoding="utf-8")
        codes = set(re.findall(r'\(\s*"confidence",\s*"([a-z_]+)"', seed))
        self.assertTrue(codes, "Konfidenz-Seed in m011 nicht gefunden.")

        g = load_weights()
        fehlend = sorted(codes - set(g.konfidenz))
        self.assertEqual(
            fehlend, [],
            "Der Katalog fuehrt Konfidenzstufen, die matrix_weights.json nicht "
            "kennt: %s. Diese Faelle wuerden als 'nicht bestimmbar' gefuehrt "
            "(nicht mit 0 — das faengt UM12 ab), aber die Matrix ist fuer sie "
            "wirkungslos. Es ist FACHLICH zu entscheiden, wie viele Punkte "
            "die neue Stufe traegt." % fehlend)

        # Die Gegenrichtung ist erlaubt und wird nur benannt: die Tabelle darf
        # einen Code fuehren, den der Seed (noch) nicht hat — das ist der
        # ungefaehrliche Fall.
        ueberzaehlig = sorted(set(g.konfidenz) - codes)
        if ueberzaehlig:
            self.assertTrue(True, "nur informativ: %s" % ueberzaehlig)


class TestUrgencyMatrixX(unittest.TestCase):
    """UM01-UM09: die Achse Dringlichkeit."""

    def setUp(self):
        self.m = UrgencyMatrix(load_weights())

    # ===================================================================== UM01
    def test_UM01_beitraege_ohne_frist(self):
        z = self.m.bewerte(_fall(
            limitation=_lim(rest=5000),          # keine Fristpunkte
            wiedervorlage_ueberfaellig=True,     # 15
            eskalationen=1,                      # 15
            tage_ohne_ereignis=120,              # 10
            unzugewiesen=True))                  # 10
        self.assertEqual(z.dringlichkeit, 50)
        self.assertTrue(z.dringlichkeit_bestimmbar)

    # ===================================================================== UM02
    def test_UM02_fristschwellen(self):
        for rest, erwartet in ((0, 40), (365, 40), (366, 20), (1095, 20),
                               (1096, 0), (5000, 0)):
            with self.subTest(rest=rest):
                z = self.m.bewerte(_fall(limitation=_lim(rest=rest)))
                self.assertEqual(z.dringlichkeit, erwartet)

    # ===================================================================== UM03
    def test_UM03_belastbarkeit_wird_nicht_eingerechnet(self):
        """
        Die Kernaussage von M-1. Zwei Faelle, gleiche Restlaufzeit, ganz
        verschiedene Beleglage — GLEICHE Punktzahl, verschiedene Belastbarkeit.
        Wer das je 'vereinheitlicht', bricht diesen Test.
        """
        fest = self.m.bewerte(_fall(limitation=_lim(
            rest=100, feststellung="festgestellt", anker="tatzeit")))
        ersatz = self.m.bewerte(_fall(limitation=_lim(
            rest=100, feststellung="vorlaeufig", anker="registrierung")))

        self.assertEqual(fest.dringlichkeit, ersatz.dringlichkeit)
        self.assertEqual(fest.dringlichkeit_belastbarkeit, "festgestellt")
        self.assertEqual(ersatz.dringlichkeit_belastbarkeit, "vorlaeufig")
        # Und der Ersatzanker traegt seinen Vermerk mit.
        self.assertTrue(any("ERSATZANKER" in v for v in ersatz.vermerke))
        self.assertFalse(any("ERSATZANKER" in v for v in fest.vermerke))

    # ===================================================================== UM04
    def test_UM04_ohne_tatzeit_ist_keine_null(self):
        z = self.m.bewerte(_fall(limitation=_lim(ampel="ohne_tatzeit",
                                                 rest=None)))
        self.assertIsNone(z.dringlichkeit,
                          "'ohne_tatzeit' darf keine 0 ergeben — eine 0 saehe "
                          "aus wie eine Aussage.")
        self.assertFalse(z.dringlichkeit_bestimmbar)
        self.assertEqual(z.quadrant, "nicht_bestimmbar")
        self.assertEqual(z.dringlichkeit_grund, "ohne_tatzeit")
        self.assertTrue(any("UNGEPRUEFT" in v for v in z.vermerke))

    # ===================================================================== UM05
    def test_UM05_die_uebrigen_punkte_gehen_nicht_verloren(self):
        z = self.m.bewerte(_fall(
            limitation=_lim(ampel="ohne_anker", rest=None),
            wiedervorlage_ueberfaellig=True, eskalationen=2,
            unzugewiesen=True))
        self.assertIsNone(z.dringlichkeit)
        self.assertEqual(z.dringlichkeit_mindestens, 40,   # 15 + 15 + 10
                         "Ein ungeprueter Fall mit vielen anderen Beitraegen "
                         "ist erkennbar dringend — das darf nicht "
                         "verschwinden.")

    # ===================================================================== UM06
    def test_UM06_positivliste_faengt_alle_nichtaussagen(self):
        self.assertEqual(set(AMPEL_MIT_FRIST),
                         {"ueberschritten", "knapp", "offen"})
        for ampel in ("ruht", "ohne_fassung", "keine_aussage", "ohne_anker",
                      "ohne_tatzeit", "irgendwas_neues"):
            with self.subTest(ampel=ampel):
                z = self.m.bewerte(_fall(limitation=_lim(ampel=ampel,
                                                         rest=10)))
                self.assertIsNone(
                    z.dringlichkeit,
                    "'%s' wurde gerechnet, obwohl es keine Restlaufzeit "
                    "verspricht." % ampel)
                self.assertEqual(z.dringlichkeit_grund, ampel)

    # ===================================================================== UM07
    def test_UM07_nicht_geladen_ist_nicht_dasselbe_wie_ohne_frist(self):
        nicht_geladen = self.m.bewerte(_fall(limitation=None,
                                             unzugewiesen=True))
        ohne_frist = self.m.bewerte(_fall(
            limitation=_lim(ampel="ohne_tatzeit", rest=None),
            unzugewiesen=True))

        self.assertIsNone(nicht_geladen.dringlichkeit)
        self.assertIsNone(ohne_frist.dringlichkeit)
        # Der GRUND unterscheidet sie — sonst saehe ein noch nicht geladener
        # Fall aus wie ein ungeprueter.
        self.assertEqual(nicht_geladen.dringlichkeit_grund, "nicht_geladen")
        self.assertEqual(ohne_frist.dringlichkeit_grund, "ohne_tatzeit")
        self.assertTrue(any("UNTERGRENZE" in v
                            for v in nicht_geladen.vermerke))

    # ===================================================================== UM08
    def test_UM08_widerspruch_wird_benannt(self):
        z = self.m.bewerte(_fall(limitation=_lim(ampel="knapp", rest=None)))
        self.assertIsNone(z.dringlichkeit)
        self.assertEqual(z.dringlichkeit_grund, "restlaufzeit_fehlt")
        self.assertTrue(any("WIDERSPRUCH" in v for v in z.vermerke))

    # ===================================================================== UM09
    def test_UM09_eskalationen_zaehlen_unabhaengig_von_der_quittierung(self):
        """
        M027 woertlich: 'Sie ist KEIN Erledigen. Die Eskalation VERSCHWINDET
        NICHT aus der Liste.' Der Aufrufer uebergibt deshalb die ZAHL der
        Meldungen, nicht die Zahl der unquittierten.
        """
        eine = self.m.bewerte(_fall(limitation=_lim(rest=5000),
                                    eskalationen=1))
        fuenf = self.m.bewerte(_fall(limitation=_lim(rest=5000),
                                     eskalationen=5))
        self.assertEqual(eine.dringlichkeit, 15)
        self.assertEqual(fuenf.dringlichkeit, 15,
                         "Mehrere Meldungen duerfen den Punktwert nicht "
                         "erhoehen — das ist nicht beschlossen.")
        # Die Zahl steht aber im Beitrag.
        b = [x for x in fuenf.beitraege if x["code"] == "eskalation"][0]
        self.assertIn("5 aktive", b["grund"])


class TestUrgencyMatrixY(unittest.TestCase):
    """UM10-UM14: die Achse Erkenntnislage."""

    def setUp(self):
        self.m = UrgencyMatrix(load_weights())

    # ===================================================================== UM10
    def test_UM10_identification_geht_nicht_in_die_abdeckung(self):
        """M-3: sonst zaehlt dieselbe Erkenntnis zweimal."""
        z = self.m.bewerte(_fall(bewertungen=[
            _bewertung("identification", "gerichtsfest", 5)]))
        self.assertEqual(z.n_kriterien_matrix, 9,
                         "Gerechnet wird ueber NEUN Kriterien.")
        # Die einzige Bewertung ist ausgeschlossen -> Abdeckung 0, Konfidenz 0.
        self.assertEqual(z.erkenntnislage, 0)

        # Gegenprobe: dieselbe Bewertung an einem anderen Kriterium zaehlt.
        z2 = self.m.bewerte(_fall(bewertungen=[
            _bewertung("abuser", "gerichtsfest", 5)]))
        # Abdeckung 1/9 -> round(0.111*40) = 4; Konfidenz 'gerichtsfest' -> 40
        self.assertEqual(z2.erkenntnislage, 44)

    # ===================================================================== UM11
    def test_UM11_identitaet_ist_abgestuft(self):
        werte = {}
        for code in ("verdacht", "wahrscheinlich", "gesichert"):
            z = self.m.bewerte(_fall(identitaet_konfidenz=code))
            werte[code] = z.erkenntnislage
        self.assertEqual(werte, {"verdacht": 7, "wahrscheinlich": 13,
                                 "gesichert": 20})
        self.assertNotEqual(
            werte["verdacht"], werte["gesichert"],
            "Eine vermutete Zuordnung darf nicht so viel wiegen wie eine "
            "gesicherte — bei genau dem Merkmal, um dessentwillen das "
            "Werkzeug gebaut wird.")

    # ===================================================================== UM12
    def test_UM12_unbekannte_konfidenz_ergibt_nicht_null(self):
        """
        M-2, die Absicherung der festen Tabelle. Nach einer Katalog-
        erweiterung darf ein Fall NICHT stillschweigend absinken.
        """
        z = self.m.bewerte(_fall(bewertungen=[
            _bewertung("abuser", "voellig_neue_stufe", 6)]))
        self.assertIsNone(z.erkenntnislage,
                          "Ein unbekannter Code wurde mit 0 gerechnet.")
        self.assertFalse(z.erkenntnislage_bestimmbar)
        self.assertIn("voellig_neue_stufe", z.unbekannte_codes)
        self.assertEqual(z.quadrant, "nicht_bestimmbar")
        self.assertTrue(any("Katalog" in v for v in z.vermerke))

    # ===================================================================== UM13
    def test_UM13_unbekannte_identitaetsstufe_ergibt_nicht_null(self):
        z = self.m.bewerte(_fall(identitaet_konfidenz="zweifelsfrei"))
        self.assertIsNone(z.erkenntnislage)
        self.assertIn("zweifelsfrei", z.unbekannte_codes)

    # ===================================================================== UM14
    def test_UM14_kein_anhalt_ist_nicht_nie_bewertet(self):
        """
        'kein_anhalt' traegt 0 Punkte — das ist Absicht (geprueft, nichts
        gefunden). Aber der Fall ist deshalb NICHT gleich einem nie bewerteten:
        er hat eine Abdeckung.
        """
        geprueft = self.m.bewerte(_fall(bewertungen=[
            _bewertung("abuser", "kein_anhalt", 1)]))
        nie = self.m.bewerte(_fall(bewertungen=[]))

        self.assertEqual(geprueft.erkenntnislage, 4)   # Abdeckung 1/9 * 40
        self.assertEqual(nie.erkenntnislage, 0)
        self.assertNotEqual(geprueft.erkenntnislage, nie.erkenntnislage,
                            "'geprueft, nichts gefunden' und 'nie geprueft' "
                            "duerfen nicht denselben Wert haben.")


class TestQuadrantenUndSortierung(unittest.TestCase):
    """UM15-UM18."""

    def setUp(self):
        self.g = load_weights()
        self.m = UrgencyMatrix(self.g)

    def _voll_bewertet(self, conf="gerichtsfest", ordinal=5):
        return [_bewertung(k, conf, ordinal) for k in _KRITERIEN
                if k != "identification"]

    # ===================================================================== UM15
    def test_UM15_die_vier_quadranten(self):
        # hoch/hoch -> arbeitsreif
        z = self.m.bewerte(_fall(
            limitation=_lim(rest=100), wiedervorlage_ueberfaellig=True,
            bewertungen=self._voll_bewertet(),
            identitaet_konfidenz="gesichert"))
        self.assertGreaterEqual(z.dringlichkeit, self.g.schwelle_dringlichkeit)
        self.assertEqual(z.quadrant, "arbeitsreif")

        # hoch/niedrig -> gefaehrlich
        z = self.m.bewerte(_fall(
            limitation=_lim(rest=100), wiedervorlage_ueberfaellig=True,
            bewertungen=[]))
        self.assertEqual(z.quadrant, "gefaehrlich")

        # niedrig/hoch -> belegt_nicht_eilig
        z = self.m.bewerte(_fall(
            limitation=_lim(rest=5000),
            bewertungen=self._voll_bewertet(),
            identitaet_konfidenz="gesichert"))
        self.assertEqual(z.quadrant, "belegt_nicht_eilig")

        # niedrig/niedrig -> nachrangig
        z = self.m.bewerte(_fall(limitation=_lim(rest=5000), bewertungen=[]))
        self.assertEqual(z.quadrant, "nachrangig")

    # ===================================================================== UM16
    def test_UM16_eine_unbestimmbare_achse_genuegt(self):
        z = self.m.bewerte(_fall(
            limitation=_lim(rest=10),                 # X waere hoch
            bewertungen=[_bewertung("abuser", "unbekannt_xy", 9)]))
        self.assertTrue(z.dringlichkeit_bestimmbar)
        self.assertFalse(z.erkenntnislage_bestimmbar)
        self.assertEqual(z.quadrant, "nicht_bestimmbar")

    # ===================================================================== UM17
    def test_UM17_ungepruftes_steht_ganz_oben(self):
        faelle = [
            _fall(subject_id=1, limitation=_lim(rest=5000)),          # nachrangig
            _fall(subject_id=2, limitation=_lim(rest=10),
                  wiedervorlage_ueberfaellig=True),                    # gefaehrlich
            _fall(subject_id=3, limitation=_lim(ampel="ohne_tatzeit",
                                                rest=None)),           # fuenftes Feld
            _fall(subject_id=4, limitation=_lim(rest=10),
                  wiedervorlage_ueberfaellig=True,
                  bewertungen=[_bewertung(k, "gerichtsfest", 5)
                               for k in _KRITERIEN if k != "identification"],
                  identitaet_konfidenz="gesichert"),                   # arbeitsreif
        ]
        zellen = self.m.bewerte_alle(faelle)
        self.assertEqual([z.subject_id for z in zellen], [3, 2, 4, 1],
                         "Ungepruefes gehoert nach oben, nicht ans Ende.")
        self.assertEqual(zellen[0].quadrant, "nicht_bestimmbar")

    # ===================================================================== UM18
    def test_UM18_keine_zahl_ohne_beitraege(self):
        z = self.m.bewerte(_fall(
            limitation=_lim(rest=100), unzugewiesen=True,
            bewertungen=[_bewertung("abuser", "verdacht", 3)],
            identitaet_konfidenz="wahrscheinlich"))
        codes = {b["code"] for b in z.beitraege}
        self.assertEqual(codes, {"frist", "unzugewiesen", "abdeckung",
                                 "konfidenz", "identitaet"})
        # Die Summe der Beitraege ergibt die beiden Achsenwerte — nachrechenbar.
        x = sum(b["punkte"] for b in z.beitraege
                if b["achse"] == "dringlichkeit")
        y = sum(b["punkte"] for b in z.beitraege
                if b["achse"] == "erkenntnislage")
        self.assertEqual(x, z.dringlichkeit)
        self.assertEqual(y, z.erkenntnislage)
        d = z.to_dict()
        self.assertIn("quadrant_bedeutung", d)
        self.assertIn(d["quadrant"], QUADRANTEN)


if __name__ == "__main__":
    unittest.main()
