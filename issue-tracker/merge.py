#!/usr/bin/env python3
"""
Issue Tracker Merge Tool - CLI zum Zusammenführen von Issue-Dateien

Verwendung:
    python merge.py import_datei.json
    python merge.py import_datei.json --dry-run
    python merge.py import_datei.json --auto-resolve newer
    python merge.py import_datei.json --output merged.json

Funktionen:
    - Importiert Issues aus externen JSON-Dateien
    - Erkennt Duplikate anhand der UUID
    - Erkennt Konflikte bei gleicher UUID aber unterschiedlichen Daten
    - Interaktive oder automatische Konfliktlösung
    - Dry-Run Modus zur Vorschau
    - Backup der Original-Datei vor dem Merge
"""

import json
import os
import sys
import uuid
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import argparse
from difflib import unified_diff
import textwrap


# ============================================================================
# Konfiguration und Datenstrukturen
# ============================================================================

class ConflictType(Enum):
    """Arten von Konflikten"""
    DUPLICATE_ID = "duplicate_id"           # Gleiche UUID, existiert bereits
    DATA_DIVERGENCE = "data_divergence"      # Gleiche UUID, unterschiedliche Daten
    STATUS_CONFLICT = "status_conflict"      # Unterschiedlicher Status
    FIELD_CONFLICT = "field_conflict"        # Unterschiedliche Feldwerte
    UPDATE_TIMELINE = "update_timeline"      # Unterschiedliche Update-Verläufe
    NEWER_EXISTS = "newer_exists"            # Ziel ist neuer als Quelle
    MISSING_FIELDS = "missing_fields"        # Pflichtfelder fehlen


class ResolutionStrategy(Enum):
    """Strategien zur Konfliktlösung"""
    KEEP_TARGET = "keep_target"          # Bestehende Version behalten
    KEEP_SOURCE = "keep_source"          # Neue Version übernehmen
    MERGE_UPDATES = "merge_updates"      # Updates zusammenführen
    NEWER_WINS = "newer_wins"           # Neueste Änderung gewinnt
    MANUAL = "manual"                   # Manuell entscheiden
    SKIP = "skip"                       # Überspringen


@dataclass
class Conflict:
    """Repräsentiert einen Merge-Konflikt"""
    issue_id: str
    type: ConflictType
    description: str
    target_data: Dict[str, Any]
    source_data: Dict[str, Any]
    conflicting_fields: List[str] = field(default_factory=list)
    resolution: Optional[ResolutionStrategy] = None


@dataclass
class MergeResult:
    """Ergebnis des Merge-Vorgangs"""
    total_imported: int = 0
    new_issues: int = 0
    updated_issues: int = 0
    skipped_issues: int = 0
    conflicts: List[Conflict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ============================================================================
# Issue Validator
# ============================================================================

class IssueValidator:
    """Validiert Issues gegen das Schema"""
    
    REQUIRED_FIELDS = ["id", "title", "type", "affected_version", "reporter", "reported_at", "status"]
    
    VALID_TYPES = ["bug", "feature_request", "improvement", "documentation", "refactoring"]
    VALID_STATUSES = ["open", "in_progress", "review", "testing", "resolved", "closed", 
                      "wont_fix", "duplicate", "cannot_reproduce"]
    VALID_PRIORITIES = ["critical", "high", "medium", "low", "wishlist"]
    VALID_SEVERITIES = ["blocker", "critical", "major", "minor", "trivial", "enhancement"]
    
    @classmethod
    def validate(cls, issue: Dict[str, Any]) -> List[str]:
        """Validiert einen Issue und gibt Liste von Fehlern zurück"""
        errors = []
        
        # Pflichtfelder prüfen
        for field in cls.REQUIRED_FIELDS:
            if field not in issue:
                errors.append(f"Pflichtfeld fehlt: {field}")
        
        # UUID-Format prüfen
        if "id" in issue:
            try:
                uuid.UUID(issue["id"])
            except (ValueError, AttributeError):
                errors.append(f"Ungültige UUID: {issue.get('id')}")
        
        # Titel-Länge
        if "title" in issue and len(issue.get("title", "")) > 80:
            errors.append(f"Titel zu lang ({len(issue['title'])} Zeichen, max. 80)")
        
        # Enum-Werte prüfen
        if issue.get("type") not in cls.VALID_TYPES:
            errors.append(f"Ungültiger Typ: {issue.get('type')}")
        
        if issue.get("status") not in cls.VALID_STATUSES:
            errors.append(f"Ungültiger Status: {issue.get('status')}")
        
        if issue.get("priority") and issue["priority"] not in cls.VALID_PRIORITIES:
            errors.append(f"Ungültige Priorität: {issue.get('priority')}")
        
        if issue.get("severity") and issue["severity"] not in cls.VALID_SEVERITIES:
            errors.append(f"Ungültiger Schweregrad: {issue.get('severity')}")
        
        # Datetime-Format prüfen
        for date_field in ["reported_at"]:
            if date_field in issue:
                try:
                    datetime.fromisoformat(issue[date_field].replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    errors.append(f"Ungültiges Datumsformat in {date_field}: {issue.get(date_field)}")
        
        return errors


# ============================================================================
# Diff-Generator
# ============================================================================

class IssueDiffer:
    """Erstellt menschenlesbare Diffs zwischen Issues"""
    
    @staticmethod
    def compare(target: Dict[str, Any], source: Dict[str, Any]) -> str:
        """Vergleicht zwei Issues und gibt formatierten Diff zurück"""
        diff_lines = []
        all_keys = set(list(target.keys()) + list(source.keys()))
        
        for key in sorted(all_keys):
            if key in ["updates", "id"]:  # Updates separat behandeln
                continue
                
            target_val = target.get(key)
            source_val = source.get(key)
            
            if target_val != source_val:
                diff_lines.append(f"\n  📌 Feld: {key}")
                
                if isinstance(target_val, dict) and isinstance(source_val, dict):
                    # Nested diff für Objekte
                    sub_keys = set(list(target_val.keys()) + list(source_val.keys()))
                    for sub_key in sorted(sub_keys):
                        t_sub = target_val.get(sub_key)
                        s_sub = source_val.get(sub_key)
                        if t_sub != s_sub:
                            diff_lines.append(f"    - {sub_key}: {t_sub}")
                            diff_lines.append(f"    + {sub_key}: {s_sub}")
                elif isinstance(target_val, list) and isinstance(source_val, list):
                    diff_lines.append(f"    - Liste mit {len(target_val)} Einträgen")
                    diff_lines.append(f"    + Liste mit {len(source_val)} Einträgen")
                else:
                    diff_lines.append(f"    - ALT: {target_val}")
                    diff_lines.append(f"    + NEU: {source_val}")
        
        # Updates vergleichen
        if "updates" in target or "updates" in source:
            target_updates = target.get("updates", [])
            source_updates = source.get("updates", [])
            
            if len(target_updates) != len(source_updates):
                diff_lines.append(f"\n  📌 Updates: {len(target_updates)} → {len(source_updates)} Einträge")
                
                # Neue Updates anzeigen
                if len(source_updates) > len(target_updates):
                    new_updates = source_updates[len(target_updates):]
                    diff_lines.append(f"    + {len(new_updates)} neue Updates:")
                    for update in new_updates[:5]:  # Max 5 anzeigen
                        diff_lines.append(f"      {update.get('timestamp', '?')[:19]} - "
                                        f"{update.get('author', '?')}: "
                                        f"{update.get('comment', update.get('action', '?'))[:50]}")
        
        return "\n".join(diff_lines) if diff_lines else "Keine Unterschiede gefunden"


# ============================================================================
# Merge Engine
# ============================================================================

class IssueMergeEngine:
    """Haupt-Engine für das Mergen von Issues"""
    
    def __init__(self, target_file: Path, auto_resolve: Optional[str] = None, 
                 dry_run: bool = False, verbose: bool = False, 
                 force: bool = False, no_backup: bool = False):
        self.target_file = target_file
        self.auto_resolve = auto_resolve
        self.dry_run = dry_run
        self.verbose = verbose
        self.force = force
        self.no_backup = no_backup
        self.result = MergeResult()
        self.differ = IssueDiffer()
    
    def load_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Lädt Issues aus einer JSON-Datei"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "issues" in data:
                return data["issues"]
            else:
                raise ValueError(f"Unerwartetes JSON-Format in {file_path}")
        except FileNotFoundError:
            print(f"❌ Datei nicht gefunden: {file_path}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"❌ Ungültiges JSON in {file_path}: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Fehler beim Laden von {file_path}: {e}")
            sys.exit(1)
    
    def save_file(self, file_path: Path, issues: List[Dict[str, Any]]):
        """Speichert Issues in JSON-Datei"""
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump({"issues": issues}, f, indent=2, ensure_ascii=False)
    
    def create_backup(self):
        """Erstellt ein Backup der Target-Datei"""
        if self.no_backup:
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        BACKUP_DIR: Path = Path(os.getenv("BACKUP_DIR", "./backups"))
        backup_path = BACKUP_DIR / f"issues_backup_before_merge_{timestamp}.json"
        
        try:
            shutil.copy2(self.target_file, backup_path)
            print(f"💾 Backup erstellt: {backup_path.name}")
        except Exception as e:
            print(f"⚠️  Backup konnte nicht erstellt werden: {e}")
            if not self.force:
                if input("Ohne Backup fortfahren? (j/N): ").lower() != 'j':
                    sys.exit(1)
    
    def detect_conflicts(self, target_issues: List[Dict], 
                         source_issues: List[Dict]) -> List[Conflict]:
        """Erkennt Konflikte zwischen Target und Source"""
        conflicts = []
        target_map = {i["id"]: i for i in target_issues}
        
        for source_issue in source_issues:
            issue_id = source_issue.get("id")
            if not issue_id:
                self.result.errors.append("Issue ohne ID gefunden, wird übersprungen")
                continue
            
            # Ist es ein neuer Issue?
            if issue_id not in target_map:
                continue
            
            target_issue = target_map[issue_id]
            conflicting_fields = []
            
            # Felder vergleichen (außer updates)
            comparable_fields = ["title", "description", "status", "priority", "severity",
                               "assigned_to", "target_version", "affected_version"]
            
            for field in comparable_fields:
                if target_issue.get(field) != source_issue.get(field):
                    conflicting_fields.append(field)
            
            if conflicting_fields:
                # Zeitstempel vergleichen
                target_time = datetime.fromisoformat(
                    target_issue.get("reported_at", "2000-01-01T00:00:00").replace("Z", "+00:00")
                )
                source_time = datetime.fromisoformat(
                    source_issue.get("reported_at", "2000-01-01T00:00:00").replace("Z", "+00:00")
                )
                
                # Letztes Update-Datum finden
                target_last_update = self._get_last_update_time(target_issue)
                source_last_update = self._get_last_update_time(source_issue)
                
                conflict_type = ConflictType.DATA_DIVERGENCE
                description = f"Issue {issue_id[:8]}... hat abweichende Daten"
                
                if "status" in conflicting_fields:
                    conflict_type = ConflictType.STATUS_CONFLICT
                    description = (f"Status-Konflikt: '{target_issue.get('status')}' vs "
                                 f"'{source_issue.get('status')}'")
                
                if source_last_update > target_last_update:
                    description += " (Quelle ist neuer)"
                elif target_last_update > source_last_update:
                    description += " (Ziel ist neuer)"
                
                conflicts.append(Conflict(
                    issue_id=issue_id,
                    type=conflict_type,
                    description=description,
                    target_data=target_issue,
                    source_data=source_issue,
                    conflicting_fields=conflicting_fields
                ))
        
        return conflicts
    
    def _get_last_update_time(self, issue: Dict) -> datetime:
        """Ermittelt den Zeitpunkt der letzten Aktualisierung"""
        updates = issue.get("updates", [])
        if updates:
            try:
                return datetime.fromisoformat(updates[-1]["timestamp"].replace("Z", "+00:00"))
            except (KeyError, ValueError):
                pass
        
        try:
            return datetime.fromisoformat(issue.get("reported_at", "").replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return datetime.min.replace(tzinfo=timezone.utc)
    
    def resolve_conflict_interactively(self, conflict: Conflict) -> ResolutionStrategy:
        """Interaktive Konfliktlösung"""
        issue_id = conflict.issue_id[:8]
        
        print("\n" + "=" * 70)
        print(f"🔀 KONFLIKT: {issue_id}... - {conflict.type.value}")
        print("=" * 70)
        print(f"\n📋 {conflict.description}")
        print(f"\n🔄 Konfliktfelder: {', '.join(conflict.conflicting_fields)}")
        
        # Diff anzeigen
        print("\n📊 Unterschiede:")
        diff = self.differ.compare(conflict.target_data, conflict.source_data)
        print(textwrap.indent(diff, "  "))
        
        # Kurze Info zum Issue
        print(f"\n📝 Titel: {conflict.target_data.get('title', '?')}")
        print(f"📌 Status: {conflict.target_data.get('status')} → {conflict.source_data.get('status')}")
        
        # Optionen anzeigen
        print("\n🔧 Lösungsoptionen:")
        print("  [1] Ziel behalten (bestehende Daten)")
        print("  [2] Quelle übernehmen (neue Daten)")
        print("  [3] Updates zusammenführen (Ziel + neue Updates)")
        print("  [4] Neuere gewinnt (automatisch nach Zeitstempel)")
        print("  [5] Detaillierten Diff anzeigen")
        print("  [6] Beide Versionen vollständig anzeigen")
        print("  [s] Überspringen")
        
        while True:
            choice = input("\n👉 Auswahl (1-6/s): ").strip().lower()
            
            if choice == "1":
                return ResolutionStrategy.KEEP_TARGET
            elif choice == "2":
                return ResolutionStrategy.KEEP_SOURCE
            elif choice == "3":
                return ResolutionStrategy.MERGE_UPDATES
            elif choice == "4":
                return ResolutionStrategy.NEWER_WINS
            elif choice == "5":
                self._show_detailed_diff(conflict)
            elif choice == "6":
                self._show_full_comparison(conflict)
            elif choice == "s":
                return ResolutionStrategy.SKIP
            else:
                print("❌ Ungültige Auswahl")
    
    def _show_detailed_diff(self, conflict: Conflict):
        """Zeigt detaillierten textuellen Diff"""
        print("\n" + "=" * 70)
        print("📊 DETAILLIERTER DIFF")
        print("=" * 70)
        
        target_str = json.dumps(conflict.target_data, indent=2, ensure_ascii=False).splitlines()
        source_str = json.dumps(conflict.source_data, indent=2, ensure_ascii=False).splitlines()
        
        diff = unified_diff(target_str, source_str, 
                          fromfile="ZIEL (bestehend)", 
                          tofile="QUELLE (import)")
        
        for line in diff:
            if line.startswith("---") or line.startswith("+++"):
                print(f"\033[1m{line}\033[0m")
            elif line.startswith("-"):
                print(f"\033[91m{line}\033[0m")
            elif line.startswith("+"):
                print(f"\033[92m{line}\033[0m")
            elif line.startswith("@@"):
                print(f"\033[94m{line}\033[0m")
            else:
                print(line)
    
    def _show_full_comparison(self, conflict: Conflict):
        """Zeigt beide Versionen nebeneinander"""
        print("\n" + "=" * 70)
        print("📋 VOLLSTÄNDIGER VERGLEICH")
        print("=" * 70)
        print("\n🔵 ZIEL (bestehend):")
        print(json.dumps(conflict.target_data, indent=2, ensure_ascii=False))
        print("\n🟢 QUELLE (import):")
        print(json.dumps(conflict.source_data, indent=2, ensure_ascii=False))
    
    def auto_resolve_conflict(self, conflict: Conflict) -> ResolutionStrategy:
        """Automatische Konfliktlösung basierend auf Strategie"""
        if self.auto_resolve == "newer":
            target_time = self._get_last_update_time(conflict.target_data)
            source_time = self._get_last_update_time(conflict.source_data)
            return ResolutionStrategy.KEEP_SOURCE if source_time > target_time else ResolutionStrategy.KEEP_TARGET
        
        elif self.auto_resolve == "target":
            return ResolutionStrategy.KEEP_TARGET
        
        elif self.auto_resolve == "source":
            return ResolutionStrategy.KEEP_SOURCE
        
        elif self.auto_resolve == "merge":
            return ResolutionStrategy.MERGE_UPDATES
        
        else:
            return ResolutionStrategy.SKIP
    
    def apply_resolution(self, issue: Dict, source: Dict, 
                        resolution: ResolutionStrategy) -> Dict:
        """Wendet eine Konfliktlösung an"""
        if resolution == ResolutionStrategy.KEEP_TARGET:
            return issue
        
        elif resolution == ResolutionStrategy.KEEP_SOURCE:
            return source
        
        elif resolution == ResolutionStrategy.MERGE_UPDATES:
            # Ziel behalten, aber neue Updates aus Quelle hinzufügen
            merged = issue.copy()
            target_updates = issue.get("updates", [])
            source_updates = source.get("updates", [])
            
            # Neue Updates identifizieren (nach Zeitstempel)
            target_timestamps = {u.get("timestamp") for u in target_updates}
            new_updates = [u for u in source_updates 
                         if u.get("timestamp") not in target_timestamps]
            
            if new_updates:
                merged["updates"] = target_updates + new_updates
                merged["updates"].sort(key=lambda x: x.get("timestamp", ""))
            
            # Auch neue Felder übernehmen, die im Ziel nicht existieren
            for key in source:
                if key not in merged and key not in ["id", "updates"]:
                    if source[key] is not None:
                        merged[key] = source[key]
            
            return merged
        
        elif resolution == ResolutionStrategy.NEWER_WINS:
            target_time = self._get_last_update_time(issue)
            source_time = self._get_last_update_time(source)
            return source if source_time > target_time else issue
        
        return issue
    
    def merge(self, source_file: Path) -> MergeResult:
        """Führt den Merge durch"""
        print("\n" + "🔄 " + "=" * 66)
        print(f"🚀 ISSUE TRACKER MERGE TOOL")
        print("=" * 68 + "\n")
        
        # Dateien laden
        print(f"📂 Lade Ziel-Datei: {self.target_file}")
        target_issues = self.load_file(self.target_file)
        print(f"   ✅ {len(target_issues)} Issues geladen")
        
        print(f"📂 Lade Quell-Datei: {source_file}")
        source_issues = self.load_file(source_file)
        print(f"   ✅ {len(source_issues)} Issues geladen")
        
        # Quell-Issues validieren
        print("\n🔍 Validiere Quell-Issues...")
        valid_sources = []
        for issue in source_issues:
            errors = IssueValidator.validate(issue)
            if errors:
                self.result.errors.append(
                    f"Validation-Fehler in Issue {issue.get('id', '?')[:8]}: {', '.join(errors)}"
                )
                print(f"   ⚠️  Issue {issue.get('id', '?')[:8]}... übersprungen: {errors[0]}")
            else:
                valid_sources.append(issue)
        
        print(f"   ✅ {len(valid_sources)} gültige Issues zum Importieren")
        
        # Konflikte erkennen
        print("\n🔍 Erkenne Konflikte...")
        conflicts = self.detect_conflicts(target_issues, valid_sources)
        self.result.conflicts = conflicts
        
        if conflicts:
            print(f"   ⚠️  {len(conflicts)} Konflikte gefunden")
        else:
            print("   ✅ Keine Konflikte")
        
        # Neue Issues identifizieren
        target_ids = {i["id"] for i in target_issues}
        new_issues = [i for i in valid_sources if i["id"] not in target_ids]
        self.result.new_issues = len(new_issues)
        print(f"   ℹ️  {len(new_issues)} neue Issues")
        
        # Bei Dry-Run nur Vorschau
        if self.dry_run:
            self._print_dry_run_summary(valid_sources, new_issues, conflicts)
            return self.result
        
        # Konflikte lösen
        if conflicts:
            print("\n" + "=" * 70)
            print("🔀 KONFLIKTLÖSUNG")
            print("=" * 70)
            
            resolutions = {}
            for i, conflict in enumerate(conflicts, 1):
                print(f"\n📌 Konflikt {i}/{len(conflicts)}: ", end="")
                
                if self.auto_resolve:
                    resolution = self.auto_resolve_conflict(conflict)
                    print(f"Auto-Resolution: {resolution.value}")
                else:
                    resolution = self.resolve_conflict_interactively(conflict)
                
                resolutions[conflict.issue_id] = resolution
                conflict.resolution = resolution
            
            # Lösungen anwenden
            print("\n" + "=" * 70)
            print("🔧 WENDE LÖSUNGEN AN")
            print("=" * 70)
            
            for conflict in conflicts:
                resolution = resolutions[conflict.issue_id]
                
                if resolution == ResolutionStrategy.SKIP:
                    print(f"   ⏭️  {conflict.issue_id[:8]}... übersprungen")
                    self.result.skipped_issues += 1
                    continue
                
                # Issue in der Target-Liste finden und ersetzen
                for idx, target_issue in enumerate(target_issues):
                    if target_issue["id"] == conflict.issue_id:
                        merged = self.apply_resolution(
                            target_issue, conflict.source_data, resolution
                        )
                        target_issues[idx] = merged
                        self.result.updated_issues += 1
                        action = "aktualisiert" if merged != target_issue else "unverändert"
                        print(f"   ✅ {conflict.issue_id[:8]}... {action} ({resolution.value})")
                        break
        
        # Neue Issues hinzufügen
        if new_issues:
            print(f"\n   ➕ Füge {len(new_issues)} neue Issues hinzu...")
            for issue in new_issues:
                # Sicherstellen, dass Updates-Array existiert
                if "updates" not in issue:
                    issue["updates"] = []
                
                # Import-Vermerk hinzufügen
                issue["updates"].append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "author": "merge-tool",
                    "action": "comment",
                    "comment": f"Importiert aus {source_file.name}"
                })
                
                target_issues.append(issue)
                print(f"   ✅ {issue['id'][:8]}... hinzugefügt: {issue.get('title', '?')[:50]}")
        
        # Ergebnis speichern
        if not self.dry_run:
            # Backup erstellen
            self.create_backup()
            
            # Speichern
            print(f"\n💾 Speichere {len(target_issues)} Issues...")
            self.save_file(self.target_file, target_issues)
            print("   ✅ Erfolgreich gespeichert")
        
        self.result.total_imported = self.result.new_issues + self.result.updated_issues
        self._print_summary()
        
        return self.result
    
    def _print_dry_run_summary(self, all_sources, new_issues, conflicts):
        """Gibt eine Dry-Run Zusammenfassung aus"""
        print("\n" + "=" * 70)
        print("🔍 DRY-RUN ZUSAMMENFASSUNG (keine Änderungen vorgenommen)")
        print("=" * 70)
        print(f"\n📊 Statistik:")
        print(f"   • {len(all_sources)} Issues in der Quelle")
        print(f"   • {len(new_issues)} neue Issues würden hinzugefügt")
        print(f"   • {len(conflicts)} Konflikte würden auftreten")
        
        if new_issues:
            print(f"\n🆕 Neue Issues:")
            for issue in new_issues[:10]:
                print(f"   • {issue['id'][:8]}... - {issue.get('title', '?')[:50]}")
            if len(new_issues) > 10:
                print(f"   ... und {len(new_issues) - 10} weitere")
        
        if conflicts:
            print(f"\n⚠️  Konflikte:")
            for conflict in conflicts:
                print(f"   • {conflict.issue_id[:8]}... - {conflict.description}")
    
    def _print_summary(self):
        """Gibt eine Zusammenfassung des Merge-Vorgangs aus"""
        print("\n" + "=" * 70)
        print("✅ MERGE ABGESCHLOSSEN")
        print("=" * 70)
        print(f"\n📊 Ergebnis:")
        print(f"   • {self.result.new_issues} neue Issues hinzugefügt")
        print(f"   • {self.result.updated_issues} Issues aktualisiert")
        print(f"   • {self.result.skipped_issues} Issues übersprungen")
        print(f"   • {len(self.result.conflicts)} Konflikte gelöst")
        
        if self.result.errors:
            print(f"\n❌ {len(self.result.errors)} Fehler:")
            for error in self.result.errors[:5]:
                print(f"   • {error}")
            if len(self.result.errors) > 5:
                print(f"   ... und {len(self.result.errors) - 5} weitere")
        
        if self.result.warnings:
            print(f"\n⚠️  {len(self.result.warnings)} Warnungen:")
            for warning in self.result.warnings[:5]:
                print(f"   • {warning}")
        
        print(f"\n💡 Tipp: Bei Problemen kann das automatische Backup wiederhergestellt werden.")


# ============================================================================
# CLI Interface
# ============================================================================

def create_parser() -> argparse.ArgumentParser:
    """Erstellt den ArgumentParser für das CLI"""
    parser = argparse.ArgumentParser(
        description="🔀 Issue Tracker Merge Tool - Führt Issue-JSON-Dateien zusammen",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Beispiele:
              # Interaktiver Merge
              python merge.py neue_issues.json
              
              # Dry-Run (Vorschau ohne Änderungen)
              python merge.py neue_issues.json --dry-run
              
              # Automatisch neuere Version übernehmen
              python merge.py neue_issues.json --auto-resolve newer
              
              # Issues aus Git-Patch extrahieren und mergen
              git diff HEAD~1 -- data/issues.json | python merge.py --stdin
              
              # Bestimmte Ausgabedatei verwenden
              python merge.py neue_issues.json --target custom/issues.json
            """)
    )
    
    parser.add_argument(
        "source",
        help="Pfad zur Import-JSON-Datei",
        nargs="?",
        default=None
    )
    
    parser.add_argument(
        "--target", "-t",
        help="Pfad zur Ziel-Issue-Datei (Standard: data/issues.json)",
        default="data/issues.json"
    )
    
    parser.add_argument(
        "--output", "-o",
        help="Pfad für die Ausgabedatei (optional, sonst wird Ziel überschrieben)"
    )
    
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Nur Vorschau, keine Änderungen vornehmen"
    )
    
    parser.add_argument(
        "--auto-resolve", "-a",
        choices=["newer", "target", "source", "merge"],
        help="Automatische Konfliktlösung (newer|target|source|merge)"
    )
    
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Ohne Rückfragen durchführen"
    )
    
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Kein Backup vor dem Merge erstellen"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Ausführliche Ausgabe"
    )
    
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="JSON von stdin lesen (für Pipe-Usage)"
    )
    
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Nur Validierung der Quelldatei, kein Merge"
    )
    
    return parser


def main():
    """Hauptfunktion"""
    parser = create_parser()
    args = parser.parse_args()
    
    # Input-Quelle bestimmen
    if args.stdin:
        # Von stdin lesen
        print("📥 Lese JSON von stdin...")
        try:
            source_data = json.load(sys.stdin)
            # Temporäre Datei erstellen
            temp_file = Path("temp_import.json")
            with open(temp_file, "w") as f:
                json.dump(source_data, f, indent=2)
            source_file = temp_file
        except json.JSONDecodeError as e:
            print(f"❌ Ungültiges JSON von stdin: {e}")
            sys.exit(1)
    elif args.source:
        source_file = Path(args.source)
    else:
        parser.print_help()
        print("\n❌ Fehler: Keine Quelle angegeben. Entweder Dateipfad oder --stdin verwenden.")
        sys.exit(1)
    
    # Ziel-Datei
    target_file = Path(args.target)
    if not target_file.exists():
        print(f"❌ Ziel-Datei nicht gefunden: {target_file}")
        if input("Soll eine neue Datei erstellt werden? (j/N): ").lower() == 'j':
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text('{"issues": []}')
            print(f"✅ Neue Datei erstellt: {target_file}")
        else:
            sys.exit(1)
    
    # Nur Validierung?
    if args.validate_only:
        print("🔍 Validiere Import-Datei...")
        engine = IssueMergeEngine(target_file)
        issues = engine.load_file(source_file)
        
        valid_count = 0
        for issue in issues:
            errors = IssueValidator.validate(issue)
            if errors:
                print(f"❌ Issue {issue.get('id', '?')[:8]}:")
                for error in errors:
                    print(f"   • {error}")
            else:
                valid_count += 1
        
        print(f"\n✅ {valid_count}/{len(issues)} Issues sind gültig")
        sys.exit(0 if valid_count == len(issues) else 1)
    
    # Merge durchführen
    engine = IssueMergeEngine(
        target_file=target_file,
        auto_resolve=args.auto_resolve,
        dry_run=args.dry_run,
        verbose=args.verbose,
        force=args.force,
        no_backup=args.no_backup
    )
    
    # Output-Datei
    if args.output:
        output_file = Path(args.output)
        # Merge in temporäre Datei, dann kopieren
        temp_target = target_file
        engine.target_file = temp_target
        
        if not args.dry_run:
            # Erst mergen, dann zum Output kopieren
            result = engine.merge(source_file)
            shutil.copy2(temp_target, output_file)
            print(f"📂 Ergebnis gespeichert in: {output_file}")
    else:
        result = engine.merge(source_file)
    
    # Temporäre Datei aufräumen
    if args.stdin:
        temp_file = Path("temp_import.json")
        if temp_file.exists():
            temp_file.unlink()
    
    # Exit-Code basierend auf Ergebnissen
    if result.errors:
        sys.exit(1)
    elif result.warnings:
        sys.exit(0)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
