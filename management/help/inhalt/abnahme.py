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
# BUILD 632 (Vorgang 17200856, Welle B1): Die Chef-Freigabe hatte zwoelf
#   Bedienelemente und keinen einzigen Text dazu - in der Sicht, in der eine
#   Freigabe UNWIDERRUFLICH erteilt wird. Nachgetragen sind: die zwoelf
#   Kontexthilfen, ein Abschnitt 'bewertung' und die Berichtigung des
#   Abschnitts 'aufbau'. Der sagte bisher, die Zusatzbereiche seien
#   "ausschliesslich lesend" - das Bewertungsformular schreibt aber, und zwar
#   in die Ermittlungsdaten des Falls. Eine Hilfe, die eine Schreibstelle
#   verschweigt, ist schlechter als keine.
#
# Version: v0.8.632 - Build: 632 - 2026-08-01
# =============================================================================

from __future__ import annotations

from typing import Tuple

from management.help.modell import Abschnitt, Kontexthilfe, Sichthilfe

_STAND = 598

#: Die Chef-Freigabe ist in Build 632 nachredigiert worden (Vorgang 17200856):
#: ihre zwoelf Bedienelemente hatten keinen einzigen Hilfetext, und das Kapitel
#: verschwieg, dass in dieser Sicht neben dem Entscheiden auch BEWERTET werden
#: kann. Beides ist hier nachgetragen; deshalb ein eigener Redaktionsstand.
_STAND_APPROVAL = 632

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
    stand=_STAND_APPROVAL,
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
                "Ganz unten steht das Ermittlungsergebnis des Falls: die "
                "bereits vergebenen Bewertungen und, ausdrücklich benannt, "
                "die noch nicht bewerteten Kriterien. Wer das Recht zum "
                "Bewerten hat, findet darunter das Erfassungsformular. Das "
                "ist die EINZIGE Stelle dieser Sicht, an der etwas "
                "geschrieben wird, das nicht die Entscheidung selbst ist.",
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
            "bewertung", "Das Ermittlungsergebnis bewerten",
            (
                "Unter dem Vermerk steht das Ermittlungsergebnis des Falls. "
                "Es besteht aus Bewertungen: je Kriterium wird festgehalten, "
                "wie schwer die gravierendste und wie belastbar die am besten "
                "belegte Erkenntnis ist. Wer das Recht zum Bewerten hat, kann "
                "hier eine Bewertung nachtragen, ohne die Sicht zu wechseln — "
                "das ist der Sinn: man liest den Vermerk und sieht sofort, "
                "worauf er sich stützt und was noch offen ist.",
                "Eine Bewertung besteht aus vier Angaben. KRITERIUM: worum es "
                "geht. AUSPRÄGUNG: ob die gravierendste oder die am besten "
                "belegte Erkenntnis gemeint ist — beide werden getrennt "
                "geführt und nicht miteinander verrechnet. KONFIDENZ: wie "
                "sicher die Aussage ist; dieselbe Abstufung für alle "
                "Kriterien. QUALITÄT: wie tief geprüft wurde; diese "
                "Abstufung gehört zum jeweiligen Kriterium und fehlt bei "
                "manchen ganz.",
                "JEDE BEWERTUNG WIRD ANGEFÜGT, KEINE ÜBERSCHRIEBEN. Eine "
                "Korrektur ist eine neue Bewertung; die frühere bleibt "
                "lesbar. Das ist gewollt, denn der Verlauf zeigt die "
                "Ermittlungsleistung — wie aus einem Verdacht eine "
                "belastbare Aussage wurde. Ein Löschen ist nicht vorgesehen "
                "und wird auch nicht durch einen Umweg möglich.",
                "Die Zeile „Noch nicht bewertet“ ist die wichtigste des "
                "Abschnitts. Sie benennt die blinden Flecken; ein Kriterium "
                "ohne Bewertung ist NICHT dasselbe wie ein Kriterium ohne "
                "Befund.",
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
                "Bewerten beim Lesen: unten das Ermittlungsergebnis ansehen, "
                "die Zeile „Noch nicht bewertet“ lesen und eine fehlende "
                "Bewertung gleich hier nachtragen.",
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
                "EINE BEWERTUNG IST KEINE FREIGABE und eine Freigabe keine "
                "Bewertung. Beides steht hier untereinander und wird getrennt "
                "festgehalten: Wer bewertet, sagt etwas über den Fall; wer "
                "freigibt, entscheidet über den Vermerk. Das Bewerten hängt "
                "an einem eigenen Recht — ohne dieses Recht erscheint das "
                "Formular nicht, und das ist kein Fehler.",
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

        # ------------------------------------------------------------------
        # Die zwoelf Bedienelemente (Build 632, Vorgang 17200856).
        #
        # ANLASS, woertlich (mc): "Die Sichten haben sehr viele
        # Schaltflaechen und Eingabezeilen, aber keine einzige wird erklaert.
        # Wie soll der Anwender wissen, was er tun soll, wenn es ihm nicht
        # definiert und erklaert wird?" Diese Sicht stand bei null von zwoelf
        # und ist die, in der eine Freigabe UNWIDERRUFLICH erteilt wird -
        # deshalb zuerst.
        #
        # Erst die sechs Felder des Bewertungsformulars in der Reihenfolge
        # des Formulars, dann die sechs der Entscheidung.
        # ------------------------------------------------------------------
        Kontexthilfe(
            "approval.bedienung.kriterium", "Kriterium",
            "Worum es bei dieser Bewertung geht. Die Auswahl kommt aus dem "
            "Kriterienkatalog; ausser Dienst gestellte Kriterien werden nicht "
            "mehr angeboten, bleiben in alten Bewertungen aber lesbar.",
            verweis="approval#bewertung"),
        Kontexthilfe(
            "approval.bedienung.auspraegung", "Ausprägung",
            "Welche der beiden Seiten Sie bewerten: die GRAVIERENDSTE "
            "Erkenntnis zu diesem Kriterium oder die am BESTEN BELEGTE. "
            "Beide werden getrennt geführt und nicht miteinander verrechnet "
            "— eine einzelne schwere Feststellung soll nicht durch viele "
            "harmlose verschwinden.",
            verweis="approval#bewertung"),
        Kontexthilfe(
            "approval.bedienung.konfidenz", "Konfidenz",
            "Wie sicher die Aussage ist. Die Abstufung ist für alle Kriterien "
            "dieselbe, damit Bewertungen vergleichbar bleiben. Pflichtangabe: "
            "eine Bewertung ohne Sicherheitsgrad wäre nicht einzuordnen.",
            verweis="approval#bewertung"),
        Kontexthilfe(
            "approval.bedienung.qualitaet", "Qualität",
            "Wie tief geprüft wurde. Diese Abstufung gehört zum jeweiligen "
            "Kriterium und wechselt deshalb mit, sobald Sie ein anderes "
            "wählen. Sie ist freiwillig; bei Kriterien ohne eigene Abstufung "
            "steht hier nur „keine Qualitaet“.",
            verweis="approval#bewertung"),
        Kontexthilfe(
            "approval.bedienung.bewertungsvermerk", "Vermerk zur Bewertung",
            "Freitext zur Begründung dieser einen Bewertung — freiwillig, "
            "aber die einzige Stelle, an der Sie festhalten können, WARUM Sie "
            "so eingestuft haben. Der Text gehört zur Bewertung und wird mit "
            "ihr aufbewahrt.",
            verweis="approval#bewertung"),
        Kontexthilfe(
            "approval.bedienung.bewertung_erfassen", "Bewertung erfassen",
            "Trägt die Bewertung ein. Kriterium, Ausprägung und Konfidenz "
            "müssen gesetzt sein. Die Bewertung wird ANGEFÜGT: eine frühere "
            "zum selben Kriterium bleibt bestehen und lesbar, denn der "
            "Verlauf ist die Ermittlungsleistung.",
            verweis="approval#bewertung"),
        Kontexthilfe(
            "approval.bedienung.siegel_pruefen", "Siegel prüfen",
            "Vergleicht den heutigen Inhalt des Vermerks mit dem Stand, der "
            "bei der Freigabe festgehalten wurde. Meldet die Prüfung eine "
            "Abweichung, ist das ein Manipulationsverdacht und muss verfolgt "
            "werden. Die Prüfung steht auch ohne Freigaberecht offen.",
            verweis="approval#siegel"),
        Kontexthilfe(
            "approval.bedienung.freigabevermerk", "Freigabevermerk",
            "Ihre Anmerkung zur Freigabe — freiwillig. Sie wird mit der "
            "Freigabe festgehalten und ist später der einzige Hinweis "
            "darauf, unter welcher Erwägung Sie abgenommen haben.",
            verweis="approval#entscheidung"),
        Kontexthilfe(
            "approval.bedienung.abschlussvermerk",
            "Als Abschlussbericht kennzeichnen",
            "Vermerkt, dass dieser Vermerk die Dienststelle verlässt. Das ist "
            "KEINE höhere Freigabestufe, sondern die Feststellung des "
            "Versands. Im Zweifel lassen Sie das Feld leer — der Vermerk "
            "lässt sich später gesondert als versandt kennzeichnen.",
            verweis="approval#entscheidung"),
        Kontexthilfe(
            "approval.bedienung.freigeben", "Freigeben & versiegeln",
            "Nimmt den Vermerk ab und versiegelt ihn. DAS IST "
            "UNWIDERRUFLICH: es gibt keinen Weg, eine Freigabe "
            "zurückzunehmen. Bei inhaltlichen Mängeln gehört der Vermerk "
            "nicht freigegeben, sondern zurückgewiesen. Vor dem Ausführen "
            "wird nachgefragt.",
            verweis="approval#entscheidung"),
        Kontexthilfe(
            "approval.bedienung.rueckweisungsgrund", "Grund der Rückweisung",
            "Was nachzubessern ist. Der Eintrag ist freiwillig — aber er ist "
            "das Einzige, was die verfassende Person zur Nachbesserung in der "
            "Hand hat. Eine Rückweisung ohne Grund kostet beide Seiten einen "
            "zweiten Durchgang.",
            verweis="approval#entscheidung"),
        Kontexthilfe(
            "approval.bedienung.zurueckweisen", "Zurückweisen (an Entwurf)",
            "Schickt den Vermerk als Entwurf an die verfassende Person "
            "zurück. Das ist der Weg für inhaltliche Mängel und der einzige, "
            "der eine Änderung am Text noch zulässt.",
            verweis="approval#entscheidung"),
    ),
)


#: Der Teilbestand dieser Nav-Gruppe, in Katalogreihenfolge
#: (reports, lectorate, approval - siehe VIEW_CATALOG).
ABNAHME: Tuple[Sichthilfe, ...] = (REPORTS, LECTORATE, APPROVAL)
