# =============================================================================
# management/help/sichtbarkeit.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H2)
# =============================================================================
# Zweck:
#   Die Capability-Sperre der Vollhilfe (Entscheidung E1, mc 2026-07-30):
#   Eine Person sieht in der Hilfe GENAU die Kapitel der Sichten, die sie auch
#   in der Navigation sieht - im Inhaltsverzeichnis, in der Suche und im
#   Inhalt.
#
#   WARUM DIE FILTERUNG EINE EIGENE, REINE FUNKTION IST (gesicherte
#   Erkenntnis): Eine Sperre, die im Renderer oder in der Route verstreut
#   liegt, laesst sich nicht gegen eine Rechte-Matrix pruefen - man kann sie
#   nur "im Betrieb ausprobieren", und das ist fuer eine Zugriffsbeschraenkung
#   zu wenig. Als vorgelagerte reine Funktion ist sie mit einem Tisch von
#   Rechtesaetzen -> erwarteten Kapitelmengen belegbar.
#
#   WARUM SERVERSEITIG (E1, Konzept §3.3): Ein clientseitiges Ausblenden
#   koennte man umgehen (Entwicklerwerkzeuge, direkte URL). Der Server
#   liefert gefiltert aus; ein Direktaufruf ohne Recht antwortet 403.
#
#   DIE AUSNAHME, und nur diese eine: 'viewprefs' (Sicht ohne Rechtepruefung,
#   Beleg cockpit.js:337-348) sowie die Hilfe-Grundlagen sind immer sichtbar.
#   Begruendung dort im Original: "Ein Recht, das man niemandem sinnvoll
#   vorenthalten kann, ist keines." Was fuer die Sicht gilt, gilt fuer ihr
#   Kapitel.
#
#   DIE LOGIK IST DIESELBE WIE visibleViews() in cockpit.js:401-409 - any-of
#   ueber die Rechte des Katalogeintrags, 'immer' umgeht die Pruefung. Sie ist
#   hier NICHT neu erfunden, sondern nachgebildet; ein Test haelt beide
#   Auffassungen zusammen.
#
#   Reine Funktionen, kein DB-/Netz-/Uhrzugriff.
#
# Version: v0.8.589 - Build: 589 - 2026-07-31
# =============================================================================

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from management.help.modell import HilfeRegister, Sichthilfe
from management.help.sicht_katalog import (
    SICHT_KATALOG, SichtEintrag, sicht as katalog_sicht,
)


def hat_recht(capabilities: Iterable[str], eintrag: SichtEintrag) -> bool:
    """
    Darf diese Person diese Sicht sehen? Nachbildung von visibleViews()
    (cockpit.js:401-409):
      * 'immer: true' -> ja, ohne Pruefung,
      * sonst genuegt EINES der Rechte des Eintrags (any-of).
    """
    if eintrag.immer:
        return True
    besitz = set(capabilities)
    return any(r in besitz for r in eintrag.rechte())


def sichtbare_sicht_ids(capabilities: Iterable[str],
                        katalog: Sequence[SichtEintrag] = SICHT_KATALOG
                        ) -> Tuple[str, ...]:
    """Die IDs der fuer diese Person sichtbaren Sichten, in Katalogfolge."""
    besitz = set(capabilities)
    return tuple(e.id for e in katalog if hat_recht(besitz, e))


def sichtbare_kapitel(register: HilfeRegister,
                      capabilities: Iterable[str],
                      katalog: Sequence[SichtEintrag] = SICHT_KATALOG
                      ) -> Tuple[Sichthilfe, ...]:
    """
    Die Kapitel, die diese Person sehen darf - in KATALOGREIHENFOLGE, nicht in
    Registerreihenfolge.

    Warum Katalogreihenfolge: Das Handbuch soll so geordnet sein wie die
    Navigation, sonst sucht man zweimal. Das Register kann in beliebiger
    Reihenfolge zusammengebaut worden sein; massgeblich ist der Katalog.

    Ein Kapitel zu einer Sicht, die es im Katalog NICHT gibt, erscheint hier
    NICHT - das waere ein Waisenkapitel, und pruefung.verify_sichten_abgedeckt
    verhindert es ohnehin schon beim Bauen. Hier wird es zusaetzlich nicht
    ausgeliefert: eine Sperre, die auf einer Vollstaendigkeitspruefung an
    anderer Stelle beruht, waere keine.
    """
    erlaubt = set(sichtbare_sicht_ids(capabilities, katalog))
    return tuple(k for e in katalog
                 for k in (register.get(e.id),)
                 if k is not None and e.id in erlaubt)


def darf_kapitel(sicht_id: str, capabilities: Iterable[str]) -> bool:
    """
    Einzelpruefung fuer den Direktaufruf /api/help/sicht/<id>.

    Eine unbekannte Sicht-ID ist NICHT "verboten", sondern "gibt es nicht" -
    die Route unterscheidet 404 und 403 bewusst. Hier liefert sie False, und
    die Route entscheidet anhand des Katalogs, welcher Status richtig ist.
    """
    e = katalog_sicht(sicht_id)
    if e is None:
        return False
    return hat_recht(capabilities, e)


def gruppen_mit_kapiteln(kapitel: Sequence[Sichthilfe],
                         katalog: Sequence[SichtEintrag] = SICHT_KATALOG
                         ) -> List[Tuple[str, List[Sichthilfe]]]:
    """
    Gliedert die (bereits gefilterten) Kapitel nach Nav-Gruppen, in
    Katalogfolge. Gruppen ohne sichtbares Kapitel entfallen - eine leere
    Gruppenueberschrift im Inhaltsverzeichnis waere ein Hinweis darauf, dass
    es dort etwas gibt, das man nicht sehen darf. Genau das soll die strenge
    Lesart von E1 vermeiden.
    """
    ordnung: Dict[str, str] = {e.id: e.gruppe for e in katalog}
    gruppenfolge: List[str] = []
    for e in katalog:
        if e.gruppe not in gruppenfolge:
            gruppenfolge.append(e.gruppe)

    nach_gruppe: Dict[str, List[Sichthilfe]] = {}
    for k in kapitel:
        g = ordnung.get(k.sicht)
        if g is None:
            continue
        nach_gruppe.setdefault(g, []).append(k)

    return [(g, nach_gruppe[g]) for g in gruppenfolge if g in nach_gruppe]


def capabilities_aus_policy(policy) -> Tuple[str, ...]:
    """
    Kleiner Adapter: PersonPolicy -> Menge der Rechte-Codes. Bewusst als
    Funktion und nicht als Direktzugriff in der Route, damit die Route keine
    Annahme ueber die innere Form der Policy trifft (heute ein dict
    Code -> Scope; das war schon einmal anders).
    """
    caps = getattr(policy, "capabilities", None)
    if not caps:
        return ()
    return tuple(sorted(caps))
