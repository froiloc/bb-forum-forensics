# =============================================================================
# management/help/pruefung.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H1)
# =============================================================================
# Zweck:
#   Die Vollstaendigkeits- und Verweispruefungen des Hilfe-Registers - das
#   maschinelle Gegenstueck zu Grundregel 1 ("Kein Beleg darf je still
#   uebersprungen werden").
#
#   VORBILD: KpiGlossary.verify_covers_stats() (management/stats/glossary.py).
#   Dort wie hier gilt: eine Luecke wird BENANNT und bricht den Lauf; sie wird
#   nicht geloggt und weitergereicht.
#
#   DIE FEHLLISTE - warum es sie gibt (gesicherte Erkenntnis, Konzept §3.1):
#   Zwischen dem ersten und dem letzten Inhaltsbuild gibt es einen Zustand,
#   in dem manche Sichten Hilfe haben und andere nicht. Zwei Wege waeren
#   falsch: die Pruefung ganz abschalten (dann faellt am Ende niemandem auf,
#   was fehlt) oder sie scharf schalten (dann ist kein Zwischenbuild
#   lauffaehig, Grundregel 2). Der dritte Weg ist die EXPLIZITE Fehlliste:
#   Jede Luecke steht namentlich darin, das Werkzeug zeigt an der Stelle den
#   ehrlichen Platzhalter "Hilfe folgt", und ein Regressionstest erzwingt,
#   dass die Liste nur SCHRUMPFEN kann. Damit ist der Fortschritt jederzeit
#   belegbar und ein Rueckfall unmoeglich.
#
#   Alle Funktionen sind rein: kein DB-, Netz- oder Uhrzugriff.
#
# Version: v0.8.588 - Build: 588 - 2026-07-31
# =============================================================================

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Sequence, Tuple

from management.help.modell import HilfeRegister, PFLICHT_ANKER
from management.help.inhalt.shell import SHELL_PRAEFIX
from management.help.sicht_katalog import SICHT_IDS, sicht


class HilfePruefungError(Exception):
    """Oberklasse aller Hilfe-Pruefungsfehler."""


class HilfeUnvollstaendigError(HilfePruefungError):
    """Eine Sicht/ein Werkzeug hat keine Hilfe - und steht auch nicht auf der
    Fehlliste."""


class HilfeVerweisError(HilfePruefungError):
    """Ein Verweis zeigt auf einen Anker, den es nicht gibt."""


class HilfeFehllisteError(HilfePruefungError):
    """Die Fehlliste ist gewachsen oder nennt Unbekanntes."""


class HilfeInhaltError(HilfePruefungError):
    """Ein Hilfetext verstoesst gegen Regel H-0 (fallinhaltsfrei)."""


# -----------------------------------------------------------------------------
# 1) Abdeckung: keine Sicht ohne Kapitel, kein Kapitel ohne Sicht
# -----------------------------------------------------------------------------

def fehlliste_sichten(register: HilfeRegister,
                      sicht_ids: Sequence[str] = SICHT_IDS) -> Tuple[str, ...]:
    """
    Die ABGELEITETE Fehlliste: alle Katalogsichten ohne Kapitel im Register,
    in Katalogreihenfolge. Bewusst abgeleitet und nicht gepflegt - eine
    gepflegte Liste koennte luegen (siehe HilfeRegister.__post_init__).
    """
    vorhanden = set(register.ids())
    return tuple(i for i in sicht_ids if i not in vorhanden)


def verify_sichten_abgedeckt(register: HilfeRegister,
                             erlaubte_luecken: Iterable[str] = (),
                             sicht_ids: Sequence[str] = SICHT_IDS) -> None:
    """
    Erzwingt die Deckung Katalog <-> Register:
      * jede Katalogsicht hat ein Kapitel ODER steht namentlich in
        erlaubte_luecken (der Fehlliste),
      * kein Kapitel ohne Katalogsicht (kein Waisen-Kapitel),
      * kein Eintrag der Fehlliste, der laengst ein Kapitel hat (die Liste
        muss ehrlich sein, sonst verdeckt sie Fortschritt),
      * kein unbekannter Eintrag auf der Fehlliste.

    erlaubte_luecken leer -> die Pruefung ist SCHARF (Endzustand ab H14).
    """
    erlaubt = list(erlaubte_luecken)
    katalog = list(sicht_ids)
    vorhanden = set(register.ids())

    unbekannt = sorted(set(erlaubt) - set(katalog))
    if unbekannt:
        raise HilfeFehllisteError(
            "Fehlliste nennt Sichten, die es im Katalog nicht gibt: %s"
            % ", ".join(unbekannt))

    ueberholt = sorted(set(erlaubt) & vorhanden)
    if ueberholt:
        raise HilfeFehllisteError(
            "Fehlliste nennt Sichten, die laengst ein Kapitel haben - die "
            "Liste ist nicht fortgeschrieben: %s" % ", ".join(ueberholt))

    fehlend = [i for i in katalog if i not in vorhanden and i not in erlaubt]
    if fehlend:
        raise HilfeUnvollstaendigError(
            "Sichten ohne Hilfekapitel und ohne Fehllisten-Eintrag: %s"
            % ", ".join(fehlend))

    waisen = sorted(vorhanden - set(katalog))
    if waisen:
        raise HilfeUnvollstaendigError(
            "Hilfekapitel ohne Sicht im Katalog: %s" % ", ".join(waisen))


def verify_gliederung(register: HilfeRegister) -> None:
    """
    Jedes Kapitel traegt die Pflichtgliederung (Konzept §2.3). Das prueft zwar
    schon Sichthilfe.__post_init__ beim Bauen - hier steht es noch einmal als
    BESTANDSpruefung, damit ein per Konstruktion umgangenes Kapitel (z. B.
    aus einem Test heraus zusammengesetzt) nicht durchrutscht.
    """
    fehler: List[str] = []
    for s in register.sichten:
        anker = set(s.anker())
        fehlend = [p for p in PFLICHT_ANKER if p not in anker]
        if fehlend:
            fehler.append("%s: %s" % (s.sicht, ", ".join(fehlend)))
    if fehler:
        raise HilfeUnvollstaendigError(
            "Kapitel ohne Pflichtabschnitte -> %s" % "; ".join(fehler))


# -----------------------------------------------------------------------------
# 2) Verweise: kein Verweis ins Leere
# -----------------------------------------------------------------------------

def verify_verweise(register: HilfeRegister) -> None:
    """
    Jeder Kontexthilfe-Verweis '<sicht>#<anker>' zeigt auf ein Kapitel des
    Registers UND einen dort vorhandenen Anker.

    ABSICHT (Konzept §4.2d): Ein Verweis, der ins Leere zeigt, ist im Betrieb
    schlimmer als kein Verweis - er kostet die ermittelnde Person Zeit und
    Vertrauen mitten in der Arbeit. Deshalb bricht er den Build.
    """
    fehler: List[str] = []
    # Shell-Kontexthilfen werden mitgeprueft: auch ein Verweis aus der
    # Kopfzeile darf nicht ins Leere zeigen.
    for k in register.alle_kontexthilfen():
        if k.verweis is None:
            continue
        ziel_sicht, _, ziel_anker = k.verweis.partition("#")
        ziel = register.get(ziel_sicht)
        if ziel is None:
            fehler.append(
                "%s -> '%s': Kapitel '%s' gibt es (noch) nicht"
                % (k.schluessel, k.verweis, ziel_sicht))
            continue
        if ziel_anker not in ziel.anker():
            fehler.append(
                "%s -> '%s': Anker '%s' gibt es im Kapitel '%s' nicht"
                % (k.schluessel, k.verweis, ziel_anker, ziel_sicht))
    if fehler:
        raise HilfeVerweisError(
            "Verweise ins Leere: %s" % "; ".join(fehler))


def verify_kontextschluessel(register: HilfeRegister) -> None:
    """
    Kontextschluessel sind global eindeutig und tragen die Sicht als Praefix.
    (Die Form prueft bereits Kontexthilfe.__post_init__; hier geht es um die
    globale Eindeutigkeit ueber alle Kapitel hinweg.)
    """
    alle = list(register.kontext_schluessel())
    doppelt = sorted({s for s in alle if alle.count(s) > 1})
    if doppelt:
        raise HilfePruefungError(
            "Kontextschluessel doppelt vergeben: %s" % ", ".join(doppelt))


# -----------------------------------------------------------------------------
# 3) Fehllisten-Monotonie
# -----------------------------------------------------------------------------

def verify_fehlliste_monoton(aktuell: Iterable[str],
                             stand: Iterable[str]) -> None:
    """
    Die Fehlliste darf gegenueber dem eingecheckten Stand nur SCHRUMPFEN.

    Ein neuer Eintrag bedeutet eines von zweien: eine neue Sicht ist ohne
    Hilfe hinzugekommen, oder ein Kapitel ist verschwunden. Beides muss
    auffallen - und zwar hier, nicht im Betrieb.
    """
    neu = sorted(set(aktuell) - set(stand))
    if neu:
        raise HilfeFehllisteError(
            "Die Fehlliste ist GEWACHSEN um: %s. Entweder ist eine Sicht ohne "
            "Hilfe hinzugekommen, oder ein Kapitel ist verlorengegangen - "
            "beides ist zu klaeren, nicht fortzuschreiben." % ", ".join(neu))


# -----------------------------------------------------------------------------
# 4) Regel H-0: fallinhaltsfrei
# -----------------------------------------------------------------------------
#
# EHRLICHE ABGRENZUNG (wichtig, damit niemand mehr erwartet, als hier steht):
# Diese Pruefung ist ein NETZ GEGEN DIE WAHRSCHEINLICHSTEN VERSEHEN, keine
# Garantie. Ein frei formulierter Satz mit einem echten Forennamen darin ist
# maschinell nicht von einem erfundenen zu unterscheiden. Die eigentliche
# Sicherung ist und bleibt redaktionell (Vier-Augen: Claude verfasst, mc
# nimmt ab - Konzept §4.1). Was hier steht, faengt die Muster, die beim
# Abschreiben aus einer echten Sitzung typischerweise mitwandern.

# Fiktiver Beispielraum. Beispielwerte in Hilfetexten MUESSEN hieraus stammen;
# damit ist an jeder Zahl im Text sofort erkennbar, dass sie erfunden ist.
FIKTIVE_UIDS: Tuple[str, ...] = ("900001", "900002", "900003")
FIKTIVE_PERSONALNUMMER: str = "h999999"

_VERBOTE: Tuple[Tuple[str, str], ...] = (
    # Konkrete Fall-Datenbanknamen. In der Hilfe steht IMMER der Platzhalter
    # evidence_<uid>.db - eine konkrete Zahl waere eine echte Kontonummer.
    (r"(?:evidence|forensic|assets)_\d+\.db",
     "konkreter Fall-Datenbankname (bitte 'evidence_<uid>.db' schreiben)"),
    # Personalnummern der Anlage (Muster hNNNNNN, vgl. Testdaten des Projekts).
    (r"\bh\d{6}\b",
     "Personalnummer-Muster hNNNNNN"),
    # E-Mail-Adressen.
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
     "E-Mail-Adresse"),
    # Aktenzeichen-Muster der Staatsanwaltschaft (z. B. '123 Js 4567/25').
    (r"\b\d{2,4}\s+[A-Z][a-z]{1,3}\s+\d+/\d{2}\b",
     "Aktenzeichen-Muster"),
    # IP-Adressen ausser der dokumentierten Loopback-Lage 127.0.0.x.
    (r"\b(?!127\.0\.0\.)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
     "IP-Adresse"),
)

_VERBOTE_KOMPILIERT: Tuple[Tuple[re.Pattern, str], ...] = tuple(
    (re.compile(muster), bezeichnung) for muster, bezeichnung in _VERBOTE)


def _texte(register: HilfeRegister):
    """Alle redaktionellen Texte des Registers als (Herkunft, Text)-Paare."""
    for k in register.shell:
        yield ("%s (Titel)" % k.schluessel, k.titel)
        yield ("%s (Text)" % k.schluessel, k.text)
    for s in register.sichten:
        yield ("%s (Kapiteltitel)" % s.sicht, s.titel)
        yield ("%s (Rechtelage)" % s.sicht, s.recht_klartext)
        for a in s.abschnitte:
            yield ("%s#%s (Titel)" % (s.sicht, a.anker), a.titel)
            for i, p in enumerate(a.absaetze):
                yield ("%s#%s (Absatz %d)" % (s.sicht, a.anker, i + 1), p)
            for i, p in enumerate(a.liste):
                yield ("%s#%s (Punkt %d)" % (s.sicht, a.anker, i + 1), p)
        for k in s.kontext:
            yield ("%s (Titel)" % k.schluessel, k.titel)
            yield ("%s (Text)" % k.schluessel, k.text)


def verify_fallinhaltsfrei(register: HilfeRegister) -> None:
    """
    Regel H-0 (Konzept §4.1): kein Hilfetext enthaelt Falldaten. Prueft die
    Verbotsmuster; Treffer werden mit Fundstelle benannt.
    """
    fehler: List[str] = []
    for herkunft, text in _texte(register):
        if not text:
            continue
        for muster, bezeichnung in _VERBOTE_KOMPILIERT:
            treffer = muster.search(text)
            if treffer is None:
                continue
            if bezeichnung == "Personalnummer-Muster hNNNNNN" \
                    and treffer.group(0) == FIKTIVE_PERSONALNUMMER:
                continue
            fehler.append("%s: %s -> '%s'"
                          % (herkunft, bezeichnung, treffer.group(0)))
    if fehler:
        raise HilfeInhaltError(
            "Regel H-0 verletzt (fallinhaltsfrei): %s" % "; ".join(fehler))


# -----------------------------------------------------------------------------
# 4b) ANWENDERSPRACHE (Regel H-1, mc 2026-07-31)
# -----------------------------------------------------------------------------
#
# DIE REGEL IM WORTLAUT DES AUFTRAGS:
#   "Die Texte richten sich im Regelfall an den Endanwender. Dieser hat keinen
#   technischen Hintergrund, und fuer ihn ist das Werkzeug ein
#   Anwendungsgegenstand und kein Softwareprojekt. Dem Endanwender ist es egal,
#   wie die Historie der Entwicklung war. Ihn interessiert der Ist-Stand: 'Was
#   kann ich damit machen?' Technische Begriffe wie 'Build', 'Backend' oder
#   'Wahrheitsquelle' haben hier nichts zu suchen."
#
# WARUM DAS EINE MASCHINELLE PRUEFUNG WIRD UND KEIN GUTER VORSATZ:
#   Ich habe diese Begriffe beim Verfassen der ersten zehn Kapitel an 35
#   Stellen benutzt, ohne es zu bemerken - weil ich beim Schreiben in den
#   Quelltext geschaut habe, aus dem die Texte belegt sind. Ein Vorsatz haette
#   denselben Fehler in den restlichen 33 Kapiteln wiederholt. Eine Liste, die
#   den Lauf bricht, tut das nicht.
#
# WAS DIE LISTE NICHT KANN: Sie faengt WOERTER, nicht HALTUNG. Ein Satz kann
#   ohne ein einziges verbotenes Wort trotzdem aus der Entwicklersicht
#   geschrieben sein. Die Liste ist ein Netz gegen den Rueckfall, kein Ersatz
#   fuer die Redaktion - genauso wie bei Regel H-0.

class HilfeSpracheError(HilfePruefungError):
    """Ein Hilfetext benutzt Entwicklersprache statt Anwendersprache."""


#: Begriff -> was stattdessen dasteht. Der zweite Teil ist kein Schmuck: Wer
#: den Fehler behebt, soll nicht raten muessen, was gemeint war.
JARGON: Tuple[Tuple[str, str], ...] = (
    (r"\bBuilds?\b",
     "Entwicklungsstand - fuer den Anwender bedeutungslos; die Aussage ohne "
     "den Verweis formulieren"),
    (r"\bBack-?[Ee]nd\b|\bFront-?[Ee]nd\b",
     "wo etwas gerechnet wird, ist Anwendersache nicht; 'das Werkzeug' oder "
     "die Aussage ohne Ortsangabe"),
    (r"\bWahrheitsquelle\b",
     "'massgeblich' oder 'verbindlich'"),
    (r"\bEndpunkt\b|/api/",
     "die Schnittstelle nicht nennen; die Sicht oder die Angabe benennen"),
    (r"\bScope\b",
     "'Umfang' - so heisst es auch in der Oberflaeche"),
    (r"\bHash\b|\baudit_log\b",
     "'Protokollbuch' und 'lueckenlose Kette'"),
    (r"\bMigration\b|\bM0\d\d\b",
     "'die Vorbereitung fehlt noch' o. ae."),
    (r"\bTooltip\b",
     "'Kurzhinweis, wenn Sie mit der Maus darauf zeigen'"),
    (r"(?i)\bserver\w*\b",
     "'das Werkzeug'"),
    (r"\bF(?:ä|ae)higkeit(?:en)?\b",
     "'Recht' - so heisst es in der Oberflaeche und in der Rechteverwaltung"),
    (r"\bArbeitsschlange\b|\bSchlange\b",
     "'Auftragsliste' (Festlegung mc 2026-07-31)"),
    (r"\bRepository\b|\bCommit\b|\bAPI\b|\bJSON\b|\bCache\b",
     "Entwicklerbegriff - ohne Entsprechung in der Anwendersprache"),
    (r"_<uid>\.db|\.db\b",
     "Dateinamen nicht nennen; 'die Falldateien des Kontos'"),
    (r"\blocalStorage\b|\bDOM\b|\bRegex\b",
     "Entwicklerbegriff"),
)

_JARGON_KOMPILIERT: Tuple[Tuple["re.Pattern", str, str], ...] = tuple(
    (re.compile(muster), muster, rat) for muster, rat in JARGON)


#: WOERTLICHE BILDSCHIRMZITATE - die einzige zulaessige Ausnahme von Regel H-1.
#:
#: ANLASS (Build 604, Gruppe "Administration"): die Rechte-Sicht fuehrt zwei
#: Spalten, die auf dem Bildschirm "Faehigkeit" und "Scope" heissen. Regel H-1
#: verbietet beide Woerter - zu Recht, denn in der HILFE sind sie Jargon. Aber
#: eine Hilfe, die eine Spalte anders nennt als der Bildschirm, ist schlechter
#: als eine mit Jargon: die suchende Person findet die Spalte dann gar nicht.
#:
#: Deshalb duerfen diese Woerter stehen, wenn sie ALS ZITAT gekennzeichnet sind
#: - in deutschen Anfuehrungszeichen, genau so geschrieben wie auf dem Schirm.
#: Der Fliesstext daneben benutzt weiterhin die Anwendersprache ("Recht",
#: "Umfang"). Damit die Liste kein Schlupfloch wird, prueft SP08, dass jedes
#: Zitat WIRKLICH als sichtbarer Text im Bestand vorkommt.
BILDSCHIRMZITATE: Tuple[str, ...] = (
    "„Faehigkeit“",
    "„Scope“",
)


def verify_anwendersprache(register: HilfeRegister) -> None:
    """
    Regel H-1: Hilfetexte sind in Anwendersprache verfasst.

    Geprueft werden ALLE Texte, die eine anwendende Person zu sehen bekommt:
    Kapiteltitel, Rechtelage, Abschnittsueberschriften, Absaetze, Listenpunkte
    und die Popup-Texte. Nicht geprueft werden Quelltext-Kommentare - dort ist
    Entwicklersprache richtig.

    Woertliche Bildschirmzitate (BILDSCHIRMZITATE) werden vor der Pruefung
    entfernt: sie benennen, was auf dem Schirm steht, und sind damit keine
    Sprachwahl der Hilfe, sondern eine Ortsangabe.
    """
    fehler: List[str] = []
    for herkunft, text in _texte(register):
        if not text:
            continue
        for zitat in BILDSCHIRMZITATE:
            text = text.replace(zitat, "")
        for muster, roh, rat in _JARGON_KOMPILIERT:
            treffer = muster.search(text)
            if treffer is None:
                continue
            fehler.append("%s: '%s' -> %s"
                          % (herkunft, treffer.group(0), rat))
    if fehler:
        raise HilfeSpracheError(
            "Regel H-1 verletzt (Anwendersprache): %s" % "; ".join(fehler))


# -----------------------------------------------------------------------------
# 5) Sammelpruefung
# -----------------------------------------------------------------------------

def verify_shell_kontext(register: HilfeRegister,
                         sicht_ids: Sequence[str] = SICHT_IDS) -> None:
    """
    Der Shell-Bestand (Build 591 / H4):
      * jeder Schluessel traegt den reservierten Praefix 'shell.',
      * 'shell' ist KEINE Sicht-ID (der Praefix bleibt eindeutig),
      * kein Sichtkapitel benutzt den Praefix.

    Warum die zweite Regel: Kaeme irgendwann eine Sicht mit der ID 'shell'
    hinzu, waeren Shell- und Sichtschluessel nicht mehr unterscheidbar - und
    zwar STILL, weil beide dieselbe Form haben.
    """
    if SHELL_PRAEFIX in set(sicht_ids):
        raise HilfePruefungError(
            "Der Praefix '%s' ist fuer die Shell-Kontexthilfe reserviert, "
            "wird aber im Sichtenkatalog als Sicht-ID gefuehrt."
            % SHELL_PRAEFIX)
    falsch = sorted(k.schluessel for k in register.shell
                    if k.sicht != SHELL_PRAEFIX)
    if falsch:
        raise HilfePruefungError(
            "Shell-Kontexthilfen ohne Praefix '%s.': %s"
            % (SHELL_PRAEFIX, ", ".join(falsch)))
    fremd = sorted(k.schluessel for s in register.sichten for k in s.kontext
                   if k.sicht == SHELL_PRAEFIX)
    if fremd:
        raise HilfePruefungError(
            "Sichtkapitel benutzen den reservierten Shell-Praefix: %s"
            % ", ".join(fremd))


def verify_alles(register: HilfeRegister,
                 erlaubte_luecken: Iterable[str] = (),
                 sicht_ids: Sequence[str] = SICHT_IDS) -> None:
    """
    Alle Registerpruefungen in einem Aufruf - der Einstieg fuer den
    Regressionstest und (ab H2) fuer den Serverstart.
    """
    verify_sichten_abgedeckt(register, erlaubte_luecken, sicht_ids)
    verify_gliederung(register)
    verify_kontextschluessel(register)
    verify_shell_kontext(register, sicht_ids)
    verify_verweise(register)
    verify_fallinhaltsfrei(register)
    verify_anwendersprache(register)


def katalog_bezug(sicht_id: str) -> Dict[str, object]:
    """
    Kleine Auskunft fuer Renderer und Tests: die Katalogdaten einer Sicht als
    einfaches Woerterbuch (leer, wenn es die Sicht nicht gibt).
    """
    e = sicht(sicht_id)
    if e is None:
        return {}
    return {"id": e.id, "label": e.label, "gruppe": e.gruppe,
            "rechte": list(e.rechte()), "immer": e.immer,
            "stichworte": e.stichworte}
