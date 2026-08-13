#!/usr/bin/env python3
# =============================================================================
# tools/pruefe_rbac_waisen.py
# IT-Forensisches Ermittlungswerkzeug — Betriebsdiagnose (kein Produktivcode)
# =============================================================================
# Zweck:
#   MACHT VERWEISE INS LEERE IN DER RECHTE-MATRIX SICHTBAR. Prueft
#   coordinator.db darauf, ob rbac_grant und person_role auf Rollen,
#   Faehigkeiten, Personen oder Belege zeigen, die es in dieser Datenbank
#   nicht (mehr) gibt — und ob der Katalog im Code und der in der Datenbank
#   auseinanderlaufen.
#
#   Aufruf:
#     python tools/pruefe_rbac_waisen.py --db data/coordinator.db
#     python tools/pruefe_rbac_waisen.py --db data/coordinator.db --json
#
# ── WARUM ES DIESES WERKZEUG GIBT ──────────────────────────────────────────
#
#   ANLASS (Vorgang 9c4e17b2, 13.08.2026): Ein Grant auf 'caseoverview.view'
#   entstand, bevor die Migration diese Faehigkeit in der Datenbank anlegte.
#   Das ist moeglich, weil zwei Kataloge existieren und nur einer geprueft
#   wird: RbacRepo._validate_capability prueft gegen
#   management/rbac/catalog.py — den Katalog im CODE. Ob die Faehigkeit in
#   rbac_capability der DATENBANK steht, prueft dort niemand. Die
#   Fremdschluessel bestehen zwar (M006), greifen aber nicht: die
#   Management-Verbindungen laufen mit foreign_keys=OFF (SQLite-Vorgabe,
#   in m002/m004 ausdruecklich festgehalten).
#
#   DIE FOLGE WAR NICHT HARMLOS. Die Migration, die das Recht anlegen sollte,
#   fand einen Grant darauf vor, brach ab und rollte zurueck; das Management
#   verweigerte den Start. Der Zustand war von aussen nicht zu sehen — der
#   Befund musste von Hand aus drei Tabellen zusammengesucht werden.
#
#   WAS DIESES WERKZEUG DARAN AENDERT: Es sucht denselben Zustand in einem
#   Lauf, in ALLEN Richtungen statt nur der einen, die damals wehtat, und es
#   nennt zu jedem Fund den BELEG. rbac_grant.audit_seq ist NOT NULL — jeder
#   Grant traegt die seq seiner Vergabe, und darueber steht in audit_log, wer
#   ihn wann vergeben hat. Die Herkunft ist also nachvollziehbar; sie war nur
#   nie an einer Stelle versammelt.
#
#   ES SCHLIESST DIE URSACHE NICHT. Die Pruefung im Schreibpfad selbst ist
#   Vorgang 1b7d55ae und steht aus; seit Build 711 prueft nur
#   'rbac_admin migrate-grants' die Reihenfolge. Dieses Werkzeug ist die
#   Betriebsseite: es macht sichtbar, was durchgerutscht ist, statt sich
#   darauf zu verlassen, dass nichts durchrutscht.
#
#   ES AENDERT NICHTS. Es oeffnet die Datenbank 'mode=ro' und liest. Damit ist
#   es auch auf einer Produktivdatenbank unbedenklich, braucht kein
#   Wartungsfenster und greift nicht in den Migrationsvorbehalt ein.
#
# ── WARUM DER KATALOGVERSATZ EINEN EIGENEN RUECKGABEWERT HAT ───────────────
#
#   'Der Code kennt ein Recht, die Datenbank nicht' heisst in aller Regel:
#   eine Migration steht noch aus. Das ist ein ARBEITSSTAND, kein Schaden —
#   nach dem naechsten 'python -m management.migrate' ist es weg. Eine Waise
#   dagegen ist ein Verweis ins Leere und bleibt es von allein. Beides mit
#   demselben Code zu melden hiesse, dem Betriebsskript die Unterscheidung zu
#   nehmen, auf die es ankommt.
#
# ── EXIT-CODES (fuer das Betriebsskript) ───────────────────────────────────
#     0 — kein Befund.
#     1 — Aufruffehler (Datei fehlt, nicht lesbar, keine RBAC-Tabellen).
#     2 — WAISEN oder gebrochene Beleg-Kopplungen gefunden. Hat Vorrang vor 3.
#     3 — NUR Katalogversatz zwischen Code und Datenbank (kein Verweis ins
#         Leere). Meist eine ausstehende Migration.
#
# Version: v0.8.713 · Build: 713 · 2026-08-13
# =============================================================================

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.help import cli_epilog  # noqa: E402
from management.rbac import catalog     # noqa: E402

#: Tabellen, ohne die keine Pruefung moeglich ist. Fehlen sie, ist das kein
#  Befund, sondern die falsche oder eine uneingerichtete Datenbank.
_PFLICHT = ("rbac_capability", "rbac_role", "rbac_grant")

#: Tabellen, die einzelne Pruefungen brauchen. Fehlt eine, wird die zugehoerige
#  Pruefung UEBERSPRUNGEN — und das wird gemeldet (Grundregel 1). Ein stiller
#  Uebersprung saehe aus wie 'geprueft und nichts gefunden'.
_OPTIONAL = ("person_role", "person", "audit_log")


def _ts(wert):
    """Unix-Sekunden lesbar machen; None bleibt '-'."""
    if wert is None:
        return "-"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(wert)))


def _tabellen(con):
    return {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def _beleg(con, seq, da):
    """
    Der audit_log-Eintrag zu einer seq — oder die Auskunft, dass er fehlt.

    Das ist der eigentliche Mehrwert gegenueber einem blossen 'da ist eine
    Waise': wer sie erzeugt hat, steht im Belegbuch, und ohne diese Aufloesung
    muesste man es von Hand nachschlagen.
    """
    if seq is None:
        return None
    if not da:
        return {"seq": seq, "vorhanden": None,
                "hinweis": "audit_log fehlt — nicht aufloesbar"}
    row = con.execute(
        "SELECT seq, ts, actor_id, event_type, target_type, target_id "
        "FROM audit_log WHERE seq=?", (seq,)).fetchone()
    if row is None:
        return {"seq": seq, "vorhanden": False}
    name = None
    if row["actor_id"] is not None:
        p = con.execute("SELECT system_username FROM person WHERE id=?",
                        (row["actor_id"],)).fetchone()
        if p:
            name = p[0]
    return {"seq": row["seq"], "vorhanden": True, "zeit": _ts(row["ts"]),
            "actor_id": row["actor_id"], "actor": name,
            "event_type": row["event_type"],
            "ziel": "%s/%s" % (row["target_type"], row["target_id"])}


def _grants_ohne_faehigkeit(con, da):
    """rbac_grant zeigt auf eine Faehigkeit, die rbac_capability nicht kennt."""
    funde = []
    for r in con.execute(
            "SELECT g.id, g.role_code, g.capability_code, g.scope, "
            "       g.audit_seq, g.granted_at, g.revoked_at, g.note "
            "FROM rbac_grant g LEFT JOIN rbac_capability c "
            "  ON c.code = g.capability_code "
            "WHERE c.code IS NULL ORDER BY g.id"):
        funde.append({
            "grant_id": r["id"], "rolle": r["role_code"],
            "faehigkeit": r["capability_code"], "umfang": r["scope"],
            "aktiv": r["revoked_at"] is None,
            "vergeben_am": _ts(r["granted_at"]),
            "notiz": r["note"],
            # Steht die Faehigkeit wenigstens im Code? Dann ist es die
            # Reihenfolge (Migration stand aus). Steht sie auch dort nicht,
            # ist es ein anderer Fall - ein entferntes oder erfundenes Recht.
            "im_code_katalog": r["capability_code"] in catalog.CAPABILITY_CODES,
            "beleg": _beleg(con, r["audit_seq"], da),
        })
    return funde


def _grants_ohne_rolle(con, da):
    """rbac_grant zeigt auf eine Rolle, die rbac_role nicht kennt."""
    funde = []
    for r in con.execute(
            "SELECT g.id, g.role_code, g.capability_code, g.audit_seq, "
            "       g.revoked_at "
            "FROM rbac_grant g LEFT JOIN rbac_role o ON o.code = g.role_code "
            "WHERE o.code IS NULL ORDER BY g.id"):
        funde.append({
            "grant_id": r["id"], "rolle": r["role_code"],
            "faehigkeit": r["capability_code"],
            "aktiv": r["revoked_at"] is None,
            "im_code_katalog": r["role_code"] in catalog.ROLE_CODES,
            "beleg": _beleg(con, r["audit_seq"], da),
        })
    return funde


def _rollen_zuweisungen_ohne_ziel(con, tab, da):
    """person_role zeigt auf eine unbekannte Rolle oder eine unbekannte Person."""
    funde = []
    if "person_role" not in tab:
        return funde
    for r in con.execute(
            "SELECT id, person_id, role_code, audit_seq, revoked_at "
            "FROM person_role ORDER BY id"):
        fehlt = []
        if con.execute("SELECT 1 FROM rbac_role WHERE code=?",
                       (r["role_code"],)).fetchone() is None:
            fehlt.append("Rolle '%s'" % r["role_code"])
        if "person" in tab and con.execute(
                "SELECT 1 FROM person WHERE id=?",
                (r["person_id"],)).fetchone() is None:
            fehlt.append("Person id=%s" % r["person_id"])
        if fehlt:
            funde.append({
                "zuweisung_id": r["id"], "person_id": r["person_id"],
                "rolle": r["role_code"], "aktiv": r["revoked_at"] is None,
                "fehlt": fehlt,
                "beleg": _beleg(con, r["audit_seq"], da),
            })
    return funde


def _gebrochene_belege(con, tab):
    """
    Eine Zeile traegt eine audit_seq, zu der es keinen audit_log-Eintrag gibt.

    Das ist der schwerste der hier gesuchten Befunde: die Beleg-Kopplung ist
    die Zusage, dass kein Grant ohne nachvollziehbare Vergabe existiert. Ein
    Verweis ins Leere HIER heisst, dass jemand am Belegbuch war — oder dass
    eine Zeile aus einer anderen Datenbank stammt.
    """
    funde = []
    if "audit_log" not in tab:
        return funde
    paare = [("rbac_grant", "audit_seq", "Vergabe"),
             ("rbac_grant", "revoke_audit_seq", "Ruecknahme")]
    if "person_role" in tab:
        paare += [("person_role", "audit_seq", "Zuweisung"),
                  ("person_role", "revoke_audit_seq", "Ruecknahme")]
    for tabelle, spalte, anlass in paare:
        for r in con.execute(
                "SELECT t.id, t.%s AS seq FROM %s t "
                "LEFT JOIN audit_log a ON a.seq = t.%s "
                "WHERE t.%s IS NOT NULL AND a.seq IS NULL ORDER BY t.id"
                % (spalte, tabelle, spalte, spalte)):
            funde.append({"tabelle": tabelle, "zeile_id": r["id"],
                          "spalte": spalte, "anlass": anlass,
                          "seq": r["seq"]})
    return funde


def _katalogversatz(con):
    """
    Code-Katalog gegen Datenbank-Katalog, in BEIDE Richtungen.

    Die eine Richtung ist der Alltagsfall (Migration steht aus), die andere
    der seltenere: die Datenbank kennt ein Recht, das der Code nicht mehr
    fuehrt. Beide gehoeren genannt — wer nur eine Richtung prueft, sieht die
    Datenbank immer als das Nachhinkende an.
    """
    in_db_caps = {r[0] for r in con.execute("SELECT code FROM rbac_capability")}
    in_db_rollen = {r[0] for r in con.execute("SELECT code FROM rbac_role")}
    return {
        "faehigkeiten_nur_im_code": sorted(
            set(catalog.CAPABILITY_CODES) - in_db_caps),
        "faehigkeiten_nur_in_der_db": sorted(
            in_db_caps - set(catalog.CAPABILITY_CODES)),
        "rollen_nur_im_code": sorted(set(catalog.ROLE_CODES) - in_db_rollen),
        "rollen_nur_in_der_db": sorted(in_db_rollen - set(catalog.ROLE_CODES)),
    }


def pruefe(db_pfad):
    """
    Fuehrt alle Pruefungen aus. -> (ergebnis: dict, rueckgabewert: int)

    Als Funktion herausgezogen, damit die Regressionstests sie ohne den
    Umweg ueber die Befehlszeile fahren koennen — und damit sie dabei
    dasselbe pruefen, was der Aufruf tut, statt einer zweiten Fassung
    derselben Logik ('gruen aber tot').
    """
    con = sqlite3.connect("file:%s?mode=ro" % Path(db_pfad).resolve(),
                          uri=True)
    con.row_factory = sqlite3.Row
    try:
        tab = _tabellen(con)
        fehlend = [t for t in _PFLICHT if t not in tab]
        if fehlend:
            return {"datei": str(db_pfad), "fehlende_pflichttabellen": fehlend}, 1

        uebersprungen = []
        for t in _OPTIONAL:
            if t not in tab:
                uebersprungen.append(t)
        da_audit = "audit_log" in tab

        ergebnis = {
            "datei": str(db_pfad),
            "uebersprungene_pruefungen_wegen_fehlender_tabelle": uebersprungen,
            "grants_ohne_faehigkeit": _grants_ohne_faehigkeit(con, da_audit),
            "grants_ohne_rolle": _grants_ohne_rolle(con, da_audit),
            "zuweisungen_ohne_ziel": _rollen_zuweisungen_ohne_ziel(
                con, tab, da_audit),
            "gebrochene_belege": _gebrochene_belege(con, tab),
            "katalogversatz": _katalogversatz(con),
        }
    finally:
        con.close()

    waisen = (len(ergebnis["grants_ohne_faehigkeit"])
              + len(ergebnis["grants_ohne_rolle"])
              + len(ergebnis["zuweisungen_ohne_ziel"])
              + len(ergebnis["gebrochene_belege"]))
    versatz = any(ergebnis["katalogversatz"].values())
    ergebnis["anzahl_waisen"] = waisen
    if waisen:
        return ergebnis, 2
    if versatz:
        return ergebnis, 3
    return ergebnis, 0


def _drucke(e):
    print("Rechte-Matrix — %s (schreibgeschuetzt geoeffnet)" % e["datei"])

    if e.get("fehlende_pflichttabellen"):
        print("  ABBRUCH: Diese Datenbank hat keine Rechte-Matrix. Es fehlen: "
              "%s" % ", ".join(e["fehlende_pflichttabellen"]))
        print("  Entweder ist es nicht die coordinator.db, oder M006 ist "
              "nicht angewandt.")
        return

    # Grundregel 1: was NICHT geprueft wurde, wird zuerst genannt - sonst
    # liest sich ein leerer Befund wie eine Unbedenklichkeitsbescheinigung.
    if e["uebersprungene_pruefungen_wegen_fehlender_tabelle"]:
        print("  ACHTUNG - NICHT VOLLSTAENDIG GEPRUEFT. Diese Tabellen fehlen, "
              "die zugehoerigen Pruefungen entfielen: %s"
              % ", ".join(e["uebersprungene_pruefungen_wegen_fehlender_tabelle"]))

    def beleg_zeile(b):
        if b is None:
            return "        Beleg  : keiner hinterlegt"
        if b.get("hinweis"):
            return "        Beleg  : seq=%s (%s)" % (b["seq"], b["hinweis"])
        if not b["vorhanden"]:
            return ("        Beleg  : seq=%s ZEIGT INS LEERE - kein Eintrag "
                    "im Belegbuch" % b["seq"])
        return ("        Beleg  : seq=%s, %s, %s, Akteur person.id=%s (%s)"
                % (b["seq"], b["zeit"], b["event_type"], b["actor_id"],
                   b["actor"] or "-"))

    print("\n[1] Grants auf Faehigkeiten, die die Datenbank nicht kennt")
    if not e["grants_ohne_faehigkeit"]:
        print("    keine.")
    for f in e["grants_ohne_faehigkeit"]:
        print("    Grant #%-4d rolle=%-14s -> '%s'  umfang=%s  [%s]"
              % (f["grant_id"], f["rolle"], f["faehigkeit"],
                 f["umfang"] or "-", "aktiv" if f["aktiv"] else "zurueckgenommen"))
        if f["im_code_katalog"]:
            print("        Deutung: Das Recht steht im Katalog des CODES. Das "
                  "ist der Reihenfolgefall - die Migration stand beim "
                  "Vergeben noch aus. 'python -m management.migrate' loest "
                  "ihn auf.")
        else:
            print("        Deutung: Das Recht steht AUCH IM CODE nicht. Hier "
                  "ist von Hand zu klaeren, woher es stammt.")
        if f["notiz"]:
            print("        Notiz  : %s" % f["notiz"])
        print(beleg_zeile(f["beleg"]))

    print("\n[2] Grants auf Rollen, die die Datenbank nicht kennt")
    if not e["grants_ohne_rolle"]:
        print("    keine.")
    for f in e["grants_ohne_rolle"]:
        print("    Grant #%-4d rolle='%s' -> %s  [%s]"
              % (f["grant_id"], f["rolle"], f["faehigkeit"],
                 "aktiv" if f["aktiv"] else "zurueckgenommen"))
        print(beleg_zeile(f["beleg"]))

    print("\n[3] Rollenzuweisungen ins Leere")
    if not e["zuweisungen_ohne_ziel"]:
        print("    keine.")
    for f in e["zuweisungen_ohne_ziel"]:
        print("    Zuweisung #%-4d person_id=%s rolle=%s  [%s]"
              % (f["zuweisung_id"], f["person_id"], f["rolle"],
                 "aktiv" if f["aktiv"] else "zurueckgenommen"))
        print("        fehlt  : %s" % ", ".join(f["fehlt"]))
        print(beleg_zeile(f["beleg"]))

    print("\n[4] Gebrochene Beleg-Kopplungen")
    if not e["gebrochene_belege"]:
        print("    keine.")
    for f in e["gebrochene_belege"]:
        print("    %s #%-4d %s (%s) verweist auf audit_log seq=%s - "
              "dort steht nichts."
              % (f["tabelle"], f["zeile_id"], f["spalte"], f["anlass"],
                 f["seq"]))

    print("\n[5] Katalogversatz Code <-> Datenbank")
    v = e["katalogversatz"]
    if not any(v.values()):
        print("    keiner - beide Kataloge fuehren dasselbe.")
    if v["faehigkeiten_nur_im_code"]:
        print("    nur im CODE (Migration steht vermutlich aus): %s"
              % ", ".join(v["faehigkeiten_nur_im_code"]))
    if v["faehigkeiten_nur_in_der_db"]:
        print("    nur in der DATENBANK: %s"
              % ", ".join(v["faehigkeiten_nur_in_der_db"]))
    if v["rollen_nur_im_code"]:
        print("    Rollen nur im CODE: %s" % ", ".join(v["rollen_nur_im_code"]))
    if v["rollen_nur_in_der_db"]:
        print("    Rollen nur in der DATENBANK: %s"
              % ", ".join(v["rollen_nur_in_der_db"]))

    print("\n  Waisen gesamt ......... %d" % e["anzahl_waisen"])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="python tools/pruefe_rbac_waisen.py",
        description="Prueft die Rechte-Matrix der coordinator.db auf Verweise "
                    "ins Leere. Rein lesend.",
        epilog=cli_epilog.epilog("pruefe_rbac_waisen"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--db", required=True,
                   help="Pfad der zu pruefenden coordinator.db")
    p.add_argument("--json", action="store_true", help="Ausgabe als JSON")
    args = p.parse_args(argv)

    db = Path(args.db)
    if not db.is_file():
        print("Fehler: %s ist keine Datei." % db, file=sys.stderr)
        return 1

    try:
        ergebnis, rueckgabe = pruefe(db)
    except sqlite3.Error as exc:
        print("Fehler: %s nicht lesbar: %s" % (db, exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(ergebnis, ensure_ascii=False, indent=2,
                         sort_keys=True))
    else:
        _drucke(ergebnis)
    return rueckgabe


if __name__ == "__main__":  # pragma: no cover — Einstiegspunkt
    sys.exit(main())
