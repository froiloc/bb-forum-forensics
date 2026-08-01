# =============================================================================
# management/help/inhalt/shell.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H4)
# =============================================================================
# Zweck:
#   Kontexthilfe fuer die Bedienelemente der SHELL - also fuer das, was in
#   JEDER Sicht an derselben Stelle steht: Kopfzeile, Navigation,
#   Integritaets-Banner, Akten-Export, Hilfe-Knopf.
#
#   WARUM DIE SHELL EINEN EIGENEN BESTAND BRAUCHT (gesicherte Erkenntnis aus
#   dem Bau von H4): Die Kontexthilfe wird je Sicht geladen. Die Shell gehoert
#   aber zu KEINER Sicht - sie umgibt alle. Haengte man ihre Texte an eine
#   beliebige Sicht, waeren sie auf allen anderen Sichten unerreichbar; legte
#   man sie in jede Sicht, waeren es 43 Kopien desselben Satzes (und damit
#   43 Stellen, an denen er veralten kann). Deshalb: EIN Bestand, der jeder
#   Kontext-Antwort beigelegt wird.
#
#   RECHTELAGE: Die Shell ist fuer jede Person sichtbar, die das Werkzeug
#   ueberhaupt oeffnen kann - diese Texte unterliegen daher KEINER
#   Capability-Sperre. Das ist kein Loch in E1: E1 schuetzt die Kapitel der
#   SICHTEN. Ein Satz darueber, was der Hilfe-Knopf tut, verraet nichts, was
#   die Person nicht ohnehin vor sich sieht.
#
#   REGEL H-0 gilt unveraendert: kein Falldatum, kein Beispiel aus dem
#   Betrieb.
#
# Version: v0.8.636 - Build: 636 - 2026-08-01
# =============================================================================

from __future__ import annotations

from typing import Tuple

from management.help.modell import Kontexthilfe

#: Der reservierte Praefix fuer Shell-Schluessel. Er ist KEINE Sicht-ID und
#: darf auch nie eine werden - pruefung.verify_shell_kontext haelt das fest.
SHELL_PRAEFIX = "shell"

SHELL_KONTEXT: Tuple[Kontexthilfe, ...] = (
    Kontexthilfe(
        "shell.hilfeknopf",
        "Hilfemodus",
        "Schaltet die Oberfläche in den Hilfemodus: erklärte Elemente bleiben "
        "klar, alles übrige wird abgedunkelt, und ein Klick öffnet die "
        "Erklärung statt die Funktion. Derselbe Weg über Shift+F1. Der Modus "
        "endet mit Esc, erneutem Klick oder einem Sichtwechsel.",
    ),
    Kontexthilfe(
        "shell.navigation",
        "Bereichsnavigation",
        "Führt die Bereiche auf, für die Sie ein Recht besitzen — was Sie "
        "hier nicht sehen, ist Ihnen nicht zugeteilt und nicht etwa "
        "ausgefallen. Reihenfolge und Sichtbarkeit lassen sich unter "
        "„Ansicht anpassen“ für das eigene Konto einstellen.",
    ),
    Kontexthilfe(
        "shell.integritaet",
        "Integritätsanzeige",
        "Zeigt, ob das Protokollbuch lückenlos ist. „In Ordnung“ heißt: "
        "jeder Eintrag hängt nachweisbar an seinem Vorgänger und ist seit "
        "dem Schreiben unverändert. Eine "
        "Meldung hier ist ein Betriebsvorfall und gehört gemeldet, nicht "
        "weggeklickt.",
    ),
    Kontexthilfe(
        "shell.aktenexport",
        "Akten-Export",
        "Erzeugt aus der gerade geöffneten Sicht eine Aktenfassung mit "
        "Kopfzeile, Erzeugungsvermerk und Prüfsumme. Der Knopf erscheint nur "
        "bei Sichten, für die ein Export festgelegt ist, und exportiert genau "
        "das, was Sie sehen — einschließlich der gesetzten Filter.",
    ),
    # -----------------------------------------------------------------
    # Die vier Bedienelemente der Navigation (Build 636, Welle B4).
    # -----------------------------------------------------------------
    Kontexthilfe(
        "shell.bedienung.navsuche",
        "Sichtsuche",
        "Filtert die Bereichsliste nach Begriff oder Stichwort. Die Suche "
        "klappt eingeklappte Gruppen auf und zeigt auch Bereiche, die Sie "
        "sich ausgeblendet haben — solche sind gekennzeichnet. Was Ihnen "
        "nicht zugeteilt ist, findet auch die Suche nicht.",
    ),
    Kontexthilfe(
        "shell.bedienung.navgruppe",
        "Bereichsgruppe",
        "Klappt die Gruppe auf oder zu. Der Zustand bleibt für Ihr Konto "
        "erhalten. Eine zugeklappte Gruppe, in der der gerade geöffnete "
        "Bereich liegt, wird trotzdem aufgeklappt — sonst behauptete die "
        "Leiste stillschweigend, es gebe ihn nicht.",
    ),
    Kontexthilfe(
        "shell.bedienung.navsicht",
        "Bereich öffnen",
        "Wechselt in diesen Bereich. Nicht gespeicherte Eingaben in der "
        "aktuellen Ansicht gehen dabei verloren — das Werkzeug führt keinen "
        "Entwurf über einen Wechsel hinweg mit.",
    ),
    Kontexthilfe(
        "shell.bedienung.ausgeblendet",
        "Ausgeblendete Bereiche",
        "Nennt, wie viele Bereiche Sie sich ausgeblendet haben, und führt "
        "mit einem Klick dorthin, wo sich das rückgängig machen lässt. Die "
        "Zeile steht dauerhaft da: Ein ausgeblendeter Bereich darf nicht "
        "still verschwinden — er könnte etwas Übersehenes enthalten. "
        "Erreichbar bleiben ausgeblendete Bereiche über die Kommandopalette.",
    ),
    Kontexthilfe(
        "shell.bedienung.palette",
        "Kommandopalette",
        "Springt über den eingetippten Namen in einen Bereich — auch in "
        "einen, den Sie sich in der Navigation ausgeblendet haben. Zu "
        "erreichen mit Strg-K von jeder Ansicht aus. Was Ihnen nicht "
        "zugeteilt ist, erscheint auch hier nicht.",
    ),
    Kontexthilfe(
        "shell.bedienung.popup_schliessen",
        "Erklärung schließen",
        "Schließt dieses Erklärungsfenster. Der Hilfemodus bleibt dabei an; "
        "er endet mit Esc, mit einem erneuten Klick auf den Hilfeknopf oder "
        "mit einem Bereichswechsel.",
    ),
    Kontexthilfe(
        "shell.kennung",
        "Angemeldete Person",
        "Nennt das Windows-Konto, unter dem dieses Werkzeug läuft. Alle "
        "Schreibvorgänge werden auf diese Kennung protokolliert; ein Wechsel "
        "der Person ist nur über eine neue Windows-Anmeldung möglich.",
    ),
)
