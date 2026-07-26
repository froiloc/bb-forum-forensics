#!/usr/bin/env python3
# =============================================================================
# tools/diag_matrix_laufzeit.py
# IT-Forensisches Ermittlungswerkzeug — DIAGNOSE-Werkzeug (AP-3B, Build 538)
# =============================================================================
# Zweck:
#   Beantwortet EINE Frage mit Zahlen: Was kostet die FRISTKOMPONENTE der
#   Dringlichkeits-/Erkenntnislage-Matrix — und ist die Matrix MIT Fristen im
#   Betrieb zumutbar, oder braucht die Sicht das Nachladen?
#
#   Die Matrix hat sechs Beitraege. Fuenf davon kosten zusammen fuenf Abfragen
#   auf EINER Verbindung. Der sechste — die Verjaehrungsfrist (X-1) — oeffnet
#   je Fall bis zu zwei Dateien (forensic_<uid>.db, evidence_<uid>.db). Genau
#   dieser Unterschied wird hier gemessen: einmal mit, einmal ohne.
#
#   Die Entscheidung, die davon abhaengt: ob die Sicht (Build 539) die Fristen
#   sofort mitlaedt oder erst auf Anforderung. Sie wird NICHT auf Verdacht
#   getroffen — der Fristenmonitor hat 2026-07-25 gezeigt, dass der Faktor
#   zwischen DEV und PROD (Netzlaufwerk) bei rund 24 liegt. Eine im Container
#   gemessene Zahl beweist fuer PROD nichts; deshalb dieses Werkzeug.
#
# FORENSISCHE SORGFALT (Grundregel 1 — keine stillen Aenderungen):
#   * ALLE Datenbanken werden AUSSCHLIESSLICH LESEND geoeffnet, ueber URI
#     'file:...?mode=ro'. Kein PRAGMA, das Header oder Journalmodus aendert.
#   * Es wird NICHTS geschrieben: keine Datei, keine Zeile, kein audit_log-
#     Eintrag. Das Werkzeug ist in PROD gefahrlos ausfuehrbar.
#   * Es wird KEIN Fallinhalt ausgegeben — Zahlen und Codes, keine
#     Kontonamen, keine Annotationstexte (Fallregel 3). Der Block am Ende darf
#     unbedenklich in ein Chat-Protokoll kopiert werden.
#
# AUFRUF (in der VM, aus dem Verzeichnis des Webservers, z. B. S:\):
#     python tools/diag_matrix_laufzeit.py
#     python tools/diag_matrix_laufzeit.py --runs 5
#     python tools/diag_matrix_laufzeit.py --url http://127.0.0.1:8090
#     python tools/diag_matrix_laufzeit.py --coordinator-db D:\pfad\coordinator.db \
#                                          --forensic-dir D:\pfad\forensic \
#                                          --evidence-dir D:\pfad\evidence
#
#   Ohne --url wird die Rechenschicht DIREKT gemessen (ohne HTTP). Das ist die
#   aussagekraeftigere Messung, weil sie die Dateiarbeit isoliert. Mit --url
#   wird zusaetzlich der echte Endpunkt gemessen; dazu muss der Management-
#   Server laufen und die aufrufende Person 'matrix.view' haben.
#
# ERWARTETE AUSGABE: ein Block 'ERGEBNIS ZUM ZURUECKMELDEN' am Ende. Genau
#   diesen Block bitte zurueckschicken — je einmal aus DEV und aus PROD.
#
# Version: v0.8.538 · 2026-07-26 · Diagnose, NICHT Teil des Produktivsystems
# =============================================================================

from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


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
    except Exception:                                   # noqa: BLE001
        return vorgabe


def _fmt(sek: float) -> str:
    """
    Lesbare Zeit. Unter 1 ms in Mikrosekunden — '0 ms' waere keine Messung,
    sondern eine gerundete Nichtaussage (uebernommen aus
    tools/diag_limitation_laufzeit.py).
    """
    if sek < 0.001:
        return "%.0f us" % (sek * 1000000.0)
    if sek < 1.0:
        return "%.1f ms" % (sek * 1000.0)
    return "%.2f s" % sek


def _kennzahlen(werte: List[float]):
    if not werte:
        return (0.0, 0.0, 0.0)
    return (min(werte), statistics.median(werte), max(werte))


# ------------------------------------------------------------ (1) Bestand

def bestand(coordinator_db: str, forensic_dir: str,
            evidence_dir: str) -> Dict[str, Any]:
    """Zaehlt, WORAN gemessen wird. Rein lesend, keine Inhalte."""
    out: Dict[str, Any] = {
        "coordinator_db": coordinator_db,
        "forensic_dir": forensic_dir,
        "evidence_dir": evidence_dir,
    }
    con = _ro(coordinator_db)
    try:
        out["faelle_gesamt"] = int(con.execute(
            "SELECT COUNT(*) FROM cases").fetchone()[0])
        out["faelle_unzugewiesen"] = int(con.execute(
            "SELECT COUNT(*) FROM cases WHERE assigned_to IS NULL"
        ).fetchone()[0])
    finally:
        con.close()

    for schluessel, verz, muster in (
            ("forensic", forensic_dir, "forensic_*.db"),
            ("evidence", evidence_dir, "evidence_*.db")):
        p = Path(verz)
        dateien = sorted(p.glob(muster)) if p.is_dir() else []
        groessen = [f.stat().st_size for f in dateien]
        out["%s_dateien" % schluessel] = len(dateien)
        out["%s_bytes_gesamt" % schluessel] = sum(groessen)
        out["%s_bytes_median" % schluessel] = (
            int(statistics.median(groessen)) if groessen else 0)
    return out


# ------------------------------------------- (2) Messung ohne/mit Fristen

def messung_direkt(coordinator_db: str, forensic_dir: str,
                   evidence_dir: Optional[str], runs: int) -> Dict[str, Any]:
    """
    Misst MatrixRepo.compute() zweimal: mit_fristen=False und True.

    Der ERSTE Lauf wird getrennt ausgewiesen — er traegt die kalten Caches des
    Betriebssystems und entspricht dem Fall 'die Leitung oeffnet die Sicht
    morgens zum ersten Mal'. Auf einem Netzlaufwerk liegen erster und
    spaeterer Lauf weit auseinander, und beide Zahlen werden gebraucht.

    Die Antwort traegt seit Build 538 selbst 'dauer_gesamt_ms' und
    'dauer_fristen_ms'. Diese Werte werden MITGEMELDET und nicht durch die
    Stoppuhr des Werkzeugs ersetzt: weichen sie voneinander ab, steckt der
    Unterschied im Aufbau der Verbindung oder in der Serialisierung, und das
    ist eine eigene Aussage.
    """
    from management.results.matrix_repo import MatrixRepo
    from management.results.matrix_weights import (
        MatrixWeightsError, load_weights,
    )

    try:
        gewichte = load_weights()
    except MatrixWeightsError as exc:
        return {"fehler": "Gewichtungssatz unbrauchbar: %s" % exc}

    ergebnis: Dict[str, Any] = {}
    for name, mit in (("ohne_fristen", False), ("mit_fristen", True)):
        zeiten: List[float] = []
        letzter: Dict[str, Any] = {}
        for _ in range(max(1, runs)):
            con = _ro(coordinator_db)
            try:
                t0 = time.perf_counter()
                letzter = MatrixRepo(
                    con, gewichte, forensic_dir, evidence_dir
                ).compute(now_ts=int(time.time()), mit_fristen=mit)
                zeiten.append(time.perf_counter() - t0)
            except Exception as exc:                    # noqa: BLE001
                ergebnis[name] = {"fehler": str(exc)}
                break
            finally:
                con.close()
        if name in ergebnis:
            continue
        lo, med, hi = _kennzahlen(zeiten)
        ergebnis[name] = {
            "laeufe": len(zeiten),
            "erster_lauf_s": zeiten[0] if zeiten else 0.0,
            "min_s": lo, "median_s": med, "max_s": hi,
            "faelle": letzter.get("faelle_gesamt"),
            "fristen_geladen": letzter.get("fristen_geladen"),
            "dauer_gesamt_ms": letzter.get("dauer_gesamt_ms"),
            "dauer_fristen_ms": letzter.get("dauer_fristen_ms"),
            "quadranten": letzter.get("quadranten"),
            "belastbarkeit": letzter.get("belastbarkeit_verteilung"),
            "fehlende_quellen": letzter.get("fehlende_quellen"),
        }
    return ergebnis


# ------------------------------------------------- (3) Endpunkt via HTTP

def messung_http(basis_url: str, runs: int) -> Dict[str, Any]:
    """
    Misst GET /api/matrix ueber HTTP, einmal mit und einmal ohne Fristen.

    Nur GET, kein X-AIW-Token noetig (der gilt nur fuer Schreibpfade).
    Fehlt das Recht, kommt 403 — dann wird das GESAGT, statt eine Zeit zu
    melden, die nichts misst.
    """
    import urllib.error
    import urllib.request

    out: Dict[str, Any] = {}
    for name, pfad in (("ohne_fristen", "/api/matrix?fristen=0"),
                       ("mit_fristen", "/api/matrix?fristen=1")):
        url = basis_url.rstrip("/") + pfad
        zeiten: List[float] = []
        status: Optional[int] = None
        groesse = 0
        for _ in range(max(1, runs)):
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(url, timeout=600) as resp:
                    roh = resp.read()
                    status = resp.status
                    groesse = len(roh)
                zeiten.append(time.perf_counter() - t0)
            except urllib.error.HTTPError as exc:
                out[name] = {"fehler": "HTTP %s" % exc.code,
                             "hinweis": "403 heisst: 'matrix.view' fehlt."}
                break
            except Exception as exc:                    # noqa: BLE001
                out[name] = {"fehler": str(exc)}
                break
        if name in out:
            continue
        lo, med, hi = _kennzahlen(zeiten)
        out[name] = {"status": status, "laeufe": len(zeiten),
                     "erster_lauf_s": zeiten[0] if zeiten else 0.0,
                     "min_s": lo, "median_s": med, "max_s": hi,
                     "antwortgroesse_bytes": groesse}
    return out


def _block_ausgeben(titel: str, d: Dict[str, Any]) -> None:
    print("--- %s ---" % titel)
    if "fehler" in d:
        print("  FEHLER: %s" % d["fehler"])
        print()
        return
    print("  Laeufe                   : %d" % d.get("laeufe", 0))
    print("  ERSTER Lauf (kalt)       : %s" % _fmt(d.get("erster_lauf_s", 0.0)))
    print("  min / median / max       : %s / %s / %s"
          % (_fmt(d.get("min_s", 0.0)), _fmt(d.get("median_s", 0.0)),
             _fmt(d.get("max_s", 0.0))))
    if "faelle" in d:
        print("  Faelle                   : %s" % d.get("faelle"))
        print("  fristen_geladen          : %s" % d.get("fristen_geladen"))
        print("  Selbstmessung gesamt/Frist: %s ms / %s ms"
              % (d.get("dauer_gesamt_ms"), d.get("dauer_fristen_ms")))
        print("  Quadranten               : %s" % d.get("quadranten"))
        print("  Belastbarkeit            : %s" % d.get("belastbarkeit"))
        if d.get("fehlende_quellen"):
            print("  FEHLENDE QUELLEN         : %s"
                  % "; ".join(d["fehlende_quellen"]))
    if "antwortgroesse_bytes" in d:
        print("  Antwortgroesse           : %.1f KiB"
              % (d["antwortgroesse_bytes"] / 1024.0))
    print()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="diag_matrix_laufzeit",
        description="Misst die Laufzeit der Matrix mit und ohne Fristen. "
                    "REIN LESEND.")
    p.add_argument("--coordinator-db", default=None)
    p.add_argument("--forensic-dir", default=None)
    p.add_argument("--evidence-dir", default=None)
    p.add_argument("--runs", type=int, default=3,
                   help="Wiederholungen je Variante (Vorgabe 3; der erste "
                        "Lauf wird getrennt ausgewiesen).")
    p.add_argument("--url", default=None,
                   help="Basis-URL des Management-Servers, z. B. "
                        "http://127.0.0.1:8090 — dann wird ZUSAETZLICH der "
                        "echte Endpunkt gemessen.")
    p.add_argument("--json", action="store_true",
                   help="Alles zusaetzlich als JSON ausgeben.")
    args = p.parse_args(argv)

    coordinator_db = args.coordinator_db or _cfg(
        "paths.coordinator_db", "./data/coordinator.db")
    forensic_dir = args.forensic_dir or _cfg(
        "paths.forensic_db_dir", "./data/forensic/")
    evidence_dir = args.evidence_dir or _cfg(
        "paths.evidence_db_dir", "./data/evidence/")

    if not Path(coordinator_db).exists():
        print("[diag] coordinator.db nicht gefunden: %s" % coordinator_db,
              file=sys.stderr)
        return 2

    print("=" * 78)
    print("AIW — Laufzeitmessung Matrix (AP-3B, Build 538). REIN LESEND.")
    print("=" * 78)
    print("Python      : %s" % sys.version.split()[0])
    print("System      : %s %s" % (platform.system(), platform.release()))
    print("coordinator : %s" % coordinator_db)
    print("forensic    : %s" % forensic_dir)
    print("evidence    : %s" % evidence_dir)
    print()

    b = bestand(coordinator_db, forensic_dir, evidence_dir)
    print("--- BESTAND ---")
    print("  Faelle in 'cases'        : %d" % b["faelle_gesamt"])
    print("  davon unzugewiesen       : %d" % b["faelle_unzugewiesen"])
    print("  forensic_<uid>.db        : %d Dateien, %.1f MiB gesamt"
          % (b["forensic_dateien"], b["forensic_bytes_gesamt"] / 1048576.0))
    print("  evidence_<uid>.db        : %d Dateien, %.1f MiB gesamt"
          % (b["evidence_dateien"], b["evidence_bytes_gesamt"] / 1048576.0))
    print()

    d = messung_direkt(coordinator_db, forensic_dir, evidence_dir, args.runs)
    if "fehler" in d:
        print("--- DIREKTMESSUNG ---")
        print("  FEHLER: %s" % d["fehler"])
        print()
    else:
        _block_ausgeben("DIREKT, OHNE FRISTEN (fuenf Beitraege)",
                        d.get("ohne_fristen", {}))
        _block_ausgeben("DIREKT, MIT FRISTEN (sechs Beitraege)",
                        d.get("mit_fristen", {}))

    h: Dict[str, Any] = {}
    if args.url:
        h = messung_http(args.url, args.runs)
        _block_ausgeben("HTTP, OHNE FRISTEN", h.get("ohne_fristen", {}))
        _block_ausgeben("HTTP, MIT FRISTEN", h.get("mit_fristen", {}))

    # ------------------------------------------------ Block zum Zuruecksenden
    print("=" * 78)
    print("ERGEBNIS ZUM ZURUECKMELDEN (enthaelt KEINE Fallinhalte)")
    print("=" * 78)
    zeile = ("Faelle=%d  forensic=%d(%.1fMiB)  evidence=%d(%.1fMiB)  "
             % (b["faelle_gesamt"], b["forensic_dateien"],
                b["forensic_bytes_gesamt"] / 1048576.0,
                b["evidence_dateien"],
                b["evidence_bytes_gesamt"] / 1048576.0))
    ohne = d.get("ohne_fristen", {}) if "fehler" not in d else {}
    mit = d.get("mit_fristen", {}) if "fehler" not in d else {}
    if ohne and "fehler" not in ohne:
        zeile += ("ohneFrist: erster=%s median=%s  "
                  % (_fmt(ohne["erster_lauf_s"]), _fmt(ohne["median_s"])))
    if mit and "fehler" not in mit:
        zeile += ("mitFrist: erster=%s median=%s (davon Frist %s ms)  "
                  % (_fmt(mit["erster_lauf_s"]), _fmt(mit["median_s"]),
                     mit.get("dauer_fristen_ms")))
    if (ohne and mit and "fehler" not in ohne and "fehler" not in mit
            and ohne["median_s"] > 0):
        zeile += "Faktor=%.1fx" % (mit["median_s"] / ohne["median_s"])
    print(zeile)
    print("Umgebung: Python %s, %s %s"
          % (sys.version.split()[0], platform.system(), platform.release()))
    print("=" * 78)

    if args.json:
        print()
        print(json.dumps({"bestand": b, "direkt": d, "http": h},
                         ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
