# =============================================================================
# db/reparatur/defekt_sicherung.py
# IT-Forensisches Ermittlungswerkzeug — Sicherung einer beschaedigten Datei
# =============================================================================
# Zweck:
#   Kopiert eine beschaedigte Datenbank (samt -journal/-wal/-shm, falls
#   vorhanden) in den Ordner fuer beschaedigte Dateien:
#       <ziel>/<stamm>_defekt_<zeitstempel>.db  (+ .sha256)
#   und belegt per SHA-256 (Original vorher, Original nachher, Kopie), dass die
#   Kopie dem Original entspricht.
#
# SHA-256-ABGLEICH (Festlegung Alex 14.10.2026): Liegt im Ziel bereits eine
#   Sicherung desselben Stamms mit IDENTISCHEN Pruefsummen (Datei und
#   Begleitdateien), wird KEINE weitere Kopie angelegt, sondern die vorhandene
#   wiederverwendet. Wiederholte Startversuche mit unveraenderter Datei fuellen
#   den Ordner so nicht. Die vorhandene Sicherung wird dabei neu gehasht —
#   eine .sha256-Datei allein ist kein Beleg dafuer, dass die Kopie noch
#   stimmt.
#
# Das Original wird NUR gelesen.
# Version: v0.8.776 · Build: 776 · 2026-10-14
# =============================================================================
from __future__ import annotations

import os
import re
import shutil
from typing import Dict, Optional

from db.reparatur.hilfen import BEGLEIT, sha256
from db.reparatur.sicherungs_ergebnis import SicherungsErgebnis


class DefektSicherung:
    """Sichert eine Datei in den Ordner fuer beschaedigte Dateien."""

    def __init__(self, ziel: str) -> None:
        self._ziel = ziel

    # ------------------------------------------------------------------
    @staticmethod
    def _pruefsummen_lesen(sha_datei: str) -> Dict[str, str]:
        """'.sha256'-Datei -> {Dateiname: SHA-256}."""
        aus: Dict[str, str] = {}
        with open(sha_datei, encoding="utf-8") as fh:
            for zeile in fh:
                teile = zeile.strip().split("  ", 1)
                if len(teile) == 2:
                    aus[teile[1]] = teile[0].lower()
        return aus

    def vorhandene(self, stamm: str, sha: str,
                   begleit: Dict[str, str]) -> Optional[str]:
        """Pfad einer vorhandenen, nachgeprueft identischen Sicherung, sonst None."""
        if not os.path.isdir(self._ziel):
            return None
        muster = re.compile(r"^%s_defekt_\d{8}_\d{6}\.db$" % re.escape(stamm))
        for name in sorted(os.listdir(self._ziel)):
            if not muster.match(name):
                continue
            pfad = os.path.join(self._ziel, name)
            if not os.path.isfile(pfad + ".sha256"):
                continue
            try:
                belegt = self._pruefsummen_lesen(pfad + ".sha256")
            except OSError:
                continue
            erwartet = {name: sha}
            erwartet.update({name + e: s for e, s in begleit.items()})
            if belegt != erwartet:
                continue
            # Nachrechnen statt der .sha256-Datei zu glauben.
            try:
                if sha256(pfad) != sha or any(
                        sha256(pfad + e) != s for e, s in begleit.items()):
                    continue
            except OSError:
                continue
            return pfad
        return None

    # ------------------------------------------------------------------
    def sichern(self, original: str, stamm: str, zeitstempel: str) -> SicherungsErgebnis:
        os.makedirs(self._ziel, exist_ok=True)
        begleit_endungen = [s for s in BEGLEIT if os.path.exists(original + s)]
        h_vorher = sha256(original)
        begleit = {e: sha256(original + e) for e in begleit_endungen}

        vorhanden = self.vorhandene(stamm, h_vorher, begleit)
        if vorhanden is not None:
            return SicherungsErgebnis(
                pfad=vorhanden, sha256=h_vorher, begleit=begleit,
                neu_angelegt=False, stimmig=True,
                meldung="Sicherung mit identischer SHA-256 liegt bereits vor "
                        "und wurde wiederverwendet: %s" % vorhanden,
                sha256_nachher=h_vorher, sha256_kopie=h_vorher)

        ziel = os.path.join(self._ziel, "%s_defekt_%s.db" % (stamm, zeitstempel))
        shutil.copy2(original, ziel)
        for e in begleit_endungen:
            shutil.copy2(original + e, ziel + e)
        h_nachher = sha256(original)
        h_kopie = sha256(ziel)
        begleit_kopie = {e: sha256(ziel + e) for e in begleit_endungen}
        stimmig = (h_vorher == h_nachher == h_kopie and begleit_kopie == begleit)
        if stimmig:
            with open(ziel + ".sha256", "w", encoding="utf-8") as fh:
                fh.write("%s  %s\n" % (h_kopie, os.path.basename(ziel)))
                for e in begleit_endungen:
                    fh.write("%s  %s\n" % (begleit[e], os.path.basename(ziel) + e))
            meldung = "Sicherung: %s" % ziel
        else:
            meldung = ("Die Pruefsummen stimmen nicht ueberein. Das Original "
                       "wurde waehrend des Kopierens veraendert (laeuft der "
                       "Webserver noch?), oder die Kopie ist fehlerhaft.")
        return SicherungsErgebnis(
            pfad=ziel, sha256=h_vorher, begleit=begleit, neu_angelegt=True,
            stimmig=stimmig, meldung=meldung, sha256_nachher=h_nachher,
            sha256_kopie=h_kopie)
