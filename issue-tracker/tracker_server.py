#!/usr/bin/env python3
"""
Issue Tracker - Einfacher Bug- und Feature-Request-Tracker
Git-integrierbar mit JSON-Speicher und Web-Interface
"""

import json
import hashlib
import re
from contextlib import asynccontextmanager
import uuid
import logging
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, HTTPException, Query, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
# Build 647: fuer den nl2br-Filter. 'escape' maskiert, 'Markup' erklaert eine
# Zeichenkette fuer bereits maskiert - beides ausdruecklich und an genau einer
# Stelle, siehe die Begruendung am Filter selbst.
from markupsafe import Markup, escape

# ---------------------------------------------------------------------------
# Eigene Bausteine (Build 642).
#
# Beide liegen im selben Verzeichnis wie diese Datei; Python nimmt das
# Skriptverzeichnis von sich aus in sys.path auf, sowohl bei 'python server.py'
# als auch bei 'uvicorn tracker_server:app' aus diesem Verzeichnis.
#
# WARUM AUSGELAGERT: Ein Baustein, der 'fastapi' voraussetzt, ist in der
# Regression nicht pruefbar - das Paket ist keine Abhaengigkeit der Testumgebung
# (vgl. die Begruendung in tests/test_issue_tracker_schema.py zu 'jsonschema').
# Der Schreibweg und die Namensregel der Sicherungen sind aber genau das, was
# geprueft werden MUSS. Also stehen sie in eigenen Dateien - das entspricht
# zugleich Grundregel 10.
# ---------------------------------------------------------------------------
from json_safe_writer import JsonSafeWriter
from textformat import zeilen_html
from tag_cloud import tag_wolke, STUFEN as TAG_STUFEN
from backup_names import (
    SERVER_MUSTER,
    zeitpunkt_aus_namen,
    SUCH_GLOB,
    eigene_sicherungen,
    server_sicherungsname,
)

# ============================================================================
# Konfiguration laden
# ============================================================================

# .env-Datei laden
load_dotenv()

class Config:
    """Zentrale Konfiguration aus .env-Datei"""
    
    # Server
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    RELOAD: bool = os.getenv("RELOAD", "false").lower() == "true"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # Pfade
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "./data"))
    TEMPLATES_DIR: Path = Path(os.getenv("TEMPLATES_DIR", "./templates"))
    ISSUES_FILE: Path = Path(os.getenv("ISSUES_FILE", "./data/issues.json"))
    STATIC_DIR: Path = Path(os.getenv("STATIC_DIR", "./static"))
    LOGS_DIR: Path = Path(os.getenv("LOGS_DIR", "./logs"))
    
    # Backup
    AUTO_BACKUP: bool = os.getenv("AUTO_BACKUP", "true").lower() == "true"
    BACKUP_DIR: Path = Path(os.getenv("BACKUP_DIR", "./backups"))
    # BUILD 650 (Vorgang 0c14996b): Vorgabe von 24 auf 1 Stunde. Festlegung
    # mc, 2026-08-02: "Jede Stunde, 48 Generationen." Ein Arbeitstag am
    # Tracker bekommt damit rund acht Sicherungspunkte statt einem, und der
    # Vorrat reicht zwei Arbeitswochen zurueck.
    BACKUP_INTERVAL_HOURS: int = int(os.getenv("BACKUP_INTERVAL_HOURS", "1"))
    # Bis Build 649 stand die Zahl 10 fest im Code. Sie gehoert in die
    # Konfiguration - sie ist eine Betriebsentscheidung, keine Bauentscheidung.
    BACKUP_KEEP: int = int(os.getenv("BACKUP_KEEP", "48"))
    
    # UI
    TITLE: str = os.getenv("TITLE", "Software Issue Tracker")
    COMPANY_NAME: str = os.getenv("COMPANY_NAME", "MyCompany")
    MAX_TITLE_LENGTH: int = int(os.getenv("MAX_TITLE_LENGTH", "80"))
    ITEMS_PER_PAGE: int = int(os.getenv("ITEMS_PER_PAGE", "50"))
    
    # Benutzer
    DEFAULT_REPORTER: str = os.getenv("DEFAULT_REPORTER", "developer")
    ALLOWED_REPORTERS: List[str] = os.getenv("ALLOWED_REPORTERS", "developer,tester,admin").split(",")
    REQUIRE_AUTH: bool = os.getenv("REQUIRE_AUTH", "false").lower() == "true"
    
    # E-Mail (optional)
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    NOTIFICATION_EMAILS: List[str] = os.getenv("NOTIFICATION_EMAILS", "").split(",") if os.getenv("NOTIFICATION_EMAILS") else []


config = Config()

# ============================================================================
# Logging einrichten
# ============================================================================

# Logs-Verzeichnis erstellen
config.LOGS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOGS_DIR / "tracker.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# Verzeichnisse initialisieren
# ============================================================================

def init_directories():
    """Erstellt alle benötigten Verzeichnisse"""
    directories = [
        config.DATA_DIR,
        config.TEMPLATES_DIR,
        config.STATIC_DIR,
        config.LOGS_DIR,
        config.BACKUP_DIR
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        logger.info(f"Verzeichnis bereit: {directory}")

init_directories()

# ============================================================================
# FastAPI App erstellen
# ============================================================================

# ----------------------------------------------------------------------------
# BUILD 649 (Vorgang 044ca2ee): Die laufende Fassung des Pakets.
#
# Die Schnellaktionen der Detailansicht setzen einen Vorgang auf 'geloest',
# ohne nach der Fassung zu fragen - drei Vorgaenge im Bestand sind so ohne
# 'resolved_in_version' entstanden. Die Fassung ABZUFRAGEN waere das Ende der
# Schnellaktion; sie EINZUTRAGEN kostet nichts, denn sie steht in build.json.
#
# Faellt das Lesen aus, bleibt der Wert leer - genau wie bisher. Ein
# Erzeugungsvermerk, der eine falsche Fassung nennt, waere schlechter als
# keiner (vgl. Vorgang ff7e80ab zum Rueckfall auf 'Build 0').
# ----------------------------------------------------------------------------
def _paketfassung() -> str:
    try:
        datei = Path(__file__).resolve().parent.parent / "build.json"
        wert = json.loads(datei.read_text(encoding="utf-8")).get("version", "")
        return str(wert) if wert else ""
    except Exception as fehler:  # pragma: no cover - Randfall
        logger.warning("build.json nicht lesbar, Fassung bleibt leer: %s", fehler)
        return ""


PAKETFASSUNG = _paketfassung()

# ============================================================================
# BUILD 650 - START UND ENDE UEBER 'lifespan' (Vorgang afa7f325)
#
# Bis Build 649 standen hier '@app.on_event("startup")' und '("shutdown")'.
# FastAPI hat beide zugunsten des 'lifespan'-Kontextes fuer ueberholt
# erklaert und meldet das bei jedem Lauf der Regression als Warnung.
#
# WAS SICH FACHLICH AENDERT: NICHTS. Es sind dieselben Zeilen im Protokoll,
# an derselben Stelle im Ablauf. Der Unterschied ist die Bauform: statt zweier
# Rueckrufe gibt es EINEN Kontext, in dem 'vor dem Betrieb' und 'nach dem
# Betrieb' um ein 'yield' herum stehen. Das ist auch der Grund, warum die
# Umstellung ueberhaupt lohnt - man sieht beide Haelften auf einen Blick und
# kann nicht mehr vergessen, dass es die zweite gibt.
#
# WARUM JETZT UND NICHT SPAETER: Die Fassung in issue-tracker/requirements.txt
# ist auf fastapi 0.115.0 festgenagelt, es lief also. Aber eine festgenagelte
# Fassung ist kein Zustand, sondern ein Aufschub - und der Aufschub kostet bei
# jedem Regressionslauf eine Warnzeile, die man wegsehen lernt. Genau das ist
# der Weg, auf dem echte Warnungen untergehen (vgl. Vorgang 9de086d3,
# 'Alarmmuedigkeit').
# ============================================================================

@asynccontextmanager
async def lebenszyklus(anwendung: FastAPI):
    """Was vor dem ersten und nach dem letzten Aufruf geschieht."""
    logger.info("=" * 60)
    logger.info(f"{config.TITLE} wird gestartet")
    logger.info(f"Host: {config.HOST}:{config.PORT}")
    logger.info(f"Daten-Verzeichnis: {config.DATA_DIR.absolute()}")
    logger.info(f"Issue-Datei: {config.ISSUES_FILE.absolute()}")
    logger.info(f"Backup-Verzeichnis: {config.BACKUP_DIR.absolute()}")
    logger.info(f"Debug-Modus: {config.DEBUG}")
    logger.info(f"Auto-Backup: {config.AUTO_BACKUP}")
    logger.info("=" * 60)

    yield

    logger.info("Server wird heruntergefahren")


app = FastAPI(
    lifespan=lebenszyklus,
    title=config.TITLE,
    version="2.0.0",
    description="Lokaler Issue Tracker für die Softwareentwicklung"
)

# Templates konfigurieren
templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))

# Globale Template-Variablen
templates.env.globals["config"] = config
templates.env.globals["paketfassung"] = PAKETFASSUNG


# ============================================================================
# Jinja-Filter - BUILD 647
# ============================================================================

def zeilen(text: Any) -> Markup:
    """
    Jinja-Filter: mehrzeiliger Text -> Zeilen-Bloecke, sicher maskiert.

    DIE ARBEIT STEHT IN textformat.py, nicht hier. Grund: server.py setzt
    'fastapi' voraus und ist in der Regression nicht importierbar; die
    Maskierung ist aber die einzige Stelle, an der aus Daten HTML wird, und
    muss geprueft werden koennen. Dort steht auch die Begruendung dafuer,
    dass KEIN <br> herauskommt (gemessen im Browser: mit <br> sind die von
    mc gewuenschten 1,5 Zeilenhoehen nicht zu erreichen).

    Hier bleibt nur die Zusage an Jinja: 'dieses HTML ist fertig maskiert'.
    """
    return Markup(zeilen_html(text))


templates.env.filters["zeilen"] = zeilen

# ============================================================================
# Daten-Management
# ============================================================================

class IssueManager:
    """Verwaltet das Laden und Speichern der Issues"""
    
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.last_backup: Optional[datetime] = None
        # Build 642: EIN Schreibweg, und der ist atomar. Siehe
        # json_safe_writer.py fuer die Begruendung.
        self.writer = JsonSafeWriter()
    
    def load(self) -> List[Dict[str, Any]]:
        """Lädt Issues aus JSON-Datei"""
        if not self.file_path.exists():
            logger.warning(f"Issue-Datei nicht gefunden: {self.file_path}")
            return []
        
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                issues = data.get("issues", [])
                logger.info(f"{len(issues)} Issues geladen")
                return issues
        except json.JSONDecodeError as e:
            logger.error(f"Fehler beim Lesen der JSON-Datei: {e}")
            # Backup versuchen
            backup_file = self._find_latest_backup()
            if backup_file:
                logger.info(f"Versuche Backup zu laden: {backup_file}")
                with open(backup_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("issues", [])
            return []
        except Exception as e:
            logger.error(f"Unerwarteter Fehler beim Laden: {e}")
            return []
    
    def save(self, issues: List[Dict[str, Any]]) -> bool:
        """
        Speichert Issues in JSON-Datei.

        BUILD 642 - ATOMAR. Bis Build 641 stand hier ein unmittelbares
        open(self.file_path, "w"). Das kuerzt die Datei auf null Byte, BEVOR
        der erste Vorgang geschrieben ist; jeder Ausfall in diesem Fenster
        loeschte den gesamten Bestand. Jetzt wird in eine Nachbardatei
        geschrieben und erst am Ende umgehaengt: entweder steht der alte
        vollstaendige Stand da oder der neue vollstaendige - nie etwas
        dazwischen.
        """
        try:
            # Vor dem Speichern Backup erstellen
            if config.AUTO_BACKUP:
                self._create_backup()

            # Daten schreiben - atomar (json_safe_writer.py)
            self.writer.write(self.file_path, {"issues": issues})

            logger.info(f"{len(issues)} Issues gespeichert")
            return True
        except Exception as e:
            # Der Bestand ist in diesem Fall UNVERAENDERT - das ist die
            # eigentliche Zusage des atomaren Schreibens. Deshalb steht es
            # auch im Protokoll: wer die Zeile liest, soll wissen, dass er
            # nichts wiederherstellen muss.
            logger.error(f"Fehler beim Speichern (Bestand unveraendert): {e}")
            return False
    
    def _juengste_eigene_sicherung(self) -> Optional[datetime]:
        """
        Wann die letzte eigene Sicherung entstanden ist - laut Dateisystem.

        BUILD 650 (Vorgang 0c14996b). Bis Build 649 stand der Zeitpunkt in
        'self.last_backup', also in einem Feld des laufenden Prozesses. Das
        hatte zwei Folgen, die beide gegen den Zweck einer Sicherung laufen:
        nach jedem Neustart begann der Takt von vorn (es entstand also eine
        Sicherung mehr als gedacht), und lief der Server durch, entstand bei
        einer Taktlaenge von 24 Stunden fuer einen ganzen Arbeitstag genau
        EIN Sicherungspunkt - der Stand VOR der ersten Aenderung.

        Der Blick auf die Platte kennt beide Probleme nicht: dort steht, was
        wirklich da ist. Gelesen wird der Zeitstempel aus dem NAMEN, nicht
        die Aenderungszeit - die kann durch Kopieren oder eine
        Dateisynchronisation verstellt sein.
        """
        eigene = eigene_sicherungen(config.BACKUP_DIR, SERVER_MUSTER)
        if not eigene:
            return None
        zeitpunkte = [zeitpunkt_aus_namen(p.name) for p in eigene]
        vorhanden = [z for z in zeitpunkte if z is not None]
        return max(vorhanden) if vorhanden else None

    def _create_backup(self):
        """Erstellt ein Backup der aktuellen Issue-Datei"""
        if not self.file_path.exists():
            return

        # Prüfen ob Backup nötig ist - am Bestand, nicht am Gedaechtnis.
        now = datetime.now()
        juengste = self._juengste_eigene_sicherung()
        if juengste and (now - juengste) < timedelta(hours=config.BACKUP_INTERVAL_HOURS):
            return
        
        backup_file = config.BACKUP_DIR / server_sicherungsname(now)

        try:
            shutil.copy2(self.file_path, backup_file)
            self.last_backup = now
            logger.info(f"Backup erstellt: {backup_file}")

            # ---------------------------------------------------------------
            # BEREINIGUNG - BUILD 642: NUR NOCH DIE EIGENEN.
            #
            # Bis Build 641 stand hier ein Glob 'issues_backup_*.json'. Der
            # passt AUCH auf 'issues_backup_before_merge_*.json', also auf die
            # Sicherungen des Merge-Werkzeugs. Der Server durfte damit fremde
            # Sicherungen loeschen - und zwar ausgerechnet die, die den Stand
            # unmittelbar vor einer Zusammenfuehrung festhalten.
            #
            # Jetzt wird nach dem Muster des EIGENEN Erzeugers ausgewaehlt
            # (backup_names.SERVER_MUSTER). Was diesem Muster nicht entspricht,
            # gehoert jemand anderem und bleibt liegen.
            # ---------------------------------------------------------------
            eigene = eigene_sicherungen(config.BACKUP_DIR, SERVER_MUSTER)
            if len(eigene) > config.BACKUP_KEEP:
                for old_backup in eigene[:-config.BACKUP_KEEP]:
                    old_backup.unlink()
                    logger.debug(f"Altes eigenes Backup gelöscht: {old_backup}")
        except Exception as e:
            logger.error(f"Backup fehlgeschlagen: {e}")
    
    def _find_latest_backup(self) -> Optional[Path]:
        """
        Findet das neueste Backup.

        HIER IST DER WEITE GLOB RICHTIG und bleibt deshalb stehen: zum LESEN
        ist jede Sicherung recht, gleich wer sie angelegt hat. Eng wird nur
        die Auswahl zum LOESCHEN (siehe _create_backup).
        """
        backups = sorted(config.BACKUP_DIR.glob(SUCH_GLOB), reverse=True)
        return backups[0] if backups else None
    
    #: Anzahl der Stufen in der Tag-Wolke. Die Begruendung steht bei der
    #: Vorgabe in tag_cloud.py; hier wird sie nur uebernommen, damit es
    #: NICHT zwei Zahlen gibt, die auseinanderlaufen koennen.
    WOLKEN_STUFEN = TAG_STUFEN

    def get_tag_cloud(self, issues: List[Dict]) -> List[Dict[str, Any]]:
        """
        Tag-Wolke fuer das Dashboard (Vorgang 2d692c67).

        DIE ARBEIT STEHT IN tag_cloud.py - aus demselben Grund wie beim
        Filter 'zeilen': ein Baustein, der in server.py steht, ist ohne
        'fastapi' nicht pruefbar. Dort stehen auch die drei Entscheidungen
        (Gross-/Kleinschreibung, ein Tag je Vorgang einmal, logarithmische
        Stufung) und der Befund, der zur logarithmischen Stufung gefuehrt hat.
        """
        return tag_wolke(issues, self.WOLKEN_STUFEN)

    def get_statistics(self, issues: List[Dict]) -> Dict[str, int]:
        """Berechnet Statistiken"""
        return {
            "total": len(issues),
            "open": sum(1 for i in issues if i.get("status") == "open"),
            "in_progress": sum(1 for i in issues if i.get("status") == "in_progress"),
            "review": sum(1 for i in issues if i.get("status") == "review"),
            "testing": sum(1 for i in issues if i.get("status") == "testing"),
            "resolved": sum(1 for i in issues if i.get("status") == "resolved"),
            "closed": sum(1 for i in issues if i.get("status") == "closed"),
            "bugs": sum(1 for i in issues if i.get("type") == "bug"),
            "features": sum(1 for i in issues if i.get("type") == "feature_request"),
            "improvements": sum(1 for i in issues if i.get("type") == "improvement"),
            "critical": sum(1 for i in issues if i.get("priority") == "critical"),
            "high": sum(1 for i in issues if i.get("priority") == "high"),
        }

# Issue Manager initialisieren
issue_manager = IssueManager(config.ISSUES_FILE)

# ============================================================================
# Status-Workflow
# ============================================================================

STATUS_FLOW = {
    "open": [
        "in_progress",      # Bearbeitung beginnen
        "resolved",         # Direkt als gelöst markieren (z.B. für triviale Fixes)
        "closed",           # Direkt schließen (z.B. Duplikat erkannt)
        "wont_fix",         # Wird nicht behoben
        "duplicate",        # Ist ein Duplikat
        "cannot_reproduce"  # Nicht reproduzierbar
    ],
    "in_progress": [
        "review",           # Zum Review
        "resolved",         # Direkt lösen (ohne formalen Review)
        "closed",           # Schließen (z.B. obsolet geworden)
        "open",             # Zurück zu offen
        "cannot_reproduce"  # Stellt sich als nicht reproduzierbar heraus
    ],
    "review": [
        "testing",          # Zum Testen
        "in_progress",      # Zurück in Bearbeitung
        "resolved",         # Direkt als gelöst markieren
        "open"              # Zurück zu offen
    ],
    "testing": [
        "resolved",         # Test bestanden
        "in_progress",      # Zurück in Bearbeitung (Bug gefunden)
        "open"              # Zurück zu offen
    ],
    "resolved": [
        "closed",           # Endgültig schließen
        "testing",          # Wieder testen
        "in_progress",      # Wieder öffnen für Nacharbeit
        "open"              # Wieder vollständig öffnen
    ],
    "closed": [
        "open"              # Wieder öffnen
    ],
    "wont_fix": [
        "open"              # Doch bearbeiten
    ],
    "duplicate": [
        "open"              # Neue Bewertung
    ],
    "cannot_reproduce": [
        "open",             # Wieder öffnen mit mehr Infos
        "closed"            # Endgültig schließen
    ]
}

STATUS_LABELS = {
    "open": "Offen",
    "in_progress": "In Bearbeitung",
    "review": "Review",
    "testing": "Test",
    "resolved": "Gelöst",
    "closed": "Geschlossen",
    "wont_fix": "Wird nicht behoben",
    "duplicate": "Duplikat",
    "cannot_reproduce": "Nicht reproduzierbar"
}

# ============================================================================
# BUILD 647 - DIE AUSWAHLLISTEN DES DASHBOARDS STEHEN AB JETZT HIER.
#
# ANLASS: Vorgang 7571d4de (mc, Prioritaet 'high') - "Im Dashboard alle
#   moeglichen Status als Filter erlauben". index.html hatte die Werte fest
#   verdrahtet und kannte 4 der 9 Status, 3 der 5 Typen und 4 der 5
#   Prioritaeten. GEZAEHLT am Bestand von Build 646 (140 Vorgaenge): 3 in
#   nicht waehlbaren Status, 8 vom Typ 'documentation', 1 mit Prioritaet
#   'wishlist' - zusammen 12 Vorgaenge, die ueber die Filter nicht auffindbar
#   waren. Dass es sie gibt, sah man nirgends.
#
# WARUM IM SERVER UND NICHT IN DER VORLAGE: Eine Aufzaehlung, die an zwei
#   Orten gepflegt wird, laeuft auseinander - sie ist genau so
#   auseinandergelaufen. STATUS_LABELS gab es die ganze Zeit; die Vorlage hat
#   nur nie hineingesehen. Ab jetzt gibt es EINE Quelle, und die Vorlage
#   baut ihre Auswahlfelder daraus. Wer einen Wert ergaenzt, ergaenzt ihn
#   hier - und er steht sofort im Filter.
#
# Die Aufzaehlungen sind woertlich dieselben wie in
# issue-tracker.schema.json und in merge.py (IssueValidator).
# ============================================================================

TYPE_LABELS = {
    "bug": "Bug",
    "feature_request": "Feature Request",
    "improvement": "Verbesserung",
    "documentation": "Dokumentation",
    "refactoring": "Refactoring",
}

PRIORITY_LABELS = {
    "critical": "Kritisch",
    "high": "Hoch",
    "medium": "Mittel",
    "low": "Niedrig",
    "wishlist": "Wunschliste",
}

SEVERITY_LABELS = {
    "blocker": "Blocker",
    "critical": "Kritisch",
    "major": "Schwerwiegend",
    "minor": "Gering",
    "trivial": "Trivial",
    "enhancement": "Erweiterung",
}

# ============================================================================
# Hilfsfunktionen
# ============================================================================

def create_update_entry(author: str, action: str, comment: str = "", 
                        old_value: str = "", new_value: str = "") -> Dict:
    """Erstellt einen Update-Eintrag für die Timeline"""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "author": author,
        "action": action,
        "old_value": old_value,
        "new_value": new_value,
        "comment": comment
    }

# ============================================================================
# Hilfen fuer die Filterung - BUILD 649
# ============================================================================

def _saubere_werte(werte: Optional[List[str]]) -> List[str]:
    """
    Macht aus dem, was ein Auswahlfeld schickt, eine brauchbare Liste.

    WARUM DAS NOETIG IST: Ein <select> ohne Auswahl schickt seinen leeren
    Eintrag mit ('status_filter='). Ohne diese Reinigung stuende in der Liste
    eine leere Zeichenkette, und der Filter wuerde alles wegwerfen, weil kein
    Vorgang den Status '' hat. Der Fehler waere schwer zu finden: die Seite
    zeigte einfach nichts an.

    Doppelte Werte werden zusammengefasst, die Reihenfolge bleibt erhalten -
    sie ist die Reihenfolge des Auswahlfelds und damit vorhersagbar.
    """
    if not werte:
        return []
    gesehen = []
    for wert in werte:
        sauber = str(wert).strip()
        if sauber and sauber not in gesehen:
            gesehen.append(sauber)
    return gesehen


def _sucht(issue: Dict[str, Any], begriff: str) -> bool:
    """
    Volltextsuche ueber einen Vorgang.

    BUILD 647 (Vorgang 18204843): erfasst ausdruecklich auch die TAGS sowie
    erwartetes und tatsaechliches Verhalten. Bis Build 646 sah die Suche nur
    in Titel, Beschreibung und ID - ausgerechnet das Merkmal, nach dem in
    diesem Projekt gearbeitet wird, blieb aussen vor.
    """
    felder = (
        issue.get("title", ""),
        issue.get("description", ""),
        issue.get("id", ""),
        issue.get("expected_behavior", ""),
        issue.get("actual_behavior", ""),
    )
    if any(begriff in str(f).lower() for f in felder):
        return True
    return any(begriff in str(t).lower() for t in (issue.get("tags") or []))


# ============================================================================
# Formularpruefung - BUILD 649
#
# VIER VORGAENGE, EINE URSACHE. 237503ce (Titel wird bei 80 Zeichen
# stillschweigend gekuerzt), fd0d5d52 (die Maske kann den Bestand
# schemawidrig machen), ed9205cc (unlesbare Aufwandsangabe wird still
# verworfen) und 04a0a4bc (unbekannte Verweise werden still verworfen)
# beschreiben dasselbe Muster: DIE MASKE VERWIRFT, STATT ABZUWEISEN.
#
# Der Grund war baulich: es gab keinen Weg zurueck. save_issue konnte nur
# speichern oder mit einem HTTP-Fehler abbrechen - und ein Abbruch haette die
# Eingabe genauso verloren. Also wurde stillschweigend zurechtgebogen.
#
# Ab Build 649 gibt es diesen Weg: Bei einem Fehler wird das Formular MIT DEN
# EINGABEN und den Meldungen neu ausgeliefert. Nichts geht verloren, und
# niemand muss ins Serverprotokoll sehen, um zu erfahren, was passiert ist.
#
# GEGENPROBE ZUR ABGRENZUNG: merge.py weist dieselben Faelle seit jeher ab
# (IssueValidator). Dass die Maske sie annahm, war der eigentliche Befund -
# dieselbe Vorgabe, zwei Verhaltensweisen.
# ============================================================================

#: Woertlich aus issue-tracker.schema.json und aus merge.py (VERSIONS_MUSTER).
FORMULAR_VERSIONSMUSTER = re.compile(r"^\d+\.\d+\.\d+[a-z]?$")


def vorgangsstand(issue: Optional[Dict[str, Any]]) -> str:
    """
    Ein kurzer Fingerabdruck EINES Vorgangs.

    BUILD 650 (Vorgang f0d2894b): Er ist die Fassungsnummer, die das Formular
    verdeckt mittraegt. Beim Speichern wird er neu gebildet und verglichen -
    stimmt er nicht mehr, hat in der Zwischenzeit jemand anderes denselben
    Vorgang geaendert.

    WARUM JE VORGANG UND NICHT UEBER DIE GANZE DATEI: Ein Fingerabdruck der
    ganzen Datei schluege auch dann an, wenn jemand einen VOELLIG ANDEREN
    Vorgang bearbeitet hat - und wuerde damit staendig Konflikte melden, die
    keine sind. Fuer den Bestand gilt das ohnehin nicht: save_issue laedt die
    Datei bei jedem Aufruf frisch und aendert darin genau einen Vorgang;
    Aenderungen an anderen Vorgaengen koennen also gar nicht verlorengehen.
    Verloren gehen kann nur der EINE Vorgang, den zwei Leute gleichzeitig
    offen haben - und genau den beschreibt dieser Fingerabdruck.

    WAS ER NICHT LEISTET: Das Fenster INNERHALB eines Aufrufs - zwischen dem
    Laden und dem Schreiben, also wenige Millisekunden - bleibt offen. Wer es
    schliessen will, braucht eine Dateisperre, und die deckt dann auch
    merge.py mit ab; das ist ein eigener Bau und ausdruecklich nicht dieser
    (Festlegung mc, 2026-08-02).

    'sort_keys' und der feste Zeichensatz sind Bedingung: sonst haenge der
    Fingerabdruck an der zufaelligen Reihenfolge im Speicher und meldete
    Konflikte, wo keine sind.
    """
    if not issue:
        return ""
    roh = json.dumps(issue, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(roh.encode("utf-8")).hexdigest()[:16]


def pruefe_formular(werte: Dict[str, Any], bekannte_ids: set,
                    bestehende_verweise: List[str]) -> List[str]:
    """
    Prüft die Eingaben einer Maske und gibt die Meldungen zurück.

    Args:
        werte:                die Formularwerte.
        bekannte_ids:         alle Vorgangs-IDs im Bestand.
        bestehende_verweise:  die Verweise, die im Vorgang schon stehen. Sie
                              werden durchgelassen, auch wenn sie unbekannt
                              sind - sonst wuerde die Maske Altlasten
                              stillschweigend entfernen, und genau das war
                              der Fehler aus Build 645.

    Returns:
        Liste von Meldungen. Leer heisst: in Ordnung.
    """
    meldungen: List[str] = []

    titel = str(werte.get("title") or "")
    if not titel.strip():
        meldungen.append("Der Titel fehlt.")
    elif len(titel) > config.MAX_TITLE_LENGTH:
        # Vorgang 237503ce. Bis Build 648 stand hier ein stilles
        # 'title[:MAX_TITLE_LENGTH]' - beim Anlegen UND beim Bearbeiten. Wer
        # einen bestehenden Vorgang nur speicherte, um ein anderes Feld zu
        # aendern, verlor dabei das Ende seines Titels.
        meldungen.append(
            f"Der Titel ist {len(titel)} Zeichen lang, erlaubt sind "
            f"{config.MAX_TITLE_LENGTH}. Bitte kürzen - abgeschnitten wird "
            f"nichts mehr."
        )

    # KEINE PFLICHT AUF DIE BESCHREIBUNG - und das ist ein Befund aus dem
    # ersten Lauf: Die erste Fassung verlangte sie, und damit liess sich ein
    # Vorgang des Bestands nicht mehr speichern, der keine hat (64edd18a).
    # Das Schema fuehrt als Pflichtfelder nur id, type, title,
    # affected_version, reporter, reported_at und status. EINE MASKE DARF
    # NICHT STRENGER SEIN ALS DAS SCHEMA - sonst sperrt sie Vorgaenge aus, die
    # regelgerecht im Bestand stehen.

    # Vorgang fd0d5d52: Versionsangaben ohne Musterpruefung. Eine Eingabe wie
    # '0.8' landete im Bestand, und erst die Regression oder
    # 'merge.py --validate-only' fiel darueber - also spaeter und bei jemand
    # anderem.
    for feld, name, pflicht in (("affected_version", "Betroffene Version", True),
                                ("target_version", "Zielversion", False)):
        wert = str(werte.get(feld) or "").strip()
        if not wert:
            if pflicht:
                meldungen.append(f"{name} fehlt.")
            continue
        if not FORMULAR_VERSIONSMUSTER.match(wert):
            meldungen.append(
                f"{name} '{wert}' passt nicht zum Versionsmuster "
                f"(z.B. '0.8.649' oder '0.8.649a')."
            )

    if not str(werte.get("reporter") or "").strip():
        meldungen.append("Der Melder fehlt.")

    # Vorgang ed9205cc: 'except ValueError: pass' - die Eingabe verschwand.
    aufwand = str(werte.get("estimated_hours") or "").strip()
    if aufwand:
        try:
            zahl = float(aufwand.replace(",", "."))
            if zahl < 0:
                meldungen.append("Der geschätzte Aufwand darf nicht negativ sein.")
        except ValueError:
            meldungen.append(
                f"Der geschätzte Aufwand '{aufwand}' ist keine Zahl."
            )

    # Vorgang 04a0a4bc: unbekannte Verweise landeten in einer Protokollzeile
    # und waren danach weg. Seit Build 645 stand wenigstens ein Vermerk im
    # Verlauf - jetzt kommt die Meldung dorthin, wo sie hingehoert: ans
    # Formular, mit stehenbleibender Eingabe.
    unbekannt = [v for v in werte.get("related_to_liste") or []
                 if v not in bekannte_ids and v not in bestehende_verweise]
    if unbekannt:
        meldungen.append(
            "Zu diesen Verweisen gibt es keinen Vorgang: "
            + ", ".join(unbekannt)
            + ". Bitte die volle UUID eintragen oder den Eintrag entfernen."
        )

    return meldungen


def formularwerte(issue: Optional[Dict[str, Any]] = None,
                  roh: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Baut den Satz Werte, aus dem die Maske gefuellt wird.

    EIN Bauplan fuer drei Wege - neues Formular, Bearbeitungsformular und die
    Neuausgabe nach einem Fehler. Ohne das haette die Vorlage drei Fassungen
    von '{{ ... if ... else '' }}' gebraucht, und die dritte haette gefehlt.
    """
    umgebung = (issue or {}).get("environment") or {}
    werte = {
        "issue_id": (issue or {}).get("id", ""),
        # BUILD 650: die Fassungsnummer (Vorgang f0d2894b).
        "stand": vorgangsstand(issue),
        "type": (issue or {}).get("type", "bug"),
        "title": (issue or {}).get("title", ""),
        "affected_version": (issue or {}).get("affected_version", ""),
        "reporter": (issue or {}).get("reporter", "") or config.DEFAULT_REPORTER,
        "priority": (issue or {}).get("priority", "medium"),
        "severity": (issue or {}).get("severity", "minor"),
        "prerequisites": (issue or {}).get("prerequisites", ""),
        "description": (issue or {}).get("description", ""),
        "expected_behavior": (issue or {}).get("expected_behavior", ""),
        "actual_behavior": (issue or {}).get("actual_behavior", ""),
        "assigned_to": (issue or {}).get("assigned_to", ""),
        "target_version": (issue or {}).get("target_version") or "",
        "tags": ", ".join((issue or {}).get("tags") or []),
        "related_to": ", ".join((issue or {}).get("related_to") or []),
        "estimated_hours": (issue or {}).get("estimated_hours", ""),
        "os": umgebung.get("os", ""),
        "browser": umgebung.get("browser", ""),
        "python_version": umgebung.get("python_version", ""),
        "database": umgebung.get("database", ""),
    }
    if roh:
        werte.update({k: v for k, v in roh.items() if v is not None})
    return werte


# ============================================================================
# Routes
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    # -----------------------------------------------------------------------
    # BUILD 649 - MEHRFACHAUSWAHL (Vorgang f42afcd9, mc):
    #   "Es waere toll, wenn man mehrere in den select Tags auswaehlen koennte
    #    (Strg + Klick, Multi-Select) und diese dann als ODER Suche verwendet
    #    werden wuerden."
    #
    # Aus jedem Filter wird damit eine LISTE. 'Query(None)' statt eines
    # einfachen Vorgabewerts ist noetig, weil FastAPI sonst nicht weiss, dass
    # der Parameter mehrfach in der Adresse vorkommen darf
    # ('?status_filter=open&status_filter=review').
    #
    # DIE VERKNUEPFUNG: ODER innerhalb einer Filterart, UND zwischen den
    # Filterarten. 'kritisch oder hoch' UND 'offen' ist die Lesart, die man
    # erwartet - und die einzige, die sich mit Auswahlfeldern ueberhaupt
    # ausdruecken laesst.
    # -----------------------------------------------------------------------
    status_filter: Optional[List[str]] = Query(None),
    type_filter: Optional[List[str]] = Query(None),
    priority_filter: Optional[List[str]] = Query(None),
    assigned_to: Optional[List[str]] = Query(None),
    tag_filter: Optional[List[str]] = Query(None),
    search: Optional[str] = None,
    page: int = 1
):
    """Hauptseite mit Issue-Liste und Filterung"""
    # -----------------------------------------------------------------------
    # BUILD 647 - DER GESAMTBESTAND WIRD FESTGEHALTEN, BEVOR GEFILTERT WIRD.
    #
    # ANLASS: Vorgang 05f65255. Bis Build 646 wurde 'issues' beim Filtern
    # ueberschrieben, und ALLES, was danach kam, beschrieb nur noch die
    # Auswahl: die Kennzahlenleiste und die Liste der Zustaendigen. Wer nach
    # 'status=open' filterte, sah eine Leiste, in der 'offen' gleich 'gesamt'
    # war und alles andere null - die Zahlen sahen aus wie Bestandszahlen und
    # waren Auswahlzahlen.
    #
    # Deshalb: 'alle_issues' bleibt der Bestand, 'issues' ist die Auswahl.
    # -----------------------------------------------------------------------
    alle_issues = issue_manager.load()

    # Leere Eintraege wegwerfen: ein nicht gesetztes Auswahlfeld schickt eine
    # leere Zeichenkette mit, und die duerfte sonst alles wegfiltern.
    status_werte = _saubere_werte(status_filter)
    typ_werte = _saubere_werte(type_filter)
    prio_werte = _saubere_werte(priority_filter)
    zustaendig_werte = _saubere_werte(assigned_to)
    tag_werte = _saubere_werte(tag_filter)

    def _hauptfilter(menge: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Alle Filter AUSSER dem Tag-Filter."""
        if status_werte:
            menge = [i for i in menge if i.get("status") in status_werte]
        if typ_werte:
            menge = [i for i in menge if i.get("type") in typ_werte]
        if prio_werte:
            menge = [i for i in menge if i.get("priority") in prio_werte]
        if zustaendig_werte:
            menge = [i for i in menge if i.get("assigned_to") in zustaendig_werte]
        if search:
            menge = [i for i in menge if _sucht(i, search.lower())]
        return menge

    # Zwischenstand OHNE den Tag-Filter - er wird gleich zweimal gebraucht.
    ohne_tags = _hauptfilter(alle_issues)

    issues = ohne_tags
    if tag_werte:
        # Vergleich ohne Ruecksicht auf Gross- und Kleinschreibung: die Tags
        # sind von Hand gepflegt, und 'Migration' und 'migration' sind
        # dasselbe Thema. ODER-Verknuepfung wie bei den uebrigen Filtern.
        gesucht = {t.strip().lower() for t in tag_werte}
        issues = [i for i in issues
                  if gesucht & {str(t).strip().lower() for t in (i.get("tags") or [])}]

    # Sortierung: neueste zuerst
    issues = sorted(issues, key=lambda x: x.get("reported_at", ""), reverse=True)

    # Paginierung
    total_issues = len(issues)
    total_pages = max(1, (total_issues + config.ITEMS_PER_PAGE - 1) // config.ITEMS_PER_PAGE)
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * config.ITEMS_PER_PAGE
    paged_issues = issues[start_idx:start_idx + config.ITEMS_PER_PAGE]

    # -----------------------------------------------------------------------
    # DIE TAG-WOLKE - BUILD 649, Vorgang 01fedc41 (mc):
    #   "Mit dem Setzen der Hauptfilter sollen auch die Elemente in der
    #    Tag-Cloud aktualisiert (und reduziert) werden."
    #
    # SIE FOLGT DEN HAUPTFILTERN, ABER NICHT SICH SELBST. Gebildet wird sie
    # aus 'ohne_tags' - also aus der Auswahl VOR dem Tag-Filter. Der
    # Unterschied ist der Punkt: Wuerde sie auch dem Tag-Filter folgen,
    # bliebe nach dem ersten Klick nur noch das angeklickte Tag stehen
    # (und die, die zufaellig in denselben Vorgaengen vorkommen) - jeder
    # weitere Weg waere verschwunden. mc hat das in seinem Vorgang ebenfalls
    # so formuliert: die HAUPTFILTER sollen wirken.
    #
    # AUSNAHME: Ein gerade gesetztes Tag bleibt IMMER in der Wolke, auch wenn
    # es dort sonst herausfiele. Sonst koennte man es nicht mehr abwaehlen -
    # eine Bedienung, aus der man nicht herauskommt, ist keine.
    # -----------------------------------------------------------------------
    wolke = issue_manager.get_tag_cloud(ohne_tags)
    vorhanden = {e["tag"].lower() for e in wolke}
    for gesetzt in tag_werte:
        if gesetzt.lower() not in vorhanden:
            wolke.append({"tag": gesetzt, "anzahl": 0, "stufe": 0})
    wolke.sort(key=lambda e: e["tag"].lower())

    stats = issue_manager.get_statistics(alle_issues)

    # Eindeutige Zugewiesene für Filter (Vorgang e2d1f0ae). Aus dem BESTAND,
    # damit die Liste beim Filtern nicht schrumpft - anders als die Wolke, die
    # ausdruecklich schrumpfen SOLL: ein Auswahlfeld, das seine eigene
    # Auswahlmoeglichkeit verliert, waere unbedienbar.
    assignees = sorted({i.get("assigned_to", "") for i in alle_issues if i.get("assigned_to")})

    return templates.TemplateResponse(request, "index.html", {
        "issues": paged_issues,
        "stats": stats,
        "assignees": assignees,
        "status_labels": STATUS_LABELS,
        "type_labels": TYPE_LABELS,
        "priority_labels": PRIORITY_LABELS,
        "tag_cloud": wolke,
        # Ab Build 649 sind das LISTEN. Die Vorlage prueft mit 'in' statt mit
        # '==' - deshalb heissen die Schluessel unveraendert weiter.
        "current_filters": {
            "status": status_werte,
            "type": typ_werte,
            "priority": prio_werte,
            "assigned_to": zustaendig_werte,
            "tag": tag_werte,
            "search": search,
        },
        "pagination": {
            "current_page": page,
            "total_pages": total_pages,
            "total_issues": total_issues,
            "total_bestand": len(alle_issues),
        }
    })


@app.get("/issue/new", response_class=HTMLResponse)
async def new_issue_form(request: Request):
    """Formular für neuen Issue"""
    return templates.TemplateResponse(request, "issue_form.html", {
        # BUILD 649: Die Maske liest nur noch aus 'formular' - ein Bauplan
        # fuer alle drei Wege (neu, bearbeiten, Neuausgabe nach Fehler).
        "formular": formularwerte(),
        "fehler": [],
        "action": "Erstellen",
        "default_reporter": config.DEFAULT_REPORTER,
        "status_labels": STATUS_LABELS
    })


@app.get("/issue/{issue_id}", response_class=HTMLResponse)
async def view_issue(request: Request, issue_id: str):
    """Issue-Detailansicht"""
    issues = issue_manager.load()
    issue = next((i for i in issues if i.get("id") == issue_id), None)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue nicht gefunden")
    
    # Verwandte Issues laden
    related_issues = []
    if issue.get("related_to"):
        related_issues = [i for i in issues if i.get("id") in issue["related_to"]]
    
    # Issues die auf dieses verweisen
    referencing_issues = [i for i in issues if issue_id in i.get("related_to", [])]
    
    # Nächste mögliche Status
    next_statuses = STATUS_FLOW.get(issue.get("status", "open"), [])
    
    return templates.TemplateResponse(request, "issue_detail.html", {
        "issue": issue,
        "related_issues": related_issues,
        "referencing_issues": referencing_issues,
        "next_statuses": next_statuses,
        "status_labels": STATUS_LABELS
    })


@app.get("/issue/{issue_id}/edit", response_class=HTMLResponse)
async def edit_issue_form(request: Request, issue_id: str):
    """Bearbeitungsformular"""
    issues = issue_manager.load()
    issue = next((i for i in issues if i.get("id") == issue_id), None)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue nicht gefunden")
    
    return templates.TemplateResponse(request, "issue_form.html", {
        "formular": formularwerte(issue),
        "fehler": [],
        "action": "Bearbeiten",
        "default_reporter": config.DEFAULT_REPORTER,
        "status_labels": STATUS_LABELS
    })


@app.post("/issue/save")
async def save_issue(
    request: Request,
    issue_id: Optional[str] = Form(None),
    # BUILD 649 (Vorgang a4a3c469): Die Parameter heissen nicht mehr 'type'
    # und 'os'. Beide verdeckten innerhalb dieser Funktion einen Namen, den
    # man dort braucht - 'os' das Modul, 'type' den eingebauten Namen. Das
    # Formularfeld heisst weiterhin so; dafuer ist 'alias' da.
    typ: str = Form(..., alias="type"),
    title: str = Form(...),
    affected_version: str = Form(...),
    reporter: str = Form(...),
    priority: str = Form("medium"),
    severity: str = Form("minor"),
    prerequisites: str = Form(""),
    description: str = Form(...),
    expected_behavior: str = Form(""),
    actual_behavior: str = Form(""),
    assigned_to: str = Form(""),
    target_version: str = Form(""),
    tags: str = Form(""),
    # BUILD 645 - 'None' STATT '""' ALS VORGABE, UND DAS IST DER GANZE PUNKT.
    # Bis Build 644 stand hier 'Form("")'. Damit war 'kein Feld abgeschickt'
    # nicht von 'Feld abgeschickt und leer' zu unterscheiden - und da
    # issue_form.html gar kein Feld 'related_to' fuehrte, loeschte JEDE
    # Bearbeitung ueber die Weboberflaeche SAEMTLICHE Verweise des Vorgangs.
    related_to: Optional[str] = Form(None),
    # BUILD 650 (Vorgang f0d2894b): der Stand, auf dem dieses Formular gebaut
    # wurde. 'None' heisst 'das Formular hat nichts dazu gesagt' - dieselbe
    # Unterscheidung wie bei 'related_to' und aus demselben Grund: ein altes
    # Formular im Browser-Zwischenspeicher darf nicht blockiert werden, es
    # soll nur nicht stillschweigend etwas ueberschreiben.
    stand: Optional[str] = Form(None),
    estimated_hours: str = Form(""),
    os_name: str = Form("", alias="os"),
    browser: str = Form(""),
    python_version: str = Form(""),
    database: str = Form("")
):
    """Issue erstellen oder aktualisieren"""
    issues = issue_manager.load()

    # Tags verarbeiten
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    # -----------------------------------------------------------------------
    # VERWANDTE VORGAENGE - der bisherige Bestand ist der Massstab (Build 645).
    # -----------------------------------------------------------------------
    bestehende_verweise: List[str] = []
    vorgang = None
    if issue_id:
        vorgang = next((i for i in issues if i.get("id") == issue_id), None)
        if vorgang:
            bestehende_verweise = list(vorgang.get("related_to") or [])

    if related_to is None:
        # Das Formular hat zu den Verweisen nichts gesagt. Ein Formular, das
        # ein Feld nicht kennt, ist keine Aussage ueber dieses Feld.
        verweisliste = list(bestehende_verweise)
        if bestehende_verweise:
            logger.info(
                "Kein Feld 'related_to' im Formular - %d bestehende Verweise "
                "unveraendert uebernommen", len(bestehende_verweise))
    else:
        verweisliste = [r.strip() for r in related_to.split(",") if r.strip()]

    # -----------------------------------------------------------------------
    # BUILD 649 - GEPRUEFT WIRD VOR DEM SPEICHERN, NICHT DANACH.
    # -----------------------------------------------------------------------
    eingaben = {
        "issue_id": issue_id or "",
        # Nach einer Abweisung muss der Stand ERHALTEN bleiben, sonst waere
        # der zweite Versuch wieder blind.
        "stand": stand or "",
        "type": typ,
        "title": title,
        "affected_version": affected_version,
        "reporter": reporter,
        "priority": priority,
        "severity": severity,
        "prerequisites": prerequisites,
        "description": description,
        "expected_behavior": expected_behavior,
        "actual_behavior": actual_behavior,
        "assigned_to": assigned_to,
        "target_version": target_version,
        "tags": tags,
        "related_to": ", ".join(verweisliste),
        "related_to_liste": verweisliste,
        "estimated_hours": estimated_hours,
        "os": os_name,
        "browser": browser,
        "python_version": python_version,
        "database": database,
    }

    meldungen = pruefe_formular(eingaben, {i["id"] for i in issues}, bestehende_verweise)
    if issue_id and vorgang is None:
        meldungen.append("Zu dieser Kennung gibt es keinen Vorgang mehr.")

    # -----------------------------------------------------------------------
    # BUILD 650 - DIE VERLORENE AENDERUNG (Vorgang f0d2894b).
    #
    # Zwei offene Browserfenster genuegten bisher: wer zuletzt speicherte,
    # loeschte die Aenderung des anderen - ohne Meldung, ohne Spur im Verlauf.
    # Ab jetzt traegt das Formular verdeckt mit, auf welchem Stand es gebaut
    # wurde; stimmt der nicht mehr, wird abgewiesen.
    #
    # DIE MELDUNG NENNT ROSS UND REITER: wer zuletzt geaendert hat und wann.
    # 'Jemand war schneller' ist keine brauchbare Auskunft - man muss wissen,
    # bei wem man nachfragt.
    # -----------------------------------------------------------------------
    if issue_id and vorgang is not None and stand:
        jetziger = vorgangsstand(vorgang)
        if jetziger != stand:
            letzte = (vorgang.get("updates") or [{}])[-1]
            wer = letzte.get("author") or "unbekannt"
            wann = str(letzte.get("timestamp") or "")[:19].replace("T", " ")
            meldungen.append(
                f"Dieser Vorgang wurde zwischenzeitlich geändert - zuletzt von "
                f"{wer} am {wann}. Deine Eingaben stehen unten unverändert; "
                f"bitte den Vorgang in einem zweiten Fenster ansehen und die "
                f"Änderungen zusammenführen, dann erneut speichern."
            )
            logger.warning("Fassungskonflikt bei %s: Formular %s, Bestand %s",
                           issue_id, stand, jetziger)
    elif issue_id and vorgang is not None and stand is None:
        # Ein Formular ohne das Feld - etwa aus dem Zwischenspeicher des
        # Browsers. Nicht blockieren, aber vermerken: sonst waere die Sperre
        # unbemerkt wirkungslos.
        logger.info("Formular ohne Fassungsnummer gespeichert (%s)", issue_id)

    if meldungen:
        # DIE EINGABE BLEIBT STEHEN. Das ist der Unterschied zu allem, was
        # vorher da war: bis Build 648 wurde zurechtgebogen oder verworfen,
        # weil es keinen Weg zurueck gab. Statuscode 400, damit auch ein
        # Skript merkt, dass nichts gespeichert wurde.
        logger.info("Formular abgewiesen (%d Meldungen): %s",
                    len(meldungen), "; ".join(meldungen))
        return templates.TemplateResponse(
            request,
            "issue_form.html",
            {
                "formular": formularwerte(roh=eingaben),
                "fehler": meldungen,
                "action": "Bearbeiten" if issue_id else "Erstellen",
                "default_reporter": config.DEFAULT_REPORTER,
                "status_labels": STATUS_LABELS,
            },
            status_code=400,
        )

    # Umgebungsinformationen
    environment = {}
    env_fields = {"os": os_name, "browser": browser,
                  "python_version": python_version, "database": database}
    for key, value in env_fields.items():
        if value:
            environment[key] = value

    aufwand = None
    if str(estimated_hours).strip():
        aufwand = float(str(estimated_hours).strip().replace(",", "."))

    if issue_id:  # Update existierender Issue
        issue = vorgang

        # -------------------------------------------------------------------
        # BUILD 649 - DER AENDERUNGSVERMERK NENNT JETZT DIE FELDER
        # (Vorgang b2175ac7).
        #
        # Bis Build 648 stand hier
        #     if issue.get("status") != issue.get("status"):
        # - ein Vergleich desselben Werts mit sich selbst, also nie wahr. Die
        # Liste blieb leer, und der Vermerk lautete immer nur 'Issue
        # aktualisiert'. Die Zeitleiste war fuer Bearbeitungen ueber die
        # Maske damit ohne Aussagewert.
        #
        # GEMESSEN WIRD VOR DEM SCHREIBEN - sonst vergleicht man wieder den
        # neuen Stand mit sich selbst. Genau daran ist die alte Zeile
        # gescheitert.
        # -------------------------------------------------------------------
        neue_werte = {
            "type": typ,
            "title": title,
            "affected_version": affected_version,
            "priority": priority,
            "severity": severity,
            "prerequisites": prerequisites,
            "description": description,
            "expected_behavior": expected_behavior,
            "actual_behavior": actual_behavior,
            "assigned_to": assigned_to,
            "target_version": target_version if target_version else None,
            "tags": tag_list,
            "related_to": verweisliste,
            "environment": environment,
        }
        BENENNUNG = {
            "type": "Typ", "title": "Titel", "affected_version": "Betroffene Version",
            "priority": "Priorität", "severity": "Schweregrad",
            "prerequisites": "Voraussetzungen", "description": "Beschreibung",
            "expected_behavior": "Erwartetes Verhalten",
            "actual_behavior": "Tatsächliches Verhalten",
            "assigned_to": "Zuständig", "target_version": "Zielversion",
            "tags": "Tags", "related_to": "Verweise", "environment": "Umgebung",
        }

        def _kurz(wert):
            """Lange Texte werden benannt, nicht abgedruckt."""
            if isinstance(wert, (list, dict)):
                return f"{len(wert)} Einträge" if wert else "leer"
            text = str(wert or "")
            if not text:
                return "leer"
            return text if len(text) <= 60 else text[:57] + "…"

        def _gleich(links, rechts) -> bool:
            """
            Vergleich, der 'nicht vorhanden' und 'leer' als dasselbe ansieht.

            BEFUND AUS DEM ERSTEN LAUF: Nicht jeder Vorgang fuehrt jedes Feld.
            Wird ein solcher Vorgang ueber die Maske gespeichert, kommt aus
            dem Formular eine leere Zeichenkette, und ein blosser Vergleich
            meldete 'Beschreibung geaendert' - obwohl sich nichts geaendert
            hat, was jemand als Aenderung erkennen wuerde. Ein Vermerk, der
            Aenderungen erfindet, ist so wenig wert wie einer, der keine
            nennt.
            """
            if links in (None, "", [], {}) and rechts in (None, "", [], {}):
                return True
            return links == rechts

        changes = []
        for feld, neuer_wert in neue_werte.items():
            alter_wert = issue.get(feld)
            if _gleich(alter_wert, neuer_wert):
                continue
            if feld in ("description", "expected_behavior", "actual_behavior",
                        "prerequisites"):
                # Bei Fliesstext nur die Tatsache vermerken - der ganze Text
                # stuende sonst zweimal in der Datei.
                changes.append(f"{BENENNUNG[feld]} geändert")
            else:
                changes.append(f"{BENENNUNG[feld]}: {_kurz(alter_wert)} → {_kurz(neuer_wert)}")

        # Der Aufwand steht nicht in 'neue_werte', weil er nur gesetzt wird,
        # wenn eine Zahl kam - im Vergleich muss er trotzdem auftauchen.
        if aufwand is not None and issue.get("estimated_hours") != aufwand:
            changes.append(
                f"{'Aufwand'}: {_kurz(issue.get('estimated_hours'))} → {_kurz(aufwand)}")

        issue.update(neue_werte)
        if aufwand is not None:
            issue["estimated_hours"] = aufwand

        if "updates" not in issue:
            issue["updates"] = []

        issue["updates"].append(create_update_entry(
            author=reporter,
            action="comment",
            comment=("Issue aktualisiert: " + ", ".join(changes)) if changes
                    else "Issue gespeichert, keine Änderung"
        ))

        logger.info(f"Issue {issue_id} aktualisiert: {len(changes)} Feld(er)")

    else:  # Neu erstellen
        now = datetime.now(timezone.utc).isoformat()
        new_issue = {
            "id": str(uuid.uuid4()),
            "type": typ,
            "title": title,
            "affected_version": affected_version,
            "reporter": reporter,
            "reported_at": now,
            "prerequisites": prerequisites,
            "description": description,
            "expected_behavior": expected_behavior,
            "actual_behavior": actual_behavior,
            "status": "open",
            "priority": priority,
            "severity": severity,
            "assigned_to": assigned_to,
            "related_to": verweisliste,
            "resolved_in_version": None,
            "target_version": target_version if target_version else None,
            "environment": environment,
            "tags": tag_list,
            "attachments": [],
            "updates": [create_update_entry(
                author=reporter,
                action="comment",
                comment="Issue erstellt"
            )]
        }
        if aufwand is not None:
            new_issue["estimated_hours"] = aufwand

        issues.append(new_issue)
        logger.info(f"Neuer Issue erstellt: {new_issue['id']}")

    if issue_manager.save(issues):
        return RedirectResponse(url="/", status_code=303)
    else:
        raise HTTPException(status_code=500, detail="Fehler beim Speichern")


@app.post("/issue/{issue_id}/status")
async def update_status(
    issue_id: str,
    new_status: str = Form(...),
    author: str = Form(...),
    comment: str = Form(""),
    resolved_version: Optional[str] = Form(None)
):
    """Status aktualisieren"""
    issues = issue_manager.load()
    issue = next((i for i in issues if i.get("id") == issue_id), None)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue nicht gefunden")
    
    # Prüfen ob Status-Wechsel erlaubt ist
    allowed_statuses = STATUS_FLOW.get(issue["status"], [])
    if new_status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Status-Wechsel von {issue['status']} zu {new_status} nicht erlaubt"
        )
    
    old_status = issue["status"]
    issue["status"] = new_status
    
    if new_status in ["resolved", "closed"] and resolved_version:
        issue["resolved_in_version"] = resolved_version
    
    if "updates" not in issue:
        issue["updates"] = []
    
    issue["updates"].append(create_update_entry(
        author=author,
        action="status_change",
        old_value=old_status,
        new_value=new_status,
        comment=comment
    ))
    
    if issue_manager.save(issues):
        logger.info(f"Status von Issue {issue_id}: {old_status} → {new_status}")
        return RedirectResponse(url=f"/issue/{issue_id}", status_code=303)
    else:
        raise HTTPException(status_code=500, detail="Fehler beim Speichern")


@app.post("/issue/{issue_id}/comment")
async def add_comment(
    issue_id: str,
    author: str = Form(...),
    comment: str = Form(...)
):
    """Kommentar hinzufügen"""
    issues = issue_manager.load()
    issue = next((i for i in issues if i.get("id") == issue_id), None)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue nicht gefunden")
    
    if "updates" not in issue:
        issue["updates"] = []
    
    issue["updates"].append(create_update_entry(
        author=author,
        action="comment",
        comment=comment
    ))
    
    if issue_manager.save(issues):
        logger.info(f"Kommentar zu Issue {issue_id} hinzugefügt")
        return RedirectResponse(url=f"/issue/{issue_id}", status_code=303)
    else:
        raise HTTPException(status_code=500, detail="Fehler beim Speichern")


@app.get("/api/issues")
async def api_get_issues():
    """REST API: Alle Issues"""
    return issue_manager.load()


@app.get("/api/issue/{issue_id}")
async def api_get_issue(issue_id: str):
    """REST API: Einzelner Issue"""
    issues = issue_manager.load()
    issue = next((i for i in issues if i.get("id") == issue_id), None)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue nicht gefunden")
    return issue


@app.get("/api/statistics")
async def api_get_statistics():
    """REST API: Statistiken"""
    issues = issue_manager.load()
    return issue_manager.get_statistics(issues)


@app.get("/health")
async def health_check():
    """Health Check Endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "2.0.0",
        "data_file_exists": config.ISSUES_FILE.exists()
    }


# ============================================================================
# Main - Wichtig: Dieser Block behebt den Uvicorn-Fehler!
# ============================================================================

#: Der Modulname, unter dem uvicorn diese Datei nachladen kann.
#:
#: BUILD 651 - BEFUND AUS DEM BETRIEB (mc, 2026-08-02):
#:   ERROR: Error loading ASGI app. Could not import module "server".
#:
#: WAS PASSIERT IST: Build 650 hat die Datei von 'server.py' in
#: 'tracker_server.py' umbenannt (Vorgang 7c7a738f). Ich habe run.py, die
#: readme und vier Testdateien nachgezogen - und die Stelle IM INNEREN
#: DIESER DATEI uebersehen. Dort stand der Modulname als Zeichenkette
#: ("server:app"), und eine Zeichenkette benennt kein Werkzeug um.
#:
#: WARUM ES IM CONTAINER NICHT AUFFIEL: Der Zweig wird nur bei RELOAD=true
#: durchlaufen; ohne Reload bekommt uvicorn das App-OBJEKT und braucht den
#: Namen gar nicht. Meine Startprobe lief ohne .env, also ohne Reload - sie
#: hat den einen Weg geprueft, den es nicht getroffen hat. In der VM steht
#: RELOAD=true (run.py schreibt das so in die .env).
#:
#: DIE LEHRE, UND SIE IST NICHT NEU: Ein Name, der als Zeichenkette
#: dasteht, wandert bei keiner Umbenennung mit. Deshalb steht er hier nicht
#: mehr als Zeichenkette, sondern wird aus dem DATEINAMEN gebildet. Wer die
#: Datei kuenftig umbenennt, benennt diesen Wert mit um, ohne es zu merken -
#: und das ist genau der Zweck.
MODULNAME = Path(__file__).stem


def start():
    """Startet den Uvicorn-Server"""
    import uvicorn

    # Wichtig: Wenn RELOAD=True, muss die App als String übergeben werden
    if config.RELOAD:
        # Bei Reload muss uvicorn mit dem Modul-String gestartet werden
        uvicorn.run(
            f"{MODULNAME}:app",  # aus dem Dateinamen, nicht von Hand
            host=config.HOST,
            port=config.PORT,
            reload=True,
            log_level="debug" if config.DEBUG else "info"
        )
    else:
        # Ohne Reload kann das App-Objekt direkt übergeben werden
        uvicorn.run(
            app,
            host=config.HOST,
            port=config.PORT,
            reload=False,
            log_level="debug" if config.DEBUG else "info"
        )


if __name__ == "__main__":
    start()
