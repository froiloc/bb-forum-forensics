#!/usr/bin/env python3
# =============================================================================
# tools/diag_limitation_laufzeit.py
# IT-Forensisches Ermittlungswerkzeug — DIAGNOSE-Werkzeug (AP-3A, Build 524)
# =============================================================================
# Zweck:
#   Beantwortet EINE Frage mit Zahlen: Wie lange braucht der Fristenmonitor
#   (GET /api/limitation, LimitationRepo.compute) bei ECHTEM Fallbestand — und
#   lohnt sich deshalb ein Zwischenspeicher?
#
#   Die Entscheidung, die davon abhaengt: Der Endpunkt oeffnet bei JEDEM Abruf
#   jede forensic_<uid>.db einzeln und rechnet MIN/MAX ueber die Zeitspalten.
#   Bei kleinem Bestand ist das belanglos, bei grossem nicht. Ein Cache auf
#   einer FRISTAUSSAGE ist aber nichts, was man auf Verdacht einbaut — eine
#   veraltete gruene Ampel waere schlimmer als eine langsame richtige. Deshalb
#   erst messen, dann entscheiden.
#
# FORENSISCHE SORGFALT (Grundregel 1 — keine stillen Aenderungen):
#   * ALLE Datenbanken werden AUSSCHLIESSLICH LESEND geoeffnet, ueber URI
#     'file:...?mode=ro'. Es wird KEIN PRAGMA gesetzt, das den Header oder den
#     Journalmodus veraendern koennte.
#   * Es wird NICHTS geschrieben: keine Datei angelegt, keine Zeile eingefuegt,
#     kein audit_log-Eintrag. Das Werkzeug ist in PROD gefahrlos ausfuehrbar —
#     es tut genau das, was die Sicht 'Fristen' auch tut, nur mit Stoppuhr.
#   * Es wird KEIN Fallinhalt ausgegeben. Die Ausgabe enthaelt Zahlen und
#     Dateinamen-Muster, KEINE Kontonamen und KEINE Annotationstexte — sie darf
#     damit unbedenklich in ein Chat-Protokoll kopiert werden (Fallregel 3).
#
# AUFRUF (in der VM, aus dem Verzeichnis des Webservers, z. B. S:\):
#     python tools/diag_limitation_laufzeit.py
#     python tools/diag_limitation_laufzeit.py --runs 5
#     python tools/diag_limitation_laufzeit.py --url http://127.0.0.1:8090
#     python tools/diag_limitation_laufzeit.py --coordinator-db D:\pfad\coordinator.db \
#                                              --forensic-dir D:\pfad\forensic
#
#   Ohne --url wird die Rechenschicht DIREKT gemessen (ohne HTTP, ohne Server).
#   Das ist die aussagekraeftigere Messung, weil sie die Datenbankarbeit
#   isoliert. Mit --url wird zusaetzlich der echte Endpunkt gemessen; dazu muss
#   der Management-Server laufen (python management.py) und die aufrufende
#   Person das Recht 'limitation.view' haben.
#
# ERWARTETE AUSGABE: ein Block 'ERGEBNIS ZUM ZURUECKMELDEN' am Ende. Genau
#   diesen Block bitte zurueckschicken — je einmal aus DEV und aus PROD.
#
# v2 (2026-07-25, nach der ersten Messung): (a) SCHEMA-SONDE ergaenzt, die
#   die ECHTEN Spaltennamen und den Zeitkandidaten BELEGT statt zu raten;
#   (b) Fehlklassifikation behoben — v1 zaehlte 'Spalte fehlt' als 'Datei
#   nicht lesbar' und meldete '0 lesbar, 25 nicht', obwohl alle Dateien
#   tadellos lesbar waren. Eine irreführende Diagnose im Diagnosewerkzeug
#   ist der schlechteste Ort fuer einen solchen Fehler.
# v3 (2026-07-25): Die Sonde prueft ALLE uid_*-Tabellen auf Zeitkandidaten,
#   nicht nur die zwei Beitragstabellen — insbesondere uid_profile
#   (Registrierungsdatum) und uid_surveillance (Anmeldungen aus der
#   100a-Massnahme), die als Zeitanker in Betracht kommen. Auch deren
#   Spaltennamen sind im Repository nur ueber Testvorrichtungen und
#   Platzhalter-SQL 'belegt' — also nicht belegt. Die Stichprobe nimmt die
#   KLEINSTEN Dateien (gleiches Schema, aber kein voller Durchlauf ueber
#   eine 1-GiB-Datei je Spalte).
# v4 (2026-07-25, nach dem zweiten Lauf): (a) Die Stichprobe nimmt die
#   GROESSENSPANNE statt nur die kleinsten Dateien — die kleinsten gehoeren
#   zu Konten OHNE Beitraege, dort stand ueberall 'nichtnull=0' und ueber
#   die WERTE war damit nichts belegt. (b) Spalten, deren Name auf einen
#   Bezeichner deutet, werden als Zeitkandidat GEKENNZEICHNET statt still
#   mitgezaehlt: 'uid_profile.id' fiel rechnerisch in den Epoch-Bereich,
#   weil Forum-Benutzer-IDs um 1,0 Mrd. liegen. (c) Spalten ohne Werte
#   werden ausdruecklich benannt — Schema belegt, Bedeutung nicht.
# Version: v0.8.527 · 2026-07-25 · Diagnose, NICHT Teil des Produktivsystems
# =============================================================================

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sqlite3
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Das Werkzeug laeuft aus dem Projektverzeichnis (wie tools/maintenance.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_FORENSIC_RE = re.compile(r"^forensic_(\d+)\.db$")


# ---------------------------------------------------------------- Hilfsmittel

def _ro(pfad: str) -> sqlite3.Connection:
    """READ-ONLY-Verbindung. Kein PRAGMA, kein Schreibpfad."""
    con = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
    con.row_factory = sqlite3.Row
    return con


def _cfg(schluessel: str, vorgabe: str) -> str:
    try:
        from core.config_loader import ConfigLoader
        wert = ConfigLoader().get(schluessel)
        return str(wert) if wert else vorgabe
    except Exception:
        return vorgabe


def _fmt(sek: float) -> str:
    """
    Lesbare Zeit. Unter 1 ms wird in Mikrosekunden ausgewiesen — '0 ms' waere
    keine Messung, sondern eine gerundete Nichtaussage, und genau die
    Einzeldatei-Kosten liegen im lokalen Fall darunter.
    """
    if sek < 0.001:
        return "%.0f us" % (sek * 1000000.0)
    if sek < 1.0:
        return "%.1f ms" % (sek * 1000.0)
    return "%.2f s" % sek


def _kennzahlen(werte):
    """min/median/max — bei einem einzelnen Wert alle gleich."""
    if not werte:
        return (0.0, 0.0, 0.0)
    return (min(werte), statistics.median(werte), max(werte))


# ------------------------------------------------------------ (1) Bestand

def bestand(coordinator_db: str, forensic_dir: str) -> dict:
    """Zaehlt, WORAN gemessen wird. Rein lesend."""
    out = {"coordinator_db": coordinator_db, "forensic_dir": forensic_dir}

    con = _ro(coordinator_db)
    try:
        out["faelle_gesamt"] = int(con.execute(
            "SELECT COUNT(*) FROM cases").fetchone()[0])
        out["faelle_je_status"] = {
            str(r[0]): int(r[1]) for r in con.execute(
                "SELECT status, COUNT(*) FROM cases GROUP BY status")}
    finally:
        con.close()

    d = Path(forensic_dir)
    dateien = []
    if d.is_dir():
        for eintrag in d.iterdir():
            if _FORENSIC_RE.match(eintrag.name):
                try:
                    dateien.append(eintrag.stat().st_size)
                except OSError:
                    dateien.append(0)
    out["forensic_dateien"] = len(dateien)
    out["forensic_bytes_gesamt"] = sum(dateien)
    out["forensic_bytes_groesste"] = max(dateien) if dateien else 0
    out["forensic_bytes_median"] = int(statistics.median(dateien)) if dateien else 0
    # Wie viele Faelle haben KEINE Datei? Genau die Zahl, die der Monitor als
    # 'ohne_forensic_db' fuehrt — sie kostet keine Lesezeit und erklaert
    # Abweichungen zwischen Fallzahl und Dateizahl.
    out["faelle_ohne_datei"] = max(
        0, out["faelle_gesamt"] - out["forensic_dateien"])
    return out


# --------------------------------------------- (2) Kosten EINER Datei

def kosten_je_datei(forensic_dir: str, hoechstens: int = 25) -> dict:
    """
    Misst, was das Oeffnen + MIN/MAX EINER forensic_<uid>.db kostet.

    Das ist die Groesse, mit der man hochrechnet: Gesamtzeit ~ Dateizahl x
    Einzelkosten.

    KORREKTUR NACH DER MESSUNG VOM 2026-07-25 (Fehler in v1 dieses Werkzeugs):
    v1 hat 'Spalte fehlt' als 'Datei nicht lesbar' gezaehlt und deshalb
    '0 lesbar, 25 nicht' gemeldet — obwohl ALLE 25 Dateien tadellos lesbar
    waren und lediglich eine SPALTE anders heisst. Das war eine irreführende
    Diagnose in einem Diagnosewerkzeug, also der schlechteste Ort dafuer. Die
    drei Lagen werden jetzt getrennt gezaehlt:
        lesbar        — Datei offen, mindestens eine Zeitspalte abgefragt
        spalte_fehlt  — Datei offen, aber die erwartete Spalte existiert nicht
        nicht_lesbar  — Datei laesst sich nicht oeffnen
    """
    d = Path(forensic_dir)
    if not d.is_dir():
        return {"gemessene_dateien": 0}
    kandidaten = sorted(
        [e for e in d.iterdir() if _FORENSIC_RE.match(e.name)])[:hoechstens]

    zeiten = []
    lesbar = spalte_fehlt = nicht_lesbar = 0
    gruende = {}
    for pfad in kandidaten:
        t0 = time.perf_counter()
        try:
            con = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
        except sqlite3.Error as exc:
            nicht_lesbar += 1
            gruende[str(exc)] = gruende.get(str(exc), 0) + 1
            zeiten.append(time.perf_counter() - t0)
            continue
        try:
            treffer = fehler = 0
            for tabelle, spalte in (("uid_posts", "posted"),
                                    ("uid_pms_posts", "posted_ts")):
                da = con.execute(
                    "SELECT 1 FROM sqlite_master WHERE type IN "
                    "('table','view') AND name=?", (tabelle,)).fetchone()
                if not da:
                    continue
                try:
                    con.execute("SELECT MIN(%s), MAX(%s) FROM %s "
                                "WHERE %s IS NOT NULL"
                                % (spalte, spalte, tabelle,
                                   spalte)).fetchone()
                    treffer += 1
                except sqlite3.Error as exc:
                    fehler += 1
                    schluessel = "%s.%s: %s" % (tabelle, spalte, exc)
                    gruende[schluessel] = gruende.get(schluessel, 0) + 1
            if treffer:
                lesbar += 1
            elif fehler:
                spalte_fehlt += 1
            else:
                lesbar += 1          # Tabellen fehlen ganz — auch das ist lesbar
        except sqlite3.Error as exc:
            nicht_lesbar += 1
            gruende[str(exc)] = gruende.get(str(exc), 0) + 1
        finally:
            con.close()
        zeiten.append(time.perf_counter() - t0)

    lo, med, hi = _kennzahlen(zeiten)
    return {"gemessene_dateien": len(kandidaten), "lesbar": lesbar,
            "spalte_fehlt": spalte_fehlt, "nicht_lesbar": nicht_lesbar,
            "gruende": gruende,
            "min_s": lo, "median_s": med, "max_s": hi, "summe_s": sum(zeiten)}


#: Tabellen, deren Spalten VOLLSTAENDIG ausgegeben werden. Fuer alle uebrigen
#  uid_*-Tabellen erscheinen nur die Zeitkandidaten — sonst waere die Ausgabe
#  unlesbar lang, und wir suchen hier gezielt Zeitanker.
SONDE_TABELLEN = ("uid_posts", "uid_pms_posts", "uid_profile",
                  "uid_surveillance")

#: Plausibler Epoch-Bereich fuer einen Zeitstempel: 1996-01-01 .. 2036-01-01.
#  Ein Wert ausserhalb ist kein Unix-Zeitstempel dieses Forums (das Forum ist
#  juenger, und ein Datum nach 2036 waere ein Datenfehler).
_EPOCH_VON, _EPOCH_BIS = 820454400, 2082758400

#: Obergrenze der Schema-Stichprobe. Sie greift nur, wenn die Tabellen von
#  Interesse in den kleinen Dateien nicht auftauchen.
_SONDE_MAX = 15


def schema_sonde(forensic_dir: str, hoechstens: int = 3) -> dict:
    """
    ERMITTELT DIE ECHTEN SPALTENNAMEN — der eigentliche Zweck von v2/v3.

    ANLASS (Befund 2026-07-25): Die Annahme 'uid_posts.posted' stammte aus einer
    TESTVORRICHTUNG (tests/test_build388_vorlagen.py), die die Tabelle selbst mit
    dieser Spalte anlegt — ein zirkulaerer Beleg. In den echten Datenbanken gibt
    es die Spalte nicht. Diese Sonde ersetzt die Annahme durch eine Messung.

    v3 prueft nicht mehr nur die zwei Beitragstabellen, sondern ALLE
    uid_*-Tabellen auf Zeitkandidaten — insbesondere auch uid_profile
    (Registrierungsdatum) und uid_surveillance (Anmeldungen aus der
    100a-Massnahme), die als Zeitanker in Betracht kommen. Auch fuer diese
    beiden gilt: ihre Spaltennamen sind im Repository nur ueber Testvorrichtungen
    und Platzhalter-SQL 'belegt', also NICHT belegt.

    AUSGEGEBEN WERDEN NUR STRUKTURangaben: Tabellen-, Spalten- und Typnamen,
    die Zahl der nicht-leeren Werte und — bei Zeitkandidaten — der
    ZUSAMMENGEFASSTE Datumsbereich ueber die Stichprobe. Es wird KEIN einzelner
    Wert ausgegeben und kein Bereich je Fall, damit daraus kein einzelner Fall
    ablesbar ist (Fallregel 3).

    DIE STICHPROBE NIMMT DIE KLEINSTEN DATEIEN. Das Schema ist in allen gleich,
    die Groesse ist dafuer belanglos — aber MIN/MAX ueber jede Spalte einer
    1-GiB-Datei waere ein voller Tabellendurchlauf je Spalte und damit unnoetig
    teuer.
    """
    d = Path(forensic_dir)
    if not d.is_dir():
        return {}
    alle = [e for e in d.iterdir() if _FORENSIC_RE.match(e.name)]
    try:
        alle.sort(key=lambda e: e.stat().st_size)
    except OSError:
        alle.sort()

    # SCHWACHSTELLE DER GROESSENSORTIERUNG, beim Probelauf aufgefallen: die
    # kleinsten Dateien koennen Tabellen NICHT enthalten, die in groesseren
    # stehen (ein Konto ohne private Nachrichten hat keine uid_pms_posts). Eine
    # Stichprobe von drei kleinen Dateien haette dann 'NICHT VORHANDEN'
    # gemeldet, obwohl die Tabelle existiert — also genau die Art Fehlschluss,
    # die diese Sonde ausraeumen soll. Deshalb wird WEITERGESUCHT, bis alle
    # Tabellen von Interesse einmal gesehen wurden (oder das Limit erreicht
    # ist). 'hoechstens' ist damit die MINDESTzahl, '_SONDE_MAX' die Obergrenze.
    # v4 — WARUM NICHT MEHR NUR DIE KLEINSTEN (Befund aus dem Lauf 2026-07-25):
    # Die kleinsten Dateien gehoeren zu Konten OHNE Beitraege. In der PROD-Probe
    # stand deshalb bei jeder Spalte von uid_posts 'nichtnull=0' — das Schema war
    # damit belegt, ueber die WERTE aber nichts. Genau die Werte brauchen wir
    # aber, um zu belegen, dass eine Spalte Unix-Sekunden fuehrt und nicht
    # irgendeine andere Zahl. Die Stichprobe nimmt jetzt die GROESSENSPANNE:
    # die kleinsten (billig, zeigen das Schema) UND die groessten (teurer, aber
    # gefuellt) UND die mittlere.
    n = max(1, hoechstens)
    kandidaten = []
    for e in alle[:n]:                       # die kleinsten
        kandidaten.append(e)
    if len(alle) > 2:                        # die mittlere
        mitte = alle[len(alle) // 2]
        if mitte not in kandidaten:
            kandidaten.append(mitte)
    for e in reversed(alle[-n:]):            # die groessten
        if e not in kandidaten:
            kandidaten.append(e)
    rest = [e for e in alle if e not in kandidaten]

    tabellen_gesehen = set()
    spalten = {}          # "tabelle.spalte" -> {typ, nichtnull, min, max, ...}
    fehler = {}
    i = 0
    while i < len(kandidaten):
        pfad = kandidaten[i]
        i += 1
        try:
            con = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
        except sqlite3.Error as exc:
            fehler[str(exc)] = fehler.get(str(exc), 0) + 1
            continue
        try:
            namen = [r[0] for r in con.execute(
                # ACHTUNG (Fehler in v3-Entwurf): 'uid[_]%' ESCAPE '[' ist
                # KEIN Klammerausdruck wie in anderen SQL-Dialekten — SQLite
                # kennt nur ESCAPE mit EINEM Zeichen, '[' wurde damit zum
                # Escape-Zeichen und das Muster zu 'uid_]%'. Es fand nichts.
                # Korrekt ist der Backslash als Escape.
                r"SELECT name FROM sqlite_master WHERE type IN "
                r"('table','view') AND name LIKE 'uid\_%' ESCAPE '\' "
                r"ORDER BY name")]
            tabellen_gesehen.update(namen)
            for tabelle in namen:
                try:
                    info = list(con.execute("PRAGMA table_info(%s)" % tabelle))
                except sqlite3.Error as exc:
                    fehler["%s: %s" % (tabelle, exc)] = 1
                    continue
                for zeile in info:
                    spalte, typ = zeile[1], (zeile[2] or "")
                    key = "%s.%s" % (tabelle, spalte)
                    e = spalten.setdefault(
                        key, {"tabelle": tabelle, "spalte": spalte,
                              "typ": typ, "nichtnull": 0, "min": None,
                              "max": None, "zeitkandidat": False,
                              "bezeichner_verdacht": False})
                    try:
                        row = con.execute(
                            'SELECT COUNT("%s"), MIN("%s"), MAX("%s") FROM %s'
                            % (spalte, spalte, spalte, tabelle)).fetchone()
                    except sqlite3.Error as exc:
                        fehler["%s: %s" % (key, exc)] = \
                            fehler.get("%s: %s" % (key, exc), 0) + 1
                        continue
                    if not row or not row[0]:
                        continue
                    e["nichtnull"] += int(row[0])
                    for wert, feld, fn in ((row[1], "min", min),
                                           (row[2], "max", max)):
                        try:
                            z = int(wert)
                        except (TypeError, ValueError):
                            continue
                        e[feld] = z if e[feld] is None else fn(e[feld], z)
                    if (e["min"] is not None and e["max"] is not None
                            and _EPOCH_VON <= e["min"] <= _EPOCH_BIS
                            and _EPOCH_VON <= e["max"] <= _EPOCH_BIS):
                        e["zeitkandidat"] = True
                        # FALSCHTREFFER AUS DEM LAUF 2026-07-25: 'uid_profile.id'
                        # wurde als Zeitkandidat gemeldet, weil Forum-Benutzer-IDs
                        # um 1,0 Mrd. liegen und damit rechnerisch in den
                        # Epoch-Bereich fallen (~2001). Solche Spalten werden
                        # NICHT ausgeblendet — das waere wieder eine stille
                        # Entscheidung —, sondern GEKENNZEICHNET. Die Bewertung
                        # bleibt beim Menschen.
                        name = spalte.lower()
                        e["bezeichner_verdacht"] = (
                            name == "id" or name.endswith("_id")
                            or name.endswith("_nr"))
        finally:
            con.close()

        # Fehlt noch eine Tabelle von Interesse? Dann eine weitere Datei
        # anhaengen (bis _SONDE_MAX). Der Nachschub wird an 'kandidaten'
        # angefuegt, damit die Schleife ihn mitnimmt.
        if (rest and len(kandidaten) < _SONDE_MAX
                and not set(SONDE_TABELLEN).issubset(tabellen_gesehen)):
            kandidaten.append(rest.pop(0))

    return {"dateien": len(kandidaten),
            "uid_tabellen": sorted(tabellen_gesehen), "spalten": spalten,
            "fehler": fehler,
            "nicht_gefunden": sorted(set(SONDE_TABELLEN) - tabellen_gesehen)}


def _sonde_ausgeben(sch: dict) -> None:
    """Druckt die Sonde: erst die Zeitkandidaten, dann die Detailtabellen."""
    if not sch.get("dateien"):
        print("  keine forensic_<uid>.db gefunden.")
        return
    print("  Stichprobe               : %d Dateien (kleinste, mittlere "
          "und groesste)" % sch["dateien"])
    print("  uid_*-Tabellen           : %s" % ", ".join(sch["uid_tabellen"]))
    print()

    kand = [e for e in sch["spalten"].values() if e["zeitkandidat"]]
    print("  ZEITKANDIDATEN (Werte liegen im Epoch-Bereich 1996..2036):")
    if not kand:
        print("    KEINE. Damit ist in dieser Stichprobe KEIN Unix-Zeitstempel")
        print("    auffindbar — das waere ein eigener, wichtiger Befund.")
    for e in sorted(kand, key=lambda x: (x["tabelle"], x["spalte"])):
        von = datetime.fromtimestamp(e["min"], tz=timezone.utc).date()
        bis = datetime.fromtimestamp(e["max"], tz=timezone.utc).date()
        warnung = ("  <-- ACHTUNG: Name deutet auf einen BEZEICHNER, nicht "
                   "auf eine Zeit" if e["bezeichner_verdacht"] else "")
        print("    %-38s %-8s nichtnull=%-9d %s .. %s%s"
              % (e["tabelle"] + "." + e["spalte"], e["typ"] or "?",
                 e["nichtnull"], von, bis, warnung))
    print()

    # Spalten OHNE Werte: das Schema ist belegt, die Bedeutung nicht.
    leer = [e for e in sch["spalten"].values()
            if e["nichtnull"] == 0 and e["tabelle"] in SONDE_TABELLEN]
    if leer:
        print("  OHNE WERTE in dieser Stichprobe (Schema belegt, Bedeutung "
              "NICHT belegt):")
        print("    %s" % ", ".join(sorted(
            "%s.%s" % (e["tabelle"], e["spalte"]) for e in leer)))
        print()

    print("  VOLLE SPALTENLISTE der Tabellen von Interesse:")
    for tabelle in SONDE_TABELLEN:
        eintraege = [e for e in sch["spalten"].values()
                     if e["tabelle"] == tabelle]
        if not eintraege:
            print("    %-22s in der Stichprobe NICHT GEFUNDEN (Stichprobe: "
                  "%d Dateien — das ist KEIN Beleg fuer Nichtexistenz)"
                  % (tabelle, sch["dateien"]))
            continue
        namen = ", ".join("%s(%s)" % (e["spalte"], e["typ"] or "?")
                          for e in sorted(eintraege,
                                          key=lambda x: x["spalte"]))
        print("    %-22s %s" % (tabelle, namen))
    if sch.get("fehler"):
        print()
        print("  LESEFEHLER (nicht verschwiegen):")
        for grund, n in sorted(sch["fehler"].items()):
            print("    %s (%dx)" % (grund, n))


# ------------------------------------------- (3) Rechenschicht direkt

def messung_direkt(coordinator_db: str, forensic_dir: str,
                   runs: int) -> dict:
    """
    Misst LimitationRepo.compute() OHNE HTTP — die eigentliche Datenbankarbeit.

    Der ERSTE Lauf wird getrennt ausgewiesen: er traegt die kalten Caches des
    Betriebssystems und entspricht dem Fall 'Ermittlerin oeffnet die Sicht
    morgens zum ersten Mal'. Die spaeteren Laeufe entsprechen dem wiederholten
    Aufruf. Beide Zahlen sind wichtig, und sie koennen weit auseinanderliegen —
    besonders auf einem Netzlaufwerk.
    """
    from management.deadlines.limitation_params import (
        LimitationParamsError, load_params)
    from management.deadlines.limitation_repo import LimitationRepo

    try:
        params = load_params()
    except LimitationParamsError as exc:
        return {"fehler": "Parametersatz unbrauchbar: %s" % exc}

    zeiten, zeilen, zaehler, datenlage = [], 0, {}, {}
    for i in range(max(1, runs)):
        con = _ro(coordinator_db)
        try:
            t0 = time.perf_counter()
            bericht = LimitationRepo(con, forensic_dir).compute(
                params=params, now_ts=int(time.time()))
            zeiten.append(time.perf_counter() - t0)
        finally:
            con.close()
        zeilen = bericht.faelle_gesamt
        zaehler = dict(bericht.zaehler)
        datenlage = dict(bericht.datenlage)

    lo, med, hi = _kennzahlen(zeiten)
    return {
        "laeufe": len(zeiten),
        "erster_lauf_s": zeiten[0],
        "min_s": lo, "median_s": med, "max_s": hi,
        "zeilen": zeilen,
        "aussage_moeglich": bool(params.verweigerungsgrund() is None),
        "zaehler": zaehler, "datenlage": datenlage,
    }


# ------------------------------------------------- (4) Endpunkt via HTTP

def messung_http(basis_url: str, runs: int) -> dict:
    """
    Misst GET /api/limitation ueber HTTP (Server muss laufen).

    Nur GET, kein X-AIW-Token noetig (der gilt nur fuer Schreibpfade,
    management_handler.py). Fehlt das Recht, kommt 403 — dann sagt das Werkzeug
    das, statt eine Zeit zu melden, die nichts messen wuerde.
    """
    import urllib.error
    import urllib.request

    url = basis_url.rstrip("/") + "/api/limitation"
    zeiten, status, groesse = [], None, 0
    for i in range(max(1, runs)):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(url, timeout=300) as antwort:
                rumpf = antwort.read()
                status = antwort.status
        except urllib.error.HTTPError as exc:
            return {"fehler": "HTTP %d bei %s — %s"
                              % (exc.code, url,
                                 "fehlt das Recht 'limitation.view'?"
                                 if exc.code == 403 else exc.reason)}
        except Exception as exc:                        # noqa: BLE001
            return {"fehler": "%s nicht erreichbar (%s). Laeuft "
                              "'python management.py'?" % (url, exc)}
        zeiten.append(time.perf_counter() - t0)
        groesse = len(rumpf)

    lo, med, hi = _kennzahlen(zeiten)
    return {"laeufe": len(zeiten), "status": status,
            "erster_lauf_s": zeiten[0], "min_s": lo, "median_s": med,
            "max_s": hi, "antwortgroesse_bytes": groesse}


# --------------------------------------------------------------------- main

def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="diag_limitation_laufzeit",
        description="Misst die Laufzeit des Fristenmonitors. REIN LESEND.")
    p.add_argument("--coordinator-db", default=None)
    p.add_argument("--forensic-dir", default=None)
    p.add_argument("--runs", type=int, default=3,
                   help="Wiederholungen (Vorgabe 3; der erste Lauf wird "
                        "getrennt ausgewiesen).")
    p.add_argument("--url", default=None,
                   help="Basis-URL des Management-Servers, z. B. "
                        "http://127.0.0.1:8090 — dann wird ZUSAETZLICH der "
                        "echte Endpunkt gemessen.")
    p.add_argument("--schema-dateien", type=int, default=3,
                   help="Wie viele (kleinste) Dateien die Schema-Sonde "
                        "anfasst. Vorgabe 3.")
    p.add_argument("--json", action="store_true",
                   help="Alles zusaetzlich als JSON ausgeben.")
    args = p.parse_args(argv)

    coordinator_db = args.coordinator_db or _cfg(
        "paths.coordinator_db", "./data/coordinator.db")
    forensic_dir = args.forensic_dir or _cfg(
        "paths.forensic_db_dir", "./data/forensic/")

    if not Path(coordinator_db).exists():
        print("[diag] coordinator.db nicht gefunden: %s" % coordinator_db,
              file=sys.stderr)
        return 2

    print("=" * 78)
    print("AIW — Laufzeitmessung Fristenmonitor (AP-3A). REIN LESEND.")
    print("=" * 78)
    print("Python      : %s" % sys.version.split()[0])
    print("System      : %s %s" % (platform.system(), platform.release()))
    print("coordinator : %s" % coordinator_db)
    print("forensic    : %s" % forensic_dir)
    print()

    b = bestand(coordinator_db, forensic_dir)
    print("--- BESTAND ---")
    print("  Faelle in 'cases'        : %d" % b["faelle_gesamt"])
    print("  je Status                : %s" % b["faelle_je_status"])
    print("  forensic_<uid>.db-Dateien: %d" % b["forensic_dateien"])
    print("  davon Faelle ohne Datei  : %d" % b["faelle_ohne_datei"])
    print("  Groesse gesamt           : %.1f MiB"
          % (b["forensic_bytes_gesamt"] / 1048576.0))
    print("  Groesse median / groesste: %.1f / %.1f MiB"
          % (b["forensic_bytes_median"] / 1048576.0,
             b["forensic_bytes_groesste"] / 1048576.0))
    print()

    sch = schema_sonde(forensic_dir, hoechstens=args.schema_dateien)
    print("--- SCHEMA-SONDE (nur Struktur, KEINE Werte) ---")
    _sonde_ausgeben(sch)
    print()

    k = kosten_je_datei(forensic_dir)
    print("--- KOSTEN EINER EINZELNEN DATEI (Stichprobe) ---")
    if k.get("gemessene_dateien"):
        print("  gemessen                 : %d Dateien "
              "(%d lesbar, %d mit fehlender Spalte, %d nicht oeffenbar)"
              % (k["gemessene_dateien"], k["lesbar"], k["spalte_fehlt"],
                 k["nicht_lesbar"]))
        for grund, n in sorted(k.get("gruende", {}).items()):
            print("      Grund: %s (%dx)" % (grund, n))
        print("  je Datei min/median/max  : %s / %s / %s"
              % (_fmt(k["min_s"]), _fmt(k["median_s"]), _fmt(k["max_s"])))
        if b["forensic_dateien"]:
            hoch = k["median_s"] * b["forensic_dateien"]
            print("  Hochrechnung auf %d Dateien: ~%s"
                  % (b["forensic_dateien"], _fmt(hoch)))
    else:
        print("  keine forensic_<uid>.db gefunden.")
    print()

    d = messung_direkt(coordinator_db, forensic_dir, args.runs)
    print("--- RECHENSCHICHT DIREKT (ohne HTTP) ---")
    if "fehler" in d:
        print("  FEHLER: %s" % d["fehler"])
    else:
        print("  Laeufe                   : %d" % d["laeufe"])
        print("  ERSTER Lauf (kalt)       : %s" % _fmt(d["erster_lauf_s"]))
        print("  min / median / max       : %s / %s / %s"
              % (_fmt(d["min_s"]), _fmt(d["median_s"]), _fmt(d["max_s"])))
        print("  Zeilen im Bericht        : %d" % d["zeilen"])
        print("  Fristaussage moeglich    : %s"
              % ("ja" if d["aussage_moeglich"] else
                 "nein (Parametersatz unbestaetigt — die MESSUNG ist davon "
                 "unberuehrt, es wird gleich viel gelesen)"))
        print("  Datenlage                : %s" % d["datenlage"])
        print("  Ampelverteilung          : %s" % d["zaehler"])
    print()

    h = None
    if args.url:
        h = messung_http(args.url, args.runs)
        print("--- ENDPUNKT UEBER HTTP ---")
        if "fehler" in h:
            print("  FEHLER: %s" % h["fehler"])
        else:
            print("  Status                   : %s" % h["status"])
            print("  ERSTER Lauf (kalt)       : %s" % _fmt(h["erster_lauf_s"]))
            print("  min / median / max       : %s / %s / %s"
                  % (_fmt(h["min_s"]), _fmt(h["median_s"]),
                     _fmt(h["max_s"])))
            print("  Antwortgroesse           : %.1f KiB"
                  % (h["antwortgroesse_bytes"] / 1024.0))
        print()

    # ------------------------------------------------ Block zum Zuruecksenden
    print("=" * 78)
    print("ERGEBNIS ZUM ZURUECKMELDEN (enthaelt KEINE Fallinhalte)")
    print("=" * 78)
    zeile = ("Faelle=%d  forensic-Dateien=%d  Gesamtgroesse=%.1fMiB  "
             % (b["faelle_gesamt"], b["forensic_dateien"],
                b["forensic_bytes_gesamt"] / 1048576.0))
    if "fehler" not in d:
        zeile += ("direkt: erster=%s median=%s max=%s  "
                  % (_fmt(d["erster_lauf_s"]), _fmt(d["median_s"]),
                     _fmt(d["max_s"])))
    if h and "fehler" not in h:
        zeile += ("http: erster=%s median=%s  "
                  % (_fmt(h["erster_lauf_s"]), _fmt(h["median_s"])))
    if k.get("gemessene_dateien"):
        zeile += "je-Datei-median=%s" % _fmt(k["median_s"])
    print(zeile)
    print("Umgebung: Python %s, %s %s"
          % (sys.version.split()[0], platform.system(), platform.release()))
    print("=" * 78)

    if args.json:
        print()
        print(json.dumps({"bestand": b, "je_datei": k, "schema": sch, "direkt": d,
                          "http": h}, ensure_ascii=False, indent=2,
                         default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
