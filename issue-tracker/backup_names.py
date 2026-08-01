#!/usr/bin/env python3
# =============================================================================
# issue-tracker/backup_names.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# ZWECK: Die Namen der Sicherungen an EINER Stelle festlegen und beantworten
#   koennen, WEM eine vorgefundene Sicherung gehoert.
#
# DER BEFUND, DER DAZU GEFUEHRT HAT (Build 642):
#   Es gibt zwei Erzeuger von Sicherungen, und sie kennen einander nicht:
#
#     server.py  Z. 189 (Build 641): issues_backup_<JJJJMMTT>_<HHMMSS>.json
#     merge.py   Z. 256 (Build 641): issues_backup_before_merge_<...>.json
#
#   Aufgeraeumt hat aber nur einer - server.py, Z. 197-200:
#
#       backups = sorted(config.BACKUP_DIR.glob("issues_backup_*.json"))
#       if len(backups) > 10:
#           for old_backup in backups[:-10]:
#               old_backup.unlink()
#
#   'issues_backup_*.json' PASST AUCH AUF 'issues_backup_before_merge_*.json'.
#   Der Server hat damit das Recht, die Sicherungen des Merge-Werkzeugs zu
#   loeschen. Und er tut es sogar ZUERST: sortiert wird nach Namen, und in
#   'issues_backup_2026...' steht an der Stelle, an der bei der Merge-Sicherung
#   ein 'b' steht, eine '2'. Ziffern sortieren vor Buchstaben, also stehen die
#   Server-Sicherungen vorne und werden als erste weggeschnitten - solange, bis
#   nur noch Merge-Sicherungen da sind. Ab da trifft es die Merge-Sicherungen.
#
#   Der Bestand im Repository belegt, dass das kein Randfall ist: am
#   2026-08-01 sind ZWOELF Merge-Sicherungen entstanden (issue-tracker/backups).
#   Bei einer Obergrenze von 10 haette ein einziger Server-Lauf begonnen,
#   Beweismittel-Sicherungen zu loeschen.
#
#   Warum das schwerer wiegt als es klingt: Die Merge-Sicherung ist der Stand
#   UNMITTELBAR VOR einer Zusammenfuehrung. Genau das ist der Stand, auf den
#   man zurueckwill, wenn die Zusammenfuehrung etwas verschluckt hat. Sie ist
#   die einzige Absicherung von Vorgang 042e10ef ('Ueberschreiben waere
#   Datenverlust').
#
# DIE REGEL AB BUILD 642:
#   JEDER raeumt NUR SEINE EIGENEN Sicherungen auf. Die Zuordnung geschieht
#   ueber die beiden Muster unten, nicht ueber einen Glob-Ausdruck, der
#   zufaellig auch fremde Namen trifft. Was zu keinem der Muster passt, ist
#   FREMD und wird angefasst von niemandem - Grundregel 1.
#
# Version: v0.8.642 - Build: 642 - 2026-08-01
# =============================================================================

import re
from datetime import datetime
from pathlib import Path
from typing import List

#: Sicherung des Servers vor dem Speichern (server.py).
#: Beispiel: issues_backup_20260801_183548.json
SERVER_MUSTER = re.compile(r"^issues_backup_\d{8}_\d{6}\.json$")

#: Sicherung des Merge-Werkzeugs vor dem Zusammenfuehren (merge.py).
#: Beispiel: issues_backup_before_merge_20260801_183548.json
MERGE_MUSTER = re.compile(r"^issues_backup_before_merge_\d{8}_\d{6}\.json$")

#: Sicherung des Reparaturwerkzeugs vor dem Aendern (repair_related_ids.py).
#: Beispiel: issues_backup_before_repair_20260801_183548.json
#:
#: EIGENES MUSTER MIT ABSICHT: Die Reparatur ist der seltenste und zugleich
#: eingreifendste der drei Vorgaenge. Ihre Sicherung soll von der Bereinigung
#: der beiden anderen nicht erfasst werden - und wird es nach der Regel oben
#: auch nicht: sie raeumen jeweils nur ihr eigenes Muster ab.
REPARATUR_MUSTER = re.compile(r"^issues_backup_before_repair_\d{8}_\d{6}\.json$")

#: Glob fuer das AUFFINDEN von Sicherungen (Wiederherstellung). Absichtlich
#: weit: zum LESEN ist jede Sicherung recht. Nur zum LOESCHEN gelten die
#: engen Muster oben.
SUCH_GLOB = "issues_backup_*.json"


def ist_server_sicherung(name: str) -> bool:
    """Wahr, wenn 'name' eine vom Server erzeugte Sicherung ist."""
    return bool(SERVER_MUSTER.match(name))


def ist_merge_sicherung(name: str) -> bool:
    """Wahr, wenn 'name' eine vom Merge-Werkzeug erzeugte Sicherung ist."""
    return bool(MERGE_MUSTER.match(name))


def server_sicherungsname(zeitpunkt: datetime) -> str:
    """Bildet den Dateinamen einer Server-Sicherung."""
    return f"issues_backup_{zeitpunkt.strftime('%Y%m%d_%H%M%S')}.json"


def merge_sicherungsname(zeitpunkt: datetime) -> str:
    """Bildet den Dateinamen einer Merge-Sicherung."""
    return f"issues_backup_before_merge_{zeitpunkt.strftime('%Y%m%d_%H%M%S')}.json"


def ist_reparatur_sicherung(name: str) -> bool:
    """Wahr, wenn 'name' eine vom Reparaturwerkzeug erzeugte Sicherung ist."""
    return bool(REPARATUR_MUSTER.match(name))


def reparatur_sicherungsname(zeitpunkt: datetime) -> str:
    """Bildet den Dateinamen einer Reparatur-Sicherung."""
    return f"issues_backup_before_repair_{zeitpunkt.strftime('%Y%m%d_%H%M%S')}.json"


def eigene_sicherungen(verzeichnis: Path, muster: re.Pattern) -> List[Path]:
    """
    Alle Sicherungen in 'verzeichnis', die auf 'muster' passen - aelteste
    zuerst.

    Sortiert wird nach dem NAMEN, nicht nach der Aenderungszeit: der Name
    traegt den Zeitstempel der Sicherung, die Aenderungszeit dagegen kann
    durch Kopieren, Auspacken oder eine Dateisynchronisation verstellt sein.
    Bei festem Format ist die alphabetische Ordnung die zeitliche.
    """
    if not verzeichnis.is_dir():
        return []
    return sorted(
        (p for p in verzeichnis.iterdir() if p.is_file() and muster.match(p.name)),
        key=lambda p: p.name,
    )
