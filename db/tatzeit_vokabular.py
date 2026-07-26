# =============================================================================
# db/tatzeit_vokabular.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A, Build 533)
# =============================================================================
# Zweck:
#   Das kontrollierte Vokabular der Tatzeiterfassung an EINER Stelle: Arten,
#   Genauigkeitsstufen, Quellencodes und die Schluessel fuer unscharfe
#   Angaben. Serverseitige Pruefung inklusive.
#
#   Kein Klassenmodul (Grundregel 10 betrifft Klassen) — hier stehen bewusst
#   nur Konstanten und reine Funktionen. Der Grund fuer die eigene Datei: das
#   Vokabular wird an DREI Stellen gebraucht — vom Repository (Build 533), von
#   der Annotationsmaske (Build 534) und spaeter vom Fristenmonitor
#   (Build 535). Drei Kopien waeren die sicherste Art, sie auseinanderlaufen zu
#   lassen.
#
# ── WARUM CODES UND KEIN FREITEXT (Entscheidung mc 2026-07-26) ───────────────
#
#   Der CHECK in der Migration verlangt nur, dass 'quelle' nicht leer ist
#   (m002:222). Das ist die Untergrenze, nicht das Ziel. Freitext nutzt sich in
#   der Praxis zur Floskel ab; nach dem dritten Eintrag steht ueberall
#   "Beitrag". Codes dagegen sind auswertbar — und hier ist das kein
#   Selbstzweck: 'angabe_beschuldigter' und 'beitragstext' haben voellig
#   verschiedene Belastbarkeit. Als Code laesst sich das im Fristenmonitor
#   unterscheiden, als Freitext nie.
#
#   Der Anteil 'sonstiges' ist die KENNZAHL DAFUER, OB DIESE LISTE VOLLSTAENDIG
#   IST. Steigt er, fehlt ein Code — dann wird die Liste ergaenzt, nicht der
#   Sammelcode ausgeweitet.
#
# ── DIE ABLAGEFORM VON 'sonstiges' ───────────────────────────────────────────
#
#   'annotation_tatzeit' hat GENAU EINE Spalte fuer die Herkunft ('quelle'),
#   und die Migration steht seit Build 532 unter Migrationsvorbehalt — eine
#   zweite Spalte waere ein Umbau an einer Beweismitteldatenbank fuer eine
#   Formatfrage. Der Freitext wird deshalb im selben Feld abgelegt:
#
#       "sonstiges:<Freitext>"
#
#   Das ist eindeutig parsbar, weil KEIN Code einen Doppelpunkt enthaelt
#   (durch _pruefe_codes beim Import erzwungen — ein Tippfehler in der Liste
#   faellt damit beim Serverstart auf, nicht erst beim ersten Eintrag). Alle
#   anderen Codes stehen ohne Zusatz in der Spalte.
#
#   Bewusst NICHT gewaehlt: JSON in der Spalte. Es waere machbar, aber es
#   machte aus einer les- und greifbaren Spalte ein Feld, das man erst
#   deserialisieren muss, um zu wissen, was drinsteht — in einer Datei, die
#   spaeter womoeglich jemand mit einem SQLite-Browser in der Hand sichtet.
#
# ── WEICHE ANGABEN: DIE LISTE IST ABSICHTLICH KURZ ───────────────────────────
#
#   Entscheidung mc 2026-07-26 (Uebergabe §2.2 Nr. 9): unscharfe Angaben ("vor
#   zwei Jahren", "als ich 13 war") sind BIS AUF WEITERES nur als Markierung um
#   den Text festzuhalten, damit der Eintrag nicht verloren geht; die
#   Verarbeitung kommt spaeter. Deshalb gibt es genau einen Schluessel
#   ('markierung') und nicht schon jetzt eine Taxonomie, die niemand
#   festgelegt hat. Erweitern ist billig, eine falsche Bedeutung wieder
#   loszuwerden nicht.
#
# Version: v0.8.533 · Build: 533 · 2026-07-26
# =============================================================================

from typing import Dict, FrozenSet, Optional, Tuple

#: Trennzeichen zwischen Quellencode und Freitext (nur bei QUELLE_SONSTIGES).
QUELLE_SEP: str = ":"

#: Der Sammelcode. Er ist der EINZIGE, bei dem ein Freitext Pflicht ist.
QUELLE_SONSTIGES: str = "sonstiges"

#: Die Arten einer Tatzeitangabe — deckungsgleich mit dem CHECK in
#  management/migrations/evidence/m002_annotation_tatzeit.py:180.
ART_HART: str = "hart"
ART_WEICH: str = "weich"
ARTEN: FrozenSet[str] = frozenset({ART_HART, ART_WEICH})

#: Genauigkeitsstufen — deckungsgleich mit dem CHECK in m002:185-186.
#  'unbestimmt' ist bewusst dabei: sonst wuerde eine unklare Angabe in eine der
#  drei anderen Stufen gedrueckt und truege eine Genauigkeit, die sie nicht hat.
GENAUIGKEITEN: FrozenSet[str] = frozenset(
    {"tag", "monat", "jahr", "unbestimmt"}
)

#: Quellencodes mit ihrer Bedeutung. Die Beschriftung ist Teil des Vokabulars
#  und nicht der Oberflaeche, damit Maske, Bericht und Auswertung dasselbe Wort
#  benutzen.
QUELLEN: Tuple[Tuple[str, str], ...] = (
    ("beitragstext",
     "Beitragstext im Forum"),
    ("profilangabe",
     "Angabe im Benutzerprofil"),
    ("dateiname_metadaten",
     "Dateiname oder Metadaten einer geteilten Datei"),
    ("angabe_beschuldigter",
     "Eigene Angabe des Beschuldigten"),
    ("angabe_dritter",
     "Angabe eines Dritten im Forum"),
    (QUELLE_SONSTIGES,
     "Sonstiges (Freitext erforderlich)"),
)

#: Nur die Codes — fuer schnelle Pruefungen.
QUELLE_CODES: FrozenSet[str] = frozenset(c for c, _l in QUELLEN)

#: Beschriftungen als Abbildung (fuer Maske und Bericht).
QUELLE_LABELS: Dict[str, str] = {c: l for c, l in QUELLEN}

#: Schluessel fuer unscharfe (weiche) Angaben. Siehe Kopf — absichtlich kurz.
SCHLUESSEL_MARKIERUNG: str = "markierung"
ANGABE_SCHLUESSEL: FrozenSet[str] = frozenset({SCHLUESSEL_MARKIERUNG})


class VokabularError(ValueError):
    """Ein Wert liegt ausserhalb des kontrollierten Vokabulars."""


def _pruefe_codes() -> None:
    """
    Startpruefung: kein Quellencode darf das Trennzeichen enthalten, sonst
    waere 'sonstiges:...' nicht mehr eindeutig parsbar. Laeuft beim Import,
    damit ein Tippfehler in der Liste beim SERVERSTART auffaellt und nicht
    erst, wenn eine Ermittlerin die erste Tatzeit erfasst.
    """
    for code, _label in QUELLEN:
        if QUELLE_SEP in code:
            raise VokabularError(
                "Quellencode %r enthaelt das Trennzeichen %r — damit waere "
                "die Ablageform 'sonstiges:<Freitext>' nicht mehr eindeutig."
                % (code, QUELLE_SEP)
            )
        if not code or code != code.strip():
            raise VokabularError(
                "Quellencode %r ist leer oder hat Randleerzeichen." % (code,)
            )


_pruefe_codes()


def quelle_bauen(code: str, freitext: Optional[str] = None) -> str:
    """
    Baut den Spaltenwert fuer 'annotation_tatzeit.quelle'.

    code      — einer aus QUELLE_CODES.
    freitext  — NUR bei QUELLE_SONSTIGES, dort PFLICHT und nicht leer.

    Wirft VokabularError, bevor irgendetwas geschrieben wird.
    """
    code = (code or "").strip()
    if code not in QUELLE_CODES:
        raise VokabularError(
            "Unbekannte Quelle %r. Zulaessig: %s"
            % (code, ", ".join(sorted(QUELLE_CODES)))
        )

    text = (freitext or "").strip()
    if code == QUELLE_SONSTIGES:
        if not text:
            # Ohne diese Pruefung waere 'sonstiges' ein Weg an der Begruendung
            # vorbei — und genau davor warnt die Entscheidung vom 2026-07-26.
            raise VokabularError(
                "Bei der Quelle 'sonstiges' ist ein Freitext PFLICHT — sonst "
                "waere die Herkunft nicht nachvollziehbar."
            )
        return "%s%s%s" % (QUELLE_SONSTIGES, QUELLE_SEP, text)

    if text:
        raise VokabularError(
            "Ein Freitext ist nur bei der Quelle 'sonstiges' zulaessig "
            "(angegeben bei %r). Sonst laege dieselbe Angabe an zwei Orten." % code
        )
    return code


def quelle_zerlegen(wert: str) -> Tuple[str, Optional[str]]:
    """
    Zerlegt einen gespeicherten 'quelle'-Wert in (code, freitext).

    Unbekannte oder alte Werte werden NICHT stillschweigend zu 'sonstiges'
    umgedeutet — sie kommen als (roher Wert, None) zurueck und sind damit als
    ausserhalb des Vokabulars erkennbar. Ein Leser soll sehen, dass hier etwas
    steht, das die Liste nicht kennt.
    """
    if wert is None:
        return ("", None)
    wert = str(wert)
    if wert.startswith(QUELLE_SONSTIGES + QUELLE_SEP):
        return (QUELLE_SONSTIGES, wert[len(QUELLE_SONSTIGES) + len(QUELLE_SEP):])
    return (wert, None)


def quelle_ist_bekannt(wert: str) -> bool:
    """True, wenn der gespeicherte Wert dem kontrollierten Vokabular entspricht."""
    code, freitext = quelle_zerlegen(wert)
    if code not in QUELLE_CODES:
        return False
    if code == QUELLE_SONSTIGES:
        return bool(freitext and freitext.strip())
    return freitext is None


def quellen_katalog() -> Tuple[Dict[str, object], ...]:
    """
    Der Katalog fuer die Maske: Code, Beschriftung und ob ein Freitext
    verlangt wird. Die Oberflaeche soll diese Angabe nicht selbst wissen
    muessen (Build 534 liest sie ueber den Endpunkt).
    """
    return tuple(
        {
            "code": code,
            "label": label,
            "freitext_pflicht": (code == QUELLE_SONSTIGES),
        }
        for code, label in QUELLEN
    )
