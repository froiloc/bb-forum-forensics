# =============================================================================
# management/export/context_builder.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem (AP-2B)
# =============================================================================
# Zweck:
#   Baut aus einer offenen coordinator.db-Verbindung + Pfad einen ExportContext
#   fuer die Sichten-Exporte (B442-Retrofit). Zentralisiert die drei bislang je
#   Admin dupliziert vorbereiteten Angaben:
#     * Buildnummer  — aus build.json (GR4).
#     * Integritaets-Kettenspitze — verify_chain + tip aus dem audit_log.
#     * ausfuehrende Identitaet    — IdentityResolver (SAMAccountName = stabile
#                                    forensische Identitaet; --actor uebersteuert).
#     * Zeitstempel  — jetzt (UTC), formatiert.
#
#   VOLL ABGESICHERT: KEINE Ausnahme darf aus dem Builder dringen — ein
#   Export darf nicht am Rahmen scheitern. Fehlt/bricht eine Quelle, wird der
#   jeweilige Wert EHRLICH als 'nicht geprueft'/'unbekannt' gefuehrt (GR1),
#   nicht stillschweigend geschoent.
#
#   NICHT rein (liest DB/Uhr/Datei) — bewusst getrennt von den reinen Renderern.
#
# BUILD 702 (Vorgang ff7e80ab) — DIE ABSICHERUNG WAR EHRLICH, ABER STUMM:
#   'Ehrlich gefuehrt' hiess bis Build 698: Buildnummer 0, Ersteller
#   'unbekannt', Kette None. Der GRUND des Ausfalls wurde dabei verworfen, und
#   0 und 'unbekannt' sind im fertigen Dokument von regulaeren Angaben nicht zu
#   unterscheiden. Damit war der Ausfall zwar nicht geschoent, aber auch nicht
#   erkennbar — ein still uebersprungener Beleg (GR1).
#
#   SEIT BUILD 702 haelt jede der drei Absicherungen ihren Ausfall als
#   RahmenBefund fest (Feld + Grund) und legt ihn in den ExportContext. Von
#   dort aus kennzeichnet der ExportEnvelope die betroffene Zeile des
#   Erzeugungsvermerks, und die aufrufenden Werkzeuge melden ihn auf ihrer
#   Fehlerausgabe.
#
#   DER BUILDER GIBT SELBST NICHTS AUS. Er ist die gemeinsame Quelle fuer die
#   CLIs UND fuer die Endpunkte in management/server/management_app.py; ein
#   print() hier wuerde im Serverbetrieb in einen Datenstrom schreiben, der
#   ihm nicht gehoert. Wohin eine Meldung gehoert, weiss nur der Aufrufer.
#
#   DIE ABSICHERUNG SELBST BLEIBT UNANGETASTET: der Builder wirft weiterhin
#   nie (RF06 haelt das fest). Ein Export darf nicht am Rahmen scheitern —
#   er soll nur nicht mehr so tun, als sei nichts gewesen.
#
# Version: v0.8.702 · Build: 702 · 2026-08-12
# =============================================================================

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from management.export.export_envelope import ExportContext, DEFAULT_KLASSIFIKATION
from management.export.rahmen_befund import (
    FELD_BUILD,
    FELD_ERSTELLER,
    FELD_KETTE,
    RahmenBefund,
)

_DEFAULT_BEHOERDE = "Polizei NRW"


def _build_number() -> Tuple[int, Optional[RahmenBefund]]:
    """
    (Buildnummer, Befund). Buildnummer aus der repo-eigenen build.json (GR4).

    Scheitert das Lesen, ist der zweite Rueckgabewert der Befund MIT Grund —
    der Ausfallwert 0 allein sagt nicht, ob die Datei fehlt, unlesbar ist oder
    keinen Schluessel 'build' hat. Genau das entscheidet aber, ob der Lauf zu
    wiederholen ist.
    """
    try:
        p = Path(__file__).resolve().parents[2] / "build.json"
        return int(json.loads(p.read_text(encoding="utf-8"))["build"]), None
    except Exception as exc:
        return 0, RahmenBefund(FELD_BUILD, "build.json nicht lesbar: %s" % exc)


def _verify_tip(con) -> Tuple[Optional[bool], Optional[int], Optional[str],
                              str, Optional[RahmenBefund]]:
    """
    (chain_ok, tip_seq, tip_hash, detail, befund). chain_ok: True/False/None
    (nicht pruefbar). Wirft nie — fehlt audit_log o. Ae., wird 'nicht pruefbar'
    zurueckgegeben (GR1).

    BEFUND NUR BEI 'NICHT PRUEFBAR' (chain_ok None). Eine GEBROCHENE Kette
    (chain_ok False) ist KEIN Rahmenbefund: sie ist ermittelt, sie steht als
    'GEBROCHEN' im Vermerk, und sie ist eine Aussage ueber den Bestand, nicht
    ueber den Rahmen. Die beiden zu vermengen wuerde die schwerere Lage in der
    leichteren verstecken.
    """
    try:
        from management.audit.audit_log import AuditLog
        audit = AuditLog(con)
        vr = audit.verify_chain()
        tip_hash, tip_seq = audit.tip()
        return bool(vr.ok), tip_seq, tip_hash, vr.detail, None
    except Exception as exc:  # sqlite/Attribute/Import — nie eskalieren
        detail = "audit_log nicht pruefbar: %s" % exc
        return None, None, None, detail, RahmenBefund(FELD_KETTE, detail)


def _resolve_actor(
    db_path: str, actor: Optional[str]
) -> Tuple[str, Optional[str], Optional[RahmenBefund]]:
    """
    (system_username, display_name, befund); --actor uebersteuert. Wirft nie.

    Scheitert die Aufloesung, bleibt der ROHWERT stehen (--actor bzw.
    'unbekannt') — er ist die einzige Spur, die es dann noch gibt, und sie
    wegzuwerfen waere schlechter als sie ungeprueft zu fuehren. Der Befund
    haelt fest, DASS sie ungeprueft ist; die Kennzeichnung im Vermerk
    uebernimmt der ExportEnvelope.
    """
    try:
        from management.server.identity import IdentityResolver
        person = IdentityResolver(db_path).resolve(system_username=actor)
        return (person.get("system_username") or (actor or "unbekannt"),
                person.get("display_name"), None)
    except Exception as exc:
        return ((actor or "unbekannt"), None,
                RahmenBefund(FELD_ERSTELLER,
                             "Identitaet nicht aufloesbar: %s" % exc))


def build_export_context(
    *,
    con: sqlite3.Connection,
    db_path: str,
    behoerde: Optional[str] = None,
    aktenzeichen: Optional[str] = None,
    actor: Optional[str] = None,
    klassifikation: Optional[str] = None,
    now_utc: Optional[str] = None,
) -> ExportContext:
    """
    Setzt den ExportContext zusammen. 'now_utc' ist injizierbar (Tests);
    Default = aktueller UTC-Zeitstempel. Alle Fehlerquellen sind abgesichert.

    BUILD 702: Der zusammengesetzte Kontext fuehrt zusaetzlich die
    'rahmen_befunde' — je nicht ermittelter Angabe einen. Die Reihenfolge ist
    die des Zusammenbaus (Kette, Identitaet, Buildnummer) und damit stabil;
    ein Vermerk, dessen Zeilen bei jedem Lauf anders stehen, laesst sich
    zwischen zwei Abgaben nicht vergleichen.
    """
    chain_ok, tip_seq, tip_hash, _detail, befund_kette = _verify_tip(con)
    ersteller, anzeigename, befund_actor = _resolve_actor(db_path, actor)
    build_number, befund_build = _build_number()
    generated = now_utc or datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC")

    befunde: List[RahmenBefund] = [
        b for b in (befund_kette, befund_actor, befund_build) if b is not None
    ]

    return ExportContext(
        behoerde=behoerde or _DEFAULT_BEHOERDE,
        aktenzeichen=aktenzeichen or "Gesamtuebersicht",
        ersteller=ersteller,
        build_number=build_number,
        generated_at=generated,
        chain_ok=chain_ok,
        chain_tip_seq=tip_seq,
        chain_tip_hash=tip_hash,
        klassifikation=klassifikation or DEFAULT_KLASSIFIKATION,
        anzeigename=anzeigename,
        rahmen_befunde=tuple(befunde),
    )
