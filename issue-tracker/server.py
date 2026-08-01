#!/usr/bin/env python3
"""
Issue Tracker - Einfacher Bug- und Feature-Request-Tracker
Git-integrierbar mit JSON-Speicher und Web-Interface
"""

import json
import uuid
import logging
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ---------------------------------------------------------------------------
# Eigene Bausteine (Build 642).
#
# Beide liegen im selben Verzeichnis wie diese Datei; Python nimmt das
# Skriptverzeichnis von sich aus in sys.path auf, sowohl bei 'python server.py'
# als auch bei 'uvicorn server:app' aus diesem Verzeichnis.
#
# WARUM AUSGELAGERT: Ein Baustein, der 'fastapi' voraussetzt, ist in der
# Regression nicht pruefbar - das Paket ist keine Abhaengigkeit der Testumgebung
# (vgl. die Begruendung in tests/test_issue_tracker_schema.py zu 'jsonschema').
# Der Schreibweg und die Namensregel der Sicherungen sind aber genau das, was
# geprueft werden MUSS. Also stehen sie in eigenen Dateien - das entspricht
# zugleich Grundregel 10.
# ---------------------------------------------------------------------------
from json_safe_writer import JsonSafeWriter
from backup_names import (
    SERVER_MUSTER,
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
    BACKUP_INTERVAL_HOURS: int = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))
    
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

app = FastAPI(
    title=config.TITLE,
    version="2.0.0",
    description="Lokaler Issue Tracker für die Softwareentwicklung"
)

# Templates konfigurieren
templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))

# Globale Template-Variablen
templates.env.globals["config"] = config

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
    
    def _create_backup(self):
        """Erstellt ein Backup der aktuellen Issue-Datei"""
        if not self.file_path.exists():
            return
        
        # Prüfen ob Backup nötig ist
        now = datetime.now()
        if self.last_backup and (now - self.last_backup) < timedelta(hours=config.BACKUP_INTERVAL_HOURS):
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
            if len(eigene) > 10:
                for old_backup in eigene[:-10]:
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
# Routes
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    status_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
    priority_filter: Optional[str] = None,
    search: Optional[str] = None,
    assigned_to: Optional[str] = None,
    page: int = 1
):
    """Hauptseite mit Issue-Liste und Filterung"""
    issues = issue_manager.load()
    
    # Filter anwenden
    if status_filter:
        issues = [i for i in issues if i.get("status") == status_filter]
    if type_filter:
        issues = [i for i in issues if i.get("type") == type_filter]
    if priority_filter:
        issues = [i for i in issues if i.get("priority") == priority_filter]
    if assigned_to:
        issues = [i for i in issues if i.get("assigned_to") == assigned_to]
    if search:
        search_lower = search.lower()
        issues = [i for i in issues if 
                 search_lower in i.get("title", "").lower() or 
                 search_lower in i.get("description", "").lower() or
                 search_lower in i.get("id", "").lower()]
    
    # Sortierung: neueste zuerst
    issues.sort(key=lambda x: x.get("reported_at", ""), reverse=True)
    
    # Paginierung
    total_issues = len(issues)
    total_pages = max(1, (total_issues + config.ITEMS_PER_PAGE - 1) // config.ITEMS_PER_PAGE)
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * config.ITEMS_PER_PAGE
    end_idx = start_idx + config.ITEMS_PER_PAGE
    paged_issues = issues[start_idx:end_idx]
    
    # Statistiken
    stats = issue_manager.get_statistics(issues)
    
    # Eindeutige Zugewiesene für Filter
    assignees = list(set(i.get("assigned_to", "") for i in issues if i.get("assigned_to")))
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "issues": paged_issues,
        "stats": stats,
        "assignees": assignees,
        "current_filters": {
            "status": status_filter,
            "type": type_filter,
            "priority": priority_filter,
            "search": search,
            "assigned_to": assigned_to
        },
        "pagination": {
            "current_page": page,
            "total_pages": total_pages,
            "total_issues": total_issues
        }
    })


@app.get("/issue/new", response_class=HTMLResponse)
async def new_issue_form(request: Request):
    """Formular für neuen Issue"""
    return templates.TemplateResponse("issue_form.html", {
        "request": request,
        "issue": None,
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
    
    return templates.TemplateResponse("issue_detail.html", {
        "request": request,
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
    
    return templates.TemplateResponse("issue_form.html", {
        "request": request,
        "issue": issue,
        "action": "Bearbeiten",
        "default_reporter": config.DEFAULT_REPORTER,
        "status_labels": STATUS_LABELS
    })


@app.post("/issue/save")
async def save_issue(
    request: Request,
    issue_id: Optional[str] = Form(None),
    type: str = Form(...),
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
    #
    # Bis Build 644 stand hier 'Form("")'. Damit war 'kein Feld abgeschickt'
    # nicht von 'Feld abgeschickt und leer' zu unterscheiden - beides kam als
    # "" an. Da issue_form.html gar kein Feld 'related_to' fuehrte, hiess das:
    # JEDE Bearbeitung ueber die Weboberflaeche loeschte SAEMTLICHE Verweise
    # des Vorgangs. Gemessen an f51fd838: ['906ede75','e9522fe2','c3f80e54']
    # -> [] nach einem einzigen Speichern, ohne Meldung und ohne Eintrag im
    # Verlauf.
    #
    # Mit 'Form(None)' sind die beiden Faelle unterscheidbar:
    #   None -> das Formular hat nichts dazu gesagt  -> Bestand behalten
    #   ""   -> jemand hat das Feld ausdruecklich geleert -> leeren
    related_to: Optional[str] = Form(None),
    estimated_hours: str = Form(""),
    os: str = Form(""),
    browser: str = Form(""),
    python_version: str = Form(""),
    database: str = Form("")
):
    """Issue erstellen oder aktualisieren"""
    issues = issue_manager.load()
    
    # Tags verarbeiten
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    
    # -----------------------------------------------------------------------
    # VERWANDTE VORGAENGE - BUILD 645 VOLLSTAENDIG UMGEBAUT.
    #
    # Der bisherige Bestand des Vorgangs ist der Massstab. Er wird zuerst
    # ermittelt, denn er entscheidet zwei Dinge:
    #   (1) was gilt, wenn das Formular nichts geschickt hat, und
    #   (2) was NICHT verworfen werden darf, auch wenn es die Pruefung nicht
    #       besteht.
    #
    # ZU (2), UND DAS IST DIE ZWEITE HAELFTE DES FEHLERS: Die alte Pruefung
    # liess nur durch, was als volle ID im Bestand vorkommt. Fuer die fuenf
    # Verweise, die als 8-Zeichen-Kurzform in der Datei stehen (Vorgang
    # 6da63d8b), heisst das: selbst MIT verstecktem Feld waeren sie beim
    # Speichern herausgefiltert worden - die Reparatur haette den Fehler nur
    # verschoben. Was bereits gespeichert IST, wird deshalb durchgelassen.
    # Die Oberflaeche ist nicht der Ort, an dem Altlasten stillschweigend
    # verschwinden; dafuer gibt es repair_related_ids.py, das ansagt, was es
    # tut.
    # -----------------------------------------------------------------------
    bestehende_verweise: List[str] = []
    verworfene_verweise: List[str] = []
    if issue_id:
        _vorgang = next((i for i in issues if i.get("id") == issue_id), None)
        if _vorgang:
            bestehende_verweise = list(_vorgang.get("related_to") or [])

    if related_to is None:
        # Das Formular hat zu den Verweisen nichts gesagt. Ein Formular, das
        # ein Feld nicht kennt, ist keine Aussage ueber dieses Feld.
        valid_relations = bestehende_verweise
        if bestehende_verweise:
            logger.info(
                "Kein Feld 'related_to' im Formular - %d bestehende Verweise "
                "unveraendert uebernommen", len(bestehende_verweise)
            )
    else:
        related_list = [r.strip() for r in related_to.split(",") if r.strip()]
        valid_relations = []
        existing_ids = {i["id"] for i in issues}
        for rel_id in related_list:
            if rel_id in existing_ids or rel_id in bestehende_verweise:
                valid_relations.append(rel_id)
            else:
                verworfene_verweise.append(rel_id)
                logger.warning(f"Verwandte Issue-ID nicht gefunden: {rel_id}")


    # Umgebungsinformationen
    environment = {}
    env_fields = {"os": os, "browser": browser, "python_version": python_version, "database": database}
    for key, value in env_fields.items():
        if value:
            environment[key] = value
    
    if issue_id:  # Update existierender Issue
        issue = next((i for i in issues if i.get("id") == issue_id), None)
        if not issue:
            raise HTTPException(status_code=404, detail="Issue nicht gefunden")
        
        # Änderungen tracken
        changes = []
        if issue.get("status") != issue.get("status"):
            changes.append(f"Status: {issue.get('status')} → {issue.get('status')}")
        
        # Update durchführen
        issue.update({
            "type": type,
            "title": title[:config.MAX_TITLE_LENGTH],
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
            "related_to": valid_relations,
            "environment": environment
        })
        
        if estimated_hours:
            try:
                issue["estimated_hours"] = float(estimated_hours)
            except ValueError:
                pass
        
        # Update-Historie
        if "updates" not in issue:
            issue["updates"] = []
        
        issue["updates"].append(create_update_entry(
            author=reporter,
            action="comment",
            comment="Issue aktualisiert" + (f": {', '.join(changes)}" if changes else "")
        ))

        # BUILD 645: Was die Oberflaeche nicht uebernehmen konnte, steht ab
        # jetzt IM VORGANG und nicht nur im Protokoll des Servers. Ein
        # Protokolleintrag ist kein Beleg fuer den, der spaeter die Akte liest.
        if verworfene_verweise:
            issue["updates"].append(create_update_entry(
                author=reporter,
                action="comment",
                comment=(
                    "HINWEIS: Diese Verweise wurden beim Speichern nicht "
                    "uebernommen, weil zu ihnen kein Vorgang gefunden wurde: "
                    + ", ".join(verworfene_verweise)
                )
            ))

        logger.info(f"Issue {issue_id} aktualisiert")
        
    else:  # Neu erstellen
        now = datetime.now(timezone.utc).isoformat()
        new_issue = {
            "id": str(uuid.uuid4()),
            "type": type,
            "title": title[:config.MAX_TITLE_LENGTH],
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
            "related_to": valid_relations,
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
        
        if estimated_hours:
            try:
                new_issue["estimated_hours"] = float(estimated_hours)
            except ValueError:
                pass
        
        # BUILD 645: derselbe Vermerk wie beim Bearbeiten - siehe dort.
        if verworfene_verweise:
            new_issue["updates"].append(create_update_entry(
                author=reporter,
                action="comment",
                comment=(
                    "HINWEIS: Diese Verweise wurden beim Anlegen nicht "
                    "uebernommen, weil zu ihnen kein Vorgang gefunden wurde: "
                    + ", ".join(verworfene_verweise)
                )
            ))

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
# Startup Event
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Wird beim Start ausgeführt"""
    logger.info("=" * 60)
    logger.info(f"{config.TITLE} wird gestartet")
    logger.info(f"Host: {config.HOST}:{config.PORT}")
    logger.info(f"Daten-Verzeichnis: {config.DATA_DIR.absolute()}")
    logger.info(f"Issue-Datei: {config.ISSUES_FILE.absolute()}")
    logger.info(f"Backup-Verzeichnis: {config.BACKUP_DIR.absolute()}")
    logger.info(f"Debug-Modus: {config.DEBUG}")
    logger.info(f"Auto-Backup: {config.AUTO_BACKUP}")
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Wird beim Beenden ausgeführt"""
    logger.info("Server wird heruntergefahren")


# ============================================================================
# Main - Wichtig: Dieser Block behebt den Uvicorn-Fehler!
# ============================================================================

def start():
    """Startet den Uvicorn-Server"""
    import uvicorn
    
    # Wichtig: Wenn RELOAD=True, muss die App als String übergeben werden
    if config.RELOAD:
        # Bei Reload muss uvicorn mit dem Modul-String gestartet werden
        uvicorn.run(
            "server:app",  # Modul-String statt App-Objekt
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
