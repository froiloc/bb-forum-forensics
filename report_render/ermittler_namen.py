# =============================================================================
# report_render/ermittler_namen.py
# IT-Forensisches Ermittlungswerkzeug - Vollzitat (Beweismittelgruppen)
# =============================================================================
# Zweck:
#   AUS EINEM KUERZEL EINEN NAMEN MACHEN. 'annotations.created_by' traegt den
#   SAMAccountName des Ermittlers ("h012345", gesetzt in
#   forensic_api/annotate.py:180). Im Bericht soll dort der Nachname stehen.
#
# DER AUFTRAG (Chef-Ermittlerin, 27.08.2026, Anforderung 1):
#   "Der Name des Ermittlers, der die Annotation erstellt hat, soll mit
#   Nachname (ohne Vorname) anstelle des SAMAccountName angegeben werden."
#   Weisung Alex vom selben Tag zur Herkunft: Vorname aus AD 'givenName',
#   Nachname aus 'sn', Dienstgrad aus 'title'; ist der Dienstgrad gesetzt -
#   "im Regelfall ist er immer gesetzt" -, wird er dem Nachnamen
#   VORANGESTELLT, sonst entfaellt er ersatzlos.
#
# ZWEI WEGE, UND DER BENUTZTE WIRD IMMER GENANNT.
#   Weg 1 - die AD-Felder (cdb.person.last_name/rank, M039). Das ist der
#           Sollweg: getrennt gefuehrte Attribute, nichts wird geraten.
#   Weg 2 - der Rueckfall aus cdb.person.display_name: alles bis zum ERSTEN
#           Komma. Weisung Alex: "Die Schreibweise aus dem Active Directory
#           ist durchgehend 'Nachname, Vorname'." Damit ergibt "Muster, Max"
#           den Nachnamen "Muster".
#
#   Weg 2 ist ausdruecklich als Uebergang gedacht und bleibt noetig, bis der
#   AD-Abgleich die neuen Spalten einmal befuellt hat. Er ist eine ANNAHME
#   ueber eine Schreibweise - deshalb sagt jeder Datensatz mit, welcher Weg
#   ihn erzeugt hat ('quelle'), und der Berichtsgenerator kann das ausweisen.
#   Ein Name, dem man nicht ansieht, ob er gelesen oder zerlegt wurde, waere
#   in einer Akte wertlos.
#
# WAS BEI EINEM UNBEKANNTEN KUERZEL PASSIERT: Es bleibt STEHEN. 'created_by'
#   kann ein Kuerzel tragen, das nicht (mehr) in cdb.person steht - eine
#   geloeschte AD-Kennung, eine Person aus einer anderen Dienststelle, ein
#   Bestand aus der Zeit vor der Personenpflege. GR1 verbietet, den Beleg
#   deshalb ohne Urheber zu drucken. Ausgegeben wird dann das Kuerzel selbst,
#   und 'quelle' ist 'kuerzel'. Der Bericht sagt damit die Wahrheit: "wir
#   wissen nur das Kuerzel" - statt eine Zuschreibung zu erfinden oder das
#   Feld leer zu lassen.
#
# WARUM ES EINEN ZWISCHENSPEICHER GIBT: Eine Beweismittelgruppe kann Dutzende
#   Belege desselben Bearbeiters enthalten, ein Bericht mehrere Gruppen.
#   coordinator.db liegt auf einem SMB-Netzlaufwerk (s. Kopf von
#   db/coordinator_db.py); jede Abfrage kostet dort spuerbar. Gespeichert wird
#   NUR fuer die Dauer eines Berichtsaufbaus - ein Objekt je Export.
#
# Grundregeln: GR1 (kein Beleg faellt still weg), GR6, GR10.
# Version: v0.8.725 - Build: 725 - 2026-08-27
# =============================================================================

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Dict, Optional

from core.logger import get_logger
from db.coordinator_db import lies_namensteile

logger = get_logger(__name__)

#: Der Weg, auf dem der Name zustande kam. Er wandert bis in den Bericht.
QUELLE_AD = "ad_felder"        # cdb.person.last_name / rank (M039)
QUELLE_DISPLAY = "display_name"  # Rueckfall: bis zum ersten Komma
QUELLE_KUERZEL = "kuerzel"     # nicht auffindbar - Kuerzel bleibt stehen


@dataclass(frozen=True)
class ErmittlerName:
    """
    Ein aufgeloester Ermittlername.

    Felder:
        kuerzel   - der SAMAccountName, wie er in annotations.created_by steht
        nachname  - der Nachname allein, ohne Dienstgrad und ohne Vorname
        rang      - der Dienstgrad oder "" (nie None, damit die Renderer
                    nicht jedes Mal pruefen muessen)
        anzeige   - was im Bericht steht: "KHK Muster", bei fehlendem
                    Dienstgrad "Muster", bei unbekanntem Kuerzel das Kuerzel
        quelle    - QUELLE_AD | QUELLE_DISPLAY | QUELLE_KUERZEL
    """
    kuerzel:  str
    nachname: str
    rang:     str
    anzeige:  str
    quelle:   str

    @property
    def ist_gesichert(self) -> bool:
        """True nur beim Sollweg ueber die getrennten AD-Felder."""
        return self.quelle == QUELLE_AD


def nachname_aus_display_name(display_name: str) -> str:
    """
    Den Nachnamen aus einem Anzeigenamen der Form "Nachname, Vorname" holen.

    REGEL (Weisung Alex, 27.08.2026): alles bis zum ERSTEN Komma.

    OHNE KOMMA WIRD NICHTS GERATEN. "Chefin" hat keinen erkennbaren
    Vornamensteil; die Zeichenkette wird unveraendert uebernommen. Das letzte
    Wort zu nehmen waere hier die naheliegende und falsche Ergaenzung: bei
    einer Schreibweise "KHK Muster" ergaebe sie zufaellig "Muster", bei
    "Muster zu Guttenberg" aber "Guttenberg". Wer eine Regel nur an guenstigen
    Beispielen prueft, baut eine Falle.
    """
    kopf = (display_name or "").split(",", 1)[0]
    return kopf.strip()


class ErmittlerNamen:
    """
    Loest SAMAccountNames zu Ermittlernamen auf - mit Zwischenspeicher.

    Eine Instanz je Berichtsaufbau. Sie schreibt nichts und braucht nur eine
    Verbindung, auf der cdb angebunden ist; fehlt cdb, liefert sie fuer alle
    Kuerzel QUELLE_KUERZEL und meldet das EINMAL statt bei jedem Beleg.
    """

    def __init__(self, con: Optional[sqlite3.Connection]) -> None:
        self._con = con
        self._speicher: Dict[str, ErmittlerName] = {}
        #: Wird auf True gesetzt, sobald der erste Fehlschlag gemeldet wurde -
        #: verhindert, dass ein Bericht mit 200 Belegen 200 gleiche Zeilen ins
        #: Protokoll schreibt und die wirklich seltenen Meldungen zudeckt.
        self._ausfall_gemeldet = False

    # ------------------------------------------------------------------
    def aufloesen(self, kuerzel: Optional[str]) -> ErmittlerName:
        """
        Ein Kuerzel aufloesen. Gibt IMMER einen Datensatz zurueck, nie None.

        Ein leeres Kuerzel ergibt einen Datensatz mit leerer Anzeige und
        QUELLE_KUERZEL: 'annotations.created_by' ist NOT NULL DEFAULT ''
        (evidence_uid.db.schema.sql), Bestandszeilen aus der Zeit vor der
        Urheberkennzeichnung tragen dort also den Leerstring. Auch das muss
        der Bericht sagen koennen, statt daran zu scheitern.
        """
        schluessel = (kuerzel or "").strip()
        if schluessel in self._speicher:
            return self._speicher[schluessel]

        eintrag = self._ermitteln(schluessel)
        self._speicher[schluessel] = eintrag
        return eintrag

    # ------------------------------------------------------------------
    def _ermitteln(self, kuerzel: str) -> ErmittlerName:
        if not kuerzel:
            return ErmittlerName(kuerzel="", nachname="", rang="",
                                 anzeige="", quelle=QUELLE_KUERZEL)

        satz = lies_namensteile(self._con, kuerzel) if self._con else None
        if satz is None:
            if not self._ausfall_gemeldet:
                logger.info(
                    "Ermittlername: %r nicht in cdb.person - das Kuerzel "
                    "bleibt im Bericht stehen (weitere Faelle werden nicht "
                    "einzeln gemeldet).", kuerzel)
                self._ausfall_gemeldet = True
            return ErmittlerName(kuerzel=kuerzel, nachname="", rang="",
                                 anzeige=kuerzel, quelle=QUELLE_KUERZEL)

        rang = (satz.rank or "").strip()
        nachname = (satz.last_name or "").strip()

        if nachname:
            quelle = QUELLE_AD
        else:
            # M039 nicht angewandt oder AD-Abgleich noch nicht gelaufen.
            nachname = nachname_aus_display_name(satz.display_name)
            quelle = QUELLE_DISPLAY

        if not nachname:
            # display_name ist NOT NULL, kann aber leer sein. Dann bleibt nur
            # das Kuerzel - und das wird als solches ausgewiesen.
            return ErmittlerName(kuerzel=kuerzel, nachname="", rang=rang,
                                 anzeige=kuerzel, quelle=QUELLE_KUERZEL)

        anzeige = ("%s %s" % (rang, nachname)) if rang else nachname
        return ErmittlerName(kuerzel=kuerzel, nachname=nachname, rang=rang,
                             anzeige=anzeige, quelle=quelle)
