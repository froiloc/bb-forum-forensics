# =============================================================================
# management/help/inhalt/identitaeten.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H13)
# =============================================================================
# Zweck:
#   Die Hilfetexte der Nav-Gruppe "Identitaeten": crossref, crossfindings,
#   alias, merge.
#
#   DIESE VIER SICHTEN TRAGEN DIE HEIKELSTEN AUSSAGEN DES GANZEN WERKZEUGS.
#   Sie behaupten nichts ueber Termine oder Mengen, sondern darueber, WER
#   jemand ist: "dieses Konto gehoert dieser Person", "diese beiden Konten
#   gehoeren derselben Person", "dieses Konto tritt auch unter jenem Namen
#   auf". Eine falsche Angabe hat hier keine Folgen fuer die Statistik - sie
#   hat Folgen fuer einen Menschen.
#
#   DESHALB SAGT JEDES KAPITEL IM ERSTEN ABSATZ, WAS DIE ANGABE IST UND WAS
#   SIE NICHT IST: eine belegte Annahme mit einer Konfidenzstufe - kein
#   Beweis. Die Konfidenz ist keine Verzierung, sondern der Kern: "Verdacht"
#   und "gesichert" stehen in derselben Spalte und sehen aehnlich aus, und
#   genau darin liegt die Verwechslungsgefahr.
#
#   ZWEI WEITERE DINGE, DIE DIE OBERFLAECHE BEREITS AUSDRUECKLICH SAGT und die
#   die Hilfe deshalb wiederholt:
#     1) GELOESCHT WIRD NIE. Widerruf und Trennung sind belegte Handlungen;
#        die Zeile bleibt stehen. Wer die "richtige" Loeschfunktion sucht,
#        sucht etwas, das es nicht geben darf.
#     2) EIN LEERBEFUND IST NICHT "GIBT ES NICHT". Die Namenssuche laeuft als
#        Kaskade ueber mehrere Quellen; wer in keiner davon steht, kann
#        trotzdem existieren.
#
# QUELLEN: cockpit_crossref.js, cockpit_crossfindings.js, cockpit_alias.js,
#   cockpit_merge.js, management/server/management_app.py (Rechte).
#
# REGEL H-0: kein Falldatum, keine echte Kennung.
# REGEL H-1: Anwendersprache.
#
# Version: v0.8.604 - Build: 604 - 2026-07-31
# =============================================================================

from __future__ import annotations

from typing import Tuple

from management.help.modell import Abschnitt, Kontexthilfe, Sichthilfe

_STAND = 604

#: Redaktionsstand der in Welle B2 (Build 634) nachredigierten Kapitel.
_STAND_B2 = 634

#: Die Zusicherung dieser Gruppe, wortgleich in allen vier Kapiteln.
_HYPOTHESE = (
    "Was hier steht, ist eine BELEGTE ANNAHME mit einer Konfidenzstufe — kein "
    "Beweis. Die Stufe gehört zur Aussage: „Verdacht“ und „gesichert“ stehen "
    "in derselben Spalte und sehen ähnlich aus."
)

#: Der zweite durchgehende Satz: nichts verschwindet.
_KEIN_LOESCHEN = (
    "GELÖSCHT WIRD NIE. Ein Widerruf und eine Trennung sind belegte "
    "Handlungen; die Zeile bleibt mit Zeitpunkt, Person und Grund stehen. Sie "
    "ist dann ein anderer Erkenntnisstand — kein Leerbefund."
)


# =============================================================================
# 1) crossref - "Kreuzbezug"
# =============================================================================

CROSSREF = Sichthilfe(
    sicht="crossref",
    titel="Kreuzbezug — identifizierte Personen",
    recht_klartext=(
        "Rechte: crossref.view zum Lesen, crossref.edit zum Pflegen. Der "
        "Katalog gilt fallübergreifend; er ist nicht auf die eigenen Fälle "
        "eingeschränkt."
    ),
    stand=_STAND_B2,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Der Kreuzbezug ist die Antwort auf die Frage, hinter der die "
                "ganze Ermittlung steht: Welcher Mensch steckt hinter diesem "
                "Forenkonto?",
                _HYPOTHESE,
                "Der Katalog ist fallübergreifend. Eine Zuordnung, die in "
                "einem Verfahren gewonnen wurde, steht damit auch dort zur "
                "Verfügung, wo dasselbe Konto später wieder auftaucht.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "crossref.view zum Lesen. Ohne crossref.edit fehlt das "
                "Erfassungsfeld, und in der letzten Spalte steht statt des "
                "Knopfes ein Gedankenstrich; die Sicht sagt das ausdrücklich.",
                "Die Angaben zur realen Person sind personenbezogene Daten. "
                "Sie werden nur denen gezeigt, die das Recht dafür haben.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter die Hinweiszeile. Mit Änderungsrecht "
                "folgt das Erfassungsfeld, sonst der Hinweis auf das fehlende "
                "Recht. Darunter die Zeile für Rückmeldungen und die Liste.",
                "DIE LISTE IST NACH BEWEISSTÄRKE GEORDNET — die stärkste "
                "Konfidenz zuerst. Das ist eine Aussage und keine "
                "Voreinstellung: Sie können jede Spalte umsortieren, aber die "
                "Grundordnung bedeutet etwas.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Zuordnung anlegen: Konto, reale Person, Konfidenz und die "
                "Fundgrundlage eintragen, dann speichern.",
                "Konfidenz reifen lassen: „Revidieren“ in der Zeile füllt das "
                "Feld mit dem vorhandenen Stand. Passen Sie Konfidenz und "
                "Grundlage an und speichern Sie erneut.",
                "Nach einer Person suchen: der Kopffilter der Spalte „reale "
                "Person“.",
                "Nach Beweisstärke arbeiten: nach der Spalte „Konfidenz“ "
                "sortieren — sie sortiert nach Stärke, nicht alphabetisch.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                _HYPOTHESE,
                "JE KONTO GIBT ES GENAU EINE ZUORDNUNG. Wer zu einem bereits "
                "erfassten Konto erneut speichert, ERSETZT den bisherigen "
                "Stand — das ist der Weg, eine Konfidenz reifen zu lassen, "
                "und keine zweite Meinung daneben.",
                "DIE FUNDGRUNDLAGE IST DER EIGENTLICHE WERT DER ZEILE. Ein "
                "Name ohne Grundlage ist im weiteren Verfahren nicht "
                "verwendbar: niemand kann prüfen, worauf er beruht.",
                "Die Sicht ist NICHT fallbezogen. Sie zeigt den ganzen "
                "Katalog, nicht den Stand eines einzelnen Verfahrens.",
                "Schlägt ein Speichern fehl, wurde NICHTS geschrieben, und "
                "die Liste zeigt den tatsächlichen Stand. Die Meldung sagt "
                "das ausdrücklich.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Aliasse — weitere Namen desselben Kontos.",
                "Identitäts-Gruppen — mehrere Konten derselben Person.",
                "Querfunde — Hinweise, die in einem anderen Verfahren "
                "entstanden sind.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "crossref.titel", "Kreuzbezug",
            "Der fallübergreifende Katalog: welches Forenkonto welcher realen "
            "Person zugeordnet ist — mit Konfidenzstufe.",
            verweis="crossref#zweck"),
        Kontexthilfe(
            "crossref.kennzeile", "Was hier festgehalten wird",
            "Weist darauf hin, dass jede Anlage und jede Änderung mit Person "
            "und Zeitpunkt festgehalten wird.",
            verweis="crossref#grenzen"),
        Kontexthilfe(
            "crossref.spalte.subject_id", "Spalte „subject_id“",
            "Der Ermittlungsschlüssel des Forenkontos. Er ist die Kennung, "
            "unter der dieses Konto im ganzen Werkzeug geführt wird."),
        Kontexthilfe(
            "crossref.spalte.real_identity", "Spalte „reale Person“",
            "Der Mensch, dem das Konto zugeordnet wird. Die Angabe ist eine "
            "belegte Annahme, kein Beweis.",
            verweis="crossref#grenzen"),
        Kontexthilfe(
            "crossref.spalte.konfidenz", "Spalte „Konfidenz“",
            "Die Beweisstärke: Verdacht, wahrscheinlich, gesichert. Die "
            "Spalte sortiert nach STÄRKE — alphabetisch stünde „gesichert“ "
            "ganz oben, und das wäre irreführend.",
            verweis="crossref#aufbau"),
        Kontexthilfe(
            "crossref.spalte.basis", "Spalte „Basis“",
            "Worauf die Zuordnung beruht. Ohne diese Angabe ist der Name im "
            "weiteren Verfahren nicht verwendbar.",
            verweis="crossref#grenzen"),
        Kontexthilfe(
            "crossref.spalte.geaendert", "Spalte „geändert“",
            "Wann der Stand zuletzt geändert wurde. Sortiert wird nach dem "
            "echten Zeitpunkt, nicht nach der Schreibweise des Datums."),
        Kontexthilfe(
            "crossref.spalte.aktion", "Aktionsspalte",
            "Trägt den Knopf zum Überarbeiten einer Zeile. Ohne "
            "Änderungsrecht steht hier ein Gedankenstrich.",
            verweis="crossref#rechte"),
        Kontexthilfe(
            "crossref.bedienung.speichern", "Zuordnung speichern",
            "Legt die Zuordnung an oder ersetzt die vorhandene desselben "
            "Kontos. Je Konto gibt es genau eine.",
            verweis="crossref#grenzen"),
        Kontexthilfe(
            "crossref.bedienung.revidieren", "Revidieren",
            "Füllt das Erfassungsfeld mit dem Stand dieser Zeile. Es wird "
            "dabei NICHTS gespeichert — erst das Speichern schreibt.",
            verweis="crossref#ablaeufe"),
        # Die vier Felder des Erfassungsblocks (Build 634, Welle B2).
        # 'crossref.bedienung.revidieren' und '.speichern' gab es schon;
        # 'revidieren' war allerdings an KEIN Element gebunden - der Text
        # stand seit Build 604 im Register und war nie erreichbar. Die Marke
        # sitzt jetzt am Zeilenknopf, der Schluessel blieb.
        Kontexthilfe(
            "crossref.bedienung.konto", "Konto (subject_id)",
            "Der Ermittlungsschlüssel des Forenkontos, um das es geht. Eine "
            "unvollständige Nummer wird abgewiesen und NICHT stillschweigend "
            "gekürzt gelesen — das wäre ein anderes Konto.",
            verweis="crossref#grenzen"),
        Kontexthilfe(
            "crossref.bedienung.person", "Reale Person",
            "Der Mensch, dem Sie das Konto zuordnen. Diese Angabe ist eine "
            "belegte Annahme und kein Beweis; sie ist personenbezogen und "
            "wird nur denen gezeigt, die das Recht dafür haben.",
            verweis="crossref#grenzen"),
        Kontexthilfe(
            "crossref.bedienung.konfidenz", "Konfidenz",
            "Wie stark die Zuordnung belegt ist: Verdacht, wahrscheinlich, "
            "gesichert. Setzen Sie hier lieber zu niedrig als zu hoch — eine "
            "Konfidenz lässt sich später anheben, eine falsche Sicherheit "
            "ist im Verfahren nur schwer wieder einzufangen.",
            verweis="crossref#ablaeufe"),
        Kontexthilfe(
            "crossref.bedienung.basis", "Basis (Fundgrundlage)",
            "Worauf die Zuordnung beruht. Das ist der eigentliche Wert des "
            "Eintrags: Ein Name ohne Grundlage ist im weiteren Verfahren "
            "nicht verwendbar, weil niemand prüfen kann, worauf er beruht.",
            verweis="crossref#grenzen"),
        Kontexthilfe(
            "crossref.bedienung.notiz", "Notiz",
            "Platz für eine Bemerkung zur Zuordnung — freiwillig. Sie ersetzt "
            "die Fundgrundlage nicht."),
        Kontexthilfe(
            "crossref.werkzeug.filter_entfernen", "Filter zurücksetzen",
            "Entfernt alle Spaltenfilter dieser Sicht auf einmal."),
        Kontexthilfe(
            "crossref.werkzeug.trefferzahl", "Trefferanzeige",
            "Nennt, wie viele Zeilen sichtbar sind; bei gesetztem Filter "
            "„sichtbar von gesamt“."),
    ),
)


# =============================================================================
# 2) crossfindings - "Querfunde"
# =============================================================================

CROSSFINDINGS = Sichthilfe(
    sicht="crossfindings",
    titel="Querfunde — fallübergreifende Funde",
    recht_klartext=(
        "Rechte: crossref.view zum Lesen, crossref.edit zum Bewerten. Ohne "
        "das Bewertungsrecht zeigt die Sicht den Stand, bietet aber keine "
        "Aktion an."
    ),
    stand=_STAND_B2,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Ein Querfund ist ein Fund über ein ANDERES Konto, der bei "
                "der Arbeit an einem Fall nebenbei entstanden ist. Er gehört "
                "der Kollegin, die das andere Konto bearbeitet — sie muss "
                "davon erfahren.",
                "ZWEI DINGE WERDEN HIER AUSEINANDERGEHALTEN, und sie zu "
                "verwechseln ist der Fehler, den diese Sicht verhindern soll. "
                "Der TRANSPORT ist die Technik: Wurde der Fund in die andere "
                "Fallakte kopiert? Das erledigt sich von selbst. Der "
                "RÜCKKANAL ist die Arbeit: Hat ein MENSCH den Fund gesehen "
                "und entschieden, was daraus wird? Das erledigt sich nicht "
                "von selbst.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "crossref.view zum Lesen. Das Bewerten — also das Setzen des "
                "Rückkanal-Standes — braucht crossref.edit. Ohne dieses Recht "
                "steht in der Aktionsspalte ein Gedankenstrich.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, Hinweiszeile, dann die Bedienleiste mit zwei "
                "Filtern und dem Knopf zum Aktualisieren.",
                "Darunter bis zu zwei Zahlenzeilen: eine für den Transport, "
                "eine für den Rückkanal. Die zweite erscheint nur, wenn die "
                "Angaben vorliegen — eine Zeile aus Nullen wäre eine "
                "erfundene Auskunft.",
                "Dann die Liste mit sieben Spalten: Konto, Quell-Ermittler, "
                "Transport, Rückkanal, angelegt, integriert und die Aktionen.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Arbeitsvorrat finden: den Filter „nur unquittierte“ setzen. "
                "Das sind die Funde, die noch niemand gesehen hat.",
                "Bewerten: „Bewerten“ in der Zeile, den neuen Stand wählen "
                "und „Entscheidung belegen“.",
                "Verwertet: die Pflichtangabe nennt, WO die Erkenntnis "
                "eingeflossen ist. Nicht relevant: sie nennt, WARUM der Fund "
                "nicht trägt.",
                "Aktualisieren: der Knopf holt den Stand neu. Diese Sicht "
                "aktualisiert sich NICHT von selbst.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "„INTEGRIERT“ HEISST NUR, DASS DER FUND KOPIERT WURDE. Es "
                "heißt NICHT, dass ihn jemand gelesen hat. Ob ein Mensch ihn "
                "gesehen und was er daraus gemacht hat, steht ausschließlich "
                "in der Spalte „Rückkanal“.",
                "EIN FEHLER IST KEIN LEERBEFUND. Lässt sich die Übersicht "
                "nicht abrufen, sagt die Sicht das ausdrücklich — sie zeigt "
                "dann KEINE leere Liste, die wie „keine Querfunde“ aussähe.",
                "DIE MÖGLICHEN FOLGESTÄNDE GIBT DAS WERKZEUG VOR. Angeboten "
                "wird nur, was von hier aus zulässig ist; steht nichts zur "
                "Auswahl, ist der Fund abgeschlossen. Ein geratener Übergang "
                "wäre schlimmer als gar keiner.",
                "Die Erfassung und der Transport laufen selbsttätig. Diese "
                "Sicht legt keinen Querfund an und löscht keinen.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Kreuzbezug — wem das andere Konto zugeordnet ist.",
                "Identitäts-Gruppen — ob beide Konten derselben Person "
                "gehören.",
                "Ermittlungsergebnis — wo die Erkenntnis am Ende landet.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "crossfindings.titel", "Querfunde",
            "Funde über ein anderes Konto, die bei der Arbeit an einem Fall "
            "entstanden sind. Erfassung und Weitergabe laufen selbsttätig.",
            verweis="crossfindings#zweck"),
        Kontexthilfe(
            "crossfindings.kennzeile", "Was diese Sicht tut",
            "Weist darauf hin, dass hier nichts erfasst wird: die Sicht zeigt "
            "die Funde und nimmt Ihre Bewertung entgegen.",
            verweis="crossfindings#grenzen"),
        Kontexthilfe(
            "crossfindings.zahlen_transport", "Zahlen zum Transport",
            "Wie viele Funde noch nicht in die andere Fallakte kopiert sind, "
            "wie viele schon. Das erledigt sich von selbst.",
            verweis="crossfindings#zweck"),
        Kontexthilfe(
            "crossfindings.zahlen_rueckkanal", "Zahlen zum Rückkanal",
            "Wie viele Funde noch niemand zur Kenntnis genommen hat. DAS ist "
            "die Arbeit — sie erledigt sich nicht von selbst.",
            verweis="crossfindings#zweck"),
        Kontexthilfe(
            "crossfindings.bedienung.nur_offen", "Nur offene (Transport)",
            "Zeigt die Funde, die das Werkzeug noch nicht in die andere "
            "Fallakte kopiert hat. Das löst sich von selbst.",
            verweis="crossfindings#zweck"),
        Kontexthilfe(
            "crossfindings.bedienung.nur_unquittiert",
            "Nur unquittierte (Rückkanal)",
            "Zeigt die Funde, die noch kein Mensch bestätigt hat. Das ist der "
            "eigentliche Arbeitsvorrat dieser Sicht.",
            verweis="crossfindings#ablaeufe"),
        Kontexthilfe(
            "crossfindings.bedienung.aktualisieren", "Aktualisieren",
            "Holt den Stand neu. Diese Sicht aktualisiert sich nicht von "
            "selbst — die Funde entstehen auf einem anderen Weg als die "
            "übrigen Ereignisse.",
            verweis="crossfindings#grenzen"),
        Kontexthilfe(
            "crossfindings.bedienung.bewerten", "Bewerten",
            "Öffnet die Auswahl des nächsten Standes. Angeboten wird nur, was "
            "von hier aus zulässig ist.",
            verweis="crossfindings#grenzen"),
        Kontexthilfe(
            "crossfindings.bedienung.entscheidung_belegen",
            "Entscheidung belegen",
            "Schreibt den gewählten Stand fest. Verlangt der Stand eine "
            "Angabe, wird ohne sie nichts geschrieben.",
            verweis="crossfindings#ablaeufe"),
        # Die beiden Felder der Bewertung (Build 634, Welle B2).
        Kontexthilfe(
            "crossfindings.bedienung.folgezustand", "Nächster Stand",
            "Der Stand, auf den Sie diesen Fund setzen. Angeboten wird NUR, "
            "was vom heutigen Stand aus zulässig ist — eine kurze Liste ist "
            "hier kein Mangel, sondern die Auskunft, dass es nicht mehr "
            "Wege gibt.",
            verweis="crossfindings#grenzen"),
        Kontexthilfe(
            "crossfindings.bedienung.begruendung", "Angabe zum Stand",
            "Manche Stände verlangen eine Angabe — je nach Stand eine "
            "Grundlage oder einen Grund; die Beschriftung sagt, was gemeint "
            "ist. Das Feld erscheint nur dann, und ohne die Angabe wird "
            "nichts geschrieben.",
            verweis="crossfindings#ablaeufe"),
    ),
)


# =============================================================================
# 3) alias - "Aliasse"
# =============================================================================

ALIAS = Sichthilfe(
    sicht="alias",
    titel="Aliasse — globaler Namenskatalog",
    recht_klartext=(
        "Rechte: crossref.view zum Lesen, crossref.edit zum Pflegen. Der "
        "Katalog gilt fallübergreifend."
    ),
    stand=_STAND_B2,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Der Katalog hält fest, unter welchen weiteren Namen ein "
                "Forenkonto auftritt: ein zweiter Forenname, ein Spitzname "
                "aus einer Unterhaltung, ein Name aus einer Signatur, eine "
                "Kontaktkennung.",
                "Aliasse bestehen UNABHÄNGIG von der Identifizierung. Ein "
                "Konto kann fünf Namen führen und trotzdem keiner realen "
                "Person zugeordnet sein — und umgekehrt.",
                _HYPOTHESE,
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "crossref.view zum Lesen. Ohne crossref.edit fehlen das "
                "Erfassungsfeld und die Knöpfe in den Zeilen.",
                "Die Namen und ihre Grundlagen sind Freitext, der eine reale "
                "Person erkennbar machen kann. Sie werden nur denen gezeigt, "
                "die das Recht dafür haben.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, Hinweiszeile, dann die Zählzeile: wie viele "
                "Einträge aktiv und wie viele widerrufen sind und wie viele "
                "Konten betroffen sind.",
                "Darunter die Suche, gegebenenfalls das Ergebnis der "
                "Namensauflösung, dann das Erfassungsfeld und die Liste.",
                "GROSS- UND KLEINSCHREIBUNG SPIELT BEIM ABGLEICH KEINE "
                "ROLLE. Widerrufene Einträge werden gedämpft dargestellt.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Nach einem Namen suchen: den Namen in die Suche eintragen. "
                "Gesucht wird zuerst in der Fallakte, dann in der "
                "Namensliste der Forenkonten.",
                "Das Konto zu einem Namen finden: im Erfassungsfeld „Konto "
                "über den Namen suchen“ — für alle, die die Nummern nicht im "
                "Kopf haben. Die Übernahme eines Treffers schreibt NICHTS.",
                "Alias erfassen: Konto, Name, Art und Fundgrundlage "
                "eintragen.",
                "Art, Grundlage oder Notiz berichtigen: „Ändern“ in der "
                "Zeile. Der NAME selbst ist nicht änderbar — ein anderer Name "
                "ist eine andere Erkenntnis.",
                "Einen Eintrag zurücknehmen: „Widerrufen“, mit Grund. "
                "„Zurücknehmen“ macht den Widerruf rückgängig.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                _KEIN_LOESCHEN,
                "EIN LEERBEFUND HEISST „IN DEN ABGEFRAGTEN QUELLEN NICHT "
                "GEFUNDEN“ — nicht „gibt es nicht“. Ein Name, zu dem es kein "
                "Forenkonto gibt, steht in keiner dieser Quellen.",
                "DIE SUCHE ENDET BEI DER ERSTEN QUELLE MIT TREFFERN. Gibt es "
                "in der zweiten Quelle weitere, sagt die Sicht die Zahl "
                "ausdrücklich an — eine schweigende Suche sähe aus wie ein "
                "vollständiges Ergebnis, und der gesuchte Zweitzugang wäre "
                "genau der verschwiegene Treffer.",
                "DER KATALOG KENNT NUR NAMEN, DIE JEMAND ALS ALIAS ERFASST "
                "HAT. Wer nach einem Namen als solchem sucht, meint meist die "
                "Namensauflösung darüber und nicht diese Liste.",
                "EINE UNVOLLSTÄNDIGE KONTONUMMER WIRD NICHT ERGÄNZT. Eine "
                "Eingabe wie „47xy“ wird abgewiesen und nicht stillschweigend "
                "als 47 gelesen — das wäre ein falsches Konto.",
                "Ein Ladefehler ist kein Leerbefund; er bekommt eine eigene "
                "Anzeige.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Kreuzbezug — wem das Konto zugeordnet ist.",
                "Identitäts-Gruppen — welche Konten zusammengehören.",
                "Volltextsuche — wo ein Name im Bestand vorkommt.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "alias.titel", "Aliasse",
            "Der fallübergreifende Katalog weiterer Namen eines Forenkontos. "
            "Er besteht unabhängig davon, ob das Konto einer Person "
            "zugeordnet ist.",
            verweis="alias#zweck"),
        Kontexthilfe(
            "alias.kennzeile", "Was hier festgehalten wird",
            "Weist auf dreierlei hin: Groß- und Kleinschreibung spielt keine "
            "Rolle, jede Handlung wird festgehalten, und gelöscht wird nie.",
            verweis="alias#grenzen"),
        Kontexthilfe(
            "alias.zahlen", "Umfang des Katalogs",
            "Wie viele Einträge aktiv und wie viele widerrufen sind und wie "
            "viele Konten davon betroffen sind."),
        Kontexthilfe(
            "alias.bedienung.suche", "Suche im Katalog",
            "Sucht nach einem Namen oder einer Kontonummer. Gesucht wird nur "
            "in den ERFASSTEN Aliassen.",
            verweis="alias#grenzen"),
        Kontexthilfe(
            "alias.bedienung.ganzer_katalog", "Ganzer Katalog",
            "Hebt die Suche auf und zeigt wieder alle Einträge."),
        Kontexthilfe(
            "alias.bedienung.widerrufene", "Widerrufene zeigen",
            "Blendet die zurückgenommenen Einträge ein. Sie sind gedämpft "
            "dargestellt und tragen ihren Grund.",
            verweis="alias#grenzen"),
        Kontexthilfe(
            "alias.abschnitt.namensaufloesung", "Namensauflösung",
            "Zeigt, in welcher Quelle der gesuchte Name gefunden wurde — und "
            "ob es in einer weiteren Quelle noch Treffer gibt, die hier nicht "
            "stehen.",
            verweis="alias#grenzen"),
        Kontexthilfe(
            "alias.aufloesung", "Name zum eingetragenen Konto",
            "Nennt den Namen des eingetragenen Kontos samt Quelle — die "
            "Sicherung dagegen, versehentlich das falsche Konto zu erfassen. "
            "„Nicht gefunden“ heißt: in den abgefragten Quellen.",
            verweis="alias#grenzen"),
        Kontexthilfe(
            "alias.bedienung.kontosuche", "Konto über den Namen suchen",
            "Sucht das Forenkonto zu einem Namen, damit Sie die Nummer nicht "
            "kennen müssen. Die Übernahme eines Treffers schreibt nichts.",
            verweis="alias#ablaeufe"),
        Kontexthilfe(
            "alias.bedienung.art", "Art des Alias",
            "Woher der Name stammt: weiterer Forenname, Spitzname außerhalb "
            "des Forums, Name aus einer Signatur, Kontaktkennung oder "
            "Sonstiges."),
        Kontexthilfe(
            "alias.bedienung.erfassen", "Alias erfassen",
            "Legt den Eintrag an. Der Name selbst lässt sich später nicht "
            "ändern — ein anderer Name ist eine andere Erkenntnis.",
            verweis="alias#ablaeufe"),
        Kontexthilfe(
            "alias.bedienung.aendern", "Ändern",
            "Öffnet Art, Grundlage und Notiz zur Berichtigung. Der Name "
            "bleibt unverändert.",
            verweis="alias#ablaeufe"),
        Kontexthilfe(
            "alias.bedienung.widerrufen", "Widerrufen",
            "Nimmt den Eintrag zurück. Der Grund ist Pflicht: ein stilles "
            "Aussortieren ohne Begründung ist genau das, was dieses Werkzeug "
            "verhindern soll.",
            verweis="alias#grenzen"),
        Kontexthilfe(
            "alias.bedienung.zuruecknehmen", "Zurücknehmen",
            "Macht den Widerruf rückgängig; der Eintrag gilt wieder."),

        # ------------------------------------------------------------------
        # Die restlichen Bedienelemente (Build 634, Welle B2). Neun von
        # neunzehn waren schon erklaert - diese Sicht war das Vorbild und
        # trotzdem nicht fertig. Die Eingabezeilen stammen alle aus der
        # Fabrik '_field'; ihre Marken sitzen an den Abnahmestellen.
        # ------------------------------------------------------------------
        Kontexthilfe(
            "alias.bedienung.suchen", "Suchen",
            "Führt die Suche im Katalog aus. Ein Leerbefund heißt „in den "
            "abgefragten Quellen nicht gefunden“ — nicht „gibt es nicht“.",
            verweis="alias#grenzen"),
        Kontexthilfe(
            "alias.bedienung.treffer", "Treffer der Namensauflösung",
            "Ein gefundenes Konto. Der Klick sucht den Katalog nach GENAU "
            "diesem Konto ab — die Brücke vom Namen zum Konto. Geschrieben "
            "wird dabei nichts.",
            verweis="alias#ablaeufe"),
        Kontexthilfe(
            "alias.bedienung.treffer_uebernehmen", "Treffer übernehmen",
            "Setzt die Nummer dieses Kontos in das Erfassungsfeld darüber. "
            "Das ist der Weg für alle, die die Nummern nicht im Kopf haben. "
            "Die Übernahme schreibt NICHTS.",
            verweis="alias#ablaeufe"),
        Kontexthilfe(
            "alias.bedienung.konto", "Konto (subject_id)",
            "Der Ermittlungsschlüssel des Forenkontos, zu dem der Alias "
            "gehört. Darunter erscheint zur Kontrolle der Name des "
            "eingetragenen Kontos — sehen Sie hin, bevor Sie einen Beleg "
            "erzeugen.",
            verweis="alias#grenzen"),
        Kontexthilfe(
            "alias.bedienung.namenssuche", "Name des gesuchten Kontos",
            "Der Name, zu dem Sie das Konto suchen. Die Eingabetaste löst die "
            "Suche ebenso aus wie der Knopf daneben.",
            verweis="alias#ablaeufe"),
        Kontexthilfe(
            "alias.bedienung.aliastext", "Alias / Name",
            "Der weitere Name selbst. ER IST SPÄTER NICHT MEHR ÄNDERBAR: ein "
            "anderer Name ist eine andere Erkenntnis und entsteht durch "
            "Widerruf und Neuanlage. Lesen Sie ihn vor dem Erfassen noch "
            "einmal.",
            verweis="alias#grenzen"),
        Kontexthilfe(
            "alias.bedienung.basis", "Basis (Fundgrundlage)",
            "Wo Sie diesen Namen gefunden haben. Ohne Grundlage ist ein Name "
            "im weiteren Verfahren nicht verwendbar, weil niemand prüfen "
            "kann, worauf er beruht.",
            verweis="alias#grenzen"),
        Kontexthilfe(
            "alias.bedienung.notiz", "Notiz",
            "Platz für eine Bemerkung zum Eintrag — freiwillig. Sie ersetzt "
            "die Fundgrundlage nicht."),
        Kontexthilfe(
            "alias.bedienung.edit_art", "Art (Berichtigung)",
            "Ändert die Art des vorhandenen Eintrags. Der Name bleibt, wie er "
            "ist.",
            verweis="alias#ablaeufe"),
        Kontexthilfe(
            "alias.bedienung.edit_basis", "Basis (Berichtigung)",
            "Ändert die Fundgrundlage des vorhandenen Eintrags — etwa, wenn "
            "sich die Quelle genauer benennen lässt."),
        Kontexthilfe(
            "alias.bedienung.edit_notiz", "Notiz (Berichtigung)",
            "Ändert die Bemerkung zum vorhandenen Eintrag."),
        Kontexthilfe(
            "alias.bedienung.edit_speichern", "Speichern",
            "Schreibt die Berichtigung von Art, Grundlage und Notiz. Der Name "
            "des Eintrags bleibt unverändert; auch die Berichtigung wird "
            "festgehalten.",
            verweis="alias#ablaeufe"),
        Kontexthilfe(
            "alias.bedienung.widerrufsgrund", "Grund des Widerrufs",
            "PFLICHTANGABE. Ohne Grund wird nicht widerrufen — ein stilles "
            "Aussortieren ist genau das, was dieses Werkzeug verhindern soll.",
            verweis="alias#grenzen"),
        Kontexthilfe(
            "alias.bedienung.widerruf_belegen", "Widerruf belegen",
            "Führt den Widerruf aus. Der Eintrag verschwindet nicht, sondern "
            "wird gedämpft dargestellt und trägt seinen Grund. „Zurücknehmen“ "
            "macht ihn später wieder gültig.",
            verweis="alias#grenzen"),
    ),
)


# =============================================================================
# 4) merge - "Identitaets-Gruppen"
# =============================================================================

MERGE = Sichthilfe(
    sicht="merge",
    titel="Identitäts-Gruppen — Zusammenführen und Trennen",
    recht_klartext=(
        "Rechte: crossref.view zum Lesen, crossref.edit zum Zusammenführen "
        "und Trennen. Die Gruppen gelten fallübergreifend."
    ),
    stand=_STAND_B2,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Die Sicht hält die Aussage fest: „Konto A und Konto B werden "
                "von derselben Person betrieben.“",
                _HYPOTHESE,
                "SIE SAGT NICHT, WER DIESE PERSON IST. Der häufige Fall ist "
                "gerade der: Wir wissen, dass es dieselbe Person ist, aber "
                "noch nicht, wer. Wer die Person kennt, trägt sie im "
                "Kreuzbezug ein — das ist eine andere Angabe.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "crossref.view zum Lesen. Zusammenführen, Überarbeiten, "
                "Trennen und die Rücknahme einer Trennung brauchen "
                "crossref.edit; ohne dieses Recht fehlen Formular und "
                "Zeilenknöpfe.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, Hinweiszeile, Zählzeile. Darunter die Suche "
                "nach der Gruppe eines Kontos, dann das Formular und die "
                "Liste.",
                "Jede Gruppe hat ein FÜHRENDES Konto; die übrigen sind ihm "
                "zugeordnet. Ketten sind nicht vorgesehen: ein zugeordnetes "
                "Konto kann nicht selbst führend sein, weil die Auflösung "
                "sonst mehrdeutig wäre.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Gruppe eines Kontos ansehen: die Nummer eintragen und "
                "„Gruppe zeigen“.",
                "Zusammenführen: führendes Konto, einzugliederndes Konto, "
                "Konfidenz und die Indizien eintragen.",
                "Konfidenz reifen lassen: „Revidieren“ in der Zeile. Die "
                "beteiligten Konten sind dabei NICHT änderbar.",
                "Trennen: „Trennen“, mit Pflichtgrund. Die Zeile bleibt als "
                "Beleg erhalten.",
                "Eine Trennung zurücknehmen: „Trennung zurücknehmen“. Das "
                "kann scheitern, wenn sich die Lage inzwischen geändert hat.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                _HYPOTHESE,
                "DIE SICHT BEHAUPTET NICHT, WER DIE PERSON IST. Sie sagt nur, "
                "dass es dieselbe ist.",
                _KEIN_LOESCHEN,
                "DIE INDIZIEN SIND PFLICHT — beim Anlegen und beim "
                "Überarbeiten. Eine Zusammenführung ohne Indizien wäre eine "
                "Behauptung ohne Grundlage, und sie ließe sich später weder "
                "prüfen noch verteidigen.",
                "EINE ANDERE PAARUNG IST EINE ANDERE ANNAHME. Deshalb lassen "
                "sich die beteiligten Konten nicht umschreiben: dafür ist zu "
                "trennen und neu anzulegen.",
                "EIN KONTO OHNE GRUPPE IST EIN BEFUND, KEIN LEERBEFUND. Die "
                "Sicht sagt dann ausdrücklich, dass dieses Konto keiner "
                "Gruppe zugeordnet ist.",
                "Weist das Werkzeug eine Zusammenführung zurück, nennt die "
                "Meldung die beteiligten Konten und den gangbaren Weg. Diese "
                "Angabe steht dort wörtlich und ist nicht gekürzt — ohne den "
                "konkreten Widerspruch ist er nicht aufzulösen.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (),
            liste=(
                "Kreuzbezug — wer die Person ist, wenn sie bekannt ist.",
                "Aliasse — unter welchen Namen die Konten auftreten.",
                "Querfunde — Hinweise aus anderen Verfahren.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "merge.titel", "Identitäts-Gruppen",
            "Hält fest, dass mehrere Forenkonten von derselben Person "
            "betrieben werden. Wer diese Person ist, sagt die Sicht nicht.",
            verweis="merge#zweck"),
        Kontexthilfe(
            "merge.kennzeile", "Was eine Zusammenführung ist",
            "Weist darauf hin, dass eine Zusammenführung eine Annahme ist: "
            "umkehrbar, belegt, und niemals gelöscht.",
            verweis="merge#grenzen"),
        Kontexthilfe(
            "merge.zahlen", "Umfang",
            "Wie viele Zusammenführungen aktiv und wie viele getrennt sind "
            "und wie viele Konten davon betroffen sind."),
        Kontexthilfe(
            "merge.gruppenbefund", "Befund zum gesuchten Konto",
            "Nennt die Gruppe des gesuchten Kontos. „Keiner Gruppe "
            "zugeordnet“ ist ein Befund und kein Leerbefund — das Konto ist "
            "dann seine eigene Gruppe.",
            verweis="merge#grenzen"),
        Kontexthilfe(
            "merge.bedienung.suche", "Gruppe zu einem Konto",
            "Zeigt die Gruppe, zu der dieses Konto gehört. Nur eine reine "
            "Zahl gilt als Konto — alles andere würde stillschweigend falsch "
            "gedeutet.",
            verweis="merge#ablaeufe"),
        Kontexthilfe(
            "merge.bedienung.alle", "Alle",
            "Hebt die Suche auf und zeigt wieder alle Zusammenführungen."),
        Kontexthilfe(
            "merge.bedienung.getrennte", "Getrennte zeigen",
            "Blendet die getrennten Zusammenführungen ein. Sie bleiben als "
            "Beleg erhalten und tragen ihren Grund.",
            verweis="merge#grenzen"),
        Kontexthilfe(
            "merge.bedienung.zusammenfuehren", "Zusammenführen",
            "Legt die Annahme an, dass beide Konten derselben Person "
            "gehören. Die Indizien sind Pflicht.",
            verweis="merge#grenzen"),
        Kontexthilfe(
            "merge.bedienung.revidieren", "Revidieren",
            "Öffnet Konfidenz und Indizien zur Überarbeitung. Die beteiligten "
            "Konten sind nicht änderbar.",
            verweis="merge#grenzen"),
        Kontexthilfe(
            "merge.bedienung.trennen", "Trennen",
            "Nimmt die Annahme zurück. Der Grund ist Pflicht — eine Trennung "
            "muss so belegt sein wie die Zusammenführung.",
            verweis="merge#ablaeufe"),
        Kontexthilfe(
            "merge.bedienung.trennung_zuruecknehmen",
            "Trennung zurücknehmen",
            "Setzt die Zusammenführung wieder in Kraft. Das kann scheitern, "
            "wenn sich die Lage inzwischen geändert hat — zwei einander "
            "widersprechende Zuordnungen wären schlimmer als eine abgelehnte "
            "Rücknahme.",
            verweis="merge#ablaeufe"),

        # ------------------------------------------------------------------
        # Die restlichen Bedienelemente (Build 634, Welle B2). Die drei
        # Eingabezeilen des Formulars stammen aus der Fabrik '_field'; ihre
        # Marken sitzen an den Abnahmestellen.
        # ------------------------------------------------------------------
        Kontexthilfe(
            "merge.bedienung.gruppe_zeigen", "Gruppe zeigen",
            "Sucht die Gruppe des eingetragenen Kontos. „Keiner Gruppe "
            "zugeordnet“ ist ein Befund und kein Leerbefund — das Konto ist "
            "dann seine eigene Gruppe.",
            verweis="merge#grenzen"),
        Kontexthilfe(
            "merge.bedienung.primaerkonto", "Primärkonto (führend)",
            "Das Konto, das die Gruppe führt. Die Richtung ist nicht "
            "gleichgültig: Ein zugeordnetes Konto kann nicht selbst führend "
            "sein, weil die Auflösung sonst mehrdeutig wäre.",
            verweis="merge#aufbau"),
        Kontexthilfe(
            "merge.bedienung.zweitkonto", "Einzugliederndes Konto",
            "Das Konto, das dem führenden zugeordnet wird. Weist das Werkzeug "
            "die Zusammenführung zurück, nennt die Meldung die beteiligten "
            "Konten und den gangbaren Weg — lesen Sie sie vollständig.",
            verweis="merge#grenzen"),
        Kontexthilfe(
            "merge.bedienung.konfidenz", "Konfidenz",
            "Wie stark die Annahme belegt ist, dass beide Konten derselben "
            "Person gehören. Sie lässt sich später über „Revidieren“ "
            "anheben; setzen Sie im Zweifel niedriger an.",
            verweis="merge#ablaeufe"),
        Kontexthilfe(
            "merge.bedienung.basis", "Basis (Indizien)",
            "Worauf die Annahme beruht — PFLICHTANGABE. Eine Zusammenführung "
            "ohne Indizien wäre eine Behauptung ohne Grundlage und ließe sich "
            "später weder prüfen noch verteidigen.",
            verweis="merge#grenzen"),
        Kontexthilfe(
            "merge.bedienung.edit_konfidenz", "Konfidenz (Überarbeitung)",
            "Hebt die Konfidenz der vorhandenen Zusammenführung an oder senkt "
            "sie. Die beteiligten Konten bleiben, wie sie sind.",
            verweis="merge#grenzen"),
        Kontexthilfe(
            "merge.bedienung.edit_basis", "Basis (Überarbeitung)",
            "Ändert die Indizien der vorhandenen Zusammenführung. Das Feld "
            "darf nicht GELEERT werden — die Annahme braucht ihre Indizien "
            "auch nach der Überarbeitung.",
            verweis="merge#grenzen"),
        Kontexthilfe(
            "merge.bedienung.edit_speichern", "Speichern",
            "Schreibt die Überarbeitung von Konfidenz und Indizien. Auch sie "
            "wird festgehalten; der bisherige Stand geht nicht verloren.",
            verweis="merge#ablaeufe"),
        Kontexthilfe(
            "merge.bedienung.trennungsgrund", "Grund der Trennung",
            "PFLICHTANGABE. Eine Trennung muss so belegt sein wie die "
            "Zusammenführung — sonst bliebe offen, ob die Annahme widerlegt "
            "oder nur aufgegeben wurde.",
            verweis="merge#grenzen"),
        Kontexthilfe(
            "merge.bedienung.trennung_belegen", "Trennung belegen",
            "Führt die Trennung aus. Die Zeile verschwindet nicht, sondern "
            "bleibt als Beleg erhalten und trägt ihren Grund.",
            verweis="merge#grenzen"),
    ),
)


#: Der Teilbestand dieser Nav-Gruppe, in Katalogreihenfolge
#: (crossref, crossfindings, alias, merge - siehe VIEW_CATALOG).
IDENTITAETEN: Tuple[Sichthilfe, ...] = (CROSSREF, CROSSFINDINGS, ALIAS, MERGE)
