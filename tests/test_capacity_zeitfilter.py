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
#
# BUILD 714 - DIE REGEL-ARBEITSZEITEN (Vorgang 75f84fee, zweiter Teil).
# Sie folgen derselben Grenze, aber einem anderen Nachweis des Ablaufs: eine
# Regel ist erledigt, wenn eine JUENGERE sie abgeloest hat. Auf ein Enddatum
# zu pruefen waere dort nicht falsch, sondern WIRKUNGSLOS - person_worktime
# ist append-only und traegt fast nie ein effective_to.
#
# ZF11 - die GELTENDE Regel bleibt stehen, auch wenn sie Jahre alt ist
# ZF12 - eine abgeloeste Regel faellt weg und wird gezaehlt
# ZF13 - eine Nachfolgerin, die ERST IM LAUFENDEN MONAT beginnt, loest NICHT
#        ab (bis zu ihrem Stichtag galt die aeltere noch) - der Grenzfall
# ZF14 - eine SOFT-GELOESCHTE Nachfolgerin verdraengt nichts
# ZF15 - ein gesetztes effective_to vor der Grenze wirkt weiterhin; und ohne
#        lesbaren Stichtag wird NICHTS ausgeblendet
# ZF16 - Personen werden nicht verwechselt: die Regel einer Person loest die
#        einer anderen nicht ab
# =============================================================================

import unittest
from datetime import date

from management.capacity.zeitfilter import (
    ist_abgeloest, ist_historisch, monatsbeginn, spaetester_start_je_person,
    teile_abgeloeste_worktime, teile_historisch,
)


def _wt(id_, person_id, von, bis=None, geloescht=False):
    """Eine Arbeitszeitzeile in der Form, die WorktimeRepo.list_worktime
    liefert - nur die Felder, die die Regel anfasst."""
    return {"id": id_, "person_id": person_id, "effective_from": von,
            "effective_to": bis,
            "deleted_at": (1700000000 if geloescht else None)}


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


class WorktimeAbloesungTests(unittest.TestCase):
    """Build 714: die Ablösungsregel der Regel-Arbeitszeiten."""

    GRENZE = "2026-08-01"

    # ZF11 -------------------------------------------------------------------
    def test_zf11_geltende_regel_bleibt_auch_wenn_alt(self):
        """
        DAS IST DIE ZUSICHERUNG AUS BUILD 709, und sie wird hier NICHT
        aufgeweicht: person_worktime ist append-only und setzt kein
        effective_to - die heute geltende Regel traegt fast immer einen
        Stichtag aus der Vergangenheit. Sie darf nicht verschwinden, nur
        weil sie alt ist.
        """
        zeilen = [_wt(1, 7, "2020-01-01")]
        sichtbar, anzahl = teile_abgeloeste_worktime(zeilen, self.GRENZE)
        self.assertEqual([z["id"] for z in sichtbar], [1])
        self.assertEqual(anzahl, 0)

    # ZF12 -------------------------------------------------------------------
    def test_zf12_abgeloeste_regel_faellt_weg_und_wird_gezaehlt(self):
        zeilen = [_wt(1, 7, "2020-01-01"), _wt(2, 7, "2025-06-01")]
        sichtbar, anzahl = teile_abgeloeste_worktime(zeilen, self.GRENZE)
        self.assertEqual([z["id"] for z in sichtbar], [2])
        self.assertEqual(anzahl, 1)
        # Und die Zahl geht auch dann mit, wenn nicht ausgeblendet wird -
        # dieselbe Ueberlegung wie bei teile_historisch.
        self.assertEqual(
            teile_abgeloeste_worktime(zeilen, self.GRENZE)[1], 1)

    # ZF13 -------------------------------------------------------------------
    def test_zf13_nachfolger_im_laufenden_monat_loest_nicht_ab(self):
        """
        DER GRENZFALL. Beginnt die Nachfolgerin am 05., galt die
        Vorgaengerin vom 01. bis zum 04. noch - sie gehoert in die Liste des
        laufenden Monats. Wer sie ausblendet, versteckt die Regel, nach der
        in diesem Monat gerechnet wurde.
        """
        zeilen = [_wt(1, 7, "2026-02-01"), _wt(2, 7, "2026-08-05")]
        sichtbar, anzahl = teile_abgeloeste_worktime(zeilen, self.GRENZE)
        self.assertEqual([z["id"] for z in sichtbar], [1, 2])
        self.assertEqual(anzahl, 0)

        # Gegenprobe: beginnt sie GENAU am Monatsersten, ist die
        # Vorgaengerin ab dann unerreichbar und faellt weg.
        zeilen2 = [_wt(1, 7, "2026-02-01"), _wt(2, 7, self.GRENZE)]
        sichtbar2, anzahl2 = teile_abgeloeste_worktime(zeilen2, self.GRENZE)
        self.assertEqual([z["id"] for z in sichtbar2], [2])
        self.assertEqual(anzahl2, 1)

    # ZF14 -------------------------------------------------------------------
    def test_zf14_geloeschte_nachfolgerin_verdraengt_nichts(self):
        """
        Eine zurueckgenommene Nachfolgeregel gilt fuer niemanden. Wuerde sie
        die Vorgaengerin verdraengen, verschwaende die einzige wirksame Regel
        der Person aus der Liste.
        """
        alle = [_wt(1, 7, "2020-01-01"),
                _wt(2, 7, "2026-03-01", geloescht=True)]
        aktive = [z for z in alle if not z["deleted_at"]]
        sichtbar, anzahl = teile_abgeloeste_worktime(alle, self.GRENZE,
                                                     aktive)
        self.assertEqual([z["id"] for z in sichtbar], [1, 2])
        self.assertEqual(anzahl, 0)
        # OHNE ausdrueckliche Nachfolgermenge wird dasselbe abgeleitet: die
        # nicht entfernten Zeilen aus der Eingabe.
        self.assertEqual(teile_abgeloeste_worktime(alle, self.GRENZE)[1], 0)

    # ZF15 -------------------------------------------------------------------
    def test_zf15_enddatum_wirkt_weiter_und_unlesbares_bleibt_stehen(self):
        # (a) Ein gesetztes Ende vor der Grenze erledigt die Regel auch ohne
        #     Nachfolgerin - 'ist_historisch' wirkt hier unveraendert mit.
        zeilen = [_wt(1, 7, "2024-01-01", "2025-12-31")]
        sichtbar, anzahl = teile_abgeloeste_worktime(zeilen, self.GRENZE)
        self.assertEqual(sichtbar, [])
        self.assertEqual(anzahl, 1)

        # (b) OHNE lesbaren Stichtag wird NICHTS ausgeblendet. Eine Zeile,
        #     deren Datum man nicht versteht, ist ein Befund und gehoert vor
        #     Augen - dieselbe Linie wie in ist_historisch (ZF06).
        krumm = [_wt(1, 7, "2020-01-01"), _wt(2, 7, None)]
        sichtbar2, anzahl2 = teile_abgeloeste_worktime(krumm, self.GRENZE)
        self.assertEqual(len(sichtbar2), 2)
        self.assertEqual(anzahl2, 0)

    # ZF16 -------------------------------------------------------------------
    def test_zf16_personen_werden_nicht_verwechselt(self):
        zeilen = [_wt(1, 7, "2020-01-01"), _wt(2, 8, "2026-01-01")]
        sichtbar, anzahl = teile_abgeloeste_worktime(zeilen, self.GRENZE)
        self.assertEqual([z["id"] for z in sichtbar], [1, 2])
        self.assertEqual(anzahl, 0)

        # Und die Hilfsfunktion sagt je Person das Richtige.
        je = spaetester_start_je_person(zeilen, self.GRENZE)
        self.assertEqual(je, {7: "2020-01-01", 8: "2026-01-01"})
        self.assertFalse(ist_abgeloest(zeilen[0], je, self.GRENZE))


if __name__ == "__main__":
    unittest.main()
