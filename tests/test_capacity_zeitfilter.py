# =============================================================================
# tests/test_capacity_zeitfilter.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle 7: Kapazitaetspflege
# =============================================================================
# Testsuite fuer management/capacity/zeitfilter.py (Build 709, Vorgang
# 75f84fee).
#
# WARUM DIESE REGEL EIGENE TESTS BEKOMMT: Sie entscheidet, welche BELEGE eine
# Ermittlerin zu sehen bekommt. Gemessen wird sie hier mit FESTEN Datumsangaben
# statt mit dem heutigen Tag - eine Regel, die nur an einem Tag im Monat
# richtig ist, faellt sonst erst dann auf, und dann in der VM.
#
# ZF01 - monatsbeginn liefert den Ersten des Monats als ISO-Datum
# ZF02 - der Monatserste selbst ist NICHT historisch (Grenze inklusive)
# ZF03 - der Tag davor IST historisch
# ZF04 - ein Datum in der Zukunft ist nie historisch
# ZF05 - OHNE Enddatum (offen) ist eine Zeile NIE historisch
# ZF06 - ein unlesbares Datum gilt NICHT als historisch (es wird angezeigt)
# ZF07 - teile_historisch trennt und zaehlt
# ZF08 - teile_historisch reisst inhaltsgleiche Zeilen NICHT mit
# ZF09 - gemessen wird am ENDE, nicht am Anfang (der Kern der Regel)
# ZF10 - Jahreswechsel: der Januar-Erste trennt Dezember von Januar
# =============================================================================

import unittest
from datetime import date

from management.capacity.zeitfilter import (
    ist_historisch, monatsbeginn, teile_historisch,
)


class ZeitfilterTests(unittest.TestCase):

    # ZF01 -------------------------------------------------------------------
    def test_zf01_monatsbeginn(self):
        self.assertEqual(monatsbeginn(date(2026, 8, 13)), "2026-08-01")
        self.assertEqual(monatsbeginn(date(2026, 8, 1)), "2026-08-01")
        self.assertEqual(monatsbeginn(date(2026, 12, 31)), "2026-12-01")

    # ZF02 / ZF03 ------------------------------------------------------------
    def test_zf02_die_grenze_selbst_ist_nicht_historisch(self):
        """Der Vorgang sagt: 'beginnen die Daten ab dem 1. des aktuellen
        Monats'. Der Erste gehoert also dazu."""
        self.assertFalse(ist_historisch("2026-08-01", "2026-08-01"))

    def test_zf03_der_tag_davor_ist_historisch(self):
        self.assertTrue(ist_historisch("2026-07-31", "2026-08-01"))

    # ZF04 -------------------------------------------------------------------
    def test_zf04_zukunft_ist_nie_historisch(self):
        self.assertFalse(ist_historisch("2027-01-01", "2026-08-01"))

    # ZF05 -------------------------------------------------------------------
    def test_zf05_ohne_ende_nie_historisch(self):
        """Eine Regel ohne Ende gilt bis auf weiteres - sie auszublenden hiesse,
        die derzeit GUELTIGE Angabe zu verstecken."""
        for leer in (None, "", "   "):
            self.assertFalse(ist_historisch(leer, "2026-08-01"), repr(leer))

    # ZF06 -------------------------------------------------------------------
    def test_zf06_unlesbares_datum_wird_angezeigt(self):
        """Eine Zeile, deren Datum man nicht versteht, ist ein BEFUND und
        gehoert vor Augen. Sie wegzublenden waere die stille Auslassung, die
        Grundregel 1 verbietet."""
        for krumm in ("31.07.2026", "2026/07/31", "morgen", "2026-7-3"):
            self.assertFalse(ist_historisch(krumm, "2026-08-01"), krumm)

    # ZF07 -------------------------------------------------------------------
    def test_zf07_teilen_und_zaehlen(self):
        zeilen = [
            {"id": 1, "period_end": "2026-06-30"},   # historisch
            {"id": 2, "period_end": "2026-08-01"},   # Grenze -> bleibt
            {"id": 3, "period_end": "2026-09-15"},   # Zukunft -> bleibt
            {"id": 4, "period_end": "2026-07-31"},   # historisch
        ]
        sichtbar, anzahl = teile_historisch(zeilen, "period_end", "2026-08-01")
        self.assertEqual([z["id"] for z in sichtbar], [2, 3])
        self.assertEqual(anzahl, 2)

    # ZF08 -------------------------------------------------------------------
    def test_zf08_inhaltsgleiche_zeilen_bleiben_getrennt(self):
        """Zwei Zeilen mit gleichem Inhalt sind zwei Zeilen. Ein Vergleich der
        Datensaetze untereinander wuerde beide mitreissen - und die Liste
        zaehlte eine Abwesenheit, die es zweimal gibt, nur einmal."""
        zeilen = [
            {"period_end": "2026-09-01"},
            {"period_end": "2026-09-01"},
            {"period_end": "2026-01-01"},
        ]
        sichtbar, anzahl = teile_historisch(zeilen, "period_end", "2026-08-01")
        self.assertEqual(len(sichtbar), 2)
        self.assertEqual(anzahl, 1)

    # ZF09 -------------------------------------------------------------------
    def test_zf09_gemessen_wird_am_ende(self):
        """DER KERN DER REGEL: Eine Abwesenheit, die im Vormonat BEGANN und
        noch laeuft, ist nicht historisch. Wer am Anfang misst, blendet sie
        aus - und mit ihr eine Angabe, die die Rechnung des laufenden Monats
        bestimmt."""
        laufend = {"period_start": "2026-07-20", "period_end": "2026-09-20"}
        sichtbar, anzahl = teile_historisch([laufend], "period_end",
                                            "2026-08-01")
        self.assertEqual(len(sichtbar), 1)
        self.assertEqual(anzahl, 0)
        # Zur Gegenprobe: am ANFANG gemessen waere sie weg.
        self.assertTrue(ist_historisch(laufend["period_start"], "2026-08-01"))

    # ZF10 -------------------------------------------------------------------
    def test_zf10_jahreswechsel(self):
        grenze = monatsbeginn(date(2027, 1, 9))
        self.assertEqual(grenze, "2027-01-01")
        self.assertTrue(ist_historisch("2026-12-31", grenze))
        self.assertFalse(ist_historisch("2027-01-01", grenze))


if __name__ == "__main__":
    unittest.main()
