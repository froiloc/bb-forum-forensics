# =============================================================================
# management/export/view_export_spec.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem (AP-2B)
# =============================================================================
# Zweck (Idee 5 — Druck-/Akten-Export je Sicht, Build 511):
#   Die BESCHREIBUNG einer exportierbaren Cockpit-Sicht. Reine Datenklassen,
#   kein Verhalten, keine Abhaengigkeiten — damit der Katalog
#   (view_export_catalog.py) und der Renderer (view_renderer.py) sauber
#   getrennt bleiben (Grundregel 10).
#
# ENTWURFSGRUNDSATZ (die wichtigste Entscheidung dieses Bauschritts):
#   Eine Spec sagt, WELCHER Endpunkt gelesen wird und WIE die Abschnitte
#   heissen — sie sagt NICHT, welche Spalten es gibt. Die Spalten leitet der
#   Renderer aus den DATEN ab.
#
#   Warum: Haette ich fuer 28 Sichten die Spaltenlisten von Hand abgeschrieben,
#   waere jeder Tippfehler und jede spaetere Feldergaenzung eine STILL FEHLENDE
#   SPALTE — also ein stillschweigend ausgelassener Beleg (Grundregel-1-
#   Verstoss). 'labels' verschoenert deshalb nur die Ueberschrift, und 'order'
#   zieht bekannte Spalten nach vorn; BEIDE FILTERN NIE. Was der Endpunkt
#   liefert, steht im Export.
#
# Version: v0.8.511 · Build: 511 · 2026-07-24
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class SectionSpec:
    """
    Ein Abschnitt des Exports = ein Schluessel der JSON-Antwort.

    key    — Top-Level-Schluessel der Endpunkt-Antwort (z. B. 'entries').
    title  — Ueberschrift im Dokument (deutsch, fuer die Akte).
    labels — optionale Spaltenbeschriftungen {feld: 'Anzeige'}. Rein kosmetisch:
             ein hier NICHT genanntes Feld erscheint trotzdem, mit seinem
             Rohnamen.
    order  — optionale Vorzugsreihenfolge von Feldern. Felder, die hier fehlen,
             werden HINTEN angehaengt (nie unterdrueckt).
    """
    key: str
    title: str
    labels: Dict[str, str] = field(default_factory=dict)
    order: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ViewExportSpec:
    """
    Eine exportierbare Cockpit-Sicht.

    view_id      — id aus dem Cockpit-VIEW_CATALOG (cockpit.js). Die Kopplung
                   ist absichtlich: der Export heisst wie die Sicht, die er
                   abbildet, und ein Test prueft die Deckungsgleichheit.
    label        — Titel des Dokuments (deutsch).
    api_path     — LESENDER Endpunkt, der die Sicht speist. Der Export ruft ihn
                   ueber den bestehenden dispatch() auf und erbt damit
                   Rechtepruefung, Scope und Fehlerbilder der Sicht.
    sections     — die Abschnitte in Dokumentreihenfolge.
    note         — optionaler Hinweis, der IM Dokument erscheint (z. B. dass
                   fuer diese Sicht zusaetzlich ein Spezialexport existiert).
    requires     — optionale Namen von Query-Parametern, die der Endpunkt
                   braucht (z. B. 'person_id'). Rein informativ fuer die
                   Fehlermeldung; erzwungen wird nichts — fehlt der Parameter,
                   antwortet der Endpunkt selbst und der Export reicht das
                   ehrlich durch.
    """
    view_id: str
    label: str
    api_path: str
    sections: Tuple[SectionSpec, ...]
    note: str = ""
    requires: Tuple[str, ...] = ()
