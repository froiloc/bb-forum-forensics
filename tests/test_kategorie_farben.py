# =============================================================================
# tests/test_kategorie_farben.py
# IT-Forensisches Ermittlungswerkzeug - Vollzitat (Beweismittelgruppen)
# =============================================================================
# Zweck:
#   HAELT DIE DREI KATEGORIETAFELN ZUSAMMEN. Seit Build 725 fuehrt
#   core/kategorie_farben.py die Fassung; in JavaScript stehen weiterhin zwei
#   Abschriften, weil der Werkzeugbalken im Browser ohne Python auskommen
#   muss (Begruendung im Kopf des Moduls). Diese Tests messen die Abschriften
#   an der Fassung.
#
# WARUM DAS EIN TEST IST UND KEIN KOMMENTAR: Die beiden JS-Tafeln waren
#   bereits auseinander gelaufen, bevor es diese Datei gab - nicht in den
#   Werten, aber im Beleg (userinfo/annotation_filter.js verweist auf
#   "toolbar/toolbar.js:499-506", tatsaechlich stehen die Werte dort seit
#   laengerem in 532-540). Ein Kommentar haette das nicht bemerkt.
#
# KF01 - Die sechs IDs und ihre Reihenfolge stimmen mit toolbar.js ueberein.
# KF02 - Farben und Kuerzel stimmen mit toolbar.js ueberein.
# KF03 - userinfo/annotation_filter.js stimmt mit toolbar.js ueberein.
# KF04 - Jede notierte Hinterlegung ist die nachgerechnete.
# KF05 - Schwarzer Text auf jeder Hinterlegung >= 4.5:1 (WCAG AA).
# KF06 - Die sechs Hinterlegungen sind untereinander unterscheidbar.
# KF07 - Die Tafel deckt sich mit db/evidence_db.VALID_CATEGORIES.
# KF08 - Eine unbekannte Kategorie wird benannt, nicht verschluckt (GR1).
# KF09 - Die Gegenprobe: ein veraenderter Wert laesst KF02 fallen.
#
# Version: v0.8.725 - Build: 725 - 2026-08-27
# =============================================================================

from __future__ import annotations

import re
import unittest
from pathlib import Path

from core import kategorie_farben as kf
from db.evidence_db import VALID_CATEGORIES

_WURZEL = Path(__file__).resolve().parent.parent
_TOOLBAR = _WURZEL / "toolbar" / "toolbar.js"
_FILTER = _WURZEL / "userinfo" / "annotation_filter.js"


def _tafel_aus_js(pfad: Path) -> list:
    """
    Die Kategorietafel aus einer JS-Datei lesen.

    ES WIRD BEWUSST NICHT AUF EINE ZEILENNUMMER GEZIELT, sondern auf das
    Muster der Eintraege. Genau eine Zeilenangabe ist es, die in
    annotation_filter.js verrutscht ist; ein Test, der dasselbe taete, waere
    beim naechsten Einschub still falsch geworden.

    Rueckgabe: Liste von (id, label, color) in Dateireihenfolge.
    """
    text = pfad.read_text(encoding="utf-8")
    # KEIN re.VERBOSE: das Muster enthaelt '#' (Hex-Farbe), und unter VERBOSE
    # begaenne dort ein Kommentar - das Muster liefe still ins Leere und die
    # Vergleichsschleifen in KF02/KF03 haetten nichts zu vergleichen. Genau
    # dieser Fall ist der Grund fuer die Gegenprobe KF09.
    muster = re.compile(
        r"""\{\s*id:\s*['"](?P<id>CAT_[A-Z0-9_]+)['"]\s*,"""
        r"""\s*label:\s*['"](?P<label>[^'"]+)['"]\s*,"""
        r"""\s*icon:\s*['"][^'"]*['"]\s*,"""
        r"""\s*color:\s*['"](?P<color>\#[0-9a-fA-F]{6})['"]"""
    )
    treffer = [(m.group("id"), m.group("label"), m.group("color").lower())
               for m in muster.finditer(text)]
    return treffer


def _leuchtdichte(hexfarbe: str) -> float:
    """Relative Leuchtdichte nach WCAG 2.1 (sRGB)."""
    roh = hexfarbe.lstrip("#")
    kanaele = [int(roh[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    linear = [
        (k / 12.92) if k <= 0.04045 else (((k + 0.055) / 1.055) ** 2.4)
        for k in kanaele
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _kontrast_zu_schwarz(hexfarbe: str) -> float:
    """Kontrastverhaeltnis von #000000 auf der angegebenen Farbe."""
    return (_leuchtdichte(hexfarbe) + 0.05) / 0.05


class TestKategorieFarben(unittest.TestCase):

    # -- KF01 --------------------------------------------------------------
    def test_kf01_ids_und_reihenfolge_wie_toolbar(self):
        js = _tafel_aus_js(_TOOLBAR)
        self.assertEqual(
            len(js), 6,
            "toolbar.js muss genau sechs Kategorien fuehren, gefunden: %d "
            "- entweder ist eine dazugekommen (dann gehoert sie auch in "
            "core/kategorie_farben.py) oder das Lesemuster passt nicht mehr."
            % len(js))
        self.assertEqual([e[0] for e in js], list(kf.KATEGORIE_IDS))

    # -- KF02 --------------------------------------------------------------
    def test_kf02_farben_und_kuerzel_wie_toolbar(self):
        for kat, label, color in _tafel_aus_js(_TOOLBAR):
            with self.subTest(kategorie=kat):
                self.assertEqual(
                    kf.kuerzel(kat), label,
                    "Kuerzel weicht ab: toolbar.js '%s', Python '%s'"
                    % (label, kf.kuerzel(kat)))
                self.assertEqual(
                    kf.farbe(kat).lower(), color,
                    "Farbe weicht ab: toolbar.js '%s', Python '%s'. Die "
                    "markierte Stelle im Bericht haette damit eine andere "
                    "Farbe als dieselbe Markierung auf dem Bildschirm."
                    % (color, kf.farbe(kat)))

    # -- KF03 --------------------------------------------------------------
    def test_kf03_annotation_filter_deckt_sich_mit_toolbar(self):
        self.assertEqual(
            _tafel_aus_js(_FILTER), _tafel_aus_js(_TOOLBAR),
            "userinfo/annotation_filter.js und toolbar/toolbar.js fuehren "
            "verschiedene Kategorietafeln. Beide sind Abschriften von "
            "core/kategorie_farben.py und muessen deckungsgleich sein.")

    # -- KF04 --------------------------------------------------------------
    def test_kf04_hinterlegung_ist_nachgerechnet(self):
        for kat in kf.KATEGORIE_IDS:
            with self.subTest(kategorie=kat):
                self.assertEqual(
                    kf.hinterlegung(kat), kf._aufhellen(kf.farbe(kat)),
                    "Die notierte Hinterlegung ist nicht die aus der "
                    "Bildschirmfarbe gerechnete. Der Zusammenhang zwischen "
                    "Bildschirm und Bericht waere damit behauptet, nicht "
                    "hergestellt.")

    # -- KF05 --------------------------------------------------------------
    def test_kf05_schwarzer_text_auf_hinterlegung_lesbar(self):
        for kat in kf.KATEGORIE_IDS:
            with self.subTest(kategorie=kat):
                kontrast = _kontrast_zu_schwarz(kf.hinterlegung(kat))
                self.assertGreaterEqual(
                    kontrast, 4.5,
                    "Kontrast %.2f:1 unter WCAG AA (4.5:1). Der zitierte "
                    "Beitragstext liegt auf dieser Flaeche." % kontrast)

    # -- KF06 --------------------------------------------------------------
    def test_kf06_hinterlegungen_untereinander_verschieden(self):
        werte = [kf.hinterlegung(k) for k in kf.KATEGORIE_IDS]
        self.assertEqual(
            len(set(werte)), len(werte),
            "Zwei Kategorien bekaemen dieselbe Hinterlegung. Im Bericht "
            "waeren zwei verschiedene Befunde nicht mehr auseinanderzuhalten.")

    # -- KF07 --------------------------------------------------------------
    def test_kf07_deckt_sich_mit_valid_categories(self):
        self.assertEqual(
            set(kf.KATEGORIE_IDS), set(VALID_CATEGORIES),
            "Die Farbtafel und die Schreibpruefung in db/evidence_db.py "
            "kennen verschiedene Kategorien. Eine speicherbare Kategorie "
            "ohne Farbe kaeme im Bericht als 'unbekannt' heraus.")

    # -- KF08 --------------------------------------------------------------
    def test_kf08_unbekannte_kategorie_wird_benannt(self):
        # GR1: nicht verschlucken, nicht als eine der sechs ausgeben.
        self.assertFalse(kf.ist_bekannt("CAT_XY"))
        self.assertIn("CAT_XY", kf.bezeichnung("CAT_XY"))
        self.assertEqual(kf.css_klasse("CAT_XY"), "vz-cat-unbekannt")
        self.assertEqual(kf.farbe("CAT_XY"), kf.UNBEKANNT_FARBE)
        # None und "" duerfen nicht stolpern und nicht faerben.
        for leer in (None, ""):
            with self.subTest(wert=leer):
                self.assertFalse(kf.ist_bekannt(leer))
                self.assertEqual(kf.css_klasse(leer), "vz-cat-unbekannt")
                self.assertEqual(kf.bezeichnung(leer), kf.UNBEKANNT_NAME)

    # -- KF09 --------------------------------------------------------------
    def test_kf09_gegenprobe_der_pruefung(self):
        """
        Ein Test, der nicht anschlagen kann, ist kein Test.

        Hier wird der Vergleich aus KF02 mit einem VERAENDERTEN Wert
        wiederholt; er MUSS scheitern. Andernfalls prueft KF02 nichts - etwa
        weil das Lesemuster in _tafel_aus_js ins Leere laeuft und eine leere
        Liste zurueckgibt, ueber die eine Schleife wortlos hinweggeht.
        """
        js = _tafel_aus_js(_TOOLBAR)
        self.assertTrue(js, "Lesemuster findet nichts - KF02/KF03 waeren leer.")
        verfaelscht = [(js[0][0], js[0][1], "#000000")] + js[1:]
        with self.assertRaises(AssertionError):
            for kat, _label, color in verfaelscht:
                self.assertEqual(kf.farbe(kat).lower(), color)


if __name__ == "__main__":
    unittest.main()
