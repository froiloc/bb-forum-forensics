# =============================================================================
# db/reparatur/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Reparatur beschaedigter SQLite-Dateien
# =============================================================================
# Zweck:
#   Neuaufbau einer beschaedigten evidence_<uid>.db aus allem, was sich aus
#   ihr lesen laesst — mit Protokoll, das jede nicht uebernommene Zeile
#   zaehlt (Grundregel 1). Herkunft: tools/evidence_reparatur.py 1.2 (am
#   14.10.2026 ausserhalb der Buildkette geliefert und in PROD an
#   evidence_2948078.db eingesetzt). Ab Build 776 im Bestand, damit die
#   Kommandozeile UND die Startpruefung des Webservers (Build 778) dieselbe
#   Logik nutzen.
#
# Bausteine (je Klasse eine Datei, Grundregel 10):
#   SeitenScanner      — Datensaetze direkt aus den Tabellenblattseiten
#   TabellenBergung    — Vollscan + Einzelzugriff je Tabelle
#   DefektSicherung    — Sicherung des Originals (mit SHA-256-Abgleich)
#   SicherungsErgebnis — Ergebnis der Sicherung
#   EvidenceReparierer — der Ablauf (sichern, bergen, neu aufbauen, pruefen)
#   ReparaturErgebnis  — Ergebnis des Ablaufs
#
# Das ORIGINAL wird von keinem Baustein veraendert. Der Austausch ist ein
# eigener Schritt (Kommandozeile: von Hand; Startpruefung: Build 778).
#
# Version: v0.8.776 · Build: 776 · 2026-10-14
# =============================================================================
from db.reparatur.defekt_sicherung import DefektSicherung
from db.reparatur.evidence_reparierer import EvidenceReparierer
from db.reparatur.reparatur_ergebnis import ReparaturErgebnis
from db.reparatur.seitenscanner import SeitenScanner
from db.reparatur.sicherungs_ergebnis import SicherungsErgebnis
from db.reparatur.tabellen_bergung import TabellenBergung

__all__ = ["DefektSicherung", "EvidenceReparierer", "ReparaturErgebnis",
           "SeitenScanner", "SicherungsErgebnis", "TabellenBergung"]
