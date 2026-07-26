# =============================================================================
# management/search/zweck_vokabular.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Volltextsuche (AP-3E, B561)
# =============================================================================
# Zweck:
#   Die ZWECKCODES der falluebergreifenden Volltextsuche — WAHRHEITSQUELLE IM
#   CODE. Die Katalogtabelle 'fulltext_zweck' in coordinator.db wird aus dieser
#   Liste geseedet (M036), damit die FK-Integritaet von 'fulltext_release'
#   gesichert ist.
#
#   Kein Klassenmodul (Grundregel 10 betrifft Klassen) — Konstanten und reine
#   Funktionen. Eigene Datei, weil die Codes an vier Stellen gebraucht werden:
#   Migration (561), Schreibpfad der Freigabe (561), Abfrage-Endpunkte (562)
#   und Auswahlliste der Sicht (563).
#
# ── DIE ENTSCHEIDUNG DAHINTER (mc 2026-07-26, Entscheidungen §1 E-3) ────────
#
#   Jede Abfrage — Stufe 1 UND Stufe 2 — verlangt eine Zweckangabe, und zwar
#   als AUSWAHLLISTE FESTER CODES, nicht als Freitext.
#
#   Das war eine Abweichung von meinem eigenen Vorschlag ('nur bei Stufe 2'),
#   und die Begruendung dafuer traegt: Freitext nutzt sich zur Floskel ab; nach
#   dem dritten Eintrag steht ueberall 'Recherche'. Codes dagegen sind
#   AUSWERTBAR — die Leitung sieht, WOFUER die Suche benutzt wird, nicht nur
#   DASS sie benutzt wird. Genau das ist bei einer Funktion, die den
#   Arbeitsstand fremder Faelle beruehrt, der Unterschied zwischen einer
#   Protokollzeile und einer Aufsichtsmoeglichkeit.
#
# ── DER ANTEIL 'sonstiges' IST EINE KENNZAHL, KEIN SAMMELBECKEN ─────────────
#
#   Ist die Liste unvollstaendig, drueckt sie den echten Zweck nach
#   'sonstiges'. Deshalb ist bei 'sonstiges' ein Freitext PFLICHT (sonst waere
#   der Sammelcode ein Weg an der Begruendung vorbei), und deshalb weist die
#   Sicht den ANTEIL 'sonstiges' als Kennzahl aus: steigt er, FEHLT EIN CODE.
#   Dann wird die Liste ERGAENZT — nicht der Sammelcode ausgeweitet.
#
# ── ZWEI SPALTEN, NICHT EINE — EINE BEWUSSTE ABWEICHUNG VOM TATZEIT-MUSTER ──
#
#   db/tatzeit_vokabular.py legt den Freitext im SELBEN Feld ab
#   ("sonstiges:<Freitext>"). Diese Loesung war dort RICHTIG und ist hier
#   FALSCH — und der Unterschied ist keine Geschmacksfrage:
#
#   Bei der Tatzeit stand die Spalte in einer Beweismitteldatenbank UNTER
#   MIGRATIONSVORBEHALT (m002, seit Build 532). Eine zweite Spalte waere dort
#   ein Umbau an einer Datei mit Ermittlerdaten gewesen — fuer eine reine
#   Formatfrage. Der Doppelpunkt war der kleinere Preis.
#
#   Hier entsteht eine NEUE Tabelle in coordinator.db, ohne Vorbehalt und ohne
#   Bestand. Es gibt keinen Preis zu zahlen — und damit faellt der Grund weg,
#   auf referentielle Integritaet zu verzichten. 'fulltext_release' fuehrt
#   deshalb ZWEI Spalten:
#
#       zweck_code      TEXT NOT NULL REFERENCES fulltext_zweck(code)
#       zweck_freitext  TEXT           (NULL, ausser bei 'sonstiges')
#
#   Der FREMDSCHLUESSEL ist der eigentliche Gewinn: ein Tippfehler im Code
#   wird von der DATENBANK abgelehnt, nicht erst von der Anwendung. Bei der
#   zusammengesetzten Ablageform waere er unmoeglich gewesen — 'sonstiges:x'
#   passt auf keinen Katalogeintrag. Genau deshalb gibt es die Katalogtabelle
#   ueberhaupt (Entscheidung mc: "Die Codeliste ist eine weitere
#   Katalogtabelle").
#
#   Der Preis ist eine Spalte mehr und die Regel, dass sie nur bei
#   'sonstiges' gefuellt sein darf. Sie steht als CHECK IN DER TABELLE und
#   nicht nur im Code — eine Regel, die nur die Anwendung kennt, gilt genau
#   so lange, wie alle Schreibpfade durch die Anwendung laufen.
#
# ── DIE GRUNDMENGE IST BESTAETIGUNGSBEDUERFTIG ──────────────────────────────
#
#   E-3 nennt die vier Codes ausdruecklich 'zur Bestaetigung beim Bau'. Sie
#   sind hier so umgesetzt, wie sie im Entscheidungsdokument stehen. Solange
#   mc sie nicht bestaetigt hat, ist eine Umbenennung noch billig; nach der
#   ersten erteilten Freigabe ist sie es NICHT MEHR — Codes sind stabile
#   Bezeichner und werden ERGAENZT, nie umbenannt oder wiederverwendet
#   (dieselbe Regel wie beim RBAC-Katalog und bei den EventTypes). Eine
#   Umbenennung entwertete jeden bereits erzeugten Beleg einer Suche.
#
# Version: v0.8.561 · Build: 561 · 2026-07-26
# =============================================================================

from typing import Dict, FrozenSet, NamedTuple, Optional, Tuple


class Zweck(NamedTuple):
    """Ein Zweckcode: stabiler Code + Anzeigelabel + Erlaeuterung."""

    code: str
    label: str
    beschreibung: str
    #: True, wenn zusaetzlich ein Freitext PFLICHT ist.
    freitext_pflicht: bool


ZWECK_SONSTIGES = "sonstiges"

# --- Die Grundmenge (Entscheidungen mc 2026-07-26 §1 E-3) --------------------
#   Reihenfolge = Anzeigereihenfolge in der Auswahlliste. 'sonstiges' steht
#   ABSICHTLICH ZULETZT: eine Auswahlliste wird von oben gelesen, und der
#   Sammelcode soll nicht der bequemste Griff sein.
ZWECKE: Tuple[Zweck, ...] = (
    Zweck("kreuzbezug_nickname", "Kreuzbezug zu einem Nickname",
          "Pruefen, ob ein im eigenen Fall aufgetretener Nickname in einem "
          "anderen Verfahren bereits aufgefallen ist. Der Hauptzweck der "
          "Funktion.", False),
    Zweck("alias_pruefung", "Alias-/Identitaetspruefung",
          "Pruefen, ob ein Alias oder eine Schreibvariante bereits einer "
          "Identitaetsgruppe zugeordnet wurde (Anschluss an den "
          "Alias-Katalog aus AP-2A).", False),
    Zweck("wiedervorlage", "Wiedervorlage / Nachschau",
          "Erneute Nachschau zu einem frueher bearbeiteten Begriff, etwa vor "
          "einer Wiedervorlage oder vor der Abgabe an die StA.", False),
    Zweck(ZWECK_SONSTIGES, "Sonstiges (Begruendung erforderlich)",
          "Ein Zweck, den die Liste nicht abbildet. Der Freitext ist PFLICHT. "
          "Der Anteil dieses Codes ist die Kennzahl dafuer, ob die Liste "
          "vollstaendig ist — steigt er, fehlt ein Code.", True),
)

ZWECK_CODES: FrozenSet[str] = frozenset(z.code for z in ZWECKE)

ZWECK_NACH_CODE: Dict[str, Zweck] = {z.code: z for z in ZWECKE}


class ZweckFehler(ValueError):
    """
    Die Zweckangabe ist unbrauchbar.

    EIGENE Ausnahme, damit der Endpunkt (Build 562) sie von einem
    Programmfehler unterscheiden und als 400 mit Klartext beantworten kann.
    Eine Abfrage OHNE brauchbare Zweckangabe wird NICHT ausgefuehrt — sie
    still mit einem Standardzweck laufen zu lassen, waere die Umgehung genau
    der Entscheidung, die E-3 getroffen hat.
    """


def ist_zweck(code: object) -> bool:
    """True, wenn code ein bekannter Zweckcode ist."""
    return isinstance(code, str) and code in ZWECK_CODES


def braucht_freitext(code: object) -> bool:
    """True, wenn zu diesem Code ein Freitext Pflicht ist."""
    z = ZWECK_NACH_CODE.get(code) if isinstance(code, str) else None
    return bool(z and z.freitext_pflicht)


def pruefe(code: object,
           freitext: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """
    Prueft die Zweckangabe und liefert die beiden Spaltenwerte.

    Rueckgabe:
        (zweck_code, zweck_freitext) — der Freitext ist None, ausser bei
        einem Code mit Freitextpflicht.

    Raises:
        ZweckFehler: unbekannter Code, fehlender Pflichtfreitext, oder ein
                     Freitext zu einem Code, der keinen vorsieht.

    HART UND NICHT NACHSICHTIG, anders als bei der Moduswahl der Suche
    (index_vokabular.normalisiere_suchmodus): der Suchmodus ist eine
    Bedienvorliebe, die Zweckangabe ist BESTANDTEIL DES BELEGS. Ein
    stillschweigender Rueckfall auf einen Standardzweck erzeugte einen Beleg,
    der etwas anderes behauptet, als der Mensch angegeben hat.
    """
    if not ist_zweck(code):
        raise ZweckFehler(
            "Unbekannte Zweckangabe %r. Zulaessig sind: %s."
            % (code, ", ".join(z.code for z in ZWECKE)))
    text = (freitext or "").strip()
    if braucht_freitext(code):
        if not text:
            raise ZweckFehler(
                "Bei '%s' ist eine Begruendung im Freitext Pflicht — sonst "
                "waere der Sammelcode ein Weg an der Begruendung vorbei."
                % code)
        return str(code), text
    if text:
        # Ein Freitext zu einem Code, der keinen braucht, wird NICHT still
        # verworfen und NICHT still mitgeschrieben: beides waere eine
        # Abweichung zwischen dem, was der Mensch eingegeben hat, und dem,
        # was im Beleg steht.
        raise ZweckFehler(
            "Zu '%s' ist kein Freitext vorgesehen. Wenn die Angabe nicht "
            "passt, ist '%s' mit Begruendung zu waehlen — oder der Liste "
            "fehlt ein Code." % (code, ZWECK_SONSTIGES))
    return str(code), None


def klartext(code: object, freitext: Optional[str] = None) -> str:
    """
    Anzeigetext zu einer gespeicherten Zweckangabe (Sicht, Bericht).

    Ein unbekannter Code wird NICHT zu einem gueltigen zurechtgebogen: er
    erscheint als 'unbekannter Zweck (<code>)'. In einem Bestand, der aelter
    ist als diese Liste, ist das die richtige Auskunft — nicht 'sonstiges'.
    """
    z = ZWECK_NACH_CODE.get(code) if isinstance(code, str) else None
    text = (freitext or "").strip()
    if z is None:
        roh = code if isinstance(code, str) and code else "leer"
        return ("unbekannter Zweck (%s): %s" % (roh, text) if text
                else "unbekannter Zweck (%s)" % roh)
    return "%s: %s" % (z.label, text) if text else z.label


def _pruefe_vokabular() -> None:
    """
    Selbstpruefung beim Import — ein Tippfehler faellt beim SERVERSTART auf.

    Geprueft wird, was sich sonst still auswirken wuerde:
      * doppelte Codes (die Auswertung 'wofuer wird gesucht' waere falsch),
      * ein leerer oder ungetrimmter Code (er wuerde am Fremdschluessel
        scheitern, aber erst beim ersten Schreibversuch statt beim Start),
      * ein fehlender Sammelcode (ohne ihn gaebe es keinen zulaessigen Weg
        fuer einen Zweck, den die Liste nicht kennt — und dann wuerde
        irgendein passender Code genommen, was den Beleg wertlos machte).
    """
    codes = [z.code for z in ZWECKE]
    if len(codes) != len(set(codes)):
        raise ValueError("zweck_vokabular: doppelter Zweckcode in ZWECKE")
    for c in codes:
        if not c or c != c.strip():
            raise ValueError("zweck_vokabular: leerer/ungetrimmter Code: %r" % c)
    if ZWECK_SONSTIGES not in ZWECK_CODES:
        raise ValueError(
            "zweck_vokabular: der Sammelcode %r fehlt." % ZWECK_SONSTIGES)
    if not braucht_freitext(ZWECK_SONSTIGES):
        raise ValueError(
            "zweck_vokabular: %r ohne Freitextpflicht — dann waere der "
            "Sammelcode ein Weg an der Begruendung vorbei (E-3)."
            % ZWECK_SONSTIGES)


_pruefe_vokabular()
