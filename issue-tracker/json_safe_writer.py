#!/usr/bin/env python3
# =============================================================================
# issue-tracker/json_safe_writer.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# ZWECK: EIN Schreibweg fuer issues.json - und zwar einer, der die Datei nicht
#   zerstoeren kann.
#
# DER BEFUND, DER DAZU GEFUEHRT HAT (Build 642):
#   Sowohl server.py (IssueManager.save, Z. 169 in Build 641) als auch
#   merge.py (save_file, Z. 246 in Build 641) haben unmittelbar auf die
#   Zieldatei geschrieben:
#
#       with open(self.file_path, "w", encoding="utf-8") as f:
#           json.dump({"issues": issues}, f, ...)
#
#   'open(..., "w")' KUERZT DIE DATEI AUF NULL BYTES, BEVOR das erste Zeichen
#   geschrieben wird. Zwischen dem Kuerzen und dem letzten Byte liegt der
#   gesamte Serialisierungsvorgang. Faellt in diesem Fenster irgendetwas aus -
#   Stromausfall, volle Platte, ein Fehler mitten in json.dump, ein
#   abgeschossener Prozess, ein Netzlaufwerk das wegbricht -, dann steht dort
#   eine leere oder halbe Datei. Der gesamte Vorgangsbestand waere dahin; die
#   naechste Sicherung liegt im ungluecklichsten Fall 24 Stunden zurueck
#   (server.py: BACKUP_INTERVAL_HOURS, Vorgabe 24).
#
#   Das ist KEIN theoretischer Fall. Der Tracker laeuft in derselben Umgebung
#   wie der Rest des Werkzeugs, und die Erfahrung mit Netzlaufwerken ist im
#   Projekt gesondert vermerkt (Vorgang 33b859f9, tools/diag_sqlite_netdrive2).
#
# DAS VERFAHREN (Standardverfahren, hier nur konsequent angewandt):
#   1. In eine TEMPORAERE Datei IM SELBEN VERZEICHNIS schreiben. Dasselbe
#      Verzeichnis ist Bedingung, weil os.replace nur INNERHALB eines
#      Dateisystems atomar ist. /tmp kann auf einem anderen liegen.
#   2. flush() + os.fsync() - erst danach ist der Inhalt wirklich auf dem
#      Traeger und nicht nur im Schreibpuffer des Betriebssystems.
#   3. os.replace(temp, ziel) - das ist auf POSIX UND auf Windows ein
#      atomarer Austausch des Verzeichniseintrags. Es gibt keinen Zeitpunkt,
#      zu dem unter dem Zielnamen etwas Halbes steht: entweder der alte
#      vollstaendige Inhalt oder der neue vollstaendige Inhalt.
#   4. Verzeichnis-fsync, wo das Betriebssystem es zulaesst. Ohne ihn kann der
#      Verzeichniseintrag selbst noch im Puffer stehen. Unter Windows ist das
#      nicht moeglich; der Versuch wird ausdruecklich abgefangen und NICHT als
#      Fehler gewertet (der Austausch selbst ist dort trotzdem atomar).
#
# WAS DIESES MODUL AUSDRUECKLICH NICHT LEISTET:
#   Es schuetzt NICHT vor verlorenen Aenderungen bei gleichzeitigem Zugriff
#   (zwei Browserfenster, Server und merge.py gleichzeitig). Wer zuletzt
#   speichert, gewinnt - nur eben mit einer heilen Datei statt mit einer
#   halben. Die Sperre gegen gleichzeitigen Zugriff ist ein eigener Vorgang.
#   Grundregel 1: benannt, nicht stillschweigend uebergangen.
#
# Version: v0.8.642 - Build: 642 - 2026-08-01
# =============================================================================

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class JsonSafeWriter:
    """
    Schreibt JSON so, dass die Zieldatei zu keinem Zeitpunkt unvollstaendig ist.

    Bewusst KEINE Instanzzustaende ausser den Formatvorgaben: der Schreibweg
    soll von ueberall gleich aufrufbar sein und nichts mitschleppen, was
    zwischen zwei Aufrufen kaputtgehen kann.
    """

    #: Vorsatz der temporaeren Datei. Sichtbar gewaehlt (nicht '.tmp'), damit
    #: ein Rest nach einem Absturz als das erkennbar ist, was er ist, und
    #: niemand ihn fuer eine Sicherung haelt.
    TEMP_PREFIX = ".issues_write_"

    def __init__(self, indent: int = 2, ensure_ascii: bool = False):
        # indent=2 und ensure_ascii=False entsprechen exakt dem bisherigen
        # Verhalten von server.py und merge.py. Der Schreibweg aendert sich,
        # das Dateiformat NICHT - sonst waere jeder Git-Diff der issues.json
        # unlesbar und die Migration eine Zumutung.
        self.indent = indent
        self.ensure_ascii = ensure_ascii

    # -------------------------------------------------------------------
    # Oeffentlicher Weg
    # -------------------------------------------------------------------

    def write(self, ziel: Path, nutzlast: Any) -> Path:
        """
        Schreibt 'nutzlast' als JSON nach 'ziel' - atomar.

        Args:
            ziel:     Pfad der Zieldatei.
            nutzlast: Beliebiges JSON-serialisierbares Objekt.

        Returns:
            Den Pfad der geschriebenen Datei (identisch mit 'ziel').

        Raises:
            Alles, was json.dump oder das Dateisystem werfen. WICHTIG: In
            jedem dieser Faelle ist 'ziel' UNVERAENDERT - der Fehler faellt
            in die temporaere Datei, und die wird aufgeraeumt.
        """
        ziel = Path(ziel)
        verzeichnis = ziel.parent
        verzeichnis.mkdir(parents=True, exist_ok=True)

        # delete=False, weil wir die Datei nach dem Schliessen noch umbenennen
        # muessen. Das Aufraeumen erledigt der finally-Block unten.
        griff = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(verzeichnis),
            prefix=self.TEMP_PREFIX,
            suffix=".json",
            delete=False,
        )
        temp_pfad = Path(griff.name)

        try:
            with griff as f:
                json.dump(
                    nutzlast,
                    f,
                    indent=self.indent,
                    ensure_ascii=self.ensure_ascii,
                )
                # Ein abschliessender Zeilenumbruch. Ohne ihn meldet git bei
                # jedem Commit '\ No newline at end of file' - kosmetisch,
                # aber es verrauscht genau die Diffs, die wir lesen wollen.
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())

            # Der eigentliche Austausch. Ab hier ist die neue Fassung gueltig.
            os.replace(temp_pfad, ziel)
            temp_pfad = None  # nichts mehr aufzuraeumen

            self._verzeichnis_synchronisieren(verzeichnis)
            return ziel
        finally:
            # Aufraeumen NUR im Fehlerfall. Nach erfolgreichem os.replace ist
            # temp_pfad None und dieser Block tut nichts.
            if temp_pfad is not None:
                try:
                    temp_pfad.unlink()
                except OSError:
                    # Ein liegengebliebener Rest ist aergerlich, aber er darf
                    # den urspruenglichen Fehler nicht verdecken.
                    pass

    # -------------------------------------------------------------------
    # Innere Hilfe
    # -------------------------------------------------------------------

    @staticmethod
    def _verzeichnis_synchronisieren(verzeichnis: Path) -> bool:
        """
        Schreibt den Verzeichniseintrag auf den Traeger.

        Returns:
            True, wenn es geklappt hat; False, wenn das Betriebssystem es
            nicht zulaesst (Windows). Der Rueckgabewert existiert, damit ein
            Test die beiden Faelle unterscheiden kann - nicht, damit der
            Aufrufer sich darauf verlaesst.
        """
        try:
            fd = os.open(str(verzeichnis), os.O_RDONLY)
        except OSError:
            # Windows: Verzeichnisse lassen sich nicht als Datei oeffnen.
            return False

        try:
            os.fsync(fd)
            return True
        except OSError:
            return False
        finally:
            os.close(fd)
