# =============================================================================
# management/help/inhalt/abnahme.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H9)
# =============================================================================
# Zweck:
#   Die Hilfetexte der Nav-Gruppe "Abnahme": reports, lectorate, approval.
#
#   DREI SICHTEN, EIN WEG. Ein Vermerk durchlaeuft vier Zustaende - Entwurf,
#   eingereicht, freigegeben, final. Die drei Sichten begleiten ihn dabei aus
#   drei Blickwinkeln: die Berichts-Abnahme fuehrt den BESTAND (welche gibt es,
#   in welchem Zustand), das Lektorat besorgt das GEGENLESEN (der Text im
#   Mittelpunkt, mit Anmerkungen), die Chef-Freigabe die ENTSCHEIDUNG (lesen,
#   Siegel pruefen, freigeben oder zurueckweisen).
#   Diese Abgrenzung steht in allen drei Kapiteln - sie sehen sich sonst zu
#   aehnlich, und wer im falschen sitzt, sucht dort eine Schaltflaeche, die es
#   dort nicht geben darf.
#
# REGEL H-1 (Anwendersprache): keine Entwicklerbegriffe, keine
#   Entwicklungshistorie. REGEL H-0: keine Falldaten.
#
# Version: v0.8.598 - Build: 598 - 2026-07-31
# =============================================================================

from __future__ import annotations

from typing import Tuple

from management.help.modell import Abschnitt, Kontexthilfe, Sichthilfe

_STAND = 598

# Die vier Zustaende eines Vermerks - woertlich die Beschriftungen der
# Oberflaeche. Sie stehen in allen drei Kapiteln gleich, damit niemand zwei
# Vokabulare lernen muss.
_ZUSTAENDE = (
    "Entwurf — in Arbeit, für die Abnahme noch nicht vorgelegt.",
    "eingereicht — zum Gegenlesen und zur Entscheidung vorgelegt.",
    "freigegeben — abgenommen und versiegelt.",
    "final — an die Staatsanwaltschaft versandt und damit abgeschlossen. "
    "„final“ ist KEINE höhere Freigabestufe, sondern der Versandvermerk.",
)


# =============================================================================
# 1) reports - "Berichts-Abnahme"
# =============================================================================

REPORTS = Sichthilfe(
    sicht="reports",
    titel="Berichts-Abnahme",
    recht_klartext=(
        "Recht: reports.approve ODER reports.review — eines von beiden "
        "genügt, denn wer freigeben darf, muss lesen dürfen. Welche "
        "Schaltflächen an einer Zeile erscheinen, hängt davon ab, welches der "
        "beiden Sie besitzen und in welchem Zustand der Vermerk ist. Freigeben "
        "und Versenden verlangen reports.approve."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Diese Sicht führt den Bestand: Welche Vermerke gibt es über "
                "alle Fälle hinweg, in welchem Zustand stehen sie, wer hat sie "
                "verfasst, wann wurden sie zuletzt freigegeben? Sie "
                "beantwortet „wo stehen wir?“ — nicht „was steht drin?“.",
                "Für das Lesen des Textes gibt es das Lektorat und die "
                "Chef-Freigabe. Diese Sicht ist die Übersicht davor.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "Ansehen: reports.review oder reports.approve. Freigeben und "
                "Versenden: reports.approve. Die Siegelprüfung steht auch "
                "denen offen, die nur lesen dürfen — eine Prüfung, die nur "
                "der Freigebende ausführen darf, wäre keine Kontrolle.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter die Angabe, wie viele Fallakten für "
                "diese Ansicht neu gelesen wurden, darunter die Bedienleiste "
                "mit Zustandsfilter und „Neu einlesen“, darunter die Tabelle.",
                "Unter der Tabelle steht der Hinweisbereich: nicht lesbare "
                "Fallakten und Fälle, zu denen gar keine vorliegt.",
            ),
        ),
        Abschnitt(
            "zustaende", "Die vier Zustände eines Vermerks",
            (
                "Der Zustand entscheidet darüber, was mit einem Vermerk "
                "geschehen kann. Er wandert nur in eine Richtung weiter:",
            ),
            liste=_ZUSTAENDE,
        ),
        Abschnitt(
            "siegel", "Siegel und Siegelprüfung",
            (
                "Mit der Freigabe wird ein Vermerk versiegelt: sein Inhalt "
                "wird so festgehalten, dass jede spätere Veränderung "
                "nachweisbar ist. Die Siegelprüfung vergleicht den heutigen "
                "Inhalt mit dem freigegebenen Stand.",
                "Die Prüfung kennt drei Antworten, und die dritte ist keine "
                "Kleinigkeit: „Kein Siegel vorhanden“ (der Vermerk ist nicht "
                "freigegeben), „Siegel in Ordnung“ — oder „ABWEICHUNG“. Eine "
                "Abweichung ist ein Manipulationsverdacht und muss geprüft "
                "werden; sie wird deshalb auch genau so benannt und nicht als "
                "technischer Hinweis abgetan.",
            ),
        ),
        Abschnitt(
            "hinweise", "Der Hinweisbereich",
            (
                "Unter der Tabelle stehen zwei Arten von Befunden, die man "
                "sonst nie zu Gesicht bekäme: Fallakten, die nicht gelesen "
                "werden konnten, und Fälle, zu denen überhaupt keine vorliegt.",
                "Beide gehören dorthin, weil sie das Ergebnis relativieren: "
                "Eine Liste ohne diesen Bereich sähe vollständig aus, obwohl "
                "sie es nicht ist. Ein Eintrag hier ist ein Betriebsvorfall "
                "und gehört gemeldet.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Überblick verschaffen: nach Zustand „eingereicht“ filtern — "
                "das ist die Arbeitsvorrat der Abnahme.",
                "Einen Vermerk freigeben: Zeile im Zustand „eingereicht“ "
                "wählen und freigeben. Danach ist er versiegelt.",
                "Ein Siegel prüfen: bei freigegebenen und versandten "
                "Vermerken die Siegelprüfung aufrufen und das Ergebnis lesen.",
                "Nach einer Änderung an den Fallakten: „Neu einlesen“ — sonst "
                "zeigt die Sicht den zuletzt gelesenen Stand.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "Diese Sicht zeigt ANGABEN ZU Vermerken, nicht deren Text. "
                "Wer den Text lesen will, geht ins Lektorat oder in die "
                "Chef-Freigabe.",
                "Freigabe und Versiegelung sind UNWIDERRUFLICH. Es gibt "
                "keinen Weg, eine Freigabe zurückzunehmen; inhaltliche Mängel "
                "gehen als Zurückweisung an den Entwurf zurück.",
                "„final“ ist der Versandvermerk und keine höhere "
                "Freigabestufe. Ein Vermerk wird nicht dadurch besser, dass er "
                "versandt ist.",
                "Nicht lesbare Fallakten werden AUSGEWIESEN und nicht "
                "weggelassen. Eine Zahl ohne diesen Hinweis wäre eine falsche "
                "Vollständigkeitsaussage.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (
                "Drei Sichten begleiten denselben Weg aus drei Blickwinkeln:",
            ),
            liste=(
                "Berichts-Abnahme — der Bestand: welche gibt es, in welchem "
                "Zustand?",
                "Lektorat — das Gegenlesen: der Text im Mittelpunkt, mit "
                "Anmerkungen.",
                "Chef-Freigabe — die Entscheidung: lesen, Siegel prüfen, "
                "freigeben oder zurückweisen.",
                "Ermittlungsergebnis — worauf sich ein Vermerk stützt.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "reports.titel", "Berichts-Abnahme",
            "Führt den Bestand aller Vermerke über alle Fälle hinweg: "
            "Zustand, Verfasser, Freigaben. Den Text eines Vermerks lesen Sie "
            "im Lektorat oder in der Chef-Freigabe.",
            verweis="reports#zweck"),
        Kontexthilfe(
            "reports.scaninfo", "Einlesevermerk",
            "Nennt, wie viele Fallakten für diese Ansicht tatsächlich neu "
            "gelesen wurden. Unveränderte Akten werden nicht erneut "
            "durchsucht; „Neu einlesen“ erzwingt es.",
            verweis="reports#aufbau"),
        Kontexthilfe(
            "reports.spalte.subject_id", "Spalte „Fall“",
            "Der Ermittlungsschlüssel der Fallakte, zu der der Vermerk "
            "gehört."),
        Kontexthilfe(
            "reports.spalte.username", "Spalte „Benutzername“",
            "Der im Forum geführte Kontoname des Falls."),
        Kontexthilfe(
            "reports.spalte.title", "Spalte „Titel“",
            "Die Überschrift des Vermerks, wie die verfassende Person sie "
            "vergeben hat."),
        Kontexthilfe(
            "reports.spalte.typ", "Spalte „Typ“",
            "Vermerk, Ergänzungsvermerk oder Abschlussbericht. Der Typ sagt, "
            "welche Rolle das Schriftstück in der Akte hat."),
        Kontexthilfe(
            "reports.spalte.nr", "Spalte „Nr.“",
            "Die laufende Nummer des Vermerks innerhalb seines Falls."),
        Kontexthilfe(
            "reports.spalte.status_label", "Spalte „Status“",
            "Der Zustand: Entwurf, eingereicht, freigegeben oder final. Er "
            "entscheidet, was mit dem Vermerk geschehen kann.",
            verweis="reports#zustaende"),
        Kontexthilfe(
            "reports.spalte.created_by", "Spalte „Verfasser“",
            "Wer den Vermerk angelegt hat. Die Angabe stammt aus dem "
            "Protokollbuch und lässt sich nicht überschreiben."),
        Kontexthilfe(
            "reports.spalte.created", "Spalte „Erstellt“",
            "Wann der Vermerk angelegt wurde."),
        Kontexthilfe(
            "reports.spalte.freigaben", "Spalte „Freigaben“",
            "Wie viele Freigaben zu diesem Vermerk vorliegen. Jede Freigabe "
            "ist ein eigener, protokollierter Vorgang.",
            verweis="reports#siegel"),
        Kontexthilfe(
            "reports.spalte.letzte_freigabe", "Spalte „Letzte Freigabe“",
            "Zeitpunkt der jüngsten Freigabe. Ein leeres Feld heißt: noch "
            "keine — nicht etwa „verloren“."),
        Kontexthilfe(
            "reports.werkzeug.filter_entfernen", "Filter zurücksetzen",
            "Entfernt alle Spaltenfilter dieser Sicht auf einmal."),
        Kontexthilfe(
            "reports.werkzeug.trefferzahl", "Trefferanzeige",
            "Nennt, wie viele Zeilen sichtbar sind; bei gesetztem Filter "
            "„sichtbar von gesamt“."),
    ),
)


# =============================================================================
# 2) lectorate - "Lektorat"
# =============================================================================

LECTORATE = Sichthilfe(
    sicht="lectorate",
    titel="Lektorat",
    recht_klartext=(
        "Recht: reports.review ODER reports.approve — eines genügt; die "
        "Leitung liest ebenfalls gegen. Der Umfang entscheidet, welche "
        "Vermerke Ihnen vorgelegt werden; er steht als Klartext über der "
        "Auswahl."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Das Lektorat ist die Sicht für das Gegenlesen: Der "
                "Vermerkstext steht im Mittelpunkt, nicht seine Angaben. "
                "Vorgelegt werden die Vermerke im Zustand „eingereicht“.",
                "Gegenlesen heißt hier: sprachlich und sachlich prüfen und "
                "Anmerkungen hinterlassen — nicht entscheiden. Die "
                "Entscheidung trifft die Chef-Freigabe.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "reports.review oder reports.approve. Der zugeteilte Umfang "
                "bestimmt, welche Vermerke erscheinen; er wird über der "
                "Auswahl benannt, damit eine kurze Liste nicht wie ein leerer "
                "Arbeitstag aussieht.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter die Angabe des Umfangs, darunter die "
                "Auswahl der vorgelegten Vermerke. Ist einer gewählt, "
                "erscheint darunter sein Text.",
            ),
        ),
        Abschnitt(
            "vorschau", "Der Vermerkstext",
            (
                "Der Text wird genau so dargestellt, wie er auch in die Akte "
                "gehen würde — nicht als Annäherung. Was Sie hier lesen, ist "
                "das, was gedruckt wird.",
                "Die Darstellung ist REIN LESEND. Im Lektorat wird der Text "
                "nicht geändert; Änderungen nimmt die verfassende Person am "
                "Entwurf vor.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Gegenlesen: Vermerk aus der Auswahl wählen, Text lesen, "
                "Anmerkungen setzen.",
                "Eine Stelle genau bezeichnen: die Anmerkung an der "
                "betreffenden Textstelle setzen statt am Ende — die "
                "verfassende Person muss sonst raten.",
                "Nach dem Gegenlesen: der Vermerk bleibt „eingereicht“. Über "
                "Freigabe oder Zurückweisung entscheidet die Chef-Freigabe.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "Das Lektorat GIBT NICHTS FREI und weist nichts zurück. Es "
                "kommentiert. Diese Trennung ist gewollt: Gegenlesen und "
                "Entscheiden sind zwei Vorgänge, und sie sollen auch dann "
                "unterscheidbar bleiben, wenn dieselbe Person beides darf.",
                "Der Text lässt sich hier NICHT bearbeiten. Wer ihn ändern "
                "will, muss ihn zurückgeben lassen.",
                "Vorgelegt sind ausschließlich Vermerke im Zustand "
                "„eingereicht“. Ein Entwurf ist noch nicht zum Gegenlesen "
                "bestimmt — dass er hier fehlt, ist kein Mangel.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (
                "Drei Sichten begleiten denselben Weg aus drei Blickwinkeln:",
            ),
            liste=(
                "Berichts-Abnahme — der Bestand: welche gibt es, in welchem "
                "Zustand?",
                "Lektorat — das Gegenlesen: der Text im Mittelpunkt, mit "
                "Anmerkungen.",
                "Chef-Freigabe — die Entscheidung: lesen, Siegel prüfen, "
                "freigeben oder zurückweisen.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "lectorate.titel", "Lektorat — Gegenlesen",
            "Stellt den Vermerkstext zum Gegenlesen bereit. Hier wird "
            "kommentiert, nicht entschieden und nicht bearbeitet.",
            verweis="lectorate#zweck"),
        Kontexthilfe(
            "lectorate.umfang", "Umfang und Vorlage",
            "Nennt, welcher Ausschnitt Ihnen vorgelegt wird. Zum Gegenlesen "
            "stehen ausschließlich Vermerke im Zustand „eingereicht“ — ein "
            "Entwurf ist dafür noch nicht bestimmt.",
            verweis="lectorate#grenzen"),
        Kontexthilfe(
            "lectorate.spalte.username", "Spalte „Benutzer“",
            "Der im Forum geführte Kontoname des Falls, zu dem der Vermerk "
            "gehört."),
        Kontexthilfe(
            "lectorate.spalte.title", "Spalte „Titel“",
            "Die Überschrift des Vermerks."),
        Kontexthilfe(
            "lectorate.spalte.typ", "Spalte „Typ“",
            "Vermerk, Ergänzungsvermerk oder Abschlussbericht."),
        Kontexthilfe(
            "lectorate.spalte.nr", "Spalte „Nr.“",
            "Die laufende Nummer des Vermerks innerhalb seines Falls."),
        Kontexthilfe(
            "lectorate.spalte.status_label", "Spalte „Status“",
            "Der Zustand des Vermerks. Zum Gegenlesen erscheinen nur "
            "eingereichte.",
            verweis="reports#zustaende"),
        Kontexthilfe(
            "lectorate.spalte.created_by", "Spalte „Verfasser“",
            "Wer den Vermerk angelegt hat — die Person, an die Ihre "
            "Anmerkungen gehen."),
        Kontexthilfe(
            "lectorate.spalte.created", "Spalte „Erstellt“",
            "Wann der Vermerk angelegt wurde."),
        Kontexthilfe(
            "lectorate.werkzeug.filter_entfernen", "Filter zurücksetzen",
            "Entfernt alle Spaltenfilter dieser Sicht auf einmal."),
        Kontexthilfe(
            "lectorate.werkzeug.trefferzahl", "Trefferanzeige",
            "Nennt, wie viele Zeilen sichtbar sind; bei gesetztem Filter "
            "„sichtbar von gesamt“."),
    ),
)


# =============================================================================
# 3) approval - "Chef-Freigabe"
# =============================================================================

APPROVAL = Sichthilfe(
    sicht="approval",
    titel="Chef-Freigabe",
    recht_klartext=(
        "Recht: reports.approve. Das Freigeben selbst verlangt zusätzlich den "
        "Umfang „alle“ — eine Freigabe ist eine Leitungsentscheidung über den "
        "Fall einer anderen Person und nicht über den eigenen."
    ),
    stand=_STAND,
    abschnitte=(
        Abschnitt(
            "zweck", "Zweck und Motivation",
            (
                "Hier wird entschieden: den vorgelegten Vermerk lesen, das "
                "Siegel prüfen, freigeben oder zurückweisen. Der Text steht "
                "im Mittelpunkt — man soll lesen, bevor man entscheidet.",
                "Deshalb gibt es diese Sicht neben der Berichts-Abnahme, die "
                "dieselben Entscheidungen an einer Tabelle anbietet: Eine "
                "Entscheidung, die man aus einer Zeile heraus trifft, ist "
                "eine andere als eine, die man nach dem Lesen trifft.",
            ),
        ),
        Abschnitt(
            "rechte", "Rechtelage",
            (
                "reports.approve. Freigeben und Versiegeln setzen den Umfang "
                "„alle“ voraus. Die Siegelprüfung steht auch ohne diesen "
                "Umfang offen — sie ist eine Kontrolle und keine "
                "Entscheidung.",
            ),
        ),
        Abschnitt(
            "aufbau", "Aufbau der Sicht",
            (
                "Überschrift, darunter der Hinweis auf Umfang und "
                "Unwiderruflichkeit, darunter die Auswahl der vorgelegten "
                "Vermerke, darunter der Text und die Schaltflächen.",
                "Zu einem gewählten Vermerk lassen sich zusätzlich die Belege "
                "und die Anmerkungen des Lektorats einsehen — beides "
                "ausschließlich lesend.",
            ),
        ),
        Abschnitt(
            "entscheidung", "Freigeben oder zurückweisen",
            (
                "Freigeben nimmt den Vermerk ab und versiegelt ihn. Das ist "
                "UNWIDERRUFLICH: es gibt keinen Weg, eine Freigabe "
                "zurückzunehmen.",
                "Zurückweisen schickt den Vermerk als Entwurf an die "
                "verfassende Person zurück. Das ist der Weg für inhaltliche "
                "Mängel — und der einzige, der eine Änderung am Text noch "
                "zulässt.",
                "Nach der Freigabe kann ein Vermerk als versandt vermerkt "
                "werden. Auch das ist keine höhere Freigabestufe, sondern die "
                "Feststellung, dass er die Dienststelle verlassen hat.",
            ),
        ),
        Abschnitt(
            "siegel", "Die Siegelprüfung",
            (
                "Die Siegelprüfung vergleicht den heutigen Inhalt eines "
                "freigegebenen Vermerks mit dem Stand, der bei der Freigabe "
                "festgehalten wurde. Sie ist die Kontrolle, die eine "
                "unbemerkte Änderung ausschließt.",
                "Meldet sie eine ABWEICHUNG, ist das ein "
                "Manipulationsverdacht und muss geprüft werden. Die Sicht "
                "sagt das im Klartext und nicht als beiläufige Notiz.",
            ),
        ),
        Abschnitt(
            "ablaeufe", "Arbeitsabläufe",
            (),
            liste=(
                "Entscheiden: Vermerk wählen, Text vollständig lesen, "
                "Anmerkungen des Lektorats ansehen, dann freigeben oder "
                "zurückweisen.",
                "Zurückweisen mit Begründung: Der Grund ist das Einzige, was "
                "die verfassende Person zur Nachbesserung in der Hand hat.",
                "Nachträglich prüfen: bei einem freigegebenen Vermerk die "
                "Siegelprüfung aufrufen.",
            ),
        ),
        Abschnitt(
            "grenzen", "Grenzen und Zusicherungen",
            (
                "FREIGABE UND VERSIEGELUNG SIND UNWIDERRUFLICH. Das ist keine "
                "technische Einschränkung, sondern der Sinn der Sache: eine "
                "zurücknehmbare Freigabe wäre keine.",
                "Diese Sicht ÄNDERT DEN TEXT NICHT. Sie liest und "
                "entscheidet; geändert wird ausschließlich am zurückgegebenen "
                "Entwurf.",
                "Die Anmerkungen des Lektorats erscheinen hier NUR LESEND. "
                "Wer entscheidet, kommentiert nicht zugleich — sonst wäre "
                "nicht mehr unterscheidbar, was Hinweis und was Entscheidung "
                "war.",
            ),
        ),
        Abschnitt(
            "verweise", "Querverweise",
            (
                "Drei Sichten begleiten denselben Weg aus drei Blickwinkeln:",
            ),
            liste=(
                "Berichts-Abnahme — der Bestand: welche gibt es, in welchem "
                "Zustand?",
                "Lektorat — das Gegenlesen: der Text im Mittelpunkt, mit "
                "Anmerkungen.",
                "Chef-Freigabe — die Entscheidung: lesen, Siegel prüfen, "
                "freigeben oder zurückweisen.",
                "Ermittlungsergebnis — worauf sich ein Vermerk stützt.",
            ),
        ),
    ),
    kontext=(
        Kontexthilfe(
            "approval.titel", "Chef-Freigabe",
            "Den vorgelegten Vermerk lesen, das Siegel prüfen und freigeben "
            "oder zurückweisen. Der Text steht im Mittelpunkt — man soll "
            "lesen, bevor man entscheidet.",
            verweis="approval#zweck"),
        Kontexthilfe(
            "approval.umfang", "Umfang und Unwiderruflichkeit",
            "Nennt den Ausschnitt, über den Sie entscheiden, und erinnert an "
            "das Wesentliche: Freigabe und Versiegelung sind unwiderruflich; "
            "inhaltliche Mängel gehen als Zurückweisung an den Entwurf "
            "zurück.",
            verweis="approval#entscheidung"),
        Kontexthilfe(
            "approval.spalte.username", "Spalte „Benutzer“",
            "Der im Forum geführte Kontoname des Falls, zu dem der Vermerk "
            "gehört."),
        Kontexthilfe(
            "approval.spalte.title", "Spalte „Titel“",
            "Die Überschrift des Vermerks."),
        Kontexthilfe(
            "approval.spalte.typ", "Spalte „Typ“",
            "Vermerk, Ergänzungsvermerk oder Abschlussbericht."),
        Kontexthilfe(
            "approval.spalte.nr", "Spalte „Nr.“",
            "Die laufende Nummer des Vermerks innerhalb seines Falls."),
        Kontexthilfe(
            "approval.spalte.status_label", "Spalte „Status“",
            "Der Zustand des Vermerks. Zur Entscheidung stehen die "
            "eingereichten; bei freigegebenen bleibt die Siegelprüfung.",
            verweis="approval#siegel"),
        Kontexthilfe(
            "approval.spalte.created_by", "Spalte „Verfasser“",
            "Wer den Vermerk angelegt hat — die Person, an die eine "
            "Zurückweisung geht."),
        Kontexthilfe(
            "approval.spalte.created", "Spalte „Erstellt“",
            "Wann der Vermerk angelegt wurde."),
        Kontexthilfe(
            "approval.werkzeug.filter_entfernen", "Filter zurücksetzen",
            "Entfernt alle Spaltenfilter dieser Sicht auf einmal."),
        Kontexthilfe(
            "approval.werkzeug.trefferzahl", "Trefferanzeige",
            "Nennt, wie viele Zeilen sichtbar sind; bei gesetztem Filter "
            "„sichtbar von gesamt“."),
    ),
)


#: Der Teilbestand dieser Nav-Gruppe, in Katalogreihenfolge
#: (reports, lectorate, approval - siehe VIEW_CATALOG).
ABNAHME: Tuple[Sichthilfe, ...] = (REPORTS, LECTORATE, APPROVAL)
