# =============================================================================
# db/reparatur/reparatur_ergebnis.py
# IT-Forensisches Ermittlungswerkzeug — Ergebnis einer Reparatur
# =============================================================================
# Version: v0.8.776 · Build: 776 · 2026-10-14
# =============================================================================
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

#: Die moeglichen Ergebnisse. Die Bedeutung steht bei EvidenceReparierer.
STATUS = ("freigegeben", "nicht_freigegeben", "verworfen",
          "abbruch_sicherung", "nicht_lesbar")


@dataclass
class ReparaturErgebnis:
    """
    status        — siehe STATUS:
        freigegeben        neue Datei geprueft; alle Tabellen mit
                           Ermittlungsergebnissen fehlerfrei uebernommen
        nicht_freigegeben  neue Datei technisch in Ordnung, aber mindestens
                           eine Tabelle mit Ermittlungsergebnissen war
                           beschaedigt (sperren nennt sie)
        verworfen          neue Datei hat die Pruefung nicht bestanden und
                           wurde geloescht
        abbruch_sicherung  Sicherung nicht stimmig — nichts repariert
        nicht_lesbar       Arbeitskopie nicht einmal als SQLite lesbar
    neu           — Pfad der neuen Datei (nur bei (nicht_)freigegeben)
    sperren       — Tabellen mit Ermittlungsergebnissen, die beschaedigt waren
    verloren      — {Tabelle: Zahl nicht geborgener Zeilennummern}
    daten         — der JSON-Inhalt des Protokolls
    """
    status: str
    original: str
    zeitstempel: str
    sicherung: Optional[Any] = None
    neu: Optional[str] = None
    neu_sha256: Optional[str] = None
    protokoll_txt: Optional[str] = None
    protokoll_json: Optional[str] = None
    sperren: List[str] = field(default_factory=list)
    verloren: Dict[str, int] = field(default_factory=dict)
    beschaedigte_tabellen: List[str] = field(default_factory=list)
    daten: Dict[str, Any] = field(default_factory=dict)

    @property
    def neue_datei_gut(self) -> bool:
        """True, wenn eine geprufte neue Datei vorliegt."""
        return self.status in ("freigegeben", "nicht_freigegeben")

    def protokoll_anhaengen(self, text: str = "") -> None:
        """Eine Zeile an das Textprotokoll anhaengen (z. B. Austausch)."""
        if self.protokoll_txt:
            with open(self.protokoll_txt, "a", encoding="utf-8") as fh:
                fh.write(text + "\n")

    def json_ergaenzen(self, schluessel: str, wert: Any) -> None:
        """Einen Eintrag im JSON-Protokoll ergaenzen und neu schreiben."""
        self.daten[schluessel] = wert
        if self.protokoll_json:
            with open(self.protokoll_json, "w", encoding="utf-8") as fh:
                json.dump(self.daten, fh, ensure_ascii=False, indent=1)
