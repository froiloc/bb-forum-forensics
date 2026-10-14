# =============================================================================
# management/db_vorfall/melde_ergebnis.py
# IT-Forensisches Ermittlungswerkzeug — Register "Datenbank-Vorfaelle" (Build 777)
# =============================================================================
# Zweck:
#   Was beim Melden eines Vorfalls geschah (DbVorfallMelder.melden). Genau
#   einer von drei Ausgaengen:
#     eingetragen  — im Register, audit_seq gesetzt
#     gepuffert    — coordinator.db nicht erreichbar, puffer_pfad gesetzt
#     nur_protokoll — auch der Puffer scheiterte; die Meldung steht dann
#                     VOLLSTAENDIG im Protokoll (Stufe CRITICAL), sonst nirgends
#   'fehler' traegt in den beiden letzten Faellen, woran es scheiterte.
#
# Version: v0.8.777 · Build: 777 · 2026-10-14
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

EINGETRAGEN = "eingetragen"
GEPUFFERT = "gepuffert"
NUR_PROTOKOLL = "nur_protokoll"


@dataclass
class MeldeErgebnis:
    """Ausgang einer Meldung."""

    vorfall_uid: str
    ausgang: str
    audit_seq: Optional[int] = None
    puffer_pfad: Optional[str] = None
    fehler: List[str] = field(default_factory=list)

    @property
    def eingetragen(self) -> bool:
        return self.ausgang == EINGETRAGEN

    def klartext(self) -> str:
        """Ein Satz fuer Fehlerseite und Protokoll."""
        if self.ausgang == EINGETRAGEN:
            return ("Vorfall %s im Register eingetragen (Beleg seq=%s)."
                    % (self.vorfall_uid, self.audit_seq))
        if self.ausgang == GEPUFFERT:
            return ("Vorfall %s konnte nicht ins Register (%s) und liegt im "
                    "Puffer %s; er wird beim naechsten Start nachgetragen."
                    % (self.vorfall_uid, "; ".join(self.fehler),
                       self.puffer_pfad))
        return ("Vorfall %s konnte weder ins Register noch in den Puffer (%s); "
                "er steht vollstaendig im Protokoll." % (
                    self.vorfall_uid, "; ".join(self.fehler)))
