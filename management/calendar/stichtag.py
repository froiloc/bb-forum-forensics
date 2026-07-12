# =============================================================================
# management/calendar/stichtag.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Bestimmt den STICHTAG — den Kalendertag, gegen den alle Faelligkeiten
#   gerechnet werden.
#
# WARUM EINE EIGENE DATEI FUER EINE ZEILE DATUM?
#   Weil an dieser Zeile jede Fristenrechnung des Systems haengt.
#
#   (1) ZEITZONE. 'heute' muss der Kalendertag in Europe/Berlin sein, nicht in
#       UTC. Sonst kippt eine Wiedervorlage in der Sommerzeit zwischen 00:00 und
#       02:00 Ortszeit einen Tag ZU FRUEH auf rot — und im Winter zwischen 23:00
#       und 24:00 einen Tag ZU SPAET, was schlimmer ist: eine faellige
#       Wiedervorlage bliebe gruen.
#
#   (2) DIE UHR IST EINE ANNAHME. Im abgeschotteten Netz gibt es keinen
#       Zeitserver, den wir hier pruefen koennten. Geht die VM-Uhr falsch, sind
#       ALLE Faelligkeiten falsch — und zwar still. Deshalb liefert dieses Modul
#       den Stichtag NIE nackt, sondern immer mit einem HERKUNFTSVERMERK, den
#       die Oberflaeche anzeigt ("Faelligkeiten berechnet zum 12.07.2026,
#       Zeitzone Europe/Berlin"). Eine falsche Uhr faellt damit einem Menschen
#       auf, statt unbemerkt zu wirken (Grundregel 1).
#       (mc 2026-07-12: die Uhr im Cloud-Netz ist synchronisiert — der Vermerk
#        bleibt trotzdem, denn er kostet nichts und belegt die Rechengrundlage.)
#
#   (3) TZDATA. Unter Windows bringt Python keine Zeitzonendatenbank mit;
#       'zoneinfo' braucht dort das Paket 'tzdata'. Fehlt es, faellt dieses
#       Modul auf die LOKALE Systemzeit zurueck — aber NICHT stillschweigend:
#       der Rueckfall wird protokolliert UND als Warnung in den Vermerk
#       geschrieben. Lieber ein sichtbarer Behelf als eine unsichtbare Luecke.
#
# Version: v0.7.385 · Build: 385 · 2026-07-12
# =============================================================================

import logging
from datetime import date, datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: Zeitzone der Dienststelle. Bewusst fest verdrahtet: NRW.
TIMEZONE = "Europe/Berlin"


def heute(tz_name: str = TIMEZONE) -> Dict[str, Any]:
    """
    Liefert {'stichtag': 'YYYY-MM-DD', 'zeitzone': str, 'warnung': str|None}.

    Der Stichtag wird NIE ohne diesen Kontext weitergereicht — die Oberflaeche
    zeigt ihn an, damit die Rechengrundlage nachpruefbar bleibt.
    """
    warnung: Optional[str] = None
    try:
        from zoneinfo import ZoneInfo  # stdlib ab 3.9
        tag = datetime.now(ZoneInfo(tz_name)).date()
        zone = tz_name
    except Exception as exc:                      # noqa: BLE001 — bewusst breit
        # Kein stiller Rueckfall: protokollieren UND sichtbar melden.
        tag = date.today()
        zone = "lokale Systemzeit"
        warnung = (
            "Zeitzone '%s' nicht verfuegbar (%s). Es wird die LOKALE "
            "Systemzeit der VM verwendet. Unter Windows fehlt dafuer "
            "moeglicherweise das Paket 'tzdata' — bitte pruefen, sonst koennen "
            "Faelligkeiten um einen Tag abweichen." % (tz_name, exc)
        )
        logger.warning("Stichtag: %s", warnung)

    return {"stichtag": tag.isoformat(), "zeitzone": zone, "warnung": warnung}


def stichtag_text(info: Dict[str, Any]) -> str:
    """Herkunftsvermerk als ein Satz (Oberflaeche, CLI, Bericht)."""
    txt = ("Faelligkeiten berechnet zum %s (Zeitzone: %s)."
           % (info.get("stichtag", "?"), info.get("zeitzone", "?")))
    if info.get("warnung"):
        txt += " ACHTUNG: " + info["warnung"]
    return txt
