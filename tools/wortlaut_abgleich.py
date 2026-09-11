#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# tools/wortlaut_abgleich.py
# IT-Forensisches Ermittlungswerkzeug - aiw_webserver
# BUILD 767
# =============================================================================
# ZWECK
#   MESSEN, ob der gespeicherte 'selection_json.textContent' im page BLOB
#   wiederzufinden ist - und wo. Rein lesend, es wird nichts geschrieben und
#   nichts entschieden.
#
# WARUM EIN EIGENES WERKZEUG
#   'anker_diagnose' beantwortet die Frage 'loest der Ausdruck auf und welchen
#   Umfang hat die Markierung'. Diese hier beantwortet 'steht der Wortlaut
#   ueberhaupt dort, wo der Ausdruck hinzeigt'. Das sind verschiedene Fragen,
#   der Lauf ist laenger, und 'anker_diagnose' traegt bereits sechs Messungen.
#   Getrennt bleibt jede fuer sich lesbar (Festlegung Alex, 08.09.2026).
#
# WAS DIESER LAUF BEANTWORTEN SOLL
#   Im Lauf zu Build 766 standen 107 Annotationen als WIDERLEGT: der Ausdruck
#   loest auf, aber der markierte Wortlaut steht dort nicht. Nur 6 davon
#   brechen strukturell. Bei den uebrigen 101 liefert der Berichtsgenerator
#   heute stillschweigend den falschen Text, weil '_ueber_xpath()' den Fund
#   nie gegen 'textContent' haelt.
#
#   Dieser Lauf sagt, WO der Wortlaut stattdessen steht - im benannten
#   Beitrag, in einem der zehn Nachbarn oder irgendwo auf der Seite - und wie
#   eindeutig der Fund ist.
#
# WARTUNGSSTUFE
#   C - rein lesend, beide Verbindungen 'mode=ro'.
# =============================================================================
import argparse
import json
import sqlite3
import sys
from pathlib import Path

_WURZEL = Path(__file__).resolve().parent.parent
if str(_WURZEL) not in sys.path:
    sys.path.insert(0, str(_WURZEL))

from core import werkzeug_konfig                                  # noqa: E402
from core.config_loader import coded_default                      # noqa: E402
from management.help import cli_epilog                            # noqa: E402
from management.maintenance import bestandsliste                  # noqa: E402
from management.maintenance.bestandsliste import (                # noqa: E402
    bestaende_finden)
from management.maintenance.laufkopf import Laufkopf              # noqa: E402
from management.maintenance.anker_diagnose import (               # noqa: E402
    AnkerDiagnose)
from management.maintenance.anker_postbezug import seitenklasse   # noqa: E402
from management.maintenance.wortlaut_abgleich import (            # noqa: E402
    STUFEN, WortlautAbgleich)
from management.maintenance.wortlaut_norm import (                # noqa: E402
    VERSTECKTE_KLASSEN)


#: Die Dateien, die das ERGEBNIS dieses Laufs tragen.
_GETRAGEN_VON = (
    "tools/wortlaut_abgleich.py",
    "management/maintenance/wortlaut_abgleich.py",
    "management/maintenance/wortlaut_norm.py",
    "management/maintenance/post_bereiche.py",
    "report_render/absatz_finder.py",
    "report_render/html5_zerleger.py",
)

#: Der Lernfall: die einzige Annotation in Version 1.9.0, von Alex am
#: 08.09.2026 zu Testzwecken eingefuegt. Sie traegt bereits einen
#: 'meta'-Zweig und den Zensurbaustein. Sie ist KEIN Blocker - scheitert sie,
#: ist das eine Auskunft und kein Fehlschlag des Laufs.
_LERNFALL = ("1488", 273)


class Mitschrift:
    """Ausgabe auf die Konsole und, wenn gewuenscht, in eine Datei."""

    def __init__(self, pfad: str = "") -> None:
        self._datei = open(pfad, "w", encoding="utf-8") if pfad else None

    def __call__(self, text: str = "") -> None:
        print(text)
        if self._datei:
            self._datei.write(text + "\n")

    def schliessen(self) -> None:
        if self._datei:
            self._datei.close()
            self._datei = None


def _argumente(argv):
    p = argparse.ArgumentParser(
        description="Wortlautabgleich: steht der markierte Text im Abzug?",
        epilog=cli_epilog.epilog("wortlaut_abgleich"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--evidence", default=None,
                   help="Pfad zu evidence_<uid>.db (wird NUR gelesen)")
    p.add_argument("--forensic", default=None,
                   help="Pfad zu forensic_<uid>.db (wird NUR gelesen)")
    p.add_argument("--config", default="./config.yaml",
                   help="Konfigurationsdatei fuer die Verzeichnisvorgaben")
    p.add_argument("--evidence-dir", default=None,
                   help="Verzeichnis der evidence_<uid>.db")
    p.add_argument("--forensic-dir", default=None,
                   help="Verzeichnis der forensic_<uid>.db")
    p.add_argument("--uid", action="append", default=[],
                   help="nur diesen Bestand (mehrfach angebbar)")
    p.add_argument("--grenze", type=int, default=0,
                   help="hoechstens so viele Belege je Bestand; 0 = alle")
    p.add_argument("--protokoll", default="",
                   help="die Ausgabe zusaetzlich in diese Datei schreiben")
    p.add_argument("--json", dest="json_ziel", default=None,
                   help="den Befund zusaetzlich maschinenlesbar hierhin "
                        "schreiben")
    return p.parse_args(argv)


def _bestaende_bestimmen(a, m):
    """Die Liste (uid, evidence_pfad, forensic_pfad) - wie anker_diagnose."""
    if a.evidence or a.forensic:
        if not (a.evidence and a.forensic):
            m("Aufruffehler: --evidence und --forensic gehoeren zusammen.")
            return None
        treffer = bestandsliste.RE_EVIDENCE.match(Path(a.evidence).name)
        return [(treffer.group(1) if treffer else "", a.evidence, a.forensic)]

    aufl = werkzeug_konfig.resolver(a)
    evidence_dir = werkzeug_konfig.wert(
        "wortlaut_abgleich", a, arg_attribut="evidence_dir",
        arg_name="--evidence-dir", config_schluessel="paths.evidence_db_dir",
        default=coded_default("paths.evidence_db_dir"),
        name="evidence_db_dir", r=aufl)
    forensic_dir = werkzeug_konfig.wert(
        "wortlaut_abgleich", a, arg_attribut="forensic_dir",
        arg_name="--forensic-dir", config_schluessel="paths.forensic_db_dir",
        default=coded_default("paths.forensic_db_dir"),
        name="forensic_db_dir", r=aufl)

    gefunden = bestaende_finden(evidence_dir)
    if not gefunden:
        m("Keine evidence_<uid>.db in %s gefunden." % evidence_dir)
        return None
    if a.uid:
        gewuenscht = {str(u) for u in a.uid}
        gefunden = [g for g in gefunden if g[0] in gewuenscht]
        if not gefunden:
            m("Keiner der genannten Bestaende liegt in %s." % evidence_dir)
            return None
    return [(uid, pfad, str(Path(forensic_dir) / ("forensic_%s.db" % uid)))
            for uid, pfad in gefunden]


def _zeilen(con, grenze: int):
    """
    Alle AKTIVEN Annotationen - auch die ohne XPath-Anker.

    Anders als anker_diagnose wird hier NICHT auf den Anker gefiltert: die
    Frage lautet, ob der Wortlaut im Abzug steht, und die stellt sich auch
    fuer eine Beitragsmarkierung.
    """
    sql = ("SELECT id, page_url, selection_json, post_id, element_id, "
           "deleted_at FROM annotations ORDER BY id")
    heraus = []
    for r in con.execute(sql):
        heraus.append(r)
        if grenze > 0 and len(heraus) >= grenze:
            break
    return heraus


def _selection(roh):
    try:
        sel = json.loads(roh) if isinstance(roh, (str, bytes)) else roh
    except (ValueError, TypeError):
        return None
    return sel if isinstance(sel, dict) else None


def _ein_bestand(m, uid: str, ev_pfad: str, fo_pfad: str, grenze: int):
    """Ein Bestand. Rueckgabe: (rueckgabewert, Zaehlung, Belegliste)."""
    m("=" * 78)
    m("BESTAND %s" % (uid or "(Kennung nicht ablesbar)"))
    m("=" * 78)

    for pfad in (Path(ev_pfad), Path(fo_pfad)):
        if not pfad.exists():
            m("Datei fehlt: %s" % pfad)
            return 1, {}, []

    # Der BLOB-Zugriff wird von AnkerDiagnose uebernommen und NICHT
    # nachgebaut: dort stehen die vier Abfragen und der Filter auf
    # method='GET'. Ein Werkzeug, das einen ANDEREN Abzug liest als das,
    # dessen Verhalten es erklaeren soll, erklaert nichts (Build 731).
    d = AnkerDiagnose(evidence=Path(ev_pfad), forensic=Path(fo_pfad))
    con = d._oeffnen()
    d._con_blob = con

    zaehlung = {"aktiv": 0, "geloescht": 0, "deleted_at_leer": 0,
                "ohne_wortlaut": 0, "mit_meta": 0, "geprueft": 0,
                "gefunden": 0, "eindeutig": 0, "zu_kurz": 0,
                "versteckt_wirksam": 0, "ohne_abzug": 0,
                "stufen": {s: 0 for s in STUFEN},
                "lagen": {}, "versteckte_klassen": {}}
    belege = []
    abgleich_je_seite = {}

    try:
        for r in _zeilen(con, grenze):
            geloescht = r["deleted_at"] is not None
            if geloescht and str(r["deleted_at"]).strip() == "":
                # Die Unterscheidung NULL gegen leere Zeichenkette: ein
                # Exportwerkzeug zeigt beides gleich, SQLite nicht. Wer sie
                # verwechselt, verliert einen Beleg lautlos.
                zaehlung["deleted_at_leer"] += 1
            if geloescht:
                zaehlung["geloescht"] += 1
                continue
            zaehlung["aktiv"] += 1

            sel = _selection(r["selection_json"])
            wortlaut = str((sel or {}).get("textContent") or "")
            if sel and isinstance(sel.get("meta"), dict):
                zaehlung["mit_meta"] += 1
            if not wortlaut.strip():
                zaehlung["ohne_wortlaut"] += 1
                continue

            url = str(r["page_url"] or "")
            if url not in abgleich_je_seite:
                sichten = d._sichten(url)
                abgleich_je_seite[url] = (
                    WortlautAbgleich(sichten[2].wurzel, seitenklasse(url))
                    if sichten else None)
            a = abgleich_je_seite[url]
            if a is None:
                zaehlung["ohne_abzug"] += 1
                continue

            for name, zahl in a.versteckte_klassen.items():
                zaehlung["versteckte_klassen"][name] = max(
                    zaehlung["versteckte_klassen"].get(name, 0), zahl)

            post_id = r["post_id"]
            try:
                post_id = int(post_id) if post_id is not None else None
            except (TypeError, ValueError):
                post_id = None

            b = a.pruefe(wortlaut, post_id)
            zaehlung["geprueft"] += 1
            if b.gefunden:
                zaehlung["gefunden"] += 1
                zaehlung["stufen"][b.stufe] += 1
                lage = b.fundorte[0].lage or "(unbestimmt)"
                zaehlung["lagen"][lage] = zaehlung["lagen"].get(lage, 0) + 1
            if b.eindeutig:
                zaehlung["eindeutig"] += 1
            if b.zu_kurz:
                zaehlung["zu_kurz"] += 1
            if b.versteckt_wirksam:
                zaehlung["versteckt_wirksam"] += 1

            eintrag = b.als_dict()
            eintrag["annotation_id"] = int(r["id"])
            eintrag["page_url"] = url
            eintrag["page_class"] = seitenklasse(url)
            eintrag["has_meta"] = bool(sel
                                       and isinstance(sel.get("meta"), dict))
            belege.append(eintrag)
    finally:
        con.close()
        d._con_blob = None

    _bericht(m, uid, zaehlung, belege)
    return 0, zaehlung, belege


def _bericht(m, uid, z, belege) -> None:
    m()
    m("BESTANDSAUFNAHME")
    m("   aktive Annotationen:            %d" % z["aktiv"])
    m("   als geloescht gefuehrt:         %d" % z["geloescht"])
    if z["deleted_at_leer"]:
        m("   davon mit LEERER Zeichenkette:  %d   <== kein NULL, also "
          "als geloescht behandelt" % z["deleted_at_leer"])
    m("   ohne gespeicherten Wortlaut:    %d" % z["ohne_wortlaut"])
    m("   mit 'meta'-Zweig (Version 1.9): %d" % z["mit_meta"])
    m("   ohne Seitenabzug:               %d" % z["ohne_abzug"])
    m()
    m("ABGLEICH")
    m("   geprueft:                       %d" % z["geprueft"])
    m("   Wortlaut gefunden:              %d" % z["gefunden"])
    m("   davon eindeutig:                %d" % z["eindeutig"])
    m("   zu kurz fuer eine Aussage:      %d" % z["zu_kurz"])
    m("   Ausschluss versteckter Teile war wirksam: %d"
      % z["versteckt_wirksam"])
    m()
    m("   STUFE DES TREFFERS - sie sagt, wie weit der Anker danebenliegt:")
    m("      benannter Beitrag:           %d" % z["stufen"]["named_post"])
    m("      einer der zehn Nachbarn:     %d" % z["stufen"]["neighbours"])
    m("      irgendwo auf der Seite:      %d" % z["stufen"]["page"])
    m("      nicht gefunden:              %d"
      % (z["geprueft"] - z["gefunden"]))
    m()
    m("   LAGE DES TREFFERS:")
    for name, zahl in sorted(z["lagen"].items()):
        m("      %-28s %d" % (name, zahl))
    if z["versteckte_klassen"]:
        m()
        m("   VERSTECKTE ELEMENTE im Bestand (Hoechstzahl je Seite):")
        for name, zahl in sorted(z["versteckte_klassen"].items()):
            m("      %-28s %d" % (name, zahl))
    m()


def _gesamt(m, zaehlungen, belege) -> None:
    m("=" * 78)
    m("GESAMTZAEHLUNG UEBER ALLE BESTAENDE")
    m("=" * 78)
    summe = {}
    for z in zaehlungen:
        for k, v in z.items():
            if isinstance(v, int):
                summe[k] = summe.get(k, 0) + v
    stufen = {s: sum(z["stufen"][s] for z in zaehlungen) for s in STUFEN}
    for k in ("aktiv", "geloescht", "ohne_wortlaut", "mit_meta", "geprueft",
              "gefunden", "eindeutig", "zu_kurz", "versteckt_wirksam",
              "ohne_abzug"):
        m("   %-32s %d" % (k, summe.get(k, 0)))
    m()
    m("   benannter Beitrag:               %d" % stufen["named_post"])
    m("   einer der zehn Nachbarn:         %d" % stufen["neighbours"])
    m("   irgendwo auf der Seite:          %d" % stufen["page"])
    m("   NICHT GEFUNDEN:                  %d"
      % (summe.get("geprueft", 0) - summe.get("gefunden", 0)))
    m()
    # DIE VERTEILUNG, AUS DER ALEX DIE SCHWELLE ABLEITET. Sie wird gezeigt
    # und nicht angewandt - eine Grenze, die ich mir ausdenke, waere eine
    # Festlegung ohne Messung.
    ohne = [b for b in belege if not b["found"]]
    if ohne:
        m("   AEHNLICHKEIT DER NICHT GEFUNDENEN (%d):" % len(ohne))
        koerbe = [(0.9, "0.90 - 1.00"), (0.8, "0.80 - 0.89"),
                  (0.6, "0.60 - 0.79"), (0.4, "0.40 - 0.59"),
                  (0.0, "unter 0.40")]
        for grenze, name in koerbe:
            zahl = sum(1 for b in ohne if b["best_similarity"] >= grenze)
            m("      %-14s %d" % (name, zahl))
            ohne = [b for b in ohne if b["best_similarity"] < grenze]
    m()
    m("KEINE SCHWELLE IST ANGEWANDT. Dieser Lauf misst; ob eine Aehnlichkeit")
    m("ausreicht, ist eine Festlegung und gehoert nicht in den Code.")
    m()


def _lernfall(m, belege_je_bestand) -> None:
    """Der Sonderabschnitt fuer die eine Annotation in Version 1.9.0."""
    m("=" * 78)
    m("LERNFALL %s/%d - Zensurbaustein, Version 1.9.0" % _LERNFALL)
    m("=" * 78)
    treffer = None
    for uid, belege in belege_je_bestand:
        if uid != _LERNFALL[0]:
            continue
        for b in belege:
            if b["annotation_id"] == _LERNFALL[1]:
                treffer = b
                break
    if treffer is None:
        m("Nicht im Lauf enthalten. Moegliche Gruende: 'deleted_at' ist nicht")
        m("NULL, der Bestand wurde nicht gefahren, oder die Annotation ist")
        m("wieder entfernt. KEIN BLOCKER - sie dient nur dem Lernen.")
        m()
        return
    m("   gefunden:            %s" % treffer["found"])
    m("   Stufe:               %s" % (treffer["stage"] or "-"))
    m("   eindeutig:           %s" % treffer["unique"])
    m("   Ausschluss wirksam:  %s   <== der Zensurbaustein"
      % treffer["hidden_mattered"])
    m("   'meta' vorhanden:    %s" % treffer["has_meta"])
    m("   Lage:                %s"
      % (treffer["locations"][0]["area"] if treffer["locations"] else "-"))
    m("   Wortlaut:            %s" % treffer["wording_normalised"])
    m()


def main(argv=None) -> int:
    a = _argumente(sys.argv[1:] if argv is None else argv)
    m = Mitschrift(a.protokoll)
    try:
        m("=" * 78)
        m("WORTLAUTABGLEICH - rein lesend, es wird nichts veraendert")
        m("=" * 78)
        for zeile in Laufkopf("wortlaut_abgleich", _GETRAGEN_VON).zeilen():
            m(zeile)
        m()
        m("Ausgeschlossene Klassen (im Forenstil 'display: none'): %s"
          % ", ".join(VERSTECKTE_KLASSEN))
        m()

        bestaende = _bestaende_bestimmen(a, m)
        if bestaende is None:
            return 2

        rueck = 0
        zaehlungen = []
        alle_belege = []
        je_bestand = []
        for uid, ev, fo in bestaende:
            code, z, belege = _ein_bestand(m, uid, ev, fo, a.grenze)
            rueck = max(rueck, code)
            if z:
                zaehlungen.append(z)
                alle_belege.extend(belege)
                je_bestand.append((uid, belege))

        if zaehlungen:
            _gesamt(m, zaehlungen, alle_belege)
        _lernfall(m, je_bestand)

        if a.json_ziel:
            inhalt = {
                "werkzeug": "wortlaut_abgleich",
                "ausgeschlossene_klassen": list(VERSTECKTE_KLASSEN),
                "bestaende": [
                    {"subject_id": uid, "annotations": belege}
                    for uid, belege in je_bestand],
            }
            try:
                with open(a.json_ziel, "w", encoding="utf-8") as fh:
                    json.dump(inhalt, fh, ensure_ascii=True, indent=1,
                              sort_keys=True)
                m("JSON geschrieben: %s" % a.json_ziel)
            except OSError as exc:
                m("JSON-Datei nicht schreibbar: %s" % exc)
                rueck = max(rueck, 1)
        return rueck
    finally:
        m.schliessen()


if __name__ == "__main__":
    raise SystemExit(main())
