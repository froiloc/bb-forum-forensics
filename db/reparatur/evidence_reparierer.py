# =============================================================================
# db/reparatur/evidence_reparierer.py
# IT-Forensisches Ermittlungswerkzeug — Neuaufbau einer beschaedigten
#                                       evidence_<uid>.db
# =============================================================================
# Zweck:
#   Aus einer beschaedigten Ermittler-Datenbank eine NEUE, unbeschaedigte
#   Datei aufbauen — mit allem, was sich aus der alten lesen laesst, und mit
#   einem Protokoll, das jede nicht uebernommene Zeile zaehlt (Grundregel 1).
#   DAS ORIGINAL WIRD NICHT VERAENDERT UND NICHT AUSGETAUSCHT.
#
# Ablauf (unveraendert aus tools/evidence_reparatur.py 1.2, 14.10.2026):
#   1. Sicherung des Originals nach <ziel>/<stamm>_defekt_<ts>.db
#      (DefektSicherung; seit Build 776 mit SHA-256-Abgleich gegen
#      vorhandene Sicherungen).
#   2. Arbeitskopie in einem temporaeren Verzeichnis; nur sie wird geoeffnet.
#      Ein -journal wird dort beim Oeffnen zurueckgerollt.
#   3. integrity_check gesamt (gestaffelte Grenzen) und JE TABELLE; Schaden
#      nur an Indizes zaehlt nicht als Datenschaden.
#   4. Seitenscan (SeitenScanner) VOR der Bergung: liefert je Tabelle die
#      hoechste passende Zeilennummer. Obergrenze = max(Zaehler aus
#      sqlite_sequence, Vollscan, Seitenscan) — der Zaehler ist in einer
#      beschaedigten Datei nicht verlaesslich (PROD 14.10.: report_opened
#      Zeile 31 bei Zaehler 30).
#   5. Bergung je Tabelle (TabellenBergung). Aus dem Seitenscan werden NUR
#      in ANHAENGETABELLEN Zeilen uebernommen; sonst nur gezaehlt.
#      FLUECHTIG-Tabellen werden leer uebernommen.
#   6. Neue Datei: gleiches Schema, Zeilen mit urspruenglicher Nummer,
#      Indizes/Trigger/Views danach, sqlite_sequence nie unter einer Nummer,
#      die in der alten Datei vorkommt; user_version/application_id/
#      page_size uebernommen; journal_mode DELETE.
#   7. Pruefung: integrity_check ohne Grenze, foreign_key_check, und fuer
#      JEDE Tabelle muessen die aus dem Baum gelesenen Zeilen unveraendert
#      in der neuen Datei stehen (Pruefsumme). Sonst wird verworfen.
#   8. Freigabe: 'freigegeben' nur, wenn jede Tabelle ausser ANHAENGETABELLEN
#      und FLUECHTIG fehlerfrei gelesen wurde; sonst 'nicht_freigegeben'.
#      Was daraus folgt, entscheidet der AUFRUFER (Kommandozeile: Mensch;
#      Startpruefung ab Build 778: Austausch auch dann, Festlegung Alex
#      14.10.2026 — "Die Ermittler MUESSEN ARBEITEN KOENNEN").
#
# Version: v0.8.776 · Build: 776 · 2026-10-14
#   Build 778: liegengebliebene Arbeitskopie wird gemeldet.
# =============================================================================
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from typing import Callable, List, Optional

from db.reparatur.defekt_sicherung import DefektSicherung
from db.reparatur.hilfen import (
    ANHAENGETABELLEN, BEGLEIT, FLUECHTIG, PLAUSIBEL_UEBER, q, sha256,
    zeilen_pruefsumme)
from db.reparatur.reparatur_ergebnis import ReparaturErgebnis
from db.reparatur.seitenscanner import SeitenScanner
from db.reparatur.tabellen_bergung import TabellenBergung


class EvidenceReparierer:
    """
    original   — Pfad der beschaedigten Datei
    ziel       — Ordner fuer Sicherung, neue Datei und Protokoll
                 (NICHT der Ordner des Originals — prueft der Aufrufer)
    ausgabe    — optionale Senke fuer jede Protokollzeile (z. B. print)
    kennung    — Kopfzeile des Protokolls (Werkzeug und Stand)
    kopfzeilen — weitere Zeilen nach dem Kopf (z. B. Herkunft des Ziels)
    """

    def __init__(self, original: str, ziel: str, *,
                 ausgabe: Optional[Callable[[str], None]] = None,
                 kennung: str = "evidence_reparatur (Build 776)",
                 kopfzeilen: Optional[List[str]] = None,
                 zeitstempel: Optional[str] = None) -> None:
        self._original = os.path.abspath(original)
        self._ziel = os.path.abspath(ziel)
        self._ausgabe = ausgabe
        self._kennung = kennung
        self._kopfzeilen = list(kopfzeilen or [])
        self._ts = zeitstempel or time.strftime("%Y%m%d_%H%M%S")
        self._prot = None

    # ------------------------------------------------------------------
    def _aus(self, text: str = "") -> None:
        if self._ausgabe is not None:
            self._ausgabe(text)
        if self._prot is not None:
            self._prot.write(text + "\n")
            self._prot.flush()

    # ------------------------------------------------------------------
    def ausfuehren(self) -> ReparaturErgebnis:
        original, ziel, ts = self._original, self._ziel, self._ts
        os.makedirs(ziel, exist_ok=True)
        stamm = os.path.splitext(os.path.basename(original))[0]
        p_neu = os.path.join(ziel, "%s_repariert_%s.db" % (stamm, ts))
        p_txt = os.path.join(ziel, "%s_reparatur_%s.txt" % (stamm, ts))
        p_json = os.path.join(ziel, "%s_reparatur_%s.json" % (stamm, ts))
        erg = ReparaturErgebnis(status="nicht_lesbar", original=original,
                                zeitstempel=ts, protokoll_txt=p_txt,
                                protokoll_json=p_json)
        daten = {"original": original, "zeitstempel": ts, "tabellen": {}}
        erg.daten = daten
        self._prot = open(p_txt, "w", encoding="utf-8")
        arbeit = None
        try:
            self._aus("%s  %s  Python %s  SQLite %s" % (
                self._kennung, ts, sys.version.split()[0], sqlite3.sqlite_version))
            self._aus("Original : %s" % original)
            self._aus("Zielordner: %s" % ziel)
            for z in self._kopfzeilen:
                self._aus(z)

            # --- 1. Sicherung ---------------------------------------------
            self._aus("")
            self._aus("=== 1. Sicherung des Originals")
            begleit = [s for s in BEGLEIT if os.path.exists(original + s)]
            if begleit:
                self._aus("Begleitdateien vorhanden: %s — werden mitgesichert. "
                          "Ein -journal bedeutet eine unterbrochene Transaktion; "
                          "sie wird in der Arbeitskopie zurueckgerollt."
                          % ", ".join(begleit))
            sich = DefektSicherung(ziel).sichern(original, stamm, ts)
            erg.sicherung = sich
            self._aus("SHA-256 Original vorher : %s" % sich.sha256)
            self._aus("SHA-256 Original nachher: %s" % sich.sha256_nachher)
            self._aus("SHA-256 Sicherung       : %s" % sich.sha256_kopie)
            if not sich.stimmig:
                self._aus("ABBRUCH: " + sich.meldung + " Es wurde nichts repariert.")
                erg.status = "abbruch_sicherung"
                daten["ergebnis"] = erg.status
                return erg
            self._aus(sich.meldung if not sich.neu_angelegt
                      else "Sicherung: %s" % sich.pfad)
            daten["sicherung"] = {"datei": sich.pfad, "sha256": sich.sha256,
                                  "neu_angelegt": sich.neu_angelegt}

            # --- 2. Arbeitskopie -----------------------------------------
            arbeit = tempfile.mkdtemp(prefix="aiw_reparatur_")
            p_arbeit = os.path.join(arbeit, os.path.basename(original))
            shutil.copy2(sich.pfad, p_arbeit)
            for s in begleit:
                shutil.copy2(sich.pfad + s, p_arbeit + s)
            try:
                return self._reparieren(erg, daten, p_arbeit, p_neu)
            except sqlite3.DatabaseError as exc:
                # Die Arbeitskopie ist nicht einmal als SQLite lesbar (z. B.
                # sqlite_schema zerstoert). Grundregel 1: gemeldet, nicht
                # verschluckt; das Original bleibt unberuehrt.
                if os.path.exists(p_neu):
                    os.remove(p_neu)
                self._aus("")
                self._aus("ABBRUCH: Die Arbeitskopie ist nicht lesbar (%s: %s). "
                          "Es wurde keine neue Datei erzeugt."
                          % (type(exc).__name__, exc))
                erg.status = "nicht_lesbar"
                daten["ergebnis"] = erg.status
                daten["fehler"] = "%s: %s" % (type(exc).__name__, exc)
                return erg
        finally:
            with open(p_json, "w", encoding="utf-8") as fh:
                json.dump(daten, fh, ensure_ascii=False, indent=1)
            self._prot.close()
            self._prot = None
            if arbeit:
                # Build 778 (Befund der Durchsicht): nicht still. Bleibt die
                # Arbeitskopie liegen (Windows: Virenscanner, Indexdienst),
                # liegt eine Kopie der Falldaten im temporaeren Ordner — das
                # muss im Protokoll stehen.
                try:
                    shutil.rmtree(arbeit)
                except OSError as exc:
                    hinweis = ("WARNUNG: Arbeitskopie %s konnte nicht entfernt "
                               "werden (%s) — bitte von Hand loeschen."
                               % (arbeit, exc))
                    if self._ausgabe is not None:
                        self._ausgabe(hinweis)
                    try:
                        with open(p_txt, "a", encoding="utf-8") as fh:
                            fh.write(hinweis + "\n")
                    except OSError:
                        pass

    # ------------------------------------------------------------------
    def _reparieren(self, erg: ReparaturErgebnis, daten: dict,
                    p_arbeit: str, p_neu: str) -> ReparaturErgebnis:
        alt = sqlite3.connect(p_arbeit)
        alt.text_factory = str
        try:
            return self._reparieren_mit(alt, erg, daten, p_arbeit, p_neu)
        finally:
            alt.close()

    def _reparieren_mit(self, alt, erg, daten, p_arbeit, p_neu):
        aus = self._aus
        # --- Schema -------------------------------------------------------
        schema = alt.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_schema "
            "WHERE sql IS NOT NULL ORDER BY rowid").fetchall()
        tabellen = [r[1] for r in schema
                    if r[0] == "table" and not r[1].startswith("sqlite_")]
        seq = {}
        try:
            seq = {n: int(s) for n, s in alt.execute(
                "SELECT name, seq FROM sqlite_sequence")}
        except sqlite3.DatabaseError as exc:
            aus("WARNUNG: sqlite_sequence nicht lesbar: %s" % exc)
        wurzel_zu_tabelle = {}
        for rp, typ, tbl in alt.execute(
                "SELECT rootpage, type, tbl_name FROM sqlite_schema WHERE rootpage > 0"):
            wurzel_zu_tabelle[rp] = (typ, tbl)
        # integrity_check kann bei schweren Schaeden selbst abbrechen. Dann
        # mit kleinerer Meldungsgrenze erneut.
        ic_alt, ic_grenze = None, None
        for grenze in (1000000, 1000, 100, 10):
            try:
                ic_alt = [t for r in alt.execute("PRAGMA integrity_check(%d)" % grenze)
                          for t in str(r[0]).splitlines()]
                ic_grenze = grenze
                break
            except sqlite3.DatabaseError as exc:
                aus("integrity_check(%d) bricht selbst ab: %s" % (grenze, exc))
        if ic_alt is None:
            ic_alt = []
        daten["integrity_check_alt_grenze"] = ic_grenze
        aus("")
        aus("integrity_check der ganzen Arbeitskopie: %s" % (
            "nicht ausfuehrbar" if ic_grenze is None else
            "%d Zeilen (Grenze %d)" % (len(ic_alt), ic_grenze)))
        # JE TABELLE pruefen (PRAGMA integrity_check(<tabelle>), SQLite >= 3.33).
        # Meldungen, die nur einen INDEX betreffen, zaehlen nicht als
        # Datenschaden — Indizes werden ohnehin neu gebaut.
        baum_schaden, pruefung_unmoeglich = set(), set()
        for name in tabellen:
            try:
                z = [t for r in alt.execute("PRAGMA integrity_check(%s)" % q(name))
                     for t in str(r[0]).splitlines()]
            except sqlite3.DatabaseError as exc:
                pruefung_unmoeglich.add(name)
                aus("  integrity_check(%s) bricht ab: %s" % (name, exc))
                continue
            if z == ["ok"]:
                continue
            nur_index = all(wurzel_zu_tabelle.get(int(n), ("?",))[0] == "index"
                            for n in re.findall(r"Tree (\d+)", "\n".join(z))) \
                and re.search(r"Tree \d+", "\n".join(z))
            if nur_index:
                aus("  %-28s nur Index beschaedigt (wird neu gebaut)" % name)
            else:
                baum_schaden.add(name)
        baum_schaden |= pruefung_unmoeglich
        aus("Tabellen mit Schaden im Datenbaum (oder abgebrochener Pruefung): %s" % (
            ", ".join(sorted(baum_schaden)) or "keine"))
        daten["integrity_check_alt"] = ic_alt
        erg.beschaedigte_tabellen = sorted(baum_schaden)
        user_version = alt.execute("PRAGMA user_version").fetchone()[0]
        application_id = alt.execute("PRAGMA application_id").fetchone()[0]
        page_size = alt.execute("PRAGMA page_size").fetchone()[0]

        # --- Seitenscan VOR der Bergung --------------------------------
        funde, ueberlauf, unlesbar = SeitenScanner.datensaetze(p_arbeit)
        spalten_je, seiten_ids, unplausibel = {}, {}, {}
        for name in tabellen:
            info = alt.execute("PRAGMA table_info(%s)" % q(name)).fetchall()
            spalten_je[name] = [(r[1], r[2], r[3], r[5]) for r in info]
            passend = {rowid for _s, rowid, typen, werte in funde
                       if SeitenScanner.passt_zur_tabelle(typen, werte, spalten_je[name])}
            basis = seq.get(name, 0)
            seiten_ids[name] = {r for r in passend if 0 < r <= basis + PLAUSIBEL_UEBER}
            unplausibel[name] = len(passend) - len(seiten_ids[name])

        aus("")
        aus("=== 2. Bergung je Tabelle")
        geborgen, vollstaendig, aus_baum = {}, {}, {}
        for name in tabellen:
            oberste = max([seq.get(name, 0)] + list(seiten_ids[name]))
            zeilen, voll, meld = TabellenBergung.bergen(alt, name, oberste)
            if not voll and oberste > seq.get(name, 0):
                meld.append("Einzelzugriff bis %d statt bis %s (der Seitenscan "
                            "fand passende Nummern darueber)"
                            % (oberste, "Zaehler %d" % seq[name] if name in seq
                               else "zum Abbruch des Vollscans"))
            if name in baum_schaden:
                voll = False
                meld.append("integrity_check meldet Schaeden im Baum dieser Tabelle")
            geborgen[name], vollstaendig[name] = zeilen, voll
            # Pruefsumme ueber das, was aus dem Baum gelesen wurde — BEVOR
            # der Seitenscan etwas ergaenzt (Pruefung in Schritt 5).
            aus_baum[name] = (set(zeilen), zeilen_pruefsumme(zeilen))
            aus("%-28s %7d Zeilen  %s" % (name, len(zeilen),
                                          "fehlerfrei lesbar" if voll else "BESCHAEDIGT"))
            for m in meld:
                aus("    - %s" % m)

        aus("")
        aus("=== 3. Seitenscan (Datensaetze direkt aus den Datenseiten)")
        aus("%d Datensaetze dekodiert, %d mit Ueberlaufseiten uebersprungen, "
            "%d nicht dekodierbar" % (len(funde), ueberlauf, unlesbar))
        for name in tabellen:
            spalten = spalten_je[name]
            zaehler = seq.get(name)
            obergrenze = (max([zaehler] + list(geborgen[name]) + list(seiten_ids[name]))
                          if zaehler is not None else None)
            if unplausibel[name]:
                aus("%-28s %d Seitenfunde mit unplausibel hoher Zeilennummer "
                    "(> Zaehler + %d) — als Fehldekodierung gewertet, nicht "
                    "beruecksichtigt" % (name, unplausibel[name], PLAUSIBEL_UEBER))
            if obergrenze is not None and obergrenze > zaehler:
                ueber_baum = len([r for r in geborgen[name] if r > zaehler])
                ueber_seite = len([r for r in seiten_ids[name]
                                   if r > zaehler and r not in geborgen[name]])
                aus("%-28s Zaehler %d ist ZU NIEDRIG: hoechste Nummer %d. Ueber "
                    "dem Zaehler: %d Zeilen aus dem Baum, %d weitere nur im "
                    "Seitenscan. Der Zaehler der neuen Datei wird auf %d gesetzt."
                    % (name, zaehler, obergrenze, ueber_baum, ueber_seite, obergrenze))
            fehlend = (set(range(1, obergrenze + 1)) - set(geborgen[name])
                       if obergrenze else set())
            kandidaten, widerspruch = {}, set()
            for seite, rowid, typen, werte in funde:
                if rowid in fehlend and SeitenScanner.passt_zur_tabelle(typen, werte, spalten):
                    if rowid in kandidaten and kandidaten[rowid][1] != werte:
                        # Zwei verschiedene Fassungen derselben Zeilennummer:
                        # welche die richtige ist, laesst sich nicht entscheiden.
                        widerspruch.add(rowid)
                    kandidaten.setdefault(rowid, (seite, werte))
            for rowid in widerspruch:
                del kandidaten[rowid]
            if widerspruch:
                aus("%-28s %d Zeilennummern im Seitenscan mit WIDERSPRUECHLICHEN "
                    "Fassungen — nicht uebernommen" % (name, len(widerspruch)))
            if not vollstaendig[name] and not obergrenze:
                aus("%-28s BESCHAEDIGT und ohne AUTOINCREMENT-Zaehler: wie viele "
                    "Zeilen fehlen, laesst sich nicht bestimmen" % name)
            e = {"zeilen_aus_baum": len(geborgen[name]),
                 "widerspruechliche_seitenfunde": sorted(widerspruch),
                 "fehlerfrei_lesbar": vollstaendig[name],
                 "zaehler_sqlite_sequence": zaehler,
                 "obergrenze": obergrenze,
                 "seitenscan_hoechste_nummer": max(seiten_ids[name], default=None),
                 "seitenscan_unplausibel": unplausibel[name],
                 "fehlende_nummern_vor_seitenscan": len(fehlend),
                 "seitenscan_kandidaten": len(kandidaten),
                 "aus_seitenscan_uebernommen": []}
            if kandidaten and name in ANHAENGETABELLEN:
                pk = [i for i, s in enumerate(spalten)
                      if s[3] == 1 and "INT" in (s[1] or "").upper()]
                for rowid, (_seite, werte) in kandidaten.items():
                    werte = list(werte)
                    if pk:
                        werte[pk[0]] = rowid
                    geborgen[name][rowid] = tuple(werte)
                e["aus_seitenscan_uebernommen"] = sorted(kandidaten)
                aus("%-28s %d fehlende Zeilen aus dem Seitenscan UEBERNOMMEN "
                    "(Anhaengetabelle)" % (name, len(kandidaten)))
            elif kandidaten:
                aus("%-28s %d moegliche Funde fuer fehlende Zeilen — NICHT "
                    "uebernommen (Zeilen dieser Tabelle koennen sich aendern; ein "
                    "Fund koennte eine alte Fassung sein)" % (name, len(kandidaten)))
            rest = fehlend - set(geborgen[name])
            e["fehlend_nach_bergung"] = sorted(rest)
            if rest:
                aus("%-28s %d Zeilennummern bis zur Obergrenze %d fehlen "
                    "(geloescht oder verloren)" % (name, len(rest), obergrenze))
            daten["tabellen"][name] = e

        for name in FLUECHTIG:
            if name in geborgen:
                daten["tabellen"][name]["leer_uebernommen_gelesen"] = len(geborgen[name])
                if geborgen[name]:
                    aus("%-28s %d Zeilen Laufzeitzustand — LEER uebernommen (leert "
                        "der Webserver bei jedem Start)" % (name, len(geborgen[name])))
                geborgen[name] = {}
                aus_baum[name] = (set(), zeilen_pruefsumme({}))

        # --- Freigabe-Regel -----------------------------------------------
        sperren = [n for n in tabellen
                   if n not in ANHAENGETABELLEN and n not in FLUECHTIG
                   and not vollstaendig[n]]
        daten["freigabe_gesperrt_durch"] = sperren
        erg.sperren = sperren

        # --- 4. Neue Datei ------------------------------------------------
        aus("")
        aus("=== 4. Neue Datei")
        neu = sqlite3.connect(p_neu, isolation_level=None)
        try:
            neu.text_factory = str
            neu.execute("PRAGMA page_size=%d" % page_size)
            neu.execute("PRAGMA journal_mode=DELETE")
            neu.execute("BEGIN")
            for typ, name, _tbl, sql in schema:
                if typ == "table" and not name.startswith("sqlite_"):
                    neu.execute(sql)
            for name in tabellen:
                info = alt.execute("PRAGMA table_info(%s)" % q(name)).fetchall()
                spalten = [r[1] for r in info]
                hat_alias = any(r[5] == 1 and "INT" in (r[2] or "").upper() for r in info) \
                    and sum(1 for r in info if r[5]) == 1
                if hat_alias:
                    sql = "INSERT INTO %s (%s) VALUES (%s)" % (
                        q(name), ", ".join(q(s) for s in spalten),
                        ", ".join("?" for _ in spalten))
                    neu.executemany(sql, (z for _r, z in sorted(geborgen[name].items())))
                else:
                    sql = "INSERT INTO %s (rowid, %s) VALUES (?, %s)" % (
                        q(name), ", ".join(q(s) for s in spalten),
                        ", ".join("?" for _ in spalten))
                    neu.executemany(sql, ((r,) + z for r, z in sorted(geborgen[name].items())))
            for typ, name, _tbl, sql in schema:
                if typ in ("index", "trigger", "view") and not name.startswith("sqlite_"):
                    neu.execute(sql)
            if seq:
                neu.execute("DELETE FROM sqlite_sequence")
                for name, s in seq.items():
                    # Nie unter einer Nummer, die irgendwo in der alten Datei
                    # vorkommt — im Baum oder auf einer passenden Datenseite.
                    hoechste = max([s] + list(geborgen.get(name, {}).keys())
                                   + list(seiten_ids.get(name, ())))
                    neu.execute("INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)",
                                (name, hoechste))
            neu.execute("PRAGMA user_version=%d" % user_version)
            neu.execute("PRAGMA application_id=%d" % application_id)
            neu.execute("COMMIT")

            # --- 5. Pruefung ----------------------------------------------
            aus("")
            aus("=== 5. Pruefung der neuen Datei")
            ic = [r[0] for r in neu.execute("PRAGMA integrity_check(1000000)")]
            fk = neu.execute("PRAGMA foreign_key_check").fetchall()
            aus("integrity_check: %s" % ("ok" if ic == ["ok"] else "%d Meldungen" % len(ic)))
            aus("foreign_key_check: %d Meldungen" % len(fk))
            gut = ic == ["ok"] and not fk
            for name in tabellen:
                z_neu = {r[0]: tuple(r[1:]) for r in neu.execute(
                    "SELECT rowid, * FROM %s" % q(name))}
                e = daten["tabellen"][name]
                e["zeilen_neu"] = len(z_neu)
                if len(z_neu) != len(geborgen[name]):
                    aus("FEHLER: %s — %d geborgen, %d in der neuen Datei"
                        % (name, len(geborgen[name]), len(z_neu)))
                    gut = False
                ids_baum, p_alt = aus_baum[name]
                p_neu_ = zeilen_pruefsumme({r: z for r, z in z_neu.items() if r in ids_baum})
                e["pruefsumme_baum_alt"], e["pruefsumme_baum_neu"] = p_alt, p_neu_
                gleich = p_alt == p_neu_
                zusatz = len(set(z_neu) - ids_baum)
                aus("%-28s %7d Zeilen; aus dem Baum gelesene unveraendert: %s%s" % (
                    name, len(z_neu), "JA" if gleich else "NEIN",
                    "; dazu %d aus dem Seitenscan" % zusatz if zusatz else ""))
                gut = gut and gleich
        finally:
            neu.close()
        daten["integrity_check"] = ic[:50]
        daten["foreign_key_check"] = len(fk)

        if not gut:
            os.remove(p_neu)
            erg.status = "verworfen"
            daten["ergebnis"] = erg.status
            aus("")
            aus("ERGEBNIS: Die neue Datei hat die Pruefung NICHT bestanden und "
                "wurde verworfen. Das Original ist unveraendert, die Sicherung "
                "liegt vor. Bitte dieses Protokoll zurueckmelden.")
            return erg

        h_neu = sha256(p_neu)
        with open(p_neu + ".sha256", "w", encoding="utf-8") as fh:
            fh.write("%s  %s\n" % (h_neu, os.path.basename(p_neu)))
        daten["neu"] = {"datei": p_neu, "sha256": h_neu}
        erg.neu, erg.neu_sha256 = p_neu, h_neu
        aus("")
        aus("Neue Datei: %s" % p_neu)
        aus("  SHA-256 %s" % h_neu)
        verloren = {n: len(e.get("fehlend_nach_bergung", []))
                    for n, e in daten["tabellen"].items()
                    if e.get("fehlend_nach_bergung")}
        erg.verloren = verloren
        if verloren:
            aus("")
            aus("NICHT GEBORGENE ZEILENNUMMERN (geloescht oder verloren), je Tabelle:")
            for n, k in sorted(verloren.items()):
                aus("  %-28s %d" % (n, k))
        aus("")
        if sperren:
            erg.status = "nicht_freigegeben"
            aus("ERGEBNIS: Neue Datei technisch in Ordnung, aber NICHT ZUM "
                "AUSTAUSCH FREIGEGEBEN.")
            aus("Beschaedigt sind Tabellen mit Ermittlungsergebnissen: %s."
                % ", ".join(sperren))
        else:
            erg.status = "freigegeben"
            aus("ERGEBNIS: Neue Datei bestanden und zum Austausch freigegeben.")
            aus("Alle Tabellen mit Ermittlungsergebnissen wurden fehlerfrei und")
            aus("unveraendert uebernommen.")
        daten["ergebnis"] = erg.status
        return erg
