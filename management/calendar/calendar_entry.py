# =============================================================================
# management/calendar/calendar_entry.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Der NORMALISIERTE Kalendereintrag — die gemeinsame Sprache aller
#   zeitbezogenen Quellen des Systems.
#
#   Hintergrund (mc 2026-07-12): Wir haben bewusst KEINEN gemeinsamen SPEICHER
#   fuer Personalplanung (M008) und externe Vorgaenge (M010) gebaut — die beiden
#   sind fachlich zu verschieden (Person vs. Fall; Menge vs. Zustand; Intervall
#   vs. Zeitpunkt; korrigierbar vs. unwiderruflich). Der gemeinsame
#   VERKNUEPFUNGSPUNKT ist die ZEIT. Genau den bildet diese Klasse ab.
#
#   Damit gilt: Schreibmodelle bleiben spezialisiert, die SICHT ist gemeinsam.
#   Neue Zeitquellen (Fristen, Berichts-Deadlines, Gantt in Welle 2) haengen
#   sich hier an, ohne dass eine bestehende Tabelle angefasst werden muss.
#
# ZEITBEGRIFF:
#   Ein Eintrag hat IMMER 'von' und 'bis' (ISO YYYY-MM-DD, beide inklusiv).
#   Ein ZEITPUNKT (Wiedervorlage, Feiertag) ist der Sonderfall von == bis.
#   Damit muss die Sicht nicht zwei Zeitbegriffe kennen.
#
# KAPSELUNG:
#   Der Eintrag traegt KEINE Ermittlungsinhalte ueber das hinaus, was die
#   jeweilige Quelle ohnehin freigibt. Die RBAC-Pruefung passiert in der QUELLE
#   (CalendarSource), nicht hier — dieses Objekt ist ein reiner Traeger.
#
# Version: v0.7.385 · Build: 385 · 2026-07-12
# =============================================================================

from dataclasses import dataclass
from typing import Any, Dict, Optional

#: Subjektarten. 'case' = ein Fall (user_id), 'person' = ein Mitarbeiter
#: (person.id), 'global' = betrifft alle (z. B. Feiertag).
SUBJECT_KINDS = ("case", "person", "global")


@dataclass(frozen=True)
class CalendarEntry:
    """Ein normalisierter Eintrag im gemeinsamen Kalender."""

    #: Quelle, aus der der Eintrag stammt ('external', 'availability', 'holiday').
    source: str
    #: ID des Datensatzes IN DER QUELLE (external_matters.id, availability_entry.id …).
    ref_id: int
    #: Erster und letzter betroffener Tag (ISO, inklusiv). Zeitpunkt: von == bis.
    von: str
    bis: str
    #: Kurztitel fuer die Zeile im Kalender.
    titel: str
    #: 'case' | 'person' | 'global'
    subject_kind: str
    #: user_id (Fall) bzw. person.id; None bei 'global'.
    subject_id: Optional[int] = None
    #: Klartext des Subjekts (Fall-Benutzername bzw. Anzeigename).
    subject_label: str = ""
    #: Ampel der Quelle ('rot'|'gelb'|'gruen'|'neutral').
    ampel: str = "neutral"
    #: WARUM diese Ampel — eine Ampel ohne Grund ist forensisch wertlos.
    ampel_grund: str = ""
    #: Sprungziel in der Oberflaeche (Cockpit-Sicht), z. B. 'external'.
    ziel: str = ""

    def as_dict(self) -> Dict[str, Any]:
        """JSON-Form fuer /api/calendar."""
        return {
            "source": self.source,
            "ref_id": self.ref_id,
            "von": self.von,
            "bis": self.bis,
            "ist_zeitpunkt": self.von == self.bis,
            "titel": self.titel,
            "subject_kind": self.subject_kind,
            "subject_id": self.subject_id,
            "subject_label": self.subject_label,
            "ampel": self.ampel,
            "ampel_grund": self.ampel_grund,
            "ziel": self.ziel,
        }
