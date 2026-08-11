# =============================================================================
# management/viewprefs/viewpref_katalog.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3G (Build 545)
# =============================================================================
# Zweck:
#   Der KATALOG dessen, was eine Person an ihrer Oberflaeche einstellen darf:
#   welche Sichten sie umsortieren/ausblenden kann und welche Kacheln im
#   Ueberblick zur Wahl stehen. Er ist die Pruefinstanz des Schreibpfades —
#   ein Schluessel, der hier nicht steht, wird NICHT gespeichert.
#
# ── WARUM DER SICHTEN-KATALOG HIER EINE KOPIE IST ───────────────────────────
#
#   Die Wahrheitsquelle der Sichten ist und bleibt VIEW_CATALOG in
#   management/server/static/cockpit.js. Der Server braucht die Liste
#   trotzdem, weil er sonst jeden beliebigen Schluessel speichern wuerde und
#   die Datenbank sich mit Eintraegen fuellte, zu denen es nie eine Sicht gab.
#
#   Damit die Kopie nicht abdriftet, haelt ein Test sie gegen cockpit.js —
#   dasselbe Verfahren wie VE08 in tests/test_view_export_api.py, das den
#   Export-Katalog absichert. Eine kuenftige neue Sicht faellt so nicht STILL
#   aus der Steuerung heraus, sondern bricht die Suite.
#
# ── WARUM DIE KACHELN NUR HIER STEHEN (und nicht auch im Browser) ───────────
#
#   Umgekehrter Fall: Kacheln gibt es vor diesem Build gar nicht. Sie bekommen
#   deshalb GENAU EINE Wahrheitsquelle, und zwar diese — der Browser holt den
#   Katalog ueber GET /api/viewprefs und rendert, was er bekommt. Der Grund ist
#   nicht Sparsamkeit: an jeder Kachel haengt eine FAEHIGKEIT, und wer die
#   Zuordnung Kachel->Recht im Browser fuehrt, fuehrt sie an einer Stelle, die
#   der Server nicht kennt.
#
# ── JEDE KACHEL SPEIST SICH AUS EINEM BESTEHENDEN ENDPUNKT ──────────────────
#
#   'api_path' verweist ausnahmslos auf einen Endpunkt, den es bereits gibt.
#   Dieses Arbeitspaket legt KEINEN neuen Datenweg an. Das ist die Zusicherung,
#   die den Umfang klein haelt: eine Kachel ist eine zweite, gedraengte
#   Darstellung von etwas, das die zugehoerige Sicht ohnehin schon zeigt — und
#   sie erbt damit deren Rechtepruefung, Scope und Fehlerbild.
#
# ── ZUR AUSBLENDBARKEIT (die heikle Stelle dieses Arbeitspakets) ────────────
#
#   Eine ausgeblendete Sicht koennte eine uebersehene Eskalation bedeuten. Das
#   ist die einzige Stelle, an der eine Bedienvorliebe an Grundregel 1 ruehrt.
#   Die Antwort ist NICHT, das Ausblenden zu verbieten — dann richtete sich
#   jeder seine Oberflaeche eben nicht ein und die Sicht bliebe trotzdem
#   ungelesen. Die Antwort ist, dass nichts STILL verschwindet:
#
#     (a) Die Navigation traegt dauerhaft einen Zaehler "N Sichten
#         ausgeblendet" (Build 546).
#     (b) Ausgeblendete Sichten bleiben ueber die Kommandopalette (Strg-K)
#         erreichbar — die Palette bekommt bewusst die NUR rechte-gefilterte
#         Liste (cockpit.js boot(), getViews).
#     (c) Ein Klick setzt auf Werkseinstellung zurueck.
#     (d) Die Sicht 'viewprefs' selbst ist nicht ausblendbar (s.
#         NICHT_STEUERBAR) — sonst koennte sich jemand den Rueckweg zumauern.
#
#   Und: die Zeilen sind auswertbar. "Wer hat die Eskalationssicht
#   ausgeblendet?" ist ein SELECT und keine JSON-Zerlegung (s. Kopf von
#   m037_view_pref.py).
#
# Version: v0.8.545 · Build: 545 · 2026-07-26
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

#: Die beiden Arten von Elementen. EINGEFROREN — die Migration M037 fuehrt
#  dieselben Werte als CHECK und importiert diese Stelle NICHT (m005-Prinzip).
#  Ein Test haelt beide gegeneinander.
ARTEN: Tuple[str, ...] = ("sicht", "widget")

ART_SICHT = "sicht"
ART_WIDGET = "widget"

#: Die steuerbaren Sichten, in der Reihenfolge des VIEW_CATALOG aus cockpit.js
#  (Stand 0.8.544). Wer hier etwas ergaenzt, ergaenzt eine Sicht, die es im
#  Cockpit auch gibt — der Konsistenztest erzwingt das.
STEUERBARE_SICHTEN: Tuple[str, ...] = (
    "dashboard", "calendar", "escalation", "nextactions",
    "assignment", "cases", "mentoring", "notes",
    "reports", "lectorate", "approval",
    "templates", "doctemplates", "modules",
    "results", "stats", "planung", "annostats",
    "limitation", "matrix", "qs", "workload", "capacity", "support",
    "mycases", "myhistory",
    "policy", "integrity", "audit", "handover", "retention",
    "promotion", "releases", "onboarding", "personnel",
    "crossref", "crossfindings", "alias", "merge", "search",
    # Build 574: die Falluebersicht. Steuerbar wie jede Arbeitssicht;
    # wer sie nicht braucht, blendet sie aus. Der Zaehler der
    # ausgeblendeten Sichten fuehrt zurueck.
    "faelle",
    # Build 559: die Pflegeflaeche der Kapazitaet. Steuerbar wie jede
    # andere Arbeitssicht — wer sie nicht braucht, blendet sie aus.
    "capacity_pflege",
)

#: Sichten, die es im Cockpit gibt, die aber bewusst NICHT steuerbar sind.
#  Jeder Eintrag braucht einen Grund — eine wortlose Ausnahmeliste waere eine
#  Hintertuer.
NICHT_STEUERBAR: Dict[str, str] = {
    # Build 546: die Sicht, mit der man einstellt, darf sich nicht selbst
    # wegstellen. Waere sie ausblendbar, koennte sich jemand mit einem Klick
    # den Rueckweg zumauern — und der einzige Ausweg waere ein Eingriff in die
    # Datenbank. Sie traegt ausserdem als EINZIGE Sicht kein Recht
    # ('immer: true' in cockpit.js), weil es an ihr nichts zu schuetzen gibt.
    "viewprefs": "Die Einstellsicht selbst — sonst liesse sich der Rueckweg "
                 "zumauern.",
}


@dataclass(frozen=True)
class WidgetSpec:
    """
    Eine Kachel des Ueberblicks.

    key          — stabile Kennung; sie steht in person_view_pref.element_key
                   und darf sich NIE aendern (sonst zeigt eine gespeicherte
                   Vorliebe ins Leere).
    label        — deutsche Beschriftung fuer die Oberflaeche.
    beschreibung — ein Satz, der sagt, was die Kachel zeigt. Er steht in der
                   Auswahlliste; eine Kachel, deren Zweck man raten muss, wird
                   nicht eingeschaltet.
    cap          — die Faehigkeit, die der speisende Endpunkt ohnehin prueft.
                   Sie wird hier gefuehrt, damit der SERVER sagen kann, ob die
                   Kachel fuer diese Person ueberhaupt in Frage kommt.
    api_path     — der BESTEHENDE lesende Endpunkt (kein neuer Datenweg).
    standard     — gehoert die Kachel zur Werkseinstellung?
    """
    key: str
    label: str
    beschreibung: str
    cap: str
    api_path: str
    standard: bool = False


#: Der Kachel-Katalog. Reihenfolge = Reihenfolge der Werkseinstellung bzw. der
#  Auswahlliste.
#
#  DIE WERKSEINSTELLUNG IST GENAU EINE KACHEL: die Fall-Uebersicht. Damit sieht
#  der Ueberblick ohne gespeicherte Vorliebe AUS WIE BISHER (eine Tabulator-
#  Tabelle ueber /api/overview). Wer nichts einstellt, merkt von diesem
#  Arbeitspaket nichts — das ist Absicht und keine Sparsamkeit: eine Aenderung,
#  die allen die gewohnte Oberflaeche umbaut, waere im Produktivbetrieb ab
#  01.07.2026 der falsche Weg.
WIDGETS: Tuple[WidgetSpec, ...] = (
    # BUILD 698 (Vorgang 60fe72fb): cap von 'dashboard.view' auf
    # 'caseoverview.view'. Diese Kachel war die EINZIGE ohne eigenes Recht —
    # sie lief auf dem Recht des Rahmens mit, waehrend jede andere Kachel hier
    # ihr eigenes fuehrt. Damit bekam jede Person, die den Überblick öffnen
    # darf, die vollständige Fallliste ungefragt dazu.
    #
    # DIE KACHEL BLEIBT WERKSEINSTELLUNG (standard=True). Wer das neue Recht
    # nicht hat, sieht sie deshalb trotzdem nicht: der Rechtefilter läuft
    # zuletzt. Die Werkseinstellung sagt, was jemand SEHEN WOLLTE, nicht, was
    # er sehen DARF — diese beiden Fragen getrennt zu halten ist der Grund,
    # warum die Kachelauswahl kein Zugangsmittel ist.
    WidgetSpec(
        key="fallampel", label="Fall-Übersicht (Ampel)",
        beschreibung="Die Fälle mit Ampel, Priorität und Zuweisung — "
                     "dieselbe Tabelle wie bisher im Überblick.",
        cap="caseoverview.view", api_path="/api/overview", standard=True),
    WidgetSpec(
        key="eskalationen", label="Eskalationen",
        beschreibung="Was über eine Schwelle gelaufen ist, gedrängt auf die "
                     "obersten Einträge.",
        cap="escalation.view", api_path="/api/escalations"),
    WidgetSpec(
        key="naechste_aktion", label="Nächstbeste Aktion",
        beschreibung="Die vordersten Einträge der Arbeitsschlange.",
        cap="nextactions.view", api_path="/api/next_actions"),
    WidgetSpec(
        key="wiedervorlage", label="Fällige Wiedervorlagen",
        beschreibung="Externe Vorgänge, deren Frist erreicht oder "
                     "überschritten ist.",
        cap="external.view", api_path="/api/external"),
    WidgetSpec(
        key="fristen", label="Fristen mit Vorwarnung",
        beschreibung="Fälle, deren Verjährungsfrist in den Vorwarnbereich "
                     "läuft. Der Verjährungsvorbehalt fährt mit.",
        cap="limitation.view", api_path="/api/limitation"),
    WidgetSpec(
        key="lastverteilung", label="Lastverteilung",
        beschreibung="Aktive Fälle je Ermittler:in samt Überlastwarnung.",
        cap="workload.view", api_path="/api/workload"),
    WidgetSpec(
        key="meine_auftraege", label="Meine Aufträge",
        beschreibung="Die eigenen offenen Zuweisungen.",
        cap="mycases.view", api_path="/api/mycases"),
    # Der "eigene, nur fuer ihn sichtbare Bereich" des Administrators aus
    # Idee 37 (§15 des Ideenpapiers). Er ist nicht dadurch verborgen, dass die
    # Oberflaeche ihn versteckt, sondern dadurch, dass 'ops.view' ihn traegt.
    WidgetSpec(
        key="kettenzustand", label="Zustand der Audit-Kette",
        beschreibung="Ergebnis der Kettenprüfung und die aktuelle Spitze — "
                     "der Betriebsblick für die Administration.",
        cap="ops.view", api_path="/api/integrity"),
)

_WIDGET_BY_KEY: Dict[str, WidgetSpec] = {w.key: w for w in WIDGETS}
_SICHTEN_SET = frozenset(STEUERBARE_SICHTEN)


def widget_spec(key: str) -> Optional[WidgetSpec]:
    """Die Kachel zu einem Schluessel — oder None."""
    return _WIDGET_BY_KEY.get(key)


def bekannte_schluessel(art: str) -> Tuple[str, ...]:
    """
    Die zulaessigen Schluessel einer Art, in Katalogreihenfolge.

    Unbekannte Art -> leeres Tupel. Der Aufrufer prueft die Art vorher
    ausdruecklich (viewpref_repo._pruefe_art); hier wird nicht geraten.
    """
    if art == ART_SICHT:
        return STEUERBARE_SICHTEN
    if art == ART_WIDGET:
        return tuple(w.key for w in WIDGETS)
    return ()


def ist_bekannt(art: str, key: str) -> bool:
    """Kennt der Katalog diesen Schluessel unter dieser Art?"""
    if art == ART_SICHT:
        return key in _SICHTEN_SET
    if art == ART_WIDGET:
        return key in _WIDGET_BY_KEY
    return False


def standard_widgets() -> Tuple[str, ...]:
    """Die Kacheln der Werkseinstellung, in Katalogreihenfolge."""
    return tuple(w.key for w in WIDGETS if w.standard)
