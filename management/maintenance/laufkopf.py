# =============================================================================
# management/maintenance/laufkopf.py
# IT-Forensisches Ermittlungswerkzeug - Herkunftsnachweis einer Ausgabe
# =============================================================================
# Zweck:
#   JEDER LAUF SAGT, AUS WELCHEM STAND ER STAMMT - Buildnummer und die
#   MD5-Pruefsummen der Dateien, die den Lauf tatsaechlich getragen haben.
#
# ── DER BEFUND, DER ZU DIESER DATEI GEFUEHRT HAT ─────────────────────────────
#
#   Am 31.08.2026 lag mir eine Ausgabe von tools/postid_nachtragen.py vor,
#   die ZEICHENGLEICH war mit der aus dem Build davor. Zwei Erklaerungen
#   waren damit gleich gut vereinbar:
#
#     (a) der neue Stand ist gar nicht eingespielt worden
#     (b) der neue Stand ist eingespielt und hat an dieser Stelle nichts
#         geaendert
#
#   DAS SIND ZWEI VOELLIG VERSCHIEDENE LAGEN mit zwei voellig verschiedenen
#   naechsten Schritten - und die Ausgabe liess nicht erkennen, welche
#   vorlag. Eine Messung, deren Herkunft offen ist, ist keine Messung; sie
#   ist eine Zahl, die man nach der eigenen Erwartung liest.
#
#   GRUNDREGEL 8 verlangt MD5-Pruefsummen fuer die im Einsatz befindlichen
#   Dateien, damit die Nutzung unterschiedlicher Dateiversionen
#   ausgeschlossen ist. Bisher wurden sie ANGEFORDERT. Ab jetzt gibt der Lauf
#   sie von sich aus aus - die Regel hat damit eine Durchsetzung statt einer
#   Bitte.
#
# ── WAS HIER NICHT STEHT, UND WARUM ──────────────────────────────────────────
#
#   KEIN VERGLEICH MIT EINEM SOLLWERT. Das Werkzeug weiss nicht, welcher
#   Stand der richtige ist - das weiss nur der Entwickler. Es nennt, was es
#   geladen hat, und ueberlaesst das Urteil dem, der die Lieferung kennt. Ein
#   eingebauter Sollwert waere ein zweiter Ort, an dem eine Versionsangabe
#   gepflegt werden muss, und zwei solche Orte laufen auseinander.
#
#   KEIN ABBRUCH. Laesst sich eine Pruefsumme nicht bilden, wird das GESAGT
#   und der Lauf geht weiter. Ein Diagnosewerkzeug, das wegen seines eigenen
#   Kopfes nicht laeuft, ist schlimmer als eines mit unvollstaendigem Kopf.
#
# Version: 0.8.746 - Build 746
# =============================================================================

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Iterable, List, Optional

#: Wurzelverzeichnis des Webservers - zwei Ebenen ueber dieser Datei.
WURZEL = Path(__file__).resolve().parents[2]


class Laufkopf:
    """
    Der Herkunftsnachweis eines Laufs: Buildnummer und Dateipruefsummen.

    Verwendung:

        kopf = Laufkopf("anker_diagnose", [
            "tools/anker_diagnose.py",
            "management/maintenance/anker_diagnose.py",
            "report_render/html5_zerleger.py",
        ])
        for zeile in kopf.zeilen():
            print(zeile)

    Die Pfade sind relativ zum Wurzelverzeichnis. Angegeben gehoeren die
    Dateien, die das ERGEBNIS tragen - nicht alle, die zufaellig importiert
    werden: eine Liste, in der die entscheidende Datei zwischen zwanzig
    beilaeufigen steht, wird nicht gelesen.
    """

    def __init__(self, werkzeug: str, dateien: Iterable[str]) -> None:
        self._werkzeug = str(werkzeug)
        self._dateien = [str(d) for d in dateien]

    # ------------------------------------------------------------------
    @staticmethod
    def buildnummer() -> Optional[int]:
        """
        Die Buildnummer aus build.json - None, wenn sie nicht zu lesen ist.

        None und 0 sind zu unterscheiden: 0 waere eine Buildnummer, None
        heisst 'nicht feststellbar'. Die beiden zu vermengen hiesse, ein
        Nichtwissen als Wissen auszugeben.
        """
        try:
            p = WURZEL / "build.json"
            return int(json.loads(p.read_text(encoding="utf-8"))["build"])
        except Exception:
            return None

    # ------------------------------------------------------------------
    @staticmethod
    def html5lib_fassung() -> str:
        """Die Fassung von html5lib - oder ein Klartextgrund."""
        try:
            import html5lib
            return str(getattr(html5lib, "__version__", "unbekannt"))
        except ImportError:
            return "NICHT INSTALLIERT - die Zerlegung nach HTML5 ist nicht moeglich"

    # ------------------------------------------------------------------
    @staticmethod
    def md5_von(pfad: Path) -> str:
        """MD5 einer Datei, in Bloecken gelesen - oder ein Klartextgrund."""
        try:
            h = hashlib.md5()
            with open(pfad, "rb") as f:
                for block in iter(lambda: f.read(65536), b""):
                    h.update(block)
            return h.hexdigest()
        except Exception as exc:
            return "nicht lesbar (%s)" % exc

    # ------------------------------------------------------------------
    def zeilen(self) -> List[str]:
        """Der Kopf als Textzeilen - fertig zum Ausgeben."""
        nr = self.buildnummer()
        heraus = ["HERKUNFT DIESES LAUFS (Grundregel 8 - Dateiversionen)"]
        heraus.append("  Werkzeug : %s" % self._werkzeug)
        heraus.append("  Build    : %s"
                      % ("%d" % nr if nr is not None
                         else "NICHT FESTSTELLBAR - build.json nicht lesbar"))
        heraus.append("  Python   : %d.%d.%d" % sys.version_info[:3])
        # BUILD 747: html5lib bestimmt seit dem Wechsel auf den
        # HTML5-Standard MIT, wie der Abzug zerlegt wird. Eine andere
        # Fassung kann ein anderes Ergebnis bedeuten - sie gehoert damit
        # genauso in den Herkunftsnachweis wie die eigenen Dateien.
        heraus.append("  html5lib : %s" % self.html5lib_fassung())
        for rel in self._dateien:
            pfad = WURZEL / rel
            if not pfad.exists():
                heraus.append("  %-52s FEHLT" % rel)
                continue
            heraus.append("  %-52s %s" % (rel, self.md5_von(pfad)))
        heraus.append("  Diese Summen gehoeren gegen die MD5SUMS-Datei der "
                      "Lieferung gehalten. Weichen sie ab, ist der Lauf mit "
                      "einem anderen Stand gefahren worden, als angenommen.")
        return heraus
