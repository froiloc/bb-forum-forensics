# =============================================================================
# tests/test_help_bedienelemente.py
# IT-Forensisches Ermittlungswerkzeug - Vorgang 17200856
# =============================================================================
# Testsuite ab Build 631: die Bedienelemente der Sichten und ihre Hilfe.
#
# DER VORGANG (mc, woertlich): "Die Sichten haben sehr viele Schaltflaechen
#   und Eingabezeilen, aber keine einzige wird erklaert. Meiner Meinung nach
#   ist das ein eklatanter Mangel. Wie soll der Anwender wissen, was er tun
#   soll, wenn es ihm nicht definiert und erklaert wird?"
#
# DIE ERHEBUNG GAB IHM RECHT, und sie bezifferte es: 170 Bedienelemente,
#   davon 34 erklaert, 136 OFFEN. Zwei Sichten waren vollstaendig
#   ('releases', 'handover'), 33 Dateien hatten eine Luecke.
#
# SEIT BUILD 637 IST DIE LISTE LEER: 170 von 170. Damit wechselt diese Suite
#   ihre Aufgabe - sie war eine Fehlliste, jetzt ist sie eine SPERRE (BD10).
#
# WARUM KEINE VORHANDENE PRUEFUNG DAS GEFUNDEN HAT - das ist der Kern des
#   Befundes und der Grund fuer diese Datei: Die Paritaetspruefungen
#   (SP01-SP08 in Python, UX11 in vitest) sagen "jede MARKE hat einen Text
#   und jeder TEXT hat eine Marke". Sie sagen NICHTS darueber, ob ein Knopf
#   ueberhaupt eine Marke bekommen hat. Ein Knopf ohne Marke kommt in ihrer
#   Welt nicht vor. Die Baustelle H hat die Vollzaehligkeit der TEXTE
#   hergestellt und dabei nie gefragt, ob die MENGE der markierten Elemente
#   die richtige ist.
#
# WAS DIESE SUITE TUT UND WAS NICHT: Sie schreibt die Lage fest und laesst
#   sie nur schrumpfen. Sie schreibt KEINE Hilfetexte - das ist die Arbeit,
#   die jetzt folgt, Sicht fuer Sicht. Eine Zahl, die gedeckelt ist, ist der
#   Anfang; sie ist nicht das Ergebnis.
#
# BD01 - die erhobene Lage ist nicht schlechter als der eingecheckte Stand
# BD02 - keine NEUE Datei mit Luecke (die haerteste Aussage: ein neuer Knopf
#        ohne Hilfe faellt ab jetzt sofort auf)
# BD03 - der Stand luegt nicht: die Summen passen zu den Einzelzahlen
# BD04 - GEGENPROBE: die Suche findet ein unmarkiertes Bedienelement
# BD05 - GEGENPROBE: sie erkennt beide Schreibweisen der Marke
# BD05c- GEGENPROBE (Build 632): auch eine UMGEBROCHENE Marke - die
#        zeilenweise Suche uebersah sie und zaehlte zu hoch
# BD05d- GEGENPROBE (Build 633): die FABRIKREGEL - ein zurueckgegebenes
#        Element wird beim Abnehmer markiert und gilt dann als erklaert
# BD05e- GEGENPROBE dazu: EINE unmarkierte Abnahmestelle genuegt, und das
#        Element bleibt offen. Sonst waere die Fabrikregel ein Schlupfloch
# BD05f- GEGENPROBE (Build 636): die HUELLENREGEL - gibt die Fabrik das
#        <label> statt der Eingabe zurueck, wird die Marke trotzdem gefunden
# BD05g- GEGENPROBE dazu: auch hier genuegt EINE unmarkierte Abnahmestelle
# BD05h- GEGENPROBE (Build 636): eine Abnahmestelle OHNE Variable kann keine
#        Marke tragen - sie darf nicht uebergangen werden
# BD06 - 'releases' und 'handover' sind vollstaendig und bleiben es
# BD07 - jede Ausnahme ist begruendet und gibt es wirklich (TE6)
# BD08 - der Stand nennt sein Verfahren UND seine Grenzen (TE4)
# BD10 - Build 637: die Fehlliste ist LEER und bleibt es. Kein Bedienelement
#        ohne Text - ohne Einschraenkung, ohne Ausnahmeliste
# BD03c- Build 684 (Vorgang e3b6c0d4): die GESAMTZAHL im Kopf des Standes ist
#        die gemessene. Bis dahin pruefte BD03 nur die innere Stimmigkeit und
#        BD03b nur die Fehlmenge - die Kennzahl selbst konnte beliebig weit
#        abweichen und tat es auch (170 eingecheckt, 175 gemessen).
# BD03d- GEGENPROBE dazu: die Erhebung zaehlt ein hinzugefuegtes Bedienelement
#        wirklich mit. Sonst waere BD03c gruen, weil nie etwas gezaehlt wird.
# BD09 - Build 634, DIE GEGENRICHTUNG: kein Bedienungs-TEXT ohne Marke. Was
#        heute noch ohne ist, steht namentlich im Stand und darf nur weniger
#        werden. SP02 nimmt den Bereich 'bedienung' aus - zu Unrecht, denn
#        diese Marken sind literal. Genau dort lagen sechs tote Texte.
#
# WAS DIESE SUITE NICHT KANN (TE4): Sie zaehlt am Quelltext. Die Zahl ist
#   eine UNTERGRENZE - sie kann zu niedrig sein, nie zu hoch. Die Grenzen im
#   Einzelnen stehen im Kopf von tests/_bedienelemente.py und im Feld
#   '_grenzen' des Standes. Am gerenderten Baum misst UX11, aber nur fuer die
#   acht Sichten seines REGISTERs.
#
# Version: v0.8.684 - Build: 684 - 2026-08-05
# =============================================================================

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._bedienelemente import BEDIENARTEN, erhebung, untersuche

WURZEL = Path(__file__).resolve().parent.parent
STATIC = WURZEL / "management" / "server" / "static"
STAND_PFAD = WURZEL / "tests" / "hilfe_bedienung_stand.json"


def _stand():
    return json.loads(STAND_PFAD.read_text(encoding="utf-8"))


def _lage():
    """Die HEUTIGE Lage, ohne die begruendeten Ausnahmen."""
    ausnahmen = set(_stand().get("_ausnahmen", {}))
    return {n: b for n, b in erhebung(STATIC).items() if n not in ausnahmen}


def _js(inhalt):
    """Eine Wegwerf-JS-Datei fuer die Gegenproben."""
    d = tempfile.mkdtemp()
    p = Path(d) / "cockpit_probe.js"
    p.write_text(inhalt, encoding="utf-8")
    return p


class BedienelementeTests(unittest.TestCase):

    # --- BD01 ---------------------------------------------------------------
    def test_bd01_die_lage_wird_nicht_schlechter(self):
        """
        Je Datei darf die Zahl der unerklaerten Bedienelemente nur SINKEN.

        Steigt sie, ist ein Bedienelement hinzugekommen, das niemand erklaert
        - oder eine Marke ist verlorengegangen. Beides ist ein Befund und
        kein Pflegevorgang.
        """
        stand = _stand()["offen_je_datei"]
        lage = {n: len(b.offen) for n, b in _lage().items() if b.offen}
        schlechter = []
        for datei, jetzt in sorted(lage.items()):
            frueher = stand.get(datei)
            if frueher is not None and jetzt > frueher:
                schlechter.append(
                    "%s: %d offen, eingecheckt waren %d"
                    % (datei, jetzt, frueher))
        self.assertEqual([], schlechter, "\n".join(schlechter))

    # --- BD02 ---------------------------------------------------------------
    def test_bd02_keine_neue_datei_mit_luecke(self):
        """
        DIE HAERTESTE AUSSAGE DIESER SUITE. Eine Datei, die im Stand nicht
        vorkommt, hatte keine Luecke. Taucht sie jetzt auf, ist genau das
        passiert, was der Vorgang beschreibt: ein Bedienelement ist gebaut
        und nicht erklaert worden.
        """
        stand = set(_stand()["offen_je_datei"])
        neu = sorted(n for n, b in _lage().items() if b.offen and n not in stand)
        self.assertEqual(
            [], neu,
            "Neue Sichtdateien mit unerklaerten Bedienelementen: %s. Wer ein "
            "Bedienelement baut, schreibt den Hilfetext dazu - die Regel "
            "steht in documents/rules-help.md unter 'Pflicht bei jeder "
            "Aenderung'." % ", ".join(neu))

    # --- BD03 ---------------------------------------------------------------
    def test_bd03_der_stand_luegt_nicht(self):
        """
        Die Zusammenfassung im Kopf des Standes muss zu den Einzelzahlen
        passen. Eine Kennzahl, die etwas anderes zaehlt als die Liste unter
        ihr, ist eine Falschauskunft - derselbe Befund wie in Build 602 bei
        der Lektoratsfassung.
        """
        stand = _stand()
        self.assertEqual(sum(stand["offen_je_datei"].values()),
                         stand["davon_offen"],
                         "Die Summe der Einzelzahlen passt nicht zu "
                         "'davon_offen'.")
        self.assertEqual(stand["bedienelemente_gesamt"],
                         stand["davon_erklaert"] + stand["davon_offen"])

    def test_bd03b_der_stand_passt_zur_wirklichkeit(self):
        """
        Und die Zahlen im Stand sind die, die die Erhebung heute liefert -
        oder besser. Sonst waere der Stand ein Wunschzettel.
        """
        lage = _lage()
        offen_jetzt = sum(len(b.offen) for b in lage.values())
        self.assertLessEqual(
            offen_jetzt, _stand()["davon_offen"],
            "Es sind mehr Bedienelemente offen als eingecheckt.")

    # --- BD03c --------------------------------------------------------------
    def test_bd03c_die_gesamtzahl_ist_die_gemessene(self):
        """
        BUILD 684, VORGANG e3b6c0d4 - DIE LUECKE ZWISCHEN BD03 UND BD03b.

        DER BEFUND, DER DAZU GEFUEHRT HAT: Der Stand fuehrte von Build 637 bis
        680 die Zahl 170. Gemessen wurden zuletzt 175. Die Differenz ist
        zwischen 638 und 677 entstanden; alle fuenf Zusaetze waren erklaert,
        die Fehlliste war und blieb leer. Aufgefallen ist es trotzdem nicht -
        und zwar aus einem benennbaren Grund:

          BD03  prueft nur die INNERE Stimmigkeit des Standes
                (gesamt == erklaert + offen). Eine Zahl, die zu allen anderen
                Zahlen im Kopf passt, kann trotzdem falsch sein.
          BD03b prueft nur, dass nicht MEHR offen ist als eingecheckt. Bei
                'offen == 0' ist das eine Aussage ueber nichts.
          BD01/BD02 bewachen die FEHLLISTE, nicht die Gesamtzahl.

        Die Sperre sass also auf 'offen' - und dort hat sie gehalten. Die
        Kennzahl im Kopf war trotzdem eine Falschauskunft, und genau diesen
        Befund soll BD03 fuer die Einzelzahlen verhindern.

        WARUM AUF GLEICHHEIT UND NICHT AUF EINE OBERGRENZE: Eine steigende
        Gesamtzahl ist NORMAL - es kommen Bedienelemente hinzu. Eine
        Obergrenze waere deshalb entweder wirkungslos oder ein Verbot, neue
        Bedienelemente zu bauen. Gleichheit erzwingt statt dessen das
        Richtige: wer eines baut, zieht den Stand mit. Das kostet eine Zeile
        und ist derselbe Handgriff, den BD01/BD02 fuer die Fehlliste schon
        verlangen.
        """
        lage = _lage()
        gemessen = sum(b.gesamt for b in lage.values())
        offen = sum(len(b.offen) for b in lage.values())
        stand = _stand()
        self.assertEqual(
            gemessen, stand["bedienelemente_gesamt"],
            "Die Erhebung findet %d Bedienelemente, der eingecheckte Stand "
            "fuehrt %d. Eine Kennzahl, die etwas anderes zaehlt als der "
            "Bestand, ist eine Falschauskunft - und sie faellt sonst erst "
            "auf, wenn jemand nachrechnet. Nachzutragen in "
            "tests/hilfe_bedienung_stand.json: 'bedienelemente_gesamt': %d, "
            "'davon_erklaert': %d, 'davon_offen': %d."
            % (gemessen, stand["bedienelemente_gesamt"],
               gemessen, gemessen - offen, offen))
        self.assertEqual(
            gemessen - offen, stand["davon_erklaert"],
            "Die Zahl der erklaerten Bedienelemente im Stand passt nicht zur "
            "Erhebung (gemessen %d, eingecheckt %d)."
            % (gemessen - offen, stand["davon_erklaert"]))

    def test_bd03d_gegenprobe_die_gesamtzahl_wird_wirklich_gezaehlt(self):
        """
        GEGENPROBE zu BD03c. Eine Pruefung, die nie anschlaegt, belegt nichts
        (TE5) - und BD03c ist gruen, solange niemand etwas baut. Hier wird
        deshalb ein Bedienelement HINZUGEFUEGT und nachgesehen, ob die
        Erhebung die Gesamtzahl mitzaehlt. Taete sie es nicht, waere BD03c
        eine Zusicherung ohne Deckung.
        """
        p = _js("(function () {\n"
                "    function zeichne(doc) {\n"
                "        var b = doc.createElement('button');\n"
                "        b.setAttribute('data-hilfe-id', 'probe.bedienung.x');\n"
                "        var i = doc.createElement('input');\n"
                "        i.setAttribute('data-hilfe-id', 'probe.bedienung.y');\n"
                "    }\n"
                "})();\n")
        befund = erhebung(p.parent)["cockpit_probe.js"]
        self.assertEqual(2, befund.gesamt)
        self.assertEqual([], list(befund.offen))

    # --- BD04 / BD05 --------------------------------------------------------
    def test_bd04_die_suche_findet_ein_unmarkiertes_bedienelement(self):
        """Eine Pruefung, die nie anschlaegt, belegt nichts (TE5)."""
        p = _js("(function () {\n"
                "    function zeichne(doc) {\n"
                "        var b = doc.createElement('button');\n"
                "        b.textContent = 'Tu was';\n"
                "        return b;\n"
                "    }\n"
                "})();\n")
        b = untersuche(p)
        self.assertEqual(1, b.gesamt)
        self.assertEqual(0, b.erklaert)
        self.assertEqual("button", b.elemente[0].art)

    def test_bd05_beide_schreibweisen_der_marke_werden_erkannt(self):
        """
        Der Bestand kennt zwei: setAttribute (161-mal) und hilfeAnker
        (14-mal). Wuerde die Suche nur die erste kennen, saehe die Lage
        schlechter aus, als sie ist - und eine Fehlliste, die zu schwarz
        malt, wird beim naechsten Mal nicht mehr geglaubt.
        """
        p = _js("(function () {\n"
                "    function zeichne(doc, tk) {\n"
                "        var a = doc.createElement('input');\n"
                "        a.setAttribute('data-hilfe-id', 'probe.bedienung.a');\n"
                "        var b = doc.createElement('select');\n"
                "        tk.hilfeAnker(b, 'probe.bedienung.b');\n"
                "        var c = doc.createElement('textarea');\n"
                "        return [a, b, c];\n"
                "    }\n"
                "})();\n")
        b = untersuche(p)
        self.assertEqual(3, b.gesamt)
        self.assertEqual(2, b.erklaert)
        self.assertEqual(("textarea",), tuple(e.art for e in b.offen))
        marken = sorted(e.marke for e in b.elemente if e.marke)
        self.assertEqual(["probe.bedienung.a", "probe.bedienung.b"], marken)

    def test_bd05c_eine_umgebrochene_marke_wird_erkannt(self):
        """
        BUILD 632, GEGENPROBE ZU EINER GEFUNDENEN LUECKE. Bis Build 631 suchte
        die Erhebung ZEILENWEISE. Eine Marke, die - voellig gewoehnlich - am
        Komma umgebrochen ist, blieb damit unsichtbar, und das Element galt
        als unerklaert.

        Das ist der gefaehrlichere Fehler von beiden: die Zahl waere zu HOCH
        gewesen. Eine Fehlliste, die zu schwarz malt, bringt Arbeit in Gang,
        die es nicht braucht - und beim naechsten Befund glaubt sie niemand
        mehr. Der Anlass war echt: die Marke der Bewertungs-Notiz in der
        Chef-Freigabe waere in einer Zeile 82 Zeichen breit.
        """
        p = _js("(function () {\n"
                "    function zeichne(doc) {\n"
                "        var note = doc.createElement('textarea');\n"
                "        note.setAttribute('data-hilfe-id',\n"
                "            'probe.bedienung.bewertungsvermerk');\n"
                "        return note;\n"
                "    }\n"
                "})();\n")
        b = untersuche(p)
        self.assertEqual(1, b.gesamt)
        self.assertEqual(
            1, b.erklaert,
            "Eine ueber zwei Zeilen umgebrochene Marke wurde nicht erkannt - "
            "die Erhebung meldete das Element faelschlich als offen.")
        self.assertEqual("probe.bedienung.bewertungsvermerk",
                         b.elemente[0].marke)

    _FABRIK = ("(function () {\n"
               "    function _feld(doc, cls) {\n"
               "        var sel = doc.createElement('select');\n"
               "        sel.className = cls;\n"
               "        return sel;\n"
               "    }\n"
               "    function zeichne(doc) {\n"
               "        var oben = _feld(doc, 'a');\n"
               "%s"
               "        var unten = _feld(doc, 'b');\n"
               "%s"
               "        return [oben, unten];\n"
               "    }\n"
               "})();\n")
    _M_OBEN = ("        oben.setAttribute('data-hilfe-id',\n"
               "            'probe.bedienung.oben');\n")
    _M_UNTEN = ("        unten.setAttribute('data-hilfe-id',\n"
                "            'probe.bedienung.unten');\n")

    def test_bd05d_die_fabrikregel_findet_die_marke_am_abnehmer(self):
        """
        BUILD 633, ZWEITE MESSKORREKTUR. Eine Fabrik gibt ihr Element
        ZURUECK; markiert wird es erst beim Abnehmer - und dort auch
        verschieden, weil zwei Aufrufer zwei verschiedene Bedienelemente
        meinen. Der echte Fall ist '_select' in cockpit_assignment.js
        (Ermittler und Prioritaet des Sammel-Steuerkopfs).

        Bis Build 632 galt so ein Element als unerklaert - wieder die
        alarmierende Richtung: die Zahl war zu hoch fuer Code, der alles
        richtig macht.
        """
        b = untersuche(_js(self._FABRIK % (self._M_OBEN, self._M_UNTEN)))
        self.assertEqual(1, b.gesamt)
        self.assertEqual(
            1, b.erklaert,
            "Die Marke am Abnehmer der Fabrik wurde nicht gefunden.")

    def test_bd05e_eine_unmarkierte_abnahmestelle_genuegt(self):
        """
        UND DIE REGEL BLEIBT STRENG. Markiert der eine Aufrufer und der
        andere nicht, dann gibt es eine stumme Schaltflaeche - und das
        Element bleibt offen. Ohne diesen Gegentest waere die Fabrikregel
        ein Schlupfloch: eine Marke irgendwo, und zehn Abnehmer gelten als
        erklaert.
        """
        b = untersuche(_js(self._FABRIK % (self._M_OBEN, "")))
        self.assertEqual(1, b.gesamt)
        self.assertEqual(
            0, b.erklaert,
            "Eine unmarkierte Abnahmestelle wurde uebersehen - die "
            "Fabrikregel waere damit ein Schlupfloch.")

    _HUELLE = ("(function () {\n"
               "    function _feld(doc, id, text) {\n"
               "        var wrap = doc.createElement('label');\n"
               "        var inp = doc.createElement('input');\n"
               "        inp.id = id;\n"
               "        wrap.appendChild(inp);\n"
               "        return wrap;\n"
               "    }\n"
               "    function zeichne(doc) {\n"
               "        var fa = _feld(doc, 'a', 'A');\n"
               "%s"
               "        var fb = _feld(doc, 'b', 'B');\n"
               "%s"
               "        return [fa, fb];\n"
               "    }\n"
               "})();\n")
    _H_A = ("        fa.eingabe.setAttribute('data-hilfe-id',\n"
            "            'probe.bedienung.a');\n")
    _H_B = ("        fb.eingabe.setAttribute('data-hilfe-id',\n"
            "            'probe.bedienung.b');\n")

    def test_bd05f_die_huellenregel(self):
        """
        BUILD 636, DRITTE MESSKORREKTUR. Der Bestand baut beschriftete Felder
        fast immer so: eine Funktion erzeugt <label>, Beschriftung und
        Eingabe, haengt die Eingabe in das Label und gibt DAS LABEL zurueck.
        Die Abnahmestelle haelt damit die Huelle in der Hand, nicht das
        Bedienelement - und setzt die Marke einen Schritt weiter innen.

        Die Fabrikregel aus Build 633 verlangte 'return <element>;' und griff
        deshalb hier nicht. Elf Felder allein in der Terminsicht galten so als
        unerklaert, obwohl jedes eine literale Marke traegt. Wieder die
        alarmierende Richtung.
        """
        b = untersuche(_js(self._HUELLE % (self._H_A, self._H_B)))
        self.assertEqual(1, b.gesamt)
        self.assertEqual(1, b.erklaert,
                         "Die Marke an der Huelle wurde nicht gefunden.")

    def test_bd05g_auch_die_huellenregel_bleibt_streng(self):
        """Eine unmarkierte Abnahmestelle genuegt - wie bei BD05e."""
        b = untersuche(_js(self._HUELLE % (self._H_A, "")))
        self.assertEqual(0, b.erklaert)

    def test_bd05h_eine_abnahmestelle_ohne_variable_zaehlt_nicht_als_erklaert(self):
        """
        DAS SCHLUPFLOCH, DAS DIE FABRIKREGEL SONST HAETTE. Reicht ein
        Aufrufer das Ergebnis DIREKT weiter ('leiste.appendChild(_knopf(...))'),
        kann er keine Marke setzen - das Bedienelement ist dort stumm. Die
        Regel darf ihn deshalb nicht einfach uebergehen, nur weil die
        uebrigen Abnahmestellen sauber sind.
        """
        p = _js("(function () {\n"
                "    function _knopf(doc, text) {\n"
                "        var b = doc.createElement('button');\n"
                "        b.textContent = text;\n"
                "        return b;\n"
                "    }\n"
                "    function zeichne(doc, leiste) {\n"
                "        var eins = _knopf(doc, 'eins');\n"
                "        eins.setAttribute('data-hilfe-id',\n"
                "            'probe.bedienung.eins');\n"
                "        leiste.appendChild(_knopf(doc, 'zwei'));\n"
                "        return eins;\n"
                "    }\n"
                "})();\n")
        b = untersuche(p)
        self.assertEqual(1, b.gesamt)
        self.assertEqual(
            0, b.erklaert,
            "Eine Abnahmestelle ohne Variable kann keine Marke tragen - das "
            "Element gilt trotzdem als erklaert. Das ist das Schlupfloch.")

    def test_bd05b_alle_vier_arten_werden_erfasst(self):
        p = _js("(function () {\n"
                "    function zeichne(doc) {\n"
                + "".join("        var v%d = doc.createElement('%s');\n"
                          % (i, art) for i, art in enumerate(BEDIENARTEN))
                + "        var egal = doc.createElement('div');\n"
                "    }\n"
                "})();\n")
        b = untersuche(p)
        self.assertEqual(len(BEDIENARTEN), b.gesamt)
        self.assertEqual(sorted(BEDIENARTEN),
                         sorted(e.art for e in b.elemente))

    # --- BD06 ---------------------------------------------------------------
    def test_bd06_die_vollstaendigen_sichten_bleiben_vollstaendig(self):
        """
        'releases' (neun Bedienelemente) und 'handover' (eines) erklaeren
        heute jedes einzelne. Sie sind das Vorbild fuer die uebrigen 33 -
        und ein Rueckschritt genau dort waere das schlechteste Zeichen.
        """
        lage = _lage()
        for datei in ("cockpit_releases.js", "cockpit_handover.js"):
            b = lage.get(datei)
            self.assertIsNotNone(b, "%s hat keine Bedienelemente mehr?" % datei)
            self.assertGreater(b.gesamt, 0, datei)
            self.assertEqual(
                [], [str(e) for e in b.offen],
                "%s war vollstaendig und ist es nicht mehr." % datei)

    # --- BD07 ---------------------------------------------------------------
    def test_bd07_jede_ausnahme_ist_begruendet_und_gibt_es_wirklich(self):
        """TE6: eine Ausnahmeliste wird gegen die Wirklichkeit geprueft."""
        for datei, grund in sorted(_stand().get("_ausnahmen", {}).items()):
            self.assertTrue((STATIC / datei).is_file(),
                            "%s: die Datei gibt es nicht mehr" % datei)
            self.assertGreater(
                len(grund.strip()), 80,
                "%s: eine Ausnahme braucht einen Grund, der traegt" % datei)
            b = untersuche(STATIC / datei)
            self.assertGreater(
                b.gesamt, 0,
                "%s hat gar keine Bedienelemente mehr - die Ausnahme ist "
                "ueberholt und gehoert weg." % datei)

    # --- BD08 ---------------------------------------------------------------
    def test_bd08_der_stand_nennt_verfahren_und_grenzen(self):
        """
        Ohne beides liest sich eine Zahl als Messung. Sie ist eine
        Untergrenze, und das muss dort stehen, wo die Zahl steht.
        """
        stand = _stand()
        for feld in ("_beschreibung", "_regel", "_verfahren", "_grenzen"):
            self.assertIn(feld, stand)
            self.assertGreater(len(stand[feld].strip()), 80, feld)
        self.assertIn("UNTERGRENZE", stand["_grenzen"].upper())
        self.assertIn("UX11", stand["_grenzen"])


    # --- BD09 ---------------------------------------------------------------
    def test_bd09_kein_bedienungstext_ohne_marke(self):
        """
        DAS GEGENSTUECK ZU BD02. Ein Knopf ohne Text ist der Befund des
        Vorgangs; ein TEXT OHNE KNOPF ist der stille Zwilling davon - er
        kostet Pflege, wird gegengelesen, steht in der Lektoratsfassung und
        erscheint nie.

        Warum das durchgerutscht ist: SP02 ('kein Text ins Leere') nimmt den
        Bereich 'bedienung' aus. Das war richtig, als die Liste der
        BERECHNETEN Bereiche entstand (spalte, werkzeug, kachel) - nur ist
        'bedienung' eben nicht berechnet, sondern literal. Die Ausnahme hat
        sechs tote Texte gedeckt.

        Die Liste im Stand ist gedeckelt und darf nur schrumpfen.
        """
        import re as _re
        LITERAL = _re.compile(
            r"""data-hilfe-id["']?\s*[=,]\s*["']([a-z0-9_.]+)["']""")
        marken = set()
        for pfad in list(STATIC.glob("cockpit*.js")) + [STATIC / "cockpit.html"]:
            if pfad.is_file():
                marken |= set(
                    LITERAL.findall(pfad.read_text(encoding="utf-8")))

        sys.path.insert(0, str(WURZEL))
        from management.help.inhalt import lade_register
        register = lade_register()
        erlaubt = dict(_stand().get("_texte_ohne_marke", {}))

        tot = sorted(
            k.schluessel for s in register.sichten for k in s.kontext
            if ".bedienung." in k.schluessel and k.schluessel not in marken)
        neu = [s for s in tot if s not in erlaubt]
        self.assertEqual(
            [], neu,
            "Popup-Texte fuer Bedienelemente, die es im Browser nicht gibt "
            "(toter Bestand): %s" % ", ".join(neu))

        # TE6: und die Ausnahmeliste wird gegen die Wirklichkeit geprueft -
        # ein Eintrag, der laengst erledigt ist, gehoert weg.
        veraltet = sorted(set(erlaubt) - set(tot))
        self.assertEqual(
            [], veraltet,
            "Diese Texte haben laengst eine Marke - die Eintraege in "
            "'_texte_ohne_marke' sind ueberholt: %s" % ", ".join(veraltet))
        for schluessel, grund in sorted(erlaubt.items()):
            self.assertGreater(
                len(grund.strip()), 8,
                "%s: eine Ausnahme braucht einen Grund" % schluessel)


    # --- BD10 ---------------------------------------------------------------
    def test_bd10_die_fehlliste_bleibt_leer(self):
        """
        BUILD 637 - DIE HAERTESTE FASSUNG VON BD01/BD02, moeglich geworden,
        weil die Liste leer IST. Solange sie Eintraege hatte, konnten die
        beiden Pruefungen nur verlangen, dass es nicht schlechter wird. Jetzt
        gilt der Satz ohne Einschraenkung: KEIN Bedienelement ohne Text.

        Wer diese Pruefung rot sieht, hat ein 'button', 'input', 'select'
        oder 'textarea' gebaut und den Hilfetext nicht dazugeschrieben. Die
        Regel steht in documents/rules-help.md unter 'Vollstaendigkeit'; die
        Meldung unten nennt Datei und Zeile.
        """
        offen = sorted(str(e) for b in _lage().values() for e in b.offen)
        self.assertEqual(
            [], offen,
            "Bedienelemente ohne Hilfetext:\n  " + "\n  ".join(offen))
        stand = _stand()
        self.assertEqual({}, stand["offen_je_datei"])
        self.assertEqual(0, stand["davon_offen"])
        self.assertEqual(stand["bedienelemente_gesamt"],
                         stand["davon_erklaert"])


if __name__ == "__main__":
    unittest.main()
