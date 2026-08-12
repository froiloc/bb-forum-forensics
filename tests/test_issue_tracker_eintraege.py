# =============================================================================
# tests/test_issue_tracker_eintraege.py
# IT-Forensisches Ermittlungswerkzeug -- Issue-Tracker
# =============================================================================
# Prueft die Eintragsdateien issue-tracker/eintraege_claude_Build*.json,
# BEVOR sie eingemischt werden (Build 668).
#
# WARUM AUF DER ERSTELLERSEITE: das Einmischen laeuft mit
# '--auto-resolve source', ersetzt einen vorhandenen Vorgang also vollstaendig
# durch den gelieferten. Das ist gewollt - der gelieferte Stand ist der neuere.
# Es hat aber eine Kehrseite: bringt die gelieferte Fassung die bereits
# vorhandenen Update-Eintraege NICHT mit, verschwinden sie beim Einmischen.
# Und zwar lautlos: merge.py meldet einen erfolgreichen Merge, und niemand
# sieht, dass eine Zeile Historie fehlt.
#
# Genau das war am 04.08.2026 der Fall: fuer 65a230fd und d3f933cd haette der
# Eintrag "Issue erstellt" (Alex, 2026-08-03) den Vorgang nicht ueberlebt.
# Aufgefallen ist es nur, weil vor dem Einmischen nachgelesen wurde, was die
# beiden Strategien wirklich tun.
#
# Der Tracker ist Teil der Projektdokumentation. Verlorene Historie ist dort
# dasselbe wie eine stille Auslassung im Befund (Grundregel 1).
#
# IT01 - jede Eintragsdatei ist gueltiges JSON mit der erwarteten Struktur.
# IT02 - jeder Vorgang traegt die Pflichtfelder des Schemas.
# IT02b - und HAELT DEREN GRENZEN EIN (Laenge, Aufzaehlung, Muster, Minimum).
#         BUILD 669, aus eigenem Schaden: IT02 prueft nur, OB ein Feld da ist.
#         Der Titel des Vorgangs f39ad572 war 85 Zeichen lang, das Schema
#         erlaubt 80 - IT02 war gruen, und merge.py wies die Datei auf der
#         Einspielseite ab. Ein Waechter, der nur die Anwesenheit prueft,
#         gibt eine Sicherheit vor, die er nicht hat.
# IT03 - WAECHTER: liegt ein Vorgang bereits in data/issues.json, enthaelt die
#        gelieferte Fassung ALLE dort vorhandenen Update-Zeitstempel.
# IT04 - keine doppelten Kennungen innerhalb einer Datei.
# IT05 - Zeitstempel der Updates sind aufsteigend sortiert.
# IT06 - BUILD 671 als Notbremse gebaut, BUILD 674 umgewidmet. Er fragte:
#        'kommt ein reiner Historien-Nachtrag ueberhaupt an?' - und musste
#        anschlagen, solange merge.py ihn zwischen 'neu' und 'Konflikt'
#        hindurchfallen liess. Seit der Behebung in Build 673 wuerde genau
#        diese Frage den Fall verbieten, der wieder funktioniert; am
#        05.08.2026 hat sie prompt die Lieferung blockiert, die die Behebung
#        mitbrachte. IT06 prueft jetzt statt dessen, dass der dritte Zweig
#        noch im Quelltext steht. Naeheres am Fall selbst.
#
# EINE LEHRE FUER DIE ERSTELLERSEITE, teuer bezahlt am 05.08.2026:
#        EINE EINTRAGSDATEI WIRD GEGEN DEN COMMITTETEN BESTAND GEBAUT, NIE
#        GEGEN EINEN SIMULIERTEN. Ich hatte die Datei zu Build 673 gegen einen
#        nachgestellten Bestand gebaut, in dem die noch offene Datei zu 672
#        bereits eingemischt war. Das Einmischwerkzeug schreibt beim Anlegen
#        eines neuen Vorgangs aber eine eigene Update-Zeile mit der Uhrzeit
#        DES LAUFS - und die kann keine Simulation treffen. IT03 meldete
#        daraufhin auf der Gegenseite zu Recht einen drohenden Verlust.
#        Folgerung: ein Vorgang, der erst durch eine noch nicht eingemischte
#        Datei entsteht, wird in derselben Lieferung NICHT mehr angefasst.
#
# ALTE FASSUNG VON IT06 - DIE ANDERE RICHTUNG VON IT03, BUILD 671:
#        IT03 bewacht, dass nichts VERLORENGEHT. Niemand bewachte, dass das
#        Nachgetragene ANKOMMT.
#        Am 05.08.2026 wurde eine Datei geliefert, die zu zwei vorhandenen
#        Vorgaengen je einen Update-Eintrag nachtrug und sonst nichts aenderte.
#        merge.py meldete "1 Datei(en) eingemischt", loeschte die Datei - und
#        die beiden Eintraege waren nicht im Bestand. Grund: detect_conflicts()
#        vergleicht nur die Felder in VERGLEICHSFELDER (merge.py, Z. 431/432);
#        'updates' steht bewusst nicht darunter. Unterscheiden sich zwei
#        Fassungen NUR in den Updates, ist der Vorgang weder neu noch
#        konfliktbehaftet - und faellt durch beide Zweige hindurch.
#        IT01-IT05 waren dabei alle gruen. Sie pruefen die Datei, nicht ihre
#        Wirkung.
#        IT06 schlaegt deshalb an, BEVOR geliefert wird: traegt eine Fassung
#        neue Updates, muss sie sich auch in einem verglichenen Feld
#        unterscheiden - sonst kommt sie nicht an.
#        DAS IST EIN WAECHTER, KEINE BEHEBUNG. Der Fehler sitzt in merge.py;
#        er ist als eigener Vorgang aufgenommen. Bis dahin verhindert IT06
#        wenigstens, dass eine Lieferung lautlos ins Leere geht.
#
# Version: v0.8.671 - Build: 671 - 2026-08-05
# =============================================================================

import json
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
TRACKER = WURZEL / "issue-tracker"
BESTAND = TRACKER / "data" / "issues.json"

# Die Felder, die merge.py beim Erkennen von Konflikten vergleicht.
# WORTGLEICHE ABSCHRIFT aus merge.py, detect_conflicts() ('comparable_fields').
# Nur eine Abweichung in EINEM dieser Felder bringt eine gelieferte Fassung
# ueberhaupt in den Zweig, der sie in den Bestand schreibt. Wird die Liste
# dort geaendert, gehoert sie hier nachgezogen - IT06 misst sonst am falschen
# Massstab.
VERGLEICHSFELDER = ("title", "description", "status", "priority", "severity",
                    "assigned_to", "target_version", "affected_version")


def _eintragsdateien():
    return sorted(TRACKER.glob("eintraege_claude_Build*.json"))


def _lade(pfad):
    with open(pfad, encoding="utf-8") as f:
        return json.load(f)


class EintraegeTests(unittest.TestCase):

    # IT01 -------------------------------------------------------------------
    def test_it01_dateien_sind_gueltiges_json(self):
        for pfad in _eintragsdateien():
            with self.subTest(datei=pfad.name):
                d = _lade(pfad)
                self.assertIn("issues", d)
                self.assertIsInstance(d["issues"], list)
                self.assertGreater(len(d["issues"]), 0,
                                   "Eine leere Eintragsdatei waere ein "
                                   "Versehen, kein Inhalt.")

    # IT02 -------------------------------------------------------------------
    def test_it02_pflichtfelder_des_schemas(self):
        schema = _lade(TRACKER / "issue-tracker.schema.json")
        pflicht = schema["properties"]["issues"]["items"]["required"]
        for pfad in _eintragsdateien():
            for e in _lade(pfad)["issues"]:
                with self.subTest(datei=pfad.name, id=e.get("id", "?")):
                    fehlend = [k for k in pflicht if k not in e]
                    self.assertEqual([], fehlend,
                                     "Fehlende Pflichtfelder: %s" % fehlend)

    # IT02b ------------------------------------------------------------------
    def test_it02b_grenzen_des_schemas_werden_eingehalten(self):
        """
        Prueft die EINSCHRAENKUNGEN des Schemas, nicht nur die Anwesenheit
        der Felder: maxLength, minLength, enum, pattern, minimum, maximum.

        Bewusst von Hand statt ueber eine Bibliothek: 'jsonschema' ist keine
        Abhaengigkeit dieses Projekts, und die Produktionsumgebung ist
        offline. Ein Waechter, der nur dort laeuft, wo man Pakete
        nachinstallieren kann, hilft genau dann nicht, wenn man ihn braucht.
        """
        import re
        schema = _lade(TRACKER / "issue-tracker.schema.json")
        felder = schema["properties"]["issues"]["items"]["properties"]
        verstoesse = []
        for pfad in _eintragsdateien():
            for e in _lade(pfad)["issues"]:
                kennung = "%s (%s)" % (e.get("id", "?")[:8], pfad.name)
                for name, regel in felder.items():
                    if name not in e or e[name] is None:
                        continue
                    wert = e[name]
                    if "maxLength" in regel and isinstance(wert, str) \
                            and len(wert) > regel["maxLength"]:
                        verstoesse.append(
                            "%s: %s ist %d Zeichen lang, erlaubt sind %d"
                            % (kennung, name, len(wert), regel["maxLength"]))
                    if "minLength" in regel and isinstance(wert, str) \
                            and len(wert) < regel["minLength"]:
                        verstoesse.append(
                            "%s: %s ist zu kurz (%d < %d)"
                            % (kennung, name, len(wert), regel["minLength"]))
                    if "enum" in regel and wert not in regel["enum"]:
                        verstoesse.append(
                            "%s: %s='%s' steht nicht in der Aufzaehlung %s"
                            % (kennung, name, wert, regel["enum"]))
                    if "pattern" in regel and isinstance(wert, str) \
                            and not re.match(regel["pattern"], wert):
                        verstoesse.append(
                            "%s: %s='%s' passt nicht auf %s"
                            % (kennung, name, wert, regel["pattern"]))
                    if "minimum" in regel and isinstance(wert, (int, float)) \
                            and wert < regel["minimum"]:
                        verstoesse.append(
                            "%s: %s=%s unterschreitet %s"
                            % (kennung, name, wert, regel["minimum"]))
                    if "maximum" in regel and isinstance(wert, (int, float)) \
                            and wert > regel["maximum"]:
                        verstoesse.append(
                            "%s: %s=%s ueberschreitet %s"
                            % (kennung, name, wert, regel["maximum"]))
        self.assertEqual(
            [], verstoesse,
            "Die Einspielseite wuerde diese Vorgaenge abweisen:\n  "
            + "\n  ".join(verstoesse))

    # IT07 -------------------------------------------------------------------
    def test_it07_historie_aus_noch_offenen_dateien_geht_nicht_verloren(self):
        """
        DIE LUECKE VON IT03, BUILD 673 - beim Bauen dieser Lieferung selbst
        aufgefallen.

        IT03 vergleicht die gelieferte Fassung mit dem BESTAND. Liegen aber
        mehrere Eintragsdateien nebeneinander und beruehren denselben Vorgang,
        wirken sie NACHEINANDER: die erste schreibt in den Bestand, die zweite
        ersetzt danach denselben Vorgang. Eine zweite Datei, die auf dem Stand
        VOR der ersten gebaut wurde, ist gegen den heutigen Bestand tadellos -
        und loescht beim Einmischen genau das, was die erste kurz zuvor
        eingetragen hat.

        Genau das waere am 05.08.2026 passiert: die Datei zu Build 673 wurde
        zuerst auf dem Bestand OHNE die noch nicht eingemischte Datei zu Build
        672 gebaut. IT01 bis IT06 waren gruen. Die zwei Update-Zeilen aus 672
        waeren beim Einmischen von 673 wieder verschwunden.

        Dieser Fall vergleicht deshalb jede Datei auch gegen die ANDEREN noch
        offenen Eintragsdateien.
        """
        dateien = _eintragsdateien()
        if len(dateien) < 2:
            self.skipTest("weniger als zwei offene Eintragsdateien")

        # Kennung -> {Zeitstempel} je Datei
        je_datei = {}
        for pfad in dateien:
            je_datei[pfad] = {
                e["id"]: {u.get("timestamp") for u in (e.get("updates") or [])}
                for e in _lade(pfad)["issues"]
            }

        verluste = []
        for pfad, vorgaenge in je_datei.items():
            for anderer, andere_vorgaenge in je_datei.items():
                if anderer == pfad or anderer.name >= pfad.name:
                    # Nur FRUEHERE Dateien betrachten: sie wirken zuerst.
                    # Die Reihenfolge ist die des Einmischskripts (sortiert).
                    continue
                for kennung, stempel in vorgaenge.items():
                    frueher = andere_vorgaenge.get(kennung)
                    if not frueher:
                        continue
                    fehlend = frueher - stempel
                    for t in sorted(fehlend):
                        verluste.append(
                            "%s: %s traegt die Zeile %s nicht mit, die %s "
                            "kurz zuvor eintraegt"
                            % (kennung[:8], pfad.name, t, anderer.name))

        self.assertEqual(
            [], verluste,
            "Die spaetere Datei wuerde die Eintraege der frueheren wieder "
            "entfernen - lautlos:\n  " + "\n  ".join(verluste)
            + "\n\nAbhilfe: die spaetere Fassung auf dem Stand NACH dem "
              "Einmischen der frueheren bauen.")

    # IT03 -------------------------------------------------------------------
    def test_it03_keine_historie_geht_beim_einmischen_verloren(self):
        """
        DER EIGENTLICHE WAECHTER.

        '--auto-resolve source' ersetzt den vorhandenen Vorgang vollstaendig.
        Was in der gelieferten Fassung nicht steht, ist danach weg - ohne
        Meldung. Dieser Fall prueft deshalb VOR dem Einmischen, dass jede
        gelieferte Fassung die schon vorhandene Historie mitbringt.
        """
        if not BESTAND.is_file():
            self.skipTest("data/issues.json nicht vorhanden")
        bestand = {i["id"]: i for i in _lade(BESTAND)["issues"]}
        verluste = []
        for pfad in _eintragsdateien():
            for e in _lade(pfad)["issues"]:
                alt = bestand.get(e["id"])
                if not alt:
                    continue                      # neuer Vorgang, nichts zu verlieren
                geliefert = {u.get("timestamp")
                             for u in (e.get("updates") or [])}
                for u in (alt.get("updates") or []):
                    if u.get("timestamp") not in geliefert:
                        verluste.append(
                            "%s (%s): Update %s von %s ginge verloren"
                            % (e["id"][:8], pfad.name, u.get("timestamp"),
                               u.get("author")))
        self.assertEqual(
            [], verluste,
            "Beim Einmischen mit --auto-resolve source wuerde Historie "
            "verschwinden, und zwar lautlos:\n  " + "\n  ".join(verluste))

    # IT04 -------------------------------------------------------------------
    def test_it04_keine_doppelten_kennungen(self):
        for pfad in _eintragsdateien():
            with self.subTest(datei=pfad.name):
                ids = [e["id"] for e in _lade(pfad)["issues"]]
                doppelt = [i for i in set(ids) if ids.count(i) > 1]
                self.assertEqual([], doppelt)

    # IT05 -------------------------------------------------------------------
    def test_it05_updates_sind_chronologisch(self):
        for pfad in _eintragsdateien():
            for e in _lade(pfad)["issues"]:
                stempel = [u.get("timestamp", "")
                           for u in (e.get("updates") or [])]
                with self.subTest(datei=pfad.name, id=e["id"][:8]):
                    # Eine Historie, die nicht in der Reihenfolge steht, in der
                    # sie entstanden ist, laedt zu Fehlschluessen ein.
                    self.assertEqual(sorted(stempel), stempel)

    # IT06 -------------------------------------------------------------------
    def test_it06_der_dritte_zweig_in_merge_py_ist_noch_da(self):
        """
        IT06 HAT SEINE AUFGABE GEWECHSELT - Build 674.

        BIS BUILD 673 fragte dieser Fall: 'kommt ein reiner Historien-Nachtrag
        ueberhaupt an?' Er musste anschlagen, weil merge.py fuer einen
        vorhandenen Vorgang nur zwei Wege kannte und ein Nachtrag zwischen
        ihnen hindurchfiel. Er war eine NOTBREMSE fuer einen unbehobenen
        Fehler, und er verlangte etwas Unschoenes: dass man ein Feld aendert,
        das man gar nicht aendern will, nur damit die Lieferung ankommt.

        SEIT BUILD 673 IST DER FEHLER BEHOBEN - der dritte Zweig
        (ConflictType.UPDATE_TIMELINE) nimmt den Nachtrag auf, und
        auto_resolve_conflict() fuehrt ihn ueber MERGE_UPDATES zusammen. Die
        alte Fassung von IT06 wuerde jetzt genau den Fall verbieten, der
        wieder funktioniert. Am 05.08.2026 hat sie bei Alex prompt die
        Lieferung 673 blockiert - und zwar die Lieferung, die die Behebung
        mitbrachte.

        WEGGELASSEN WIRD ER TROTZDEM NICHT. Ein Waechter, den man ersatzlos
        streicht, weil sein Fall behoben ist, laesst genau diese Behebung
        unbewacht. IT06 prueft deshalb ab jetzt die ANDERE Seite derselben
        Sache: dass der dritte Zweig noch im Quelltext steht. Wird er
        entfernt, faellt IT06 wieder - und der alte Verlustfall kommt nicht
        unbemerkt zurueck.

        Das VERHALTEN des Zweiges pruefen MN01 bis MN03 in
        tests/test_merge_nachtraege.py; dieser Fall prueft nur seine
        Anwesenheit, damit die Erstellerseite ihn auch dann bemerkt, wenn die
        Regression zum Tracker einmal nicht mitlaeuft.
        """
        quelle = (TRACKER / "merge.py").read_text(encoding="utf-8")
        self.assertIn(
            "ConflictType.UPDATE_TIMELINE", quelle,
            "Der dritte Zweig fehlt in merge.py. Damit faellt ein reiner "
            "Historien-Nachtrag wieder zwischen 'neu' und 'Konflikt' "
            "hindurch: nichts wird geschrieben, das Werkzeug meldet Erfolg, "
            "und merge-new-tickets.sh loescht die Quelldatei. Siehe Vorgang "
            "7d3c1a95.")
        self.assertIn(
            "ResolutionStrategy.MERGE_UPDATES", quelle,
            "Die Aufloesung des dritten Zweiges fehlt. Erkannt wuerde der "
            "Nachtrag dann zwar, aber nach der gewaehlten Strategie geloest - "
            "bei '--auto-resolve target' waere das erneut ein Verlust mit "
            "Erfolgsmeldung.")
        self.assertIn(
            "pruefe_einmischung.py",
            (TRACKER / "merge-new-tickets.sh").read_text(encoding="utf-8"),
            "Die Gegenprobe vor dem Loeschen fehlt im Einmischskript. Ohne "
            "sie kostet die naechste Luecke in merge.py wieder Daten statt "
            "nur einen Abbruch.")

    # IT08 -------------------------------------------------------------------
    def test_it08_keine_verlorenen_zeilenumbrueche_in_der_eingangsdatei(self):
        """
        BUILD 707 (Befund Alex, 12.08.2026): In seinem Regressionslauf fiel
        LN09 - im Bestand stand EIN verlorener Zeilenumbruch, also die zwei
        Zeichen Backslash+n als TEXT statt eines Umbruchs.

        DIE LUECKE, DIE DAS MOEGLICH GEMACHT HAT: Beide bestehenden Waechter
        greifen ZU SPAET oder ZU WEICH.
          - LN09 (tests/test_issue_tracker_umbruchreparatur.py) misst den
            BESTAND. Er schlaegt an, wenn der Fehler schon drin ist; dann ist
            die Eingangsdatei bereits eingemischt UND GELOESCHT
            (merge-new-tickets.sh), und die Quelle ist nur noch aus dem
            Bestand zu erschliessen.
          - merge.py WARNT seit Build 648 an genau dieser Stelle, bricht aber
            bewusst nicht ab (ein Windows-Pfad wie 'C:\\neu' traegt dieselbe
            Zeichenfolge zu Recht - die Begruendung steht dort und wird hier
            nicht angetastet). Eine Warnung in einer langen Ausgabe ist beim
            Einmischen mehrerer Dateien schnell fortgescrollt.

        NIEMAND PRUEFTE DIE EINGANGSDATEI, SOLANGE SIE NOCH DA IST - obwohl
        genau das der Ort ist, an dem der Fehler entsteht (beim Erzeugen) und
        an dem er ohne Datenverlust zu beheben waere. IT08 schliesst das:
        jede noch offene 'eintraege_claude_Build*.json' wird mit DERSELBEN
        Regel geprueft, die auch LN09 und die Reparatur benutzen - inklusive
        der Ausnahme fuer woertliche Erwaehnungen (ist_erwaehnung).

        WER UEBER DIE ZEICHENFOLGE SCHREIBT, schreibe sie in Worten
        ('Backslash+n') oder lasse ein Leerzeichen davor - so haelt es auch
        der Kopf von literal_newline_repair.py. Der erste Entwurf des
        Vorgangs, der diesen Fall veranlasst hat, fiel selbst durch IT08,
        weil er die Zeichenfolge in Anfuehrungszeichen zitierte. Das ist
        KEIN Fehler der Regel: sie unterscheidet 'klebt am Satz' von 'steht
        frei im Satz', und ein Zitat in Anfuehrungszeichen klebt.

        DIESER FALL HAELT DIE EIGENE LIEFERUNG SAUBER; er kann den bereits im
        Bestand liegenden Fund NICHT heilen. Dafuer gibt es das vorhandene
        Werkzeug:
            cd issue-tracker
            python repair_literal_newlines.py            # nur melden
            python repair_literal_newlines.py --apply    # beheben
        """
        import sys
        sys.path.insert(0, str(TRACKER))
        from literal_newline_repair import TEXTFELDER, LITERAL, ist_erwaehnung

        for pfad in _eintragsdateien():
            for e in _lade(pfad)["issues"]:
                texte = [(f, e.get(f)) for f in TEXTFELDER]
                texte += [(f"update[{n}].comment", u.get("comment"))
                          for n, u in enumerate(e.get("updates") or [])]
                for feld, text in texte:
                    if not isinstance(text, str):
                        continue
                    fundstellen = []
                    stelle = text.find(LITERAL)
                    while stelle != -1:
                        if not ist_erwaehnung(text, stelle):
                            fundstellen.append(stelle)
                        stelle = text.find(LITERAL, stelle + len(LITERAL))
                    with self.subTest(datei=pfad.name, id=e["id"][:8],
                                      feld=feld):
                        self.assertEqual(
                            [], fundstellen,
                            "In '%s' steht %d mal Backslash+n als TEXT. Beim "
                            "Erzeugen der Datei wurde '\\\\n' geschrieben, wo "
                            "'\\n' gemeint war. Im Bestand faellt das erst "
                            "LN09 auf - dann ist diese Datei schon geloescht. "
                            "Jetzt beheben: die Zeichenkette hier berichtigen "
                            "und die Datei neu erzeugen."
                            % (feld, len(fundstellen)))


if __name__ == "__main__":
    unittest.main()
