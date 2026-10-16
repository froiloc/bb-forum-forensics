# =============================================================================
# db/reparatur/seitenscanner.py
# IT-Forensisches Ermittlungswerkzeug — Datensaetze direkt aus den Datenseiten
# =============================================================================
# Zweck:
#   Liest eine SQLite-Datei OHNE SQLite, Seite fuer Seite, und dekodiert jeden
#   Datensatz auf jeder Tabellenblattseite (Seitentyp 0x0D) — auch auf Seiten,
#   die vom Baum abgeschnitten oder verwaist sind. Damit lassen sich Zeilen
#   finden, die ueber den Baum nicht mehr erreichbar sind.
#
# Gesicherte Grundlagen (SQLite-Dateiformat, sqlite.org/fileformat2.html):
#   * Kopf: Bytes 16-17 Seitengroesse (1 = 65536), Byte 20 reservierte Bytes
#     je Seite, Bytes 56-59 Textkodierung (1 UTF-8, 2 UTF-16le, 3 UTF-16be).
#   * Seite 1 traegt den 100-Byte-Dateikopf VOR dem Seitenkopf.
#   * Tabellenblatt: Zellzeiger ab Seitenkopf+8, je 2 Byte; Zelle =
#     varint Nutzlaenge, varint rowid, Datensatz (Kopflaenge, Serientypen,
#     Werte).
#   * Datensaetze mit Ueberlaufseiten (Nutzlaenge > nutzbar-35) werden NICHT
#     verfolgt, sondern gezaehlt (Grundregel 1).
#   * INTEGER PRIMARY KEY steht im Datensatz als NULL (Wert = rowid).
#
# Herkunft: tools/evidence_reparatur.py 1.2 (14.10.2026), Logik unveraendert.
# Version: v0.8.776 · Build: 776 · 2026-10-14
# =============================================================================
from __future__ import annotations

import struct
from typing import List, Sequence, Tuple


class SeitenScanner:
    """Zustandslose Dekodierung von Tabellenblattseiten."""

    @staticmethod
    def varint(buf, pos: int) -> Tuple[int, int]:
        """SQLite-varint ab pos -> (wert, neue_pos)."""
        wert = 0
        for i in range(9):
            b = buf[pos]
            pos += 1
            if i == 8:
                return (wert << 8) | b, pos
            wert = (wert << 7) | (b & 0x7F)
            if not b & 0x80:
                return wert, pos
        return wert, pos

    @staticmethod
    def wert_lesen(daten, pos: int, typ: int, kodierung: str):
        """Einen Wert des Serientyps 'typ' ab pos lesen -> (wert, neue_pos)."""
        if typ == 0:
            return None, pos
        if typ in (1, 2, 3, 4, 5, 6):
            laenge = {1: 1, 2: 2, 3: 3, 4: 4, 5: 6, 6: 8}[typ]
            roh = daten[pos:pos + laenge]
            if len(roh) != laenge:
                raise ValueError("Wert ueber Seitenende")
            return int.from_bytes(roh, "big", signed=True), pos + laenge
        if typ == 7:
            return struct.unpack(">d", daten[pos:pos + 8])[0], pos + 8
        if typ == 8:
            return 0, pos
        if typ == 9:
            return 1, pos
        if typ >= 12:
            laenge = (typ - 12) // 2 if typ % 2 == 0 else (typ - 13) // 2
            roh = bytes(daten[pos:pos + laenge])
            if len(roh) != laenge:
                raise ValueError("Wert ueber Seitenende")
            if typ % 2 == 0:
                return roh, pos + laenge
            return roh.decode(kodierung), pos + laenge
        raise ValueError("unzulaessiger Typ %d" % typ)

    @classmethod
    def datensaetze(cls, pfad) -> Tuple[List[tuple], int, int]:
        """
        Alle Datensaetze aus allen Tabellenblattseiten der Datei.
        Rueckgabe: (funde, ueberlauf, unlesbar);
        funde = Liste (seite, rowid, [serientypen], [werte]).
        """
        funde, ueberlauf, unlesbar = [], 0, 0
        with open(pfad, "rb") as fh:
            kopf = fh.read(100)
            groesse = int.from_bytes(kopf[16:18], "big")
            groesse = 65536 if groesse == 1 else groesse
            nutzbar = groesse - kopf[20]
            kodierung = {1: "utf-8", 2: "utf-16-le", 3: "utf-16-be"}.get(
                int.from_bytes(kopf[56:60], "big"), "utf-8")
            fh.seek(0, 2)
            seiten = fh.tell() // groesse
            x_max = nutzbar - 35
            for nr in range(1, seiten + 1):
                fh.seek((nr - 1) * groesse)
                seite = fh.read(groesse)
                k = 100 if nr == 1 else 0
                if seite[k] != 0x0D:
                    continue
                zellen = int.from_bytes(seite[k + 3:k + 5], "big")
                for i in range(zellen):
                    try:
                        off = int.from_bytes(seite[k + 8 + 2 * i:k + 10 + 2 * i], "big")
                        laenge, p = cls.varint(seite, off)
                        rowid, p = cls.varint(seite, p)
                        if laenge > x_max:
                            ueberlauf += 1
                            continue
                        daten = seite[p:p + laenge]
                        kl, r = cls.varint(daten, 0)
                        typen = []
                        while r < kl:
                            t, r = cls.varint(daten, r)
                            typen.append(t)
                        werte, w = [], kl
                        for t in typen:
                            v, w = cls.wert_lesen(daten, w, t, kodierung)
                            werte.append(v)
                        funde.append((nr, rowid, typen, werte))
                    except (ValueError, IndexError, UnicodeDecodeError):
                        unlesbar += 1
        return funde, ueberlauf, unlesbar

    @staticmethod
    def passt_zur_tabelle(typen: Sequence[int], werte: Sequence,
                          spalten: Sequence[tuple]) -> bool:
        """
        Datensatz passt zur Tabelle, wenn Spaltenzahl und Speicherklassen zu
        den deklarierten Spalten passen. spalten: Liste (name, typ, notnull,
        pk) wie aus PRAGMA table_info (Felder 1, 2, 3, 5).

        Diese Signaturpruefung ersetzt den reinen Zeilennummern-Abgleich der
        ersten schadensanalyse.py (Befund 14.10.2026: alte Fassungen von
        sqlite_sequence mit 2 Spalten wurden report_anchors zugeordnet).
        """
        if len(typen) != len(spalten):
            return False
        for (name, dtyp, notnull, pk), t, v in zip(spalten, typen, werte):
            dtyp = (dtyp or "").upper()
            if pk == 1 and "INT" in dtyp:
                # INTEGER PRIMARY KEY steht im Datensatz als NULL.
                if t != 0:
                    return False
                continue
            if t == 0:
                if notnull:
                    return False
                continue
            if "INT" in dtyp and t not in (1, 2, 3, 4, 5, 6, 8, 9):
                return False
            if ("TEXT" in dtyp or "CHAR" in dtyp) and not (t >= 13 and t % 2 == 1):
                return False
            if name == "page_url" and not (isinstance(v, str)
                                           and (v.startswith("http") or v.startswith("/"))):
                return False
        return True
