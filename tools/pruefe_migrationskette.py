#!/usr/bin/env python3
# =============================================================================
# tools/pruefe_migrationskette.py
# IT-Forensisches Ermittlungswerkzeug — Betriebsdiagnose (kein Produktivcode)
# =============================================================================
# Zweck:
#   MACHT DEN STILLEN UEBERSPRUNG SICHTBAR. Vergleicht die im Paket
#   vorhandenen Migrationen mit den in 'schema_migrations' registrierten und
#   meldet jede, die vorhanden, aber NICHT angewandt ist.
#
#   Aufruf (vor jedem Einspielen):
#     python tools/pruefe_migrationskette.py --db data/coordinator.db
#     python tools/pruefe_migrationskette.py --db data/evidence/evidence_4711.db --art evidence
#     python tools/pruefe_migrationskette.py --db data/coordinator.db --json
#
# ── WARUM ES DIESES WERKZEUG GIBT ──────────────────────────────────────────
#
#   BEFUND (reproduziert 2026-07-26, tools/diag_migrationsluecke.py; Vermerk
#   management/Vermerk_Migrationsluecke_Parallelbetrieb_v0_1.md):
#   MigrationRunner fuehrt einen HOECHSTSTAND und keine Menge —
#       current = MAX(version);  if mod.VERSION <= current: continue
#   (management/migrations/runner.py:97-123). Wird eine hohe Nummer zuerst
#   eingespielt, werden alle spaeter gelieferten niedrigeren Nummern FUER
#   IMMER uebersprungen. '_check_checksum' schweigt dabei, weil es zu einer
#   nie angewandten Version gar keine Registry-Zeile gibt (:207-209). run()
#   meldet dann "Keine ausstehenden Migrationen" — also 'alles aktuell' fuer
#   einen Zustand, in dem Schemaaenderungen fehlen.
#
#   mc hat am 2026-07-26 entschieden, die Migrationen der Instanzen STRIKT ZU
#   SERIALISIEREN, statt den Runner zu aendern. Diese Entscheidung verhindert,
#   dass die Falle AUSGELOEST wird — sie entschaerft sie nicht. Dieses
#   Werkzeug schliesst die verbleibende Luecke auf der BETRIEBSSEITE: es macht
#   einen Verstoss sichtbar, statt sich darauf zu verlassen, dass keiner
#   passiert.
#
#   ES AENDERT NICHTS. Es oeffnet die Datenbank 'mode=ro' und liest zwei
#   Tabellen. Damit ist es auch auf einer Produktivdatenbank unbedenklich und
#   greift nicht in den Migrationsvorbehalt ein.
#
# ── EXIT-CODES (fuer das Betriebsskript) ───────────────────────────────────
#     0 — Kette schluessig: alles, was im Paket liegt, ist angewandt.
#     1 — Aufruffehler (Datei/Art unbekannt, nicht lesbar).
#     2 — LUECKE: mindestens eine vorhandene Migration ist nicht angewandt.
#         EIGENER Code, weil 'geprueft und in Ordnung' und 'geprueft und
#         Luecke gefunden' im Skript nicht gleich aussehen duerfen.
#     3 — Die Registry kennt eine Version, die es im Paket NICHT (mehr) gibt.
#         Das ist die Gegenrichtung und ebenfalls ein Befund: entweder wurde
#         eine Migrationsdatei entfernt oder die Datenbank stammt aus einem
#         neueren Stand als der Code.
#
# Version: v0.8.561 · Build: 561 · 2026-07-26
# =============================================================================

import argparse
import importlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.migrations.runner import discover  # noqa: E402

#: Die drei Migrationsketten des Werkzeugs. 'forensic'/'assets' teilen sich
#  keine Kette mit evidence — jede Datenbankart hat ihre eigene.
PAKETE = {
    "coordinator": "management.migrations.coordinator",
    "evidence": "management.migrations.evidence",
    "forensic": "management.migrations.forensic",
    "assets": "management.migrations.assets",
}


def _registrierte(db_pfad: Path):
    """
    Die angewandten Versionen aus schema_migrations (read-only).

    Fehlt die Tabelle, ist das KEIN Fehler, sondern der Befund 'noch keine
    Migration angewandt' — eine frische Datenbank. Der Aufrufer unterscheidet
    das; die beiden Faelle duerfen nicht gleich aussehen.
    """
    con = sqlite3.connect("file:%s?mode=ro" % db_pfad.resolve(), uri=True)
    try:
        da = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='schema_migrations'").fetchone()
        if da is None:
            return None
        return {int(r[0]): (r[1], r[2]) for r in con.execute(
            "SELECT version, name, checksum FROM schema_migrations "
            "ORDER BY version")}
    finally:
        con.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="python tools/pruefe_migrationskette.py",
        description="Prueft, ob jede im Paket vorhandene Migration in der "
                    "Datenbank angewandt ist. Rein lesend.")
    p.add_argument("--db", required=True, help="Pfad der zu pruefenden Datei")
    p.add_argument("--art", default="coordinator", choices=sorted(PAKETE),
                   help="Migrationskette (Standard: coordinator)")
    p.add_argument("--json", action="store_true", help="Ausgabe als JSON")
    args = p.parse_args(argv)

    db = Path(args.db)
    if not db.is_file():
        print("Fehler: %s ist keine Datei." % db, file=sys.stderr)
        return 1

    try:
        paket = importlib.import_module(PAKETE[args.art])
        module = discover(paket)
    except Exception as exc:
        print("Fehler: Migrationspaket '%s' nicht ladbar: %s"
              % (args.art, exc), file=sys.stderr)
        return 1

    try:
        registriert = _registrierte(db)
    except sqlite3.Error as exc:
        print("Fehler: %s nicht lesbar: %s" % (db, exc), file=sys.stderr)
        return 1

    im_paket = {int(m.VERSION): m.NAME for m in module}
    frisch = registriert is None
    angewandt = {} if frisch else registriert

    fehlend = sorted(v for v in im_paket if v not in angewandt)
    unbekannt = sorted(v for v in angewandt if v not in im_paket)
    hoechststand = max(angewandt) if angewandt else 0
    # Die eigentlich gefaehrliche Teilmenge: eine fehlende Migration UNTERHALB
    # des Hoechststands wird vom Runner NIE MEHR angefasst. Eine fehlende
    # oberhalb laeuft beim naechsten Start ganz normal nach.
    verloren = [v for v in fehlend if v < hoechststand]

    ergebnis = {
        "datei": str(db),
        "art": args.art,
        "frisch": frisch,
        "hoechststand": hoechststand,
        "im_paket": sorted(im_paket),
        "angewandt": sorted(angewandt),
        "fehlend": fehlend,
        "fehlend_unterhalb_hoechststand": verloren,
        "registriert_aber_nicht_im_paket": unbekannt,
    }

    if args.json:
        print(json.dumps(ergebnis, ensure_ascii=False, indent=2,
                         sort_keys=True))
    else:
        print("Migrationskette '%s' — %s" % (args.art, db))
        if frisch:
            print("  schema_migrations fehlt — NOCH KEINE Migration "
                  "angewandt (frische Datenbank, kein Fehler).")
        print("  im Paket .............. %d (%s)"
              % (len(im_paket), sorted(im_paket)))
        print("  angewandt ............. %d (%s)"
              % (len(angewandt), sorted(angewandt)))
        print("  Hoechststand .......... %d" % hoechststand)
        if verloren:
            print("  *** LUECKE ***        %s" % (verloren,))
            print("      Diese Migrationen liegen UNTERHALB des "
                  "Hoechststands und werden vom Runner NIE MEHR angewandt.")
            for v in verloren:
                print("        M%03d  %s" % (v, im_paket[v]))
            print("      Abhilfe: die betroffenen Migrationen von Hand auf "
                  "einer Kopie anwenden und registrieren, ODER den Runner "
                  "auf eine MENGE statt einen Hoechststand umstellen "
                  "(Vermerk_Migrationsluecke_Parallelbetrieb_v0_1.md §6 A).")
        elif fehlend:
            print("  ausstehend (unbedenklich, laeuft beim naechsten Start "
                  "nach): %s" % (fehlend,))
        else:
            print("  Befund ................ Kette schluessig.")
        if unbekannt:
            print("  *** REGISTRIERT, ABER NICHT IM PAKET ***  %s"
                  % (unbekannt,))
            print("      Entweder wurde eine Migrationsdatei entfernt, oder "
                  "die Datenbank stammt aus einem NEUEREN Stand als der Code.")

    if unbekannt:
        return 3
    if verloren:
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover — Einstiegspunkt
    sys.exit(main())
