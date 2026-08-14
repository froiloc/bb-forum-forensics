# =============================================================================
# tests/test_quote_varianten.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle 6/7: Berichts-Ausgabe
# =============================================================================
# Testsuite fuer die drei Zitatvarianten (Vorgang 9c41a7e6-2b58-4d03-a7f1-
# 6e2b90c85fd4, Weg C - Entscheidung Alex 13.08.2026).
#
# WORUM ES GEHT: Das gebuendelte Zitatwerkzeug '@cychann/editorjs-quote' legt
# die gewaehlte Darstellung im Feld 'type' ab. Bis Build 718 hat kein Renderer
# dieses Feld gelesen - die Auswahl hatte auf den Bericht keinerlei Wirkung.
# Eine Bedienmoeglichkeit ohne Wirkung ist schlimmer als gar keine, weil sie
# eine Zusage macht, die niemand einloest.
#
# QT01 - normalisiere() bildet die drei gueltigen Werte auf sich selbst ab.
# QT02 - alles andere - fehlend, leer, falsch geschrieben, nicht-textlich -
#        ergibt die VORGABE 'quotationMark'. Das spiegelt den
#        'default'-Zweig von getTypeClass im Buendel.
# QT03 - aus_daten() ueberlebt ein Ersatzobjekt ({'_raw': ...}), wie
#        report_source es bei unlesbarem JSON anlegt.
# QT04 - css_klasse() und bezeichnung() liefern fuer JEDEN Eingabewert etwas
#        Gueltiges - kein KeyError mitten im Bericht.
# QT05 - ReportSource setzt '_quote_typ' NUR an Zitatbloecken.
# QT06 - ReportSource RUEHRT DAS ROHFELD 'type' NICHT AN (kein Schreibweg,
#        kein Migrationsschritt).
# QT07 - HTML: jede der drei Varianten bekommt ihre eigene Klasse.
# QT08 - HTML: die drei CSS-Regeln stehen im selbstenthaltenden Dokument.
# QT09 - HTML: die Quellenangabe bleibt erhalten - der Zugewinn darf den
#        Gewinn aus Build 704 nicht wieder wegnehmen.
# QT10 - HTML: ein Zitat OHNE 'type' wird zur Vorgabe 'Anfuehrungszeichen'.
#        DAS IST EINE SICHTBARE AENDERUNG AN ALTEN DATEN und deshalb
#        ausdruecklich festgehalten (siehe Kopf von quote_typen.py).
# QT11 - DOCX: 'Anfuehrungszeichen' wird zentriert.
# QT12 - DOCX: 'senkrechter Strich' bleibt, wie der Bericht bisher aussah -
#        weder zentriert noch gerahmt.
# QT13 - DOCX: 'Kasten' erzeugt einen echten Absatzrahmen (w:pBdr). Dieser
#        Test ist zugleich der Waechter ueber das interne Attribut '_p' von
#        python-docx.
# QT14 - DOCX: die Quellenangabe ist WIRKLICH kursiv. Bis Build 718 stand
#        dort 'absatz.italic = True' - eine Zeile ohne jede Wirkung.
# QT15 - PDF: alle drei Varianten erzeugen ein valides PDF.
# QT16 - Alle drei Renderer erkennen dieselbe Variante. Der Vorgang handelt
#        von zwei Stellen, die dieselbe Frage verschieden beantwortet haben;
#        dieser Fall bewacht, dass es nicht wieder passiert.
#
# ZUR VORRICHTUNG: QT05/QT06 laufen gegen eine ECHTE EvidenceDb auf einer
# In-Memory-Datei, nicht gegen einen Mock - dieselbe Regel wie in
# tests/test_report_render.py ("gruen aber tot" war dort der Fehler B1/B2).
# Die Renderer-Faelle bauen das ReportDocument von Hand: sie pruefen den
# Renderer und nicht den Weg dorthin, und QT16 haelt beide Wege zusammen.
#
# Version: v0.8.719 - Build: 719 - 2026-08-13
# =============================================================================

import io
import json
import sqlite3
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.evidence_db import EvidenceDb
from report_render.html_renderer import HtmlRenderer
from report_render.report_document import ReportDocument, RenderedBlock
from report_render.report_source import ReportSource
from report_render.quote_typen import (
    QUOTE_TYP_ANFUEHRUNG, QUOTE_TYP_FELD, QUOTE_TYP_KASTEN, QUOTE_TYP_LINIE,
    QUOTE_TYP_VORGABE, QUOTE_TYPEN, aus_daten, bezeichnung, css_klasse,
    normalisiere,
)


def _zitatblock(typ, text="Der Zeuge sagte aus.",
                caption="Vernehmung vom 03.04.2026"):
    """Ein fertiger RenderedBlock, wie ihn ReportSource liefern wuerde."""
    daten = {"_resolved_caption": caption,
             "_resolved_caption_plain": caption}
    if typ is not _FEHLT:
        daten[QUOTE_TYP_FELD] = typ
    blk = RenderedBlock(block_id="b_quote", block_type="quote",
                        data=daten, is_known_type=True)
    blk.resolved_text = text
    blk.resolved_text_plain = text
    return blk


#: Markierung fuer "das Feld ist gar nicht da" - abzugrenzen von None, das
#: ein vorhandenes Feld ohne Wert waere. Der Unterschied ist der Kern von
#: QT02 und QT10.
_FEHLT = object()


def _dokument(*bloecke):
    doc = ReportDocument(uid=18, username="testnutzer", report_id=1,
                         sequence_nr=1, title="Probe", report_type="interim",
                         status="draft", generated_at=1755000000)
    doc.blocks.extend(bloecke)
    return doc


def _docx_xml(doc):
    """Das Word-Dokument als XML-Text - so wird der Rahmen nachweisbar."""
    from report_render.docx_renderer import DocxRenderer
    roh = DocxRenderer().render(doc)
    with zipfile.ZipFile(io.BytesIO(roh)) as z:
        return z.read("word/document.xml").decode("utf-8")


def _absaetze(xml):
    """Die <w:p>-Absaetze als Einzelstuecke - fuer Aussagen je Absatz."""
    teile = xml.split("<w:p>")
    return ["<w:p>" + t.split("</w:p>")[0] for t in teile[1:]]


# =============================================================================
# Die Zuordnung selbst
# =============================================================================

class QuoteTypenTests(unittest.TestCase):

    # QT01 -------------------------------------------------------------------
    def test_qt01_gueltige_werte_bleiben(self):
        self.assertEqual(QUOTE_TYPEN,
                         ("quotationMark", "verticalLine", "box"))
        for wert in QUOTE_TYPEN:
            self.assertEqual(normalisiere(wert), wert)

    # QT02 -------------------------------------------------------------------
    def test_qt02_alles_andere_ergibt_die_vorgabe(self):
        """
        Der 'default'-Zweig von getTypeClass macht keinen Unterschied
        zwischen 'fehlt' und 'unbekannt'. Dieser Spiegel darf es deshalb auch
        nicht - sonst zeigte der Bericht etwas anderes als der Bildschirm.
        """
        self.assertEqual(QUOTE_TYP_VORGABE, "quotationMark")
        for unsinn in (None, "", "Box", "BOX", "quotation_mark", "type1",
                       0, 1, [], {}, ["box"], True):
            self.assertEqual(normalisiere(unsinn), QUOTE_TYP_VORGABE,
                             "unerwartet bei %r" % (unsinn,))

    # QT03 -------------------------------------------------------------------
    def test_qt03_aus_daten_vertraegt_ersatzobjekte(self):
        self.assertEqual(aus_daten({"type": "box"}), QUOTE_TYP_KASTEN)
        self.assertEqual(aus_daten({"text": "ohne Typ"}), QUOTE_TYP_VORGABE)
        # So legt report_source es bei unlesbarem block_data an.
        self.assertEqual(aus_daten({"_raw": "kein JSON"}), QUOTE_TYP_VORGABE)
        for kein_dict in (None, "box", 7, ["box"]):
            self.assertEqual(aus_daten(kein_dict), QUOTE_TYP_VORGABE)

    # QT04 -------------------------------------------------------------------
    def test_qt04_klasse_und_bezeichnung_ohne_keyerror(self):
        self.assertEqual(css_klasse(QUOTE_TYP_KASTEN), "zitat--kasten")
        self.assertEqual(css_klasse(QUOTE_TYP_LINIE), "zitat--linie")
        self.assertEqual(css_klasse(QUOTE_TYP_ANFUEHRUNG), "zitat--anfuehrung")
        self.assertEqual(bezeichnung(QUOTE_TYP_KASTEN), "Kasten")
        for unsinn in (None, "", "unbekannt", 7, {}):
            self.assertEqual(css_klasse(unsinn), "zitat--anfuehrung")
            self.assertTrue(bezeichnung(unsinn))


# =============================================================================
# Der Weg aus der Datenbank
# =============================================================================

class ReportSourceQuoteTests(unittest.TestCase):

    def setUp(self):
        self.con = sqlite3.connect(":memory:", check_same_thread=False)
        self.edb = EvidenceDb(self.con)
        self.con.execute(
            "INSERT INTO reports (id, report_type, sequence_nr, title, "
            "created_by, created_at, status) "
            "VALUES (1,'interim',1,'Probe','inv',1000,'draft')")

    def tearDown(self):
        self.con.close()

    def _block(self, bid, btype, daten, sort_index):
        self.con.execute(
            "INSERT INTO report_blocks (block_id, report_id, author, "
            "created_at, updated_at, block_type, block_data, "
            "placeholder_values_json, module_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (bid, 1, "inv", 1000, 1000, btype, json.dumps(daten), None, None))
        self.con.execute(
            "INSERT INTO report_block_order (block_id, sort_index, "
            "last_modified_by, last_modified_at) VALUES (?,?,?,?)",
            (bid, sort_index, "inv", 1000))

    def _doc(self):
        self.con.commit()
        # Dieselbe Aufrufform wie in tests/test_report_render.py: templates,
        # assets und forensic_con werden nicht gebraucht - an einem Zitat
        # haengt weder eine Vorlage noch ein Anhang.
        return ReportSource(
            evidence=self.edb, templates=None, assets=None, forensic_con=None,
            uid=18, username="testnutzer", generated_at=1755000000,
        ).build()

    # QT05 -------------------------------------------------------------------
    def test_qt05_nur_zitatbloecke_bekommen_das_feld(self):
        self._block("b1", "quote", {"text": "Zitat", "type": "box"}, 0)
        self._block("b2", "paragraph", {"text": "Absatz", "type": "box"}, 1)
        self._block("b3", "header", {"text": "Kapitel", "level": 2}, 2)
        doc = self._doc()
        nach_id = {b.block_id: b for b in doc.blocks}
        self.assertEqual(nach_id["b1"].data[QUOTE_TYP_FELD], QUOTE_TYP_KASTEN)
        # Ein 'type' an einem Absatz ist etwas voellig anderes (die
        # Nummerierungsart einer Liste zum Beispiel) und geht uns nichts an.
        self.assertNotIn(QUOTE_TYP_FELD, nach_id["b2"].data)
        self.assertNotIn(QUOTE_TYP_FELD, nach_id["b3"].data)

    # QT06 -------------------------------------------------------------------
    def test_qt06_das_rohfeld_bleibt_unangetastet(self):
        """
        'type' wird GELESEN, nie geschrieben. Daran haengt, dass diese
        Aenderung ohne Migrationsschritt auskommt - und der
        Migrationsvorbehalt ab 01.07.2026 gilt.
        """
        self._block("b1", "quote", {"text": "Zitat", "type": "box"}, 0)
        self._block("b2", "quote", {"text": "Ohne Typ"}, 1)
        doc = self._doc()
        nach_id = {b.block_id: b for b in doc.blocks}
        self.assertEqual(nach_id["b1"].data["type"], "box")
        self.assertNotIn("type", nach_id["b2"].data)
        self.assertEqual(nach_id["b2"].data[QUOTE_TYP_FELD],
                         QUOTE_TYP_VORGABE)

        # Und in der Datenbank steht danach unveraendert dasselbe.
        roh = dict(self.con.execute(
            "SELECT block_id, block_data FROM report_blocks").fetchall())
        self.assertEqual(json.loads(roh["b1"]), {"text": "Zitat",
                                                 "type": "box"})
        self.assertEqual(json.loads(roh["b2"]), {"text": "Ohne Typ"})

    # QT16 (erster Teil) -----------------------------------------------------
    def test_qt16_alle_drei_renderer_sehen_dieselbe_variante(self):
        """
        Der Vorgang handelt davon, dass zwei Stellen dieselbe Frage
        verschieden beantwortet haben. Dieser Fall haelt die drei
        Ausgabewege zusammen - und zwar an einem Dokument, das WIRKLICH
        durch ReportSource gegangen ist.
        """
        self._block("b1", "quote", {"text": "Kasten", "type": "box"}, 0)
        doc = self._doc()

        html = HtmlRenderer().render(doc)
        if isinstance(html, bytes):
            html = html.decode("utf-8")
        self.assertIn('class="zitat--kasten"', html)

        xml = _docx_xml(doc)
        self.assertIn("w:pBdr", xml)

        from report_render.pdf_renderer import PdfRenderer
        self.assertTrue(PdfRenderer().render(doc).startswith(b"%PDF"))


# =============================================================================
# HTML
# =============================================================================

class HtmlQuoteTests(unittest.TestCase):

    def _html(self, *bloecke):
        h = HtmlRenderer().render(_dokument(*bloecke))
        return h.decode("utf-8") if isinstance(h, bytes) else h

    # QT07 -------------------------------------------------------------------
    def test_qt07_jede_variante_bekommt_ihre_klasse(self):
        h = self._html(_zitatblock(QUOTE_TYP_ANFUEHRUNG),
                       _zitatblock(QUOTE_TYP_LINIE),
                       _zitatblock(QUOTE_TYP_KASTEN))
        for klasse in ("zitat--anfuehrung", "zitat--linie", "zitat--kasten"):
            self.assertIn('<blockquote class="%s">' % klasse, h)

    # QT08 -------------------------------------------------------------------
    def test_qt08_die_stile_stehen_im_dokument(self):
        """
        Der Bericht ist ein SELBSTENTHALTENDES Dokument. Eine Klasse ohne
        Regel waere eine Auszeichnung ohne Wirkung - genau der Mangel, den
        dieser Vorgang behebt, nur eine Ebene tiefer.
        """
        h = self._html(_zitatblock(QUOTE_TYP_KASTEN))
        for regel in ("blockquote.zitat--anfuehrung",
                      "blockquote.zitat--linie",
                      "blockquote.zitat--kasten"):
            self.assertIn(regel, h)
        # Und kein Verweis nach draussen: das Anfuehrungszeichen ist ein
        # Schriftzeichen, kein Bild von '/icons/'.
        self.assertNotIn("/icons/IconQuote.svg", h)

    # QT09 -------------------------------------------------------------------
    def test_qt09_die_quellenangabe_bleibt(self):
        h = self._html(_zitatblock(QUOTE_TYP_KASTEN,
                                   caption="Vernehmung vom 03.04.2026"))
        self.assertIn("<cite>Vernehmung vom 03.04.2026</cite>", h)
        # Ohne Quellenangabe auch kein leeres <cite>.
        self.assertNotIn("<cite></cite>",
                         self._html(_zitatblock(QUOTE_TYP_KASTEN, caption="")))

    # QT10 -------------------------------------------------------------------
    def test_qt10_altdaten_ohne_typ_werden_zur_vorgabe(self):
        """
        FESTGEHALTEN, WEIL ES SICHTBAR IST: Ein vor Build 718 angelegtes
        Zitat hat kein 'type'. Es wird ab jetzt als 'Anfuehrungszeichen'
        dargestellt - mittig - und nicht mehr als linksbuendiges Zitat mit
        senkrechtem Strich. Das ist die Angleichung an den Bildschirm des
        Bearbeiters, auf dem dasselbe Zitat schon immer so aussah.
        """
        h = self._html(_zitatblock(_FEHLT))
        self.assertIn('<blockquote class="zitat--anfuehrung">', h)
        self.assertNotIn('<blockquote class="zitat--linie">', h)


# =============================================================================
# DOCX
# =============================================================================

class DocxQuoteTests(unittest.TestCase):

    def _absatz_mit(self, xml, text):
        treffer = [a for a in _absaetze(xml) if text in a]
        self.assertTrue(treffer, "Absatz mit %r nicht gefunden" % text)
        return treffer[0]

    # QT11 -------------------------------------------------------------------
    def test_qt11_anfuehrung_wird_zentriert(self):
        xml = _docx_xml(_dokument(
            _zitatblock(QUOTE_TYP_ANFUEHRUNG, text="Mittiges Zitat")))
        absatz = self._absatz_mit(xml, "Mittiges Zitat")
        self.assertIn('w:val="center"', absatz)
        self.assertNotIn("w:pBdr", absatz)

    # QT12 -------------------------------------------------------------------
    def test_qt12_senkrechter_strich_bleibt_wie_bisher(self):
        xml = _docx_xml(_dokument(
            _zitatblock(QUOTE_TYP_LINIE, text="Zitat mit Strich")))
        absatz = self._absatz_mit(xml, "Zitat mit Strich")
        self.assertNotIn('w:val="center"', absatz)
        self.assertNotIn("w:pBdr", absatz)

    # QT13 -------------------------------------------------------------------
    def test_qt13_kasten_erzeugt_einen_absatzrahmen(self):
        """
        ZUGLEICH DER WAECHTER UEBER '_p'. Absatzrahmen gibt es in python-docx
        nur ueber rohes XML und das interne Attribut '_p'. Faellt das in
        einer kuenftigen Fassung weg, schlaegt dieser Fall an - und nicht
        erst der Ermittler, dem im Word-Export ein Kasten fehlt.
        """
        xml = _docx_xml(_dokument(
            _zitatblock(QUOTE_TYP_KASTEN, text="Zitat im Kasten")))
        absatz = self._absatz_mit(xml, "Zitat im Kasten")
        self.assertIn("w:pBdr", absatz)
        for kante in ("w:top", "w:left", "w:bottom", "w:right"):
            self.assertIn(kante, absatz)
        self.assertIn('w:color="D7D7D7"', absatz)

    # QT14 -------------------------------------------------------------------
    def test_qt14_die_quellenangabe_ist_wirklich_kursiv(self):
        """
        Bis Build 718 stand hier 'd.add_paragraph(...).italic = True'.
        'italic' ist keine Eigenschaft eines Absatzes, sondern eines Laufs;
        python-docx legt auf dem Absatz stillschweigend ein Attribut an, das
        niemand liest. GEMESSEN mit python-docx 1.2.0: das Attribut steht
        danach auf True, [r.italic for r in p.runs] aber auf [None].
        """
        xml = _docx_xml(_dokument(
            _zitatblock(QUOTE_TYP_LINIE, caption="Vernehmung vom 03.04.2026")))
        absatz = self._absatz_mit(xml, "Vernehmung vom 03.04.2026")
        self.assertIn("<w:i/>", absatz)


# =============================================================================
# PDF
# =============================================================================

class PdfQuoteTests(unittest.TestCase):

    # QT15 -------------------------------------------------------------------
    def test_qt15_alle_varianten_ergeben_ein_valides_pdf(self):
        """
        Ein PDF laesst sich nicht sinnvoll auf Aussehen pruefen, ohne es zu
        rastern. Geprueft wird deshalb das, was hier schiefgehen KANN: dass
        ein Stil mit Rahmen oder mittiger Ausrichtung reportlab nicht
        umwirft. PD01 in test_report_render.py prueft das Dokument als
        Ganzes; hier geht es um die drei Varianten einzeln UND zusammen.
        """
        from report_render.pdf_renderer import PdfRenderer
        for typ in list(QUOTE_TYPEN) + [_FEHLT]:
            with self.subTest(typ=typ):
                roh = PdfRenderer().render(_dokument(_zitatblock(typ)))
                self.assertTrue(roh.startswith(b"%PDF"))
                self.assertGreater(len(roh), 500)
        gemeinsam = PdfRenderer().render(_dokument(
            *[_zitatblock(t) for t in QUOTE_TYPEN]))
        self.assertTrue(gemeinsam.startswith(b"%PDF"))


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
