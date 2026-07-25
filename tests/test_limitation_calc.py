# =============================================================================
# tests/test_limitation_calc.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7
# =============================================================================
# Testsuite fuer Build 523 (AP-3A / Idee 32): Verjaehrungs-Parametersatz und
# reine Rechenschicht. DATEILOS bis auf den ausgelieferten Parametersatz —
# keine Datenbank, kein Server, keine Uhr (Stichtag wird injiziert).
#
# LADESCHICHT (limitation_params.py):
#   LP01 — Der AUSGELIEFERTE Parametersatz laedt fehlerfrei (die Selbstpruefung
#          gegen § 78 Abs. 3 StGB greift also fuer jeden Eintrag).
#   LP02 — Der ausgelieferte Satz ist NICHT bestaetigt -> verweigerungsgrund()
#          nennt den Grund. (Aendert sich das, ist es eine bewusste Entscheidung
#          und dieser Test muss mitgeaendert werden — genau das ist gewollt.)
#   LP03 — Jeder Eintrag traegt Fundstelle, Frist-Grundlage und Ruhen-Begruendung
#          (kein Eintrag ohne Beleg).
#   LP04 — § 78 Abs. 3 StGB: frist_aus_hoechststrafe an ALLEN Stufengrenzen.
#   LP05 — Falsche Frist im Satz -> LimitationParamsError (KEIN Korrigieren).
#   LP06 — Unbekannte schema_version -> Fehler (kein bestmoegliches Lesen).
#   LP07 — 'bestaetigt' true ohne Bestaetiger bzw. ohne Datum -> Fehler.
#   LP08 — Ueberlappende Gueltigkeitsspannen desselben Codes -> Fehler.
#   LP09 — vorgabe_tatbestaende nennt unbekannten Code -> Fehler.
#   LP10 — Leere 'vorbehalte' -> Fehler (Vorbehalte sind Pflichtbestandteil).
#   LP11 — fassung_am waehlt die zur TATZEIT geltende Fassung (Tatzeitrecht);
#          ausserhalb jeder Spanne -> None (Befund, kein Rueckfall).
#   LP12 — Fehlende Datei / kaputtes JSON -> LimitationParamsError.
#
# LADESCHICHT, SCHEMA-FASSUNG 2 (Build 529 — Ersatzanker-Merkmal):
#   LP13 — Jeder Eintrag traegt 'anker_registrierung_zulaessig' (bool) UND
#          eine nicht-leere 'anker_grundlage'.
#   LP14 — Fehlendes Merkmal -> Fehler (kein Vorgabewert, keine stille
#          Entscheidung fuer kuenftig ergaenzte Tatbestaende).
#   LP15 — Nicht-boolescher Wert ('true', 1, null) -> Fehler. Geprueft wird
#          der TYP, nicht die Wahrheit — "true" waere in Python wahr.
#   LP16 — Leere 'anker_grundlage' -> Fehler.
#   LP17 — schema_version 1 (die alte Fassung) -> Fehler; die Meldung nennt
#          das fehlende Merkmal beim Namen.
#   LP18 — Die Ankerregel folgt mcs Vorgabe: §§ 176/176a unzulaessig,
#          §§ 184a/184b/184c zulaessig, §§ 184k/184l unzulaessig — und ALLE
#          Fassungen eines Codes tragen dieselbe Regel (sonst haenge die
#          Zulaessigkeit am Tatzeitpunkt, den es gerade nicht gibt).
#   LP19 — §§ 184a, 184k, 184l sind hinterlegt: Hoechststrafen, Frist nach
#          § 78 Abs. 3 Nr. 4 StGB, ruht_bis_30 false, Fundstelle vorhanden.
#   LP20 — Inkrafttreten wird NICHT rueckdatiert (§ 1, § 2 Abs. 1 StGB):
#          einen Tag vor Inkrafttreten liefert fassung_am() None.
#   LP21 — Der Vorgabesatz bleibt unveraendert, und die Fristneutralitaet
#          der Beifang-Normen wird NACHGERECHNET statt behauptet.
#   LP22 — Der Vorbehalt zur Antragsfrist (§ 77b StGB, § 184k als relatives
#          Antragsdelikt) steht im Satz.
#
# RECHENSCHICHT (limitation.py):
#   LC01 — Nicht bestaetigter Satz -> ampel 'keine_aussage', KEINE Restlaufzeit,
#          Grund im Befund. Auch mit vorhandener Tatzeit.
#   LC02 — Kein Tatzeitpunkt -> ampel 'ohne_tatzeit'; der Befund sagt
#          ausdruecklich UNGEPRUEFT (nicht unverdaechtig).
#   LC03 — Massgeblich ist die KUERZESTE Frist, und sie wird benannt.
#   LC04 — Restlaufzeit <= 0 -> 'ueberschritten'; der Befund sagt NIE
#          'verjaehrt' und nennt § 78c StGB.
#   LC05 — Restlaufzeit unter der Schwelle -> 'knapp'; genau auf der Schwelle
#          -> 'offen' (die Schwelle selbst ist noch nicht knapp).
#   LC06 — Ruhender Tatbestand -> 'ruht', restlaufzeit_tage None, § 78b genannt.
#   LC07 — Tatzeit ohne hinterlegte Fassung -> 'ohne_fassung'; der Code steht in
#          'ohne_fassung' UND als Zeile in 'deadlines' (nichts verschwindet).
#   LC08 — Mischung: ein ruhender + ein berechneter Tatbestand -> es gewinnt der
#          BERECHNETE (eine Ampel mit Zahl ist der ruhenden vorzuziehen, weil
#          sie eine Handlungsfrist nennt).
#   LC09 — Die Vorbehalte fahren in JEDER Antwort mit — auch bei 'offen'.
#   LC10 — add_years: 29.02. -> 28.02. in einem Nicht-Schaltjahr; sonst exakt.
#   LC11 — Die angewandte Vorwarnschwelle steht in der Antwort (nachrechenbar).
#   LC12 — to_dict ist vollstaendig und JSON-serialisierbar (Endpunkt-Vertrag).
#   LC13 — AMPEL_ZUSTAENDE deckt alle tatsaechlich erzeugten Zustaende ab (ein
#          neuer Zustand ohne Eintrag waere in der Sicht farblos/unsichtbar).
#
# RECHENSCHICHT, BUILD 530 (vorlaeufig/festgestellt, Ersatzanker):
#   LC14 — 'festgestellt' ist der EINZIGE zitierfaehige Zustand; eine belegte
#          Tathandlung allein macht eine Zeile NICHT zitierfaehig.
#   LC15 — to_dict traegt die neuen Achsen und bleibt JSON-faehig.
#   LC16 — Eine UNBEKANNTE Ankerart wird zu 'keine' und NICHT auf 'aktivitaet'
#          zurechtgebogen: die staerkste Aussage aus dem schwaechsten Wissen
#          waere genau der Fehler, den dieses Modul verhindern soll.
# =============================================================================

import json
import sys
import tempfile
import unittest
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.deadlines.limitation import (                      # noqa: E402
    AMPEL_ZUSTAENDE,
    ANKER_ARTEN,
    BEFUND_RUHT,
    DEFAULT_VORWARN_TAGE,
    FESTSTELLUNGEN,
    add_years,
    assess_limitation,
)
from management.deadlines.limitation_params import (               # noqa: E402
    DEFAULT_PARAMS_PATH,
    SCHEMA_VERSION,
    LimitationParamsError,
    frist_aus_hoechststrafe,
    load_params,
)


def _ts(tag: str) -> int:
    """ISO-Tag -> Unix-Sekunden (Tagesbeginn UTC)."""
    return int(datetime.combine(date.fromisoformat(tag), time(0, 0),
                                tzinfo=timezone.utc).timestamp())


def _raw() -> dict:
    """Der ausgelieferte Parametersatz als veraenderbare Kopie."""
    return json.loads(DEFAULT_PARAMS_PATH.read_text(encoding="utf-8"))


def _write(raw: dict) -> Path:
    p = Path(tempfile.mkdtemp()) / "params.json"
    p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return p


def _bestaetigt(raw: dict) -> dict:
    """Kopie mit gesetzter Bestaetigung — nur fuer Tests der Rechenschicht."""
    raw["bestaetigt"] = True
    raw["bestaetigt_von"] = "StA Testperson (Testfixture)"
    raw["bestaetigt_am"] = "2026-07-25"
    return raw


def _params_bestaetigt():
    return load_params(_write(_bestaetigt(_raw())))


class TestLimitationParams(unittest.TestCase):
    """LP01-LP22 — die Ladeschicht und ihre Selbstpruefung."""

    def test_LP01_ausgelieferter_satz_laedt(self):
        p = load_params()
        self.assertEqual(p.schema_version, SCHEMA_VERSION)
        self.assertGreater(len(p.offences), 0)
        self.assertGreater(len(p.vorgabe_tatbestaende), 0)

    def test_LP02_ausgelieferter_satz_ist_unbestaetigt(self):
        p = load_params()
        self.assertFalse(p.bestaetigt)
        grund = p.verweigerungsgrund()
        self.assertIsNotNone(grund)
        self.assertIn("NICHT JURISTISCH BESTAETIGT", grund)

    def test_LP03_jeder_eintrag_hat_belege(self):
        for o in load_params().offences:
            self.assertTrue(o.fundstelle.strip(), o.code)
            self.assertTrue(o.frist_grundlage.strip(), o.code)
            self.assertTrue(o.ruht_grundlage.strip(), o.code)
            self.assertIn("§ 78 Abs. 3", o.frist_grundlage)

    def test_LP04_paragraph78_abs3_stufengrenzen(self):
        # Nr. 5 (uebrige Taten) / Nr. 4 / Nr. 3 / Nr. 2 — jeweils an der Kante.
        self.assertEqual(frist_aus_hoechststrafe(12), 3)     # genau 1 Jahr
        self.assertEqual(frist_aus_hoechststrafe(13), 5)     # mehr als 1 Jahr
        self.assertEqual(frist_aus_hoechststrafe(60), 5)     # genau 5 Jahre
        self.assertEqual(frist_aus_hoechststrafe(61), 10)    # mehr als 5
        self.assertEqual(frist_aus_hoechststrafe(120), 10)   # genau 10 Jahre
        self.assertEqual(frist_aus_hoechststrafe(121), 20)   # mehr als 10
        self.assertEqual(frist_aus_hoechststrafe(180), 20)   # § 38 Abs. 2
        with self.assertRaises(LimitationParamsError):
            frist_aus_hoechststrafe(0)

    def test_LP05_falsche_frist_wird_zurueckgewiesen(self):
        raw = _raw()
        raw["tatbestaende"][0]["frist_jahre"] = 3   # passt nicht zu 180 Monaten
        with self.assertRaises(LimitationParamsError) as ctx:
            load_params(_write(raw))
        self.assertIn("§ 78 Abs. 3", str(ctx.exception))

    def test_LP06_unbekannte_schema_version(self):
        raw = _raw()
        raw["schema_version"] = SCHEMA_VERSION + 1
        with self.assertRaises(LimitationParamsError):
            load_params(_write(raw))

    def test_LP07_bestaetigt_ohne_bestaetiger_oder_datum(self):
        raw = _raw()
        raw["bestaetigt"] = True
        with self.assertRaises(LimitationParamsError):
            load_params(_write(raw))
        raw["bestaetigt_von"] = "StA"
        raw["bestaetigt_am"] = "kein-datum"
        with self.assertRaises(LimitationParamsError):
            load_params(_write(raw))

    def test_LP08_ueberlappende_spannen(self):
        raw = _raw()
        erst = dict(raw["tatbestaende"][0])
        erst["gueltig_von"] = "2021-01-01"
        erst["gueltig_bis"] = None
        raw["tatbestaende"].append(erst)
        with self.assertRaises(LimitationParamsError) as ctx:
            load_params(_write(raw))
        self.assertIn("ueberlappen", str(ctx.exception))

    def test_LP09_unbekannter_vorgabe_code(self):
        raw = _raw()
        raw["vorgabe_tatbestaende"] = ["gibt_es_nicht"]
        with self.assertRaises(LimitationParamsError):
            load_params(_write(raw))

    def test_LP10_leere_vorbehalte(self):
        raw = _raw()
        raw["vorbehalte"] = []
        with self.assertRaises(LimitationParamsError) as ctx:
            load_params(_write(raw))
        self.assertIn("PFLICHTBESTANDTEIL", str(ctx.exception))

    def test_LP11_fassung_am_waehlt_tatzeitrecht(self):
        p = load_params()
        # § 184b Abs. 3 hat zwei Fassungen: 2021-07-01..2024-06-27 und ab
        # 2024-06-28. Beide fuehren dieselbe Frist (fristneutrale Reform), aber
        # NICHT dieselbe Fundstelle — genau deshalb muss die Auswahl stimmen.
        alt = p.fassung_am("184b_abs3", date(2022, 3, 14))
        neu = p.fassung_am("184b_abs3", date(2025, 1, 1))
        self.assertIsNotNone(alt)
        self.assertIsNotNone(neu)
        self.assertEqual(alt.gueltig_von, "2021-07-01")
        self.assertEqual(neu.gueltig_von, "2024-06-28")
        self.assertEqual(alt.frist_jahre, neu.frist_jahre)
        self.assertNotEqual(alt.norm, neu.norm)
        # Vor jeder hinterlegten Fassung: None — ein BEFUND, kein Rueckfall.
        self.assertIsNone(p.fassung_am("184b_abs3", date(2019, 5, 1)))

    def test_LP12_datei_fehlt_oder_kaputt(self):
        with self.assertRaises(LimitationParamsError):
            load_params(Path(tempfile.mkdtemp()) / "gibt_es_nicht.json")
        kaputt = Path(tempfile.mkdtemp()) / "kaputt.json"
        kaputt.write_text("{das ist kein json", encoding="utf-8")
        with self.assertRaises(LimitationParamsError):
            load_params(kaputt)

    # -- Build 529: Schema-Fassung 2 (Ersatzanker-Merkmal) --------------------

    def test_LP13_jeder_eintrag_hat_ankerregel_mit_begruendung(self):
        """
        Das Merkmal entscheidet, ob fuer einen Fall OHNE belegte Tathandlung
        eine Frist gerechnet wird. Es muss deshalb bei JEDEM Eintrag stehen und
        eine Begruendung tragen — eine unbegruendete Ja/Nein-Entscheidung ueber
        eine Rechtsfolge waere in der Akte wertlos.
        """
        for o in load_params().offences:
            self.assertIsInstance(o.anker_registrierung_zulaessig, bool, o.code)
            self.assertTrue(o.anker_grundlage.strip(), o.code)

    def test_LP14_fehlendes_ankermerkmal_wird_zurueckgewiesen(self):
        raw = _raw()
        del raw["tatbestaende"][0]["anker_registrierung_zulaessig"]
        with self.assertRaises(LimitationParamsError) as ctx:
            load_params(_write(raw))
        self.assertIn("anker_registrierung_zulaessig", str(ctx.exception))

    def test_LP15_ankermerkmal_muss_boolesch_sein(self):
        # Die Zeichenkette "true" ist in Python wahr — genau deshalb wird hier
        # auf den TYP geprueft und nicht auf die Wahrheit.
        for wert in ("true", 1, None):
            raw = _raw()
            raw["tatbestaende"][0]["anker_registrierung_zulaessig"] = wert
            with self.assertRaises(LimitationParamsError) as ctx:
                load_params(_write(raw))
            self.assertIn("true oder false", str(ctx.exception))

    def test_LP16_leere_ankerbegruendung_wird_zurueckgewiesen(self):
        raw = _raw()
        raw["tatbestaende"][0]["anker_grundlage"] = "   "
        with self.assertRaises(LimitationParamsError) as ctx:
            load_params(_write(raw))
        self.assertIn("anker_grundlage", str(ctx.exception))

    def test_LP17_alte_schema_fassung_wird_zurueckgewiesen(self):
        """
        Ein Satz der Fassung 1 kennt das Ankermerkmal nicht. Er darf NICHT
        'bestmoeglich' gelesen werden — sonst entschiede der Code ueber eine
        Frage, die der Satz nicht beantwortet.
        """
        raw = _raw()
        raw["schema_version"] = 1
        with self.assertRaises(LimitationParamsError) as ctx:
            load_params(_write(raw))
        self.assertIn("anker_registrierung_zulaessig", str(ctx.exception))

    def test_LP18_ankerregel_folgt_der_vorgabe_von_mc(self):
        """
        mc am 2026-07-25: §§ 176/176a unzulaessig (Missbrauch geschieht nicht
        notwendigerweise als Forumsmitglied), §§ 184b/184c zulaessig.
        """
        nach_code = {}
        for o in load_params().offences:
            nach_code.setdefault(o.code, []).append(o)
        for code, fassungen in nach_code.items():
            erwartet = code.startswith(("184a", "184b", "184c"))
            for o in fassungen:
                self.assertEqual(o.anker_registrierung_zulaessig, erwartet,
                                 "%s (%s..%s)" % (code, o.gueltig_von,
                                                  o.gueltig_bis))
            # Alle Fassungen EINES Codes muessen dieselbe Regel tragen — sonst
            # haenge die Zulaessigkeit des Ankers am Tatzeitpunkt, den es in
            # genau diesem Fall ja gerade NICHT gibt.
            self.assertEqual(
                len({o.anker_registrierung_zulaessig for o in fassungen}), 1,
                code)

    def test_LP19_neue_tatbestaende_184a_184k_184l(self):
        """
        Build 529: die Beifang-Normen sind hinterlegt, tragen alle die
        Fuenfjahresfrist des § 78 Abs. 3 Nr. 4 StGB und ruhen NICHT — der
        Katalog des § 78b Abs. 1 Nr. 1 StGB nennt keine von ihnen.
        """
        p = load_params()
        nach_code = {o.code: o for o in p.offences}
        for code, monate in (("184a", 36), ("184k", 24),
                             ("184l_abs1", 60), ("184l_abs2", 36)):
            self.assertIn(code, nach_code)
            o = nach_code[code]
            self.assertEqual(o.hoechststrafe_monate, monate, code)
            self.assertEqual(o.frist_jahre, 5, code)
            self.assertFalse(o.ruht_bis_30, code)
            self.assertIn("dejure.org", o.fundstelle, code)

    def test_LP20_inkrafttreten_wird_nicht_rueckdatiert(self):
        """
        §§ 184k/184l gab es 2019/2020 nicht (§ 1, § 2 Abs. 1 StGB). Der Satz
        darf fuer Tatzeitpunkte davor KEINE Fassung liefern.
        """
        p = load_params()
        for code, erster_tag in (("184k", date(2021, 1, 1)),
                                 ("184l_abs1", date(2021, 7, 1)),
                                 ("184l_abs2", date(2021, 7, 1)),
                                 ("184a", date(2021, 1, 1))):
            self.assertIsNone(
                p.fassung_am(code, erster_tag - timedelta(days=1)), code)
            self.assertIsNotNone(p.fassung_am(code, erster_tag), code)

    def test_LP21_vorgabesatz_unveraendert_und_fristneutral(self):
        """
        Die Beifang-Normen gehoeren NICHT in den Vorgabesatz (mc). Und ihre
        Aufnahme waere fristneutral — das ist nachrechenbar und wird hier
        nachgerechnet, statt es nur zu behaupten: alle vier tragen fuenf Jahre,
        also genau die kuerzeste Frist, die der Vorgabesatz ohnehin enthaelt.
        """
        p = load_params()
        self.assertNotIn("184a", p.vorgabe_tatbestaende)
        self.assertNotIn("184k", p.vorgabe_tatbestaende)
        self.assertNotIn("184l_abs1", p.vorgabe_tatbestaende)
        self.assertNotIn("184l_abs2", p.vorgabe_tatbestaende)
        kuerzeste_vorgabe = min(
            o.frist_jahre for o in p.offences
            if o.code in p.vorgabe_tatbestaende)
        for code in ("184a", "184k", "184l_abs1", "184l_abs2"):
            o = next(x for x in p.offences if x.code == code)
            self.assertGreaterEqual(o.frist_jahre, kuerzeste_vorgabe, code)

    def test_LP22_vorbehalt_zur_antragsfrist_ist_vorhanden(self):
        """
        § 184k ist relatives Antragsdelikt. Die Frist des § 77b StGB ist eine
        ANDERE Uhr und wird hier nicht berechnet — wer das nicht weiss, koennte
        aus einer gruenen Ampel den falschen Schluss ziehen.
        """
        vorbehalte = " ".join(load_params().vorbehalte)
        self.assertIn("§ 77b", vorbehalte)
        self.assertIn("Antrag", vorbehalte)


class TestLimitationCalc(unittest.TestCase):
    """LC01-LC13 — die reine Rechenschicht."""

    def setUp(self):
        self.p_ok = _params_bestaetigt()
        self.p_entwurf = load_params()          # der ausgelieferte, unbestaetigte
        self.stichtag = _ts("2026-07-25")

    def test_LC01_unbestaetigt_keine_aussage(self):
        a = assess_limitation(tatzeit_ts=_ts("2022-03-14"),
                              params=self.p_entwurf, now_ts=self.stichtag)
        self.assertFalse(a.aussage_moeglich)
        self.assertEqual(a.ampel, "keine_aussage")
        self.assertIsNone(a.restlaufzeit_tage)
        self.assertIsNone(a.massgeblich_code)
        self.assertEqual(a.deadlines, ())
        self.assertIn("NICHT JURISTISCH BESTAETIGT", a.befund)
        # Die Tatzeit wird trotzdem ausgewiesen — sie ist eine Tatsache und
        # geht nicht verloren, nur weil die Bewertung fehlt.
        self.assertEqual(a.tatzeit_tag, "2022-03-14")

    def test_LC02_ohne_tatzeit_ist_ungeprueft(self):
        a = assess_limitation(tatzeit_ts=None, params=self.p_ok,
                              now_ts=self.stichtag)
        self.assertEqual(a.ampel, "ohne_tatzeit")
        self.assertFalse(a.aussage_moeglich)
        self.assertIn("UNGEPRUEFT", a.befund)
        self.assertIsNone(a.restlaufzeit_tage)

    def test_LC03_massgeblich_ist_die_kuerzeste_frist(self):
        a = assess_limitation(tatzeit_ts=_ts("2022-03-14"), params=self.p_ok,
                              now_ts=self.stichtag)
        self.assertTrue(a.aussage_moeglich)
        # Vorgabesatz: 184b Abs.1 (10 J.) und drei 5-Jahres-Tatbestaende.
        # Massgeblich muss ein 5-Jahres-Tatbestand sein, Ablauf 2027-03-14.
        self.assertEqual(a.massgeblich_ablauf_tag, "2027-03-14")
        self.assertIsNotNone(a.massgeblich_norm)
        berechnet = [d for d in a.deadlines if d.zustand == "berechnet"]
        self.assertEqual(len(berechnet), len(self.p_ok.vorgabe_tatbestaende))
        # Die vollstaendige Aufstellung fahrt mit — die Zahl ist nachvollziehbar.
        self.assertIn("2032-03-14", [d.ablauf_tag for d in berechnet])

    def test_LC04_ueberschritten_sagt_nie_verjaehrt(self):
        # Tat 2021-08-01, 5-Jahres-Tatbestaende -> Ablauf 2026-08-01. Stichtag
        # eine Woche danach.
        a = assess_limitation(tatzeit_ts=_ts("2021-08-01"), params=self.p_ok,
                              now_ts=_ts("2026-08-08"),
                              offence_codes=["184b_abs3"])
        self.assertEqual(a.ampel, "ueberschritten")
        self.assertLessEqual(a.restlaufzeit_tage, 0)
        self.assertNotIn("verjährt", a.befund)
        self.assertNotIn("verjaehrt", a.befund)
        self.assertIn("§ 78c", a.befund)

    def test_LC05_knapp_und_die_schwelle_selbst(self):
        # Ablauf 2027-03-14. Stichtag 2026-07-25 -> 232 Tage -> knapp.
        a = assess_limitation(tatzeit_ts=_ts("2022-03-14"), params=self.p_ok,
                              now_ts=self.stichtag,
                              offence_codes=["184b_abs3"])
        self.assertEqual(a.ampel, "knapp")
        self.assertEqual(a.restlaufzeit_tage, 232)

        # GENAU auf der Schwelle (365 Tage) -> noch 'offen'. Die Grenze gehoert
        # ausdruecklich zur oberen Klasse; das muss festgenagelt sein, sonst
        # verschiebt sich die Ampel bei einer spaeteren Umformulierung
        # unbemerkt um einen Tag.
        a2 = assess_limitation(tatzeit_ts=_ts("2022-03-14"), params=self.p_ok,
                               now_ts=_ts("2026-03-14"),
                               offence_codes=["184b_abs3"])
        self.assertEqual(a2.restlaufzeit_tage, 365)
        self.assertEqual(a2.ampel, "offen")

        a3 = assess_limitation(tatzeit_ts=_ts("2022-03-14"), params=self.p_ok,
                               now_ts=_ts("2026-03-15"),
                               offence_codes=["184b_abs3"])
        self.assertEqual(a3.restlaufzeit_tage, 364)
        self.assertEqual(a3.ampel, "knapp")

    def test_LC06_ruhender_tatbestand(self):
        a = assess_limitation(tatzeit_ts=_ts("2022-03-14"), params=self.p_ok,
                              now_ts=self.stichtag,
                              offence_codes=["176_abs1"])
        self.assertEqual(a.ampel, "ruht")
        self.assertTrue(a.aussage_moeglich)   # 'ruht' IST eine Aussage
        self.assertIsNone(a.restlaufzeit_tage)
        self.assertIn("§ 78b Abs. 1 Nr. 1", a.befund)
        self.assertEqual(a.deadlines[0].zustand, "ruht")
        self.assertIsNone(a.deadlines[0].ablauf_tag)

    def test_LC07_ohne_fassung_verschwindet_nicht(self):
        a = assess_limitation(tatzeit_ts=_ts("2019-05-01"), params=self.p_ok,
                              now_ts=self.stichtag)
        self.assertEqual(a.ampel, "ohne_fassung")
        self.assertFalse(a.aussage_moeglich)
        self.assertEqual(set(a.ohne_fassung),
                         set(self.p_ok.vorgabe_tatbestaende))
        # Jeder Code steht AUCH als eigene Zeile da (kein stilles Weglassen).
        self.assertEqual(len(a.deadlines),
                         len(self.p_ok.vorgabe_tatbestaende))
        for d in a.deadlines:
            self.assertEqual(d.zustand, "ohne_fassung")
            self.assertIn("§ 2 Abs. 1 StGB", d.hinweis)

    def test_LC08_mischung_berechnet_gewinnt_vor_ruht(self):
        a = assess_limitation(tatzeit_ts=_ts("2022-03-14"), params=self.p_ok,
                              now_ts=self.stichtag,
                              offence_codes=["176_abs1", "184b_abs3"])
        self.assertEqual(a.ampel, "knapp")
        self.assertEqual(a.massgeblich_code, "184b_abs3")
        zustaende = {d.code: d.zustand for d in a.deadlines}
        self.assertEqual(zustaende["176_abs1"], "ruht")
        self.assertEqual(zustaende["184b_abs3"], "berechnet")

    def test_LC09_vorbehalte_immer_dabei(self):
        for tatzeit, codes in ((_ts("2024-08-01"), None),
                               (None, None),
                               (_ts("2019-05-01"), None),
                               (_ts("2022-03-14"), ["176_abs1"])):
            a = assess_limitation(tatzeit_ts=tatzeit, params=self.p_ok,
                                  now_ts=self.stichtag, offence_codes=codes)
            self.assertEqual(len(a.vorbehalte), len(self.p_ok.vorbehalte))
            self.assertTrue(any("§ 78c" in v for v in a.vorbehalte))
        # Auch der unbestaetigte Satz liefert seine Vorbehalte mit.
        a2 = assess_limitation(tatzeit_ts=None, params=self.p_entwurf,
                               now_ts=self.stichtag)
        self.assertGreater(len(a2.vorbehalte), 0)

    def test_LC10_add_years_schaltjahr(self):
        self.assertEqual(add_years(date(2024, 2, 29), 5), date(2029, 2, 28))
        self.assertEqual(add_years(date(2024, 2, 29), 4), date(2028, 2, 29))
        self.assertEqual(add_years(date(2022, 3, 14), 10), date(2032, 3, 14))
        self.assertEqual(add_years(date(2022, 3, 14), 0), date(2022, 3, 14))

    def test_LC11_vorwarnschwelle_steht_in_der_antwort(self):
        a = assess_limitation(tatzeit_ts=_ts("2022-03-14"), params=self.p_ok,
                              now_ts=self.stichtag, vorwarn_tage=30)
        self.assertEqual(a.vorwarn_tage, 30)
        # Mit 30 Tagen Vorwarnung sind 232 Tage NICHT mehr knapp.
        self.assertEqual(a.ampel, "offen")
        a_default = assess_limitation(tatzeit_ts=_ts("2022-03-14"),
                                      params=self.p_ok, now_ts=self.stichtag)
        self.assertEqual(a_default.vorwarn_tage, DEFAULT_VORWARN_TAGE)

    def test_LC12_to_dict_ist_json_faehig(self):
        a = assess_limitation(tatzeit_ts=_ts("2022-03-14"), params=self.p_ok,
                              now_ts=self.stichtag)
        blob = json.dumps(a.to_dict(), ensure_ascii=False)
        wieder = json.loads(blob)
        for key in ("aussage_moeglich", "ampel", "befund", "tatzeit_tag",
                    "stichtag", "vorwarn_tage", "massgeblich_code",
                    "massgeblich_ablauf_tag", "restlaufzeit_tage",
                    "deadlines", "ohne_fassung", "vorbehalte"):
            self.assertIn(key, wieder)
        # Auch der Parametersatz ist serialisierbar (der Endpunkt liefert ihn
        # mit, damit die Sicht die Fundstellen zeigen kann).
        json.dumps(self.p_ok.to_dict(), ensure_ascii=False)

    def test_LC13_ampel_zustaende_vollstaendig(self):
        erzeugt = set()
        faelle = (
            (None, self.p_entwurf, None, "aktivitaet"),       # keine_aussage
            (None, self.p_ok, None, "aktivitaet"),            # ohne_tatzeit
            (_ts("2019-05-01"), self.p_ok, None, "aktivitaet"),      # ohne_fassung
            (_ts("2022-03-14"), self.p_ok, ["176_abs1"], "aktivitaet"),   # ruht
            (_ts("2021-08-01"), self.p_ok, ["184b_abs3"], "aktivitaet"),  # ueberschr.
            (_ts("2022-03-14"), self.p_ok, ["184b_abs3"], "aktivitaet"),  # knapp
            (_ts("2024-08-01"), self.p_ok, ["184b_abs3"], "aktivitaet"),  # offen
            # Build 530: Ersatzanker fuer einen Tatbestand, der ihn nicht
            # zulaesst (§ 176 Abs. 1) -> 'ohne_anker'.
            (_ts("2022-03-14"), self.p_ok, ["176_abs1"], "registrierung"),
        )
        for tatzeit, params, codes, art in faelle:
            erzeugt.add(assess_limitation(
                tatzeit_ts=tatzeit, params=params, anker_art=art,
                now_ts=_ts("2026-08-08"), offence_codes=codes).ampel)
        self.assertTrue(erzeugt.issubset(set(AMPEL_ZUSTAENDE)),
                        "Nicht abgedeckte Zustaende: %s"
                        % (erzeugt - set(AMPEL_ZUSTAENDE)))
        # Und umgekehrt: jeder deklarierte Zustand kommt auch vor — ein
        # deklarierter, aber nie erzeugter Zustand waere toter Code in der
        # Farbtabelle der Sicht.
        self.assertEqual(erzeugt, set(AMPEL_ZUSTAENDE),
                         "Deklariert aber nicht erzeugt: %s"
                         % (set(AMPEL_ZUSTAENDE) - erzeugt))

    def test_LC14_nur_festgestelltes_ist_zitierfaehig(self):
        """
        Der Bericht darf nur Festgestelltes zitieren. Eine belegte Tathandlung
        ist ein BELEG, aber keine FESTSTELLUNG — den Unterschied macht ein
        Mensch, nicht die Datenbank.
        """
        gemeinsam = dict(tatzeit_ts=_ts("2022-03-14"), params=self.p_ok,
                         now_ts=self.stichtag, offence_codes=["184b_abs3"])
        vor = assess_limitation(anker_art="aktivitaet", festgestellt=False,
                                **gemeinsam)
        self.assertEqual(vor.feststellung, "vorlaeufig")
        self.assertFalse(vor.to_dict()["zitierfaehig"])
        self.assertTrue(vor.befund.startswith("VORLAEUFIG —"), vor.befund)

        fest = assess_limitation(anker_art="aktivitaet", festgestellt=True,
                                 **gemeinsam)
        self.assertEqual(fest.feststellung, "festgestellt")
        self.assertTrue(fest.to_dict()["zitierfaehig"])
        self.assertEqual(fest.anker_vermerke, ())
        self.assertFalse(fest.befund.startswith("VORLAEUFIG"))
        # Die Rechtsfolge selbst ist in beiden Faellen dieselbe — die Achsen
        # sind unabhaengig, und genau das ist der Sinn der Trennung.
        self.assertEqual(vor.ampel, fest.ampel)
        self.assertEqual(vor.restlaufzeit_tage, fest.restlaufzeit_tage)

        # Ohne Datum: weder vorlaeufig noch festgestellt, sondern 'ohne'.
        leer = assess_limitation(tatzeit_ts=None, params=self.p_ok,
                                 now_ts=self.stichtag)
        self.assertEqual(leer.feststellung, "ohne")
        self.assertEqual(leer.anker_art, "keine")

    def test_LC15_to_dict_traegt_die_neuen_achsen(self):
        a = assess_limitation(tatzeit_ts=_ts("2022-03-14"), params=self.p_ok,
                              now_ts=self.stichtag, anker_art="registrierung",
                              offence_codes=["176_abs1", "184b_abs3"])
        d = json.loads(json.dumps(a.to_dict(), ensure_ascii=False))
        for key in ("feststellung", "anker_art", "anker_vermerke",
                    "ohne_anker", "zitierfaehig"):
            self.assertIn(key, d)
        self.assertIn(d["feststellung"], FESTSTELLUNGEN)
        self.assertIn(d["anker_art"], ANKER_ARTEN)
        self.assertEqual(d["ohne_anker"], ["176_abs1"])

    def test_LC16_unbekannte_ankerart_wird_nicht_zurechtgebogen(self):
        a = assess_limitation(tatzeit_ts=_ts("2022-03-14"), params=self.p_ok,
                              now_ts=self.stichtag,
                              anker_art="irgendwas_neues",
                              offence_codes=["184b_abs3"])
        self.assertEqual(a.anker_art, "keine")
        # 'keine' ist KEIN Ersatzanker -> die tatbestandsbezogene Sperre greift
        # nicht, aber die Zeile ist und bleibt vorlaeufig.
        self.assertEqual(a.feststellung, "vorlaeufig")

    def test_LC13b_befund_ruht_wortlaut(self):
        """Der Ruhen-Befund nennt Norm UND Grund der Unberechenbarkeit."""
        self.assertIn("§ 78b Abs. 1 Nr. 1", BEFUND_RUHT)
        self.assertIn("30. Lebensjahres", BEFUND_RUHT)
        self.assertIn("nicht in den ausgewerteten Daten", BEFUND_RUHT)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
