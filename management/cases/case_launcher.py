# =============================================================================
# management/cases/case_launcher.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Startet aus dem Management-Portal heraus den FORENSIK-Webserver (main.py)
#   fuer einen bestimmten Fall (subject_id). Damit kann eine Ermittler:in einen
#   ihr zugewiesenen Fall mit EINEM Klick oeffnen, ohne start.bat oder eine
#   Kommandozeile bemuehen zu muessen.
#   Beleg: Projektgespraech 2026-07-22 (Bedarf 'Fall per Webserver starten aus
#   dem Management-Portal'); Bauplan Build 500 §1.
#
# GRUNDSATZENTSCHEIDUNGEN (mc 2026-07-22, in der Session festgelegt):
#   (E1) Start-Mechanik: Das Portal startet main.py als LOSGELOESTEN Subprozess
#        in DERSELBEN VM (beide Server laufen dort). Der Forensik-Server waehlt
#        selbst den naechsten freien Port (--auto-port) und oeffnet selbst den
#        Browser (--open-browser) — identisch zu start.bat, damit die Reihen-
#        folge 'Server zuerst, dann Browser' garantiert bleibt.
#   (E2) Fehlerbehandlung: NUR starten, Laufzeitfehler von main.py melden.
#        Diese Klasse prueft NICHT die Existenz der fallspezifischen DBs
#        (forensic_/evidence_/assets_<uid>.db). Fehlt eine Pflicht-DB, laeuft
#        das in den bestehenden HARTEN Abbruch von main.py (Grundregel 1) —
#        allerdings IM losgeloesten Prozess, also fuer das Portal nicht sichtbar
#        (dokumentierter Tradeoff, siehe Bauplan §4). START-ZEIT-Fehler (fehlender
#        Interpreter, fehlende main.py, OS-Fehler beim Spawn) werden hingegen
#        als CaseLaunchError SICHTBAR gemeldet — nie still verschluckt.
#
# INTERPRETER-AUFLOESUNG (gespiegelt aus start.bat, Projektgespraech 2026-06-24):
#   1. Portable Laufzeit  <repo>/../Python/python.exe  (falls vorhanden)
#   2. sys.executable      (der Interpreter, der das Management-Portal faehrt —
#                           robustester Rueckfall, laeuft nachweislich)
#   3. 'python'            (aus dem PATH; letzter Rueckfall)
#
# KAPSELUNG (Grundregel 10): Eine Klasse in einer eigenen Datei. Der eigentliche
#   Prozess-Spawn ist ueber den Konstruktor-Parameter 'spawn' injizierbar, damit
#   die Tests KEINEN echten Prozess starten muessen (kein Forensik-Server im CI).
#
# Version: v0.8.500 · Build: 500 · 2026-07-22
# Build 500: NEU — Fallstart aus dem Management-Portal (/api/case/launch).
# =============================================================================

from __future__ import annotations

import logging
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class CaseLaunchError(Exception):
    """
    Start-ZEIT-Fehler beim Oeffnen eines Falls (fehlender Interpreter, fehlende
    main.py, OS-Fehler beim Spawn oder ungueltige subject_id). Wird vom Endpoint
    in eine klare HTTP-Fehlerantwort uebersetzt (Grundregel 1: kein stiller
    Fehlschlag).
    """


# Typ-Alias fuer die injizierbare Spawn-Funktion. Erhaelt die vollstaendige
# Kommandozeile (argv) und das Arbeitsverzeichnis; gibt die PID zurueck.
SpawnFn = Callable[[List[str], Path], int]


class CaseLauncher:
    """
    Startet main.py fuer eine gegebene subject_id als losgeloesten Subprozess.

    Verwendung (PROD):
        launcher = CaseLauncher()
        info = launcher.launch(12345)   # -> {"pid": ..., "command": [...], ...}

    Verwendung (Test):
        launcher = CaseLauncher(spawn=fake_spawn)   # kein echter Prozess

    Konstruktor-Parameter:
        project_root — Wurzel des aiw_webserver-Repos (wo main.py liegt). Default:
                       aus dem Modulpfad abgeleitet (management/cases/.. -> repo).
        python_exe   — Interpreter-Pfad erzwingen (Test/Sonderfall). Default:
                       Auto-Aufloesung (portable > sys.executable > 'python').
        spawn        — Injizierbare Spawn-Funktion (Test). Default: interner,
                       plattformabhaengiger, DETACHED Popen (wie browser_launcher).
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        python_exe: Optional[str] = None,
        spawn: Optional[SpawnFn] = None,
    ) -> None:
        # management/cases/case_launcher.py -> parents[0]=cases, [1]=management,
        # [2]=Repo-Wurzel (dort liegt main.py). Deterministisch, unabhaengig vom
        # Arbeitsverzeichnis beim Start des Management-Servers.
        self._project_root = (project_root
                              or Path(__file__).resolve().parents[2])
        self._python_exe_override = python_exe
        self._spawn: SpawnFn = spawn or self._default_spawn

    # ------------------------------------------------------------------ Pfade
    @property
    def main_py(self) -> Path:
        """Absoluter Pfad zur main.py (Einstiegspunkt des Forensik-Servers)."""
        return (self._project_root / "main.py").resolve()

    def resolve_python(self) -> str:
        """
        Loest den zu verwendenden Python-Interpreter auf (Eskalationskette wie
        start.bat). Ein per Konstruktor gesetzter Override hat Vorrang.

        Rueckgabe: Interpreter-Pfad/-Name als String.
        """
        if self._python_exe_override:
            return self._python_exe_override

        # 1) Portable Laufzeit neben dem Repo:  <repo>/../Python/python.exe
        #    (so wird sie in der PROD-VM ausgeliefert, Beleg start.bat).
        portable = (self._project_root.parent / "Python" / "python.exe")
        if portable.is_file():
            logger.debug("CaseLauncher: portable Python gefunden: %s", portable)
            return str(portable)

        # 2) Derselbe Interpreter, der das Management-Portal faehrt — der laeuft
        #    nachweislich und passt zur Projektumgebung.
        if sys.executable:
            return sys.executable

        # 3) Letzter Rueckfall: 'python' aus dem PATH.
        return "python"

    # ---------------------------------------------------------------- Kommando
    def build_command(self, subject_id: int) -> List[str]:
        """
        Baut die vollstaendige Kommandozeile zum Start des Forensik-Servers fuer
        den Fall <subject_id>. Bewusst identisch zum start.bat-Aufruf:
            <python> main.py --mode cli --subject-id <id> --auto-port --open-browser

        --mode cli   : deterministischer Fallstart ueber die subject_id (nicht
                       'job', das den AELTESTEN offenen Fall zoege — hier will die
                       Ermittler:in GENAU DIESEN Fall oeffnen).
        --auto-port  : naechster freier Port ab 8080 (Mehrfachfaelle moeglich).
        --open-browser: der Forensik-Server oeffnet den Browser SELBST auf der
                       tatsaechlich gebundenen Adresse (Reihenfolge garantiert).
        """
        sid = self._validate_subject_id(subject_id)
        return [
            self.resolve_python(),
            str(self.main_py),
            "--mode", "cli",
            "--subject-id", str(sid),
            "--auto-port",
            "--open-browser",
        ]

    # ------------------------------------------------------------------ Start
    def launch(self, subject_id: int) -> Dict[str, Any]:
        """
        Startet den Forensik-Server fuer <subject_id> als losgeloesten Prozess.

        Rueckgabe (dict):
            {"pid": int, "subject_id": int, "command": [str, ...],
             "python": str, "cwd": str}

        Raises:
            CaseLaunchError — bei ungueltiger subject_id, fehlender main.py oder
                              OS-Fehler beim Spawn (START-ZEIT-Fehler, E2).
        """
        sid = self._validate_subject_id(subject_id)

        # main.py MUSS existieren — sonst kann der Fall nie starten. Das ist ein
        # klarer, dem Portal SICHTBARER Fehler (nicht der 'DB fehlt'-Fall aus E2,
        # der bewusst erst im losgeloesten Prozess auftritt).
        if not self.main_py.is_file():
            raise CaseLaunchError(
                "Forensik-Einstiegspunkt nicht gefunden: %s" % self.main_py)

        command = self.build_command(sid)
        logger.info("CaseLauncher: starte Fall subject_id=%d: %s",
                    sid, " ".join(command))

        try:
            pid = self._spawn(command, self._project_root)
        except OSError as exc:
            # z.B. Interpreter nicht ausfuehrbar / nicht gefunden.
            raise CaseLaunchError(
                "Fall subject_id=%d konnte nicht gestartet werden "
                "(Prozessstart fehlgeschlagen): %s" % (sid, exc)) from exc

        logger.info("CaseLauncher: Fall subject_id=%d gestartet, PID=%s",
                    sid, pid)
        return {
            "pid": pid,
            "subject_id": sid,
            "command": command,
            "python": command[0],
            "cwd": str(self._project_root),
        }

    # ------------------------------------------------------------- Interna
    @staticmethod
    def _validate_subject_id(subject_id: int) -> int:
        """
        Erzwingt eine positive Ganzzahl als subject_id. Eine falsche subject_id
        wuerde Beweise eines anderen Beschuldigten oeffnen — daher harter Abbruch
        bei jeder Unklarheit (analog ModeResolver).
        """
        try:
            sid = int(subject_id)
        except (TypeError, ValueError) as exc:
            raise CaseLaunchError(
                "subject_id ungueltig: %r" % (subject_id,)) from exc
        if sid <= 0:
            raise CaseLaunchError(
                "subject_id muss positiv sein, war: %d" % sid)
        return sid

    @staticmethod
    def _default_spawn(command: List[str], cwd: Path) -> int:
        """
        Plattformabhaengiger, LOSGELOESTER Prozessstart (gespiegelt aus
        core/browser_launcher.py::_launch_explicit). Der Forensik-Server laeuft
        eigenstaendig weiter, auch wenn das Management-Portal spaeter endet;
        stdout/stderr werden verworfen, damit keine Pipe den Elternprozess haelt.

        Rueckgabe: PID des gestarteten Prozesses.
        """
        kwargs: Dict[str, Any] = {}
        if platform.system().lower() == "windows":
            # 0x00000008 = DETACHED_PROCESS: kein Konsolenfenster, keine Bindung
            # an das Portal. CREATE_NEW_PROCESS_GROUP (0x00000200), damit ein
            # Strg+C im Portal nicht den Forensik-Server mit-killt.
            flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            kwargs["creationflags"] = flags
        else:
            # POSIX (Dev/CI): eigene Session, damit ein Terminal-Signal den
            # Kindprozess nicht mitnimmt.
            kwargs["start_new_session"] = True

        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **kwargs,
        )
        return proc.pid
