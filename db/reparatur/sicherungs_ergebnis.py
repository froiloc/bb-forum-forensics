# =============================================================================
# db/reparatur/sicherungs_ergebnis.py
# IT-Forensisches Ermittlungswerkzeug — Ergebnis einer Defekt-Sicherung
# =============================================================================
# Version: v0.8.776 · Build: 776 · 2026-10-14
# =============================================================================
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class SicherungsErgebnis:
    """
    Ergebnis von DefektSicherung.sichern().

    pfad          — die Sicherungsdatei (neu angelegt oder wiederverwendet)
    sha256        — SHA-256 des Originals (= der Sicherung)
    begleit       — {Endung: SHA-256} der mitgesicherten Begleitdateien
    neu_angelegt  — False: eine Sicherung mit identischen Pruefsummen lag
                    schon vor und wurde wiederverwendet (wiederholte
                    Startversuche erzeugen keine weiteren Kopien)
    stimmig       — SHA-256 des Originals vor und nach dem Kopieren und der
                    Kopie sind gleich. False heisst: waehrend des Kopierens
                    geaendert oder Kopie fehlerhaft — dann darf NICHTS
                    repariert werden.
    meldung       — Klartext fuer das Protokoll (bei stimmig=False der Grund)
    """
    pfad: str
    sha256: str
    begleit: Dict[str, str] = field(default_factory=dict)
    neu_angelegt: bool = True
    stimmig: bool = True
    meldung: str = ""
    sha256_nachher: Optional[str] = None
    sha256_kopie: Optional[str] = None
