# =============================================================================
# management/deadlines/limitation_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A)
# =============================================================================
# Zweck (Idee 32, Build 524):
#   Das READ-MODEL des Fristenmonitors: es beschafft je Fall den Fristbeginn
#   (§ 78a StGB — Beendigung der Tat) aus den forensic_<uid>.db und laesst die
#   reine Rechenschicht (limitation.py) darauf rechnen.
#
# WORAUS DER FRISTBEGINN GEBILDET WIRD (belegt, nicht geraten):
#   Die massgebliche Liste ist die Konstante ZEITQUELLEN weiter unten — dort
#   traegt jede Quelle ihren eigenen Belegtext. Sie wird hier NICHT wiederholt.
#
#   WARUM NICHT: Bis Build 529 stand an dieser Stelle eine zweite, von Hand
#   gepflegte Aufzaehlung. Build 528 hat die Konstante korrigiert (die echten
#   Spalten heissen 'posted_ts', nicht 'posted') — der Kopfkommentar blieb
#   stehen und behauptete danach zwei Dinge, die ich selbst schon
#   zurueckgenommen hatte: die Spalte 'uid_posts.posted' und die Aussage, fuer
#   geteilte Dateien existiere kein Zeitstempel (uid_shares.posted_ts gibt es,
#   mit eigenem Index). Zwei Wahrheitsquellen fuer dieselbe Tatsache laufen
#   auseinander, und die falsche wird gelesen. Es gibt jetzt nur noch eine.
#
#   NICHT VERWENDET: pages.fetched_at. Das ist der SICHERUNGSZEITPUNKT des
#   Scrapers und hat mit der Tatzeit nichts zu tun; eine Verwechslung wuerde
#   jede Frist um Jahre verschieben.
#
#   uid_profile.registered ist KEINE Tathandlung und geht deshalb nicht in die
#   Zeitquellen ein. Seit Build 530 dient sie als ERSATZANKER (s. u.) — das ist
#   etwas anderes und wird auch anders gekennzeichnet.
#
# DIE SPAETESTE HANDLUNG IST DER FRISTBEGINN — und die frueheste steht daneben.
#   Begruendung: § 78a StGB knuepft an die BEENDIGUNG an; die spaeteste belegte
#   Handlung ist damit die fristrechtlich guenstigste BELEGTE Tatsache. Ob
#   mehrere Handlungen eine Tat im Rechtssinne bilden, ist eine juristische
#   Bewertung — das Werkzeug trifft sie nicht und sagt das im Vorbehalt. Die
#   FRUEHESTE Handlung faehrt trotzdem mit: sie zeigt die Spanne der Aktivitaet
#   und macht sichtbar, wenn zwischen erster und letzter Handlung Jahre liegen.
#
# NICHTS WIRD STILL UEBERSPRUNGEN (Grundregel 1). Jeder Fall landet in genau
#   einer Zeile, auch wenn er unlesbar ist. SECHS Befundarten werden GEZAEHLT und
#   BENANNT:
#     ohne_forensic_db      — Fall in 'cases', aber keine forensic_<uid>.db.
#     ohne_zeittabelle      — Datei da, aber weder uid_posts noch uid_pms_posts.
#     nicht_lesbar          — Datei da, aber nicht oeffenbar/lesbar (mit Grund).
#     zeitspalte_unlesbar   — Tabelle da, aber KEINE Zeitspalte lesbar (Grund
#                             mit). NEU in Build 527.
#     belegt_unvollstaendig — Zeitstempel gefunden, ABER mindestens eine Quelle
#                             war nicht lesbar. NEU in Build 527.
#     ohne_tatzeit          — Tabellen und Spalten lesbar, aber kein einziger
#                             Zeitstempel gesetzt.
#   Ein Monitor, der solche Faelle weglaesst, saehe nach vollstaendiger Pruefung
#   aus und waere der gefaehrlichste denkbare Beleg.
#
# BUILD 527 — WAS HIER FALSCH WAR (Befund aus der PROD-Messung 2026-07-25):
#   In den ECHTEN forensic_<uid>.db existiert die Spalte 'uid_posts.posted'
#   NICHT ('no such column: posted', 162 von 162 Dateien). Build 524 hat daraus
#   ZWEI falsche Aussagen gemacht, und beide waren Grundregel-1-Verstoesse:
#
#   (a) Schlug der Spaltenzugriff fehl und lieferte auch die zweite Quelle
#       nichts, meldete der Fall 'ohne_tatzeit' mit dem Text 'Zeittabelle(n)
#       vorhanden, aber kein einziger Zeitstempel gesetzt'. Das war SCHLICHT
#       FALSCH: es war nicht 'kein Zeitstempel gesetzt', sondern 'die Spalte war
#       nicht lesbar'. Der Unterschied entscheidet darueber, ob man in den Daten
#       oder im Code sucht.
#
#   (b) Schlug uid_posts fehl, lieferte aber uid_pms_posts einen Wert, meldete
#       der Fall schlicht 'belegt' — OHNE jede Spur, dass die STAERKERE Quelle
#       ausgefallen war. Der Fristbeginn stuetzte sich dann allein auf private
#       Nachrichten. Das ist die gefaehrlichere der beiden Fehlwirkungen: die
#       Zahl sah vollwertig aus. (Richtung des Fehlers: fehlen spaetere
#       Beitraege, wird der Fristbeginn ZU FRUEH angesetzt, die Frist also zu
#       kurz gerechnet — der Fall erscheint DRINGENDER als er ist. Das ist die
#       ungefaehrliche Richtung, aber ein Bericht mit falschem Datum bleibt
#       falsch.)
#
#   Seit Build 527 gilt: ein Fall mit ausgefallener Quelle ist NIE einfach
#   'belegt'. Und der Ausfall wird EINMAL je Abruf zusammengefasst protokolliert
#   statt 162-mal einzeln (der Log-Schwall der Messung war selbst ein Befund).
#
# BUILD 530 — DIE ANKERKASKADE (mc, 2026-07-25):
#   belegte Tathandlung -> Registrierungsdatum -> erste ueber die 100a-Massnahme
#   protokollierte ERFOLGREICHE Anmeldung -> nichts.
#
#   'befund' bleibt dabei UNVERAENDERT die Aussage ueber die AKTIVITAETSquellen.
#   Der Anker steht in eigenen Feldern (anker_art, anker_ts, anker_beleg). Beide
#   Achsen werden bewusst nicht vermischt: sonst waere ein Fall mit Ersatzanker
#   nicht mehr von einem mit belegter Tathandlung zu unterscheiden, und genau
#   dieser Unterschied entscheidet ueber die Belastbarkeit der Zahl.
#
#   Der Ersatzanker wird NUR gelesen, wenn keine Tathandlung mit Zeitstempel
#   vorliegt — nicht 'zusaetzlich' und nicht 'zum Vergleich'. Ein Wert, den man
#   nicht braucht, sollte man auch nicht holen.
#
# REIN LESEND: coordinator.db und alle forensic_<uid>.db werden mit
#   file:...?mode=ro geoeffnet (Muster management/reports/reports_repo.py:122).
#   Der Migrationsvorbehalt ab 01.07.2026 ist NICHT beruehrt.
#
# Build 535: Die FESTGESTELLTE Tatzeit wird ausgewertet. Bis Build 534 stand
#   in compute() fest 'festgestellt=False' — mit dem ausdruecklichen Vermerk,
#   dass sich GENAU diese Zeile aendert, sobald es festgestellte Tatzeiten
#   gibt. Sie gibt es seit Build 533/534 (annotation_tatzeit + Maske), und die
#   Umschaltung ist vollzogen. Gelesen wird ueber
#   management/deadlines/tatzeit_anker.py (eigene Datei, Grundregel 10) aus
#   evidence_<uid>.db, READ-ONLY.
#
#   RANGFOLGE: eine festgestellte Tatzeit schlaegt jeden anderen Anker, auch
#   wenn sie frueher liegt als die spaeteste belegte Tathandlung. Das ist der
#   Sinn der Achse 'feststellung' aus Build 530.
#
#   OHNE evidence_dir WIRD NICHT STILL WEITERGERECHNET: dann traegt jede Zeile
#   den Befund 'nicht_geprueft' und der Bericht einen Hinweis.
#
# Version: v0.8.535 · Build: 535 · 2026-07-26
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from management.deadlines.limitation import (
    ANKER_ARTEN,
    DEFAULT_VORWARN_TAGE,
    FESTSTELLUNGEN,
    LimitationAssessment,
    assess_limitation,
)
from management.deadlines.limitation_params import LimitationParams
from management.deadlines.tatzeit_anker import (
    TATZEIT_BEFUNDE,
    TatzeitAnker,
    nicht_geprueft,
    read_tatzeit_anker,
)

logger = logging.getLogger(__name__)

#: Die ausgewerteten Zeitquellen: (Tabelle, Spalte, Belegqualitaet).
#
#  BELEG (Build 528): das VOLLSTAENDIGE DDL der forensic_<uid>.db, von mc am
#  2026-07-25 als 'forensic_uid.db.schema.sql' uebergeben, bestaetigt durch zwei
#  unabhaengige Sondenlaeufe (DEV und PROD, je 7 Dateien,
#  tools/diag_limitation_laufzeit.py). DAS IST EIN BELEG AUS DEN ECHTEN DATEN —
#  im Unterschied zu Build 524, das sich auf eine TESTVORRICHTUNG gestuetzt hat
#  (tests/test_build388_vorlagen.py legte 'uid_posts(id, posted)' selbst an; die
#  Spalten heissen in Wirklichkeit 'post_id' und 'posted_ts').
#
#  VIER TATHANDLUNGS-QUELLEN, nicht mehr zwei. Die beiden neuen sind fuer die
#  verfahrensgegenstaendlichen Tatbestaende die AUSSAGEKRAEFTIGSTEN:
#    * uid_shares.posted_ts    — Teilen einer Datei: die Handlung des
#                                Verbreitens (§ 184b Abs. 1 S. 1 Nr. 1).
#    * uid_downloads.time_ts   — Abruf/Download: die Handlung des
#                                Sich-Verschaffens bzw. des Abrufs
#                                (§ 184b Abs. 1 S. 1 Nr. 2, Abs. 3).
#  Beide fehlten in Build 524. Ein Fall, dessen spaeteste Handlung ein Download
#  oder ein Teilungsakt war, bekam dort einen ZU FRUEHEN Fristbeginn.
ZEITQUELLEN: Tuple[Tuple[str, str, str], ...] = (
    ("uid_posts", "posted_ts",
     "belegt: forensic_uid.db.schema.sql (Tabelle uid_posts); Sonde DEV/PROD "
     "2026-07-25 — 7562 Werte, 2019-02-28 .. 2024-07-06"),
    ("uid_pms_posts", "posted_ts",
     "belegt: forensic_uid.db.schema.sql (Tabelle uid_pms_posts); Sonde "
     "DEV/PROD 2026-07-25 — 8813 Werte, 2019-12-26 .. 2024-07-06"),
    ("uid_shares", "posted_ts",
     "belegt: forensic_uid.db.schema.sql (Tabelle uid_shares, Index "
     "uid_shares_ts_idx); Sonde DEV/PROD 2026-07-25 — 2023-01-08 .. 2024-05-12"),
    ("uid_downloads", "time_ts",
     "belegt: forensic_uid.db.schema.sql (Tabelle uid_downloads, Index "
     "uid_dl_ts_idx); Sonde DEV/PROD 2026-07-25 — 2024-02-10 .. 2024-02-16"),
)

#: Die ERSATZANKER (Build 530) — in der Reihenfolge, in der sie versucht werden.
#  (art, Tabelle, Spalte, Zusatzbedingung oder None, Belegqualitaet)
#
#  SIE SIND KEINE TATHANDLUNGEN. Sie werden nur herangezogen, wenn KEINE der
#  vier Zeitquellen einen Wert liefert, und sie erzeugen nie eine 'festgestellte'
#  Aussage. Die Reihenfolge ist von mc am 2026-07-25 festgelegt worden:
#  Registrierungsdatum -> erste ueber die 100a-Massnahme protokollierte
#  Anmeldung -> NULL.
#
#  WARUM DIE ERSTE UND NICHT DIE LETZTE ANMELDUNG: Der Ersatzanker soll den
#  fruehestmoeglichen Fristablauf erzeugen, damit der Fall eher zu frueh als zu
#  spaet auffaellt. Die spaeteste Anmeldung waere der guenstigere, aber
#  gefaehrlichere Wert.
#
#  BEWUSST NICHT VERWENDET: uid_profile.last_active und uid_profile.last_visit.
#  Beide stehen im DDL und waeren als 'Beendigung' im Sinne des § 78a StGB auf
#  den ersten Blick der passendere Anker — sie liegen aber SPAETER, erzeugen
#  also eine laengere Restlaufzeit und lassen den Fall harmloser erscheinen. Bei
#  einem Wert, den niemand festgestellt hat, ist das die falsche Richtung. Die
#  Entscheidung ist hier vermerkt, damit sie nicht als Versehen gelesen wird;
#  mc kann sie umdrehen, dann aendert sich genau diese Tabelle.
#
#  'login_success = 1': Eine fehlgeschlagene Anmeldung belegt nicht, dass der
#  Kontoinhaber im Forum war — sie kann von jedem stammen, der das Passwort
#  raet. Nur erfolgreiche Anmeldungen zaehlen.
ERSATZQUELLEN: Tuple[Tuple[str, str, str, Optional[str], str], ...] = (
    ("registrierung", "uid_profile", "registered", None,
     "belegt: forensic_uid.db.schema.sql (Tabelle uid_profile, Spalte "
     "'registered' INTEGER); Sonde DEV/PROD 2026-07-25. ACHTUNG: die Spalte "
     "enthaelt Epoch-0-Werte (1970-01-01) als Platzhalter fuer 'unbekannt' — "
     "der Plausibilitaetsrahmen faengt sie ab."),
    ("anmeldung", "uid_surveillance", "logged_at", "login_success = 1",
     "belegt: forensic_uid.db.schema.sql (Tabelle uid_surveillance, Spalten "
     "'logged_at' und 'login_success', Index uid_surv_ts_idx)"),
)

#: Plausibilitaetsrahmen fuer einen Tatzeitpunkt (Unix-Sekunden).
#
#  WARUM ES IHN GIBT: Ein INTEGER ist noch kein Zeitstempel. Die Sonde hat am
#  2026-07-25 zwei Gegenbeispiele geliefert — 'uid_profile.id' faellt
#  rechnerisch in den Epoch-Bereich (Forum-Benutzer-IDs liegen um 1,0 Mrd.), und
#  'uid_profile.registered' enthaelt Werte von 1970-01-01, also Epoch 0 als
#  Platzhalter fuer 'unbekannt'. Ohne Rahmen entstuende daraus eine Frist, die
#  plausibel AUSSIEHT.
#
#  DIE GRENZEN SIND KEINE ERFINDUNG: mc am 2026-07-25 — "Das Forum war zwischen
#  2019 und 2024 aktiv." Der Rahmen liegt grosszuegig darum (2018-01-01 bis
#  2027-01-01): er soll GROBE Fehlgriffe abfangen, nicht Feinheiten aussortieren.
#
#  KEIN STILLES VERWERFEN: Werte ausserhalb des Rahmens werden GEZAEHLT und in
#  der Antwort ausgewiesen. Ein weggelassener Wert, von dem niemand erfaehrt,
#  waere genau der Fehler, den dieser Rahmen verhindern soll.
PLAUSIBEL_VON = 1514764800     # 2018-01-01T00:00:00Z
PLAUSIBEL_BIS = 1798761600     # 2027-01-01T00:00:00Z

#: KORREKTUR EINER FALSCHEN AUSSAGE AUS BUILD 524 (Build 528).
#
#  Dort stand, fuer geteilte Dateien (share_id) existiere KEIN Zeitstempel. DAS
#  WAR FALSCH. Die Aussage beruhte auf einer Suche im QUELLTEXT dieses Projekts
#  — dort wird kein solcher Wert benutzt — und ich habe daraus geschlossen, es
#  gebe ihn nicht. Das ist ein Fehlschluss von 'der Code verwendet es nicht' auf
#  'die Daten haben es nicht'. uid_shares hat eine Spalte 'posted_ts' MIT
#  eigenem Index; sie ist seit Build 528 eine Tathandlungs-Quelle.
HINWEIS_QUELLEN = (
    "Als Tathandlung gewertet werden: Beitraege (uid_posts.posted_ts), private "
    "Nachrichten (uid_pms_posts.posted_ts), Teilungsakte "
    "(uid_shares.posted_ts) und Abrufe/Downloads (uid_downloads.time_ts). "
    "Teilungsakte und Downloads sind seit Build 528 erfasst; in Build 524 "
    "fehlten sie, weshalb der Fristbeginn dort zu frueh angesetzt sein konnte."
)

#: Der Hinweis auf den bewusst NICHT verwendeten Sicherungszeitpunkt.
HINWEIS_FETCHED_AT = (
    "pages.fetched_at (Sicherungszeitpunkt des Scrapers) wird ausdruecklich "
    "NICHT als Tatzeit verwendet."
)

#: Build 530 — der wichtigste Hinweis dieses Monitors, solange es keine
#  festgestellten Tatzeitpunkte gibt. Er steht in JEDER Antwort, damit niemand
#  eine Zahl aus dieser Liste in einen Bericht uebernimmt.
#
#  ER IST EINE ZUSTANDSAUSSAGE, KEINE DAUERAUSSAGE: sobald Ermittlerinnen
#  Tatzeitpunkte feststellen, tragen die betreffenden Zeilen 'festgestellt',
#  und die Verteilung in 'feststellung_verteilung' zeigt es. Der Text bleibt
#  richtig, weil er sagt, was die VORLAEUFIGEN Zeilen bedeuten — nicht, dass
#  alle Zeilen vorlaeufig seien.
HINWEIS_FESTSTELLUNG = (
    "VORLAEUFIG UND FESTGESTELLT: Jede Zeile traegt in 'feststellung', worauf "
    "sie beruht. 'vorlaeufig' heisst, dass das Datum aus den gesicherten Daten "
    "stammt und von KEINER Ermittlerin festgestellt wurde — es ist ein "
    "Arbeitswert fuer die Priorisierung. Der Bericht darf nur FESTGESTELLTE "
    "Daten zitieren; das Feld 'zitierfaehig' sagt es je Zeile."
)


#: Die Befundarten der Datenlage. Als Konstante, damit die Oberflaeche sie
#  gegen ihre eigene Aufzaehlung halten kann — ein neuer Befund ohne Platz in
#  der Sicht wuerde sonst aus der Zaehlung fallen (Build 527).
DATENLAGE_BEFUNDE: Tuple[str, ...] = (
    "belegt", "belegt_unvollstaendig", "ohne_tatzeit", "zeitspalte_unlesbar",
    "ohne_zeittabelle", "ohne_forensic_db", "nicht_lesbar",
)

#: Die Befunde, bei denen ein Fristbeginn VORLIEGT (mit oder ohne Einschraenkung).
BEFUNDE_MIT_TATZEIT: Tuple[str, ...] = ("belegt", "belegt_unvollstaendig")


@dataclass(frozen=True)
class CaseTatzeit:
    """Der belegte Tatzeitrahmen eines Falls (oder der Grund, warum keiner da ist)."""
    subject_id: int
    username: str
    frueheste_ts: Optional[int]
    spaeteste_ts: Optional[int]
    quellen: Tuple[str, ...]        # welche Quellen etwas geliefert haben
    befund: str                     # s. DATENLAGE_BEFUNDE
    detail: str
    # Build 527: welche Quellen NICHT lesbar waren, je Eintrag mit dem
    # SQLite-Grund. Das Feld ist auch bei 'belegt_unvollstaendig' gefuellt —
    # gerade dort ist es die eigentliche Information.
    quellen_fehler: Tuple[str, ...] = ()
    # Build 528: Zahl der Zeitwerte AUSSERHALB des Plausibilitaetsrahmens. Sie
    # gehen nicht in die Spanne ein, verschwinden aber auch nicht: eine hohe
    # Zahl deutet darauf, dass eine Spalte etwas anderes fuehrt als eine Zeit.
    unplausible_werte: int = 0
    # -- Build 530: der Ersatzanker ------------------------------------------
    # 'aktivitaet' | 'registrierung' | 'anmeldung' | 'keine'. WELCHER Zeitpunkt
    # der Rechnung zugrunde liegt. 'befund' bleibt unveraendert die Aussage
    # ueber die AKTIVITAETSquellen — die beiden Achsen werden bewusst nicht
    # vermischt, sonst waere ein Fall mit Ersatzanker nicht mehr von einem mit
    # belegter Tathandlung zu unterscheiden.
    anker_art: str = "keine"
    anker_ts: Optional[int] = None
    anker_beleg: str = ""
    # Ersatzquellen, die nicht lesbar waren (mit SQLite-Grund).
    ersatz_fehler: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject_id": self.subject_id, "username": self.username,
            "frueheste_ts": self.frueheste_ts,
            "spaeteste_ts": self.spaeteste_ts,
            "quellen": list(self.quellen),
            "befund": self.befund, "detail": self.detail,
            "quellen_fehler": list(self.quellen_fehler),
            "unplausible_werte": self.unplausible_werte,
            "anker_art": self.anker_art,
            "anker_ts": self.anker_ts,
            "anker_beleg": self.anker_beleg,
            "ersatz_fehler": list(self.ersatz_fehler),
        }


@dataclass(frozen=True)
class LimitationRow:
    """Eine Zeile des Monitors: Tatzeitrahmen + Fristeinschaetzung."""
    tatzeit: CaseTatzeit
    assessment: LimitationAssessment
    # Build 535: die Lage der FESTGESTELLTEN Tatzeit. Optional, damit
    # bestehende Aufrufer (Tests, Werkzeuge) eine Zeile ohne sie bauen
    # koennen — im Monitor ist sie IMMER gesetzt, notfalls mit dem Befund
    # 'nicht_geprueft'.
    tatzeit_anker: Optional[TatzeitAnker] = None

    def to_dict(self) -> Dict[str, Any]:
        out = self.tatzeit.to_dict()
        out.update(self.assessment.to_dict())
        # Build 535: die Felder der festgestellten Tatzeit tragen alle das
        # Praefix 'tatzeit_feststellung_'/'tatzeit_' und ueberschreiben deshalb
        # nichts. Fehlt der Anker ganz (Aufrufer ohne Build-535-Kenntnis), wird
        # das AUSGEWIESEN und nicht als "nichts festgestellt" ausgegeben.
        if self.tatzeit_anker is not None:
            out.update(self.tatzeit_anker.to_dict())
        else:
            out["tatzeit_feststellung_befund"] = "nicht_geprueft"
            out["tatzeit_feststellung_detail"] = (
                "Diese Zeile wurde ohne Tatzeit-Auswertung gebaut.")
        # 'befund' kommt in BEIDEN Teilen vor und bedeutet Verschiedenes: im
        # Tatzeitteil die Datenlage, in der Einschaetzung die Rechtsfolge. Die
        # Datenlage wird deshalb umbenannt statt ueberschrieben — ein
        # ueberschriebener Befund waere ein verlorener Beleg.
        out["tatzeit_befund"] = self.tatzeit.befund
        out["tatzeit_detail"] = self.tatzeit.detail
        out["befund"] = self.assessment.befund
        out["detail"] = self.tatzeit.detail
        # 'anker_art' steht in BEIDEN Teilen und ist per Konstruktion gleich
        # (compute() reicht den Wert des Tatzeitteils an die Rechenschicht
        # weiter). Beide bleiben trotzdem erhalten und werden VERGLICHEN — eine
        # stille Abweichung waere ein Fehler in der Verdrahtung, und der soll
        # sich zeigen, statt von der Reihenfolge im dict verdeckt zu werden.
        out["tatzeit_anker_art"] = self.tatzeit.anker_art
        out["anker_art"] = self.assessment.anker_art
        out["anker_art_stimmig"] = (
            self.tatzeit.anker_art == self.assessment.anker_art)
        return out


@dataclass(frozen=True)
class LimitationReport:
    """Der Monitor als Ganzes."""
    stichtag: str
    vorwarn_tage: int
    aussage_moeglich: bool
    verweigerungsgrund: Optional[str]
    params_stand: str
    params_bestaetigt: bool
    params_bestaetigt_von: Optional[str]
    params_bestaetigt_am: Optional[str]
    vorgabe_tatbestaende: Tuple[str, ...]
    vorbehalte: Tuple[str, ...]
    hinweise: Tuple[str, ...]
    faelle_gesamt: int
    zaehler: Dict[str, int]         # je Ampelzustand
    datenlage: Dict[str, int]       # je Tatzeit-Befund
    rows: Tuple[LimitationRow, ...]
    # Build 527: das AGGREGAT der Lesefehler — Fehlertext -> Anzahl Faelle.
    # Es ersetzt den Protokoll-Schwall durch EINE nachpruefbare Zahl und macht
    # den systematischen Ausfall sichtbar: '162 Faelle, ein und derselbe
    # Fehler' ist eine Schema-Aussage, '1 Fall' waere eine Datei-Aussage.
    quellenfehler: Dict[str, int] = field(default_factory=dict)
    faelle_mit_quellenfehler: int = 0
    # Build 528: Summe der Zeitwerte ausserhalb des Plausibilitaetsrahmens und
    # die Zahl der betroffenen Faelle. Systematisch hohe Werte sind ein Hinweis
    # darauf, dass eine Spalte etwas anderes fuehrt als eine Zeit.
    unplausible_werte: int = 0
    faelle_mit_unplausiblen: int = 0
    # Build 530: Verteilung ueber die beiden zur Ampel orthogonalen Achsen.
    # Sie beantworten die Leitungsfrage 'worauf beruhen diese Zahlen?' in
    # einem Blick — ohne dass jemand 162 Zeilen durchsehen muss.
    anker_verteilung: Dict[str, int] = field(default_factory=dict)
    feststellung_verteilung: Dict[str, int] = field(default_factory=dict)
    ersatzfehler: Dict[str, int] = field(default_factory=dict)
    # Build 535: die Lage der FESTGESTELLTEN Tatzeit, getrennt von der
    # Datenlage der Aktivitaetsquellen. Zusammengelegt waere nicht mehr zu
    # sehen, ob einem Fall die Feststellung fehlt oder die Aktivitaetsdaten.
    tatzeit_befunde: Dict[str, int] = field(default_factory=dict)
    tatzeitfehler: Dict[str, int] = field(default_factory=dict)
    #: Faelle mit MEHREREN festgestellten Tatzeitraeumen verschiedener
    #  Beendigung. Nur dort ist die Auswahl 'frueheste' eine Entscheidung.
    faelle_mehrdeutig: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stichtag": self.stichtag,
            "vorwarn_tage": self.vorwarn_tage,
            "aussage_moeglich": self.aussage_moeglich,
            "verweigerungsgrund": self.verweigerungsgrund,
            "params_stand": self.params_stand,
            "params_bestaetigt": self.params_bestaetigt,
            "params_bestaetigt_von": self.params_bestaetigt_von,
            "params_bestaetigt_am": self.params_bestaetigt_am,
            "vorgabe_tatbestaende": list(self.vorgabe_tatbestaende),
            "vorbehalte": list(self.vorbehalte),
            "hinweise": list(self.hinweise),
            "faelle_gesamt": self.faelle_gesamt,
            "zaehler": dict(self.zaehler),
            "datenlage": dict(self.datenlage),
            "quellenfehler": dict(self.quellenfehler),
            "faelle_mit_quellenfehler": self.faelle_mit_quellenfehler,
            "unplausible_werte": self.unplausible_werte,
            "faelle_mit_unplausiblen": self.faelle_mit_unplausiblen,
            "plausibel_von": PLAUSIBEL_VON, "plausibel_bis": PLAUSIBEL_BIS,
            "datenlage_befunde": list(DATENLAGE_BEFUNDE),
            "anker_verteilung": dict(self.anker_verteilung),
            "feststellung_verteilung": dict(self.feststellung_verteilung),
            "ersatzfehler": dict(self.ersatzfehler),
            "anker_arten": list(ANKER_ARTEN),
            "feststellungen": list(FESTSTELLUNGEN),
            "tatzeit_befunde": dict(self.tatzeit_befunde),
            "tatzeit_befund_arten": list(TATZEIT_BEFUNDE),
            "tatzeitfehler": dict(self.tatzeitfehler),
            "faelle_mehrdeutig": self.faelle_mehrdeutig,
            "rows": [r.to_dict() for r in self.rows],
        }


def _tag_iso(ts: int) -> str:
    """Unix-Sekunden -> ISO-Tag (UTC). Nur fuer Meldungstexte."""
    from datetime import datetime, timezone
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (name,)).fetchone() is not None


def _lese_ersatzanker(con: sqlite3.Connection
                      ) -> Tuple[str, Optional[int], str, Tuple[str, ...]]:
    """
    Der Ersatzanker (Build 530) — nur aufzurufen, wenn KEINE Tathandlung mit
    Zeitstempel vorliegt.

    -> (art, ts, beleg, fehler). art ist 'keine', wenn nichts gefunden wurde.

    Es wird der FRUEHESTE plausible Wert genommen (MIN), und die Quellen werden
    in der von mc festgelegten Reihenfolge versucht: Registrierung vor erster
    protokollierter Anmeldung. Die erste Quelle, die einen plausiblen Wert
    liefert, gewinnt — es wird NICHT ueber Quellen hinweg das Minimum gebildet,
    weil die Reihenfolge eine Rangfolge der Aussagekraft ist und kein
    Rechenweg.

    Wie ueberall in diesem Modul: eine unlesbare Quelle wirft nicht, sie wird
    BENANNT und mitgefuehrt.
    """
    fehler: List[str] = []
    for art, tabelle, spalte, bedingung, beleg in ERSATZQUELLEN:
        if not _table_exists(con, tabelle):
            fehler.append("%s: Tabelle nicht vorhanden" % tabelle)
            continue
        where = "%s BETWEEN ? AND ?" % spalte
        if bedingung:
            where += " AND %s" % bedingung
        try:
            row = con.execute(
                "SELECT MIN(%s) FROM %s WHERE %s" % (spalte, tabelle, where),
                (PLAUSIBEL_VON, PLAUSIBEL_BIS)).fetchone()
        except sqlite3.Error as exc:
            fehler.append("%s.%s: %s" % (tabelle, spalte, exc))
            continue
        if row is not None and row[0] is not None:
            return art, int(row[0]), beleg, tuple(fehler)
    return "keine", None, "", tuple(fehler)


def read_tatzeit(path: Path, subject_id: int, username: str) -> CaseTatzeit:
    """
    Liest den Tatzeitrahmen aus EINER forensic_<uid>.db (read-only).

    Reine E/A-Funktion ohne Rechtsbewertung — dadurch getrennt testbar. Sie
    wirft NICHT: jeder Fehlerfall wird zu einem benannten Befund, damit der
    Fall in der Liste BLEIBT.

    Build 527: ein Lesefehler an einer Zeitquelle wird MITGEFUEHRT
    (quellen_fehler) und aendert den Befund. Frueher verschwand er in einer
    Protokollzeile, und der Fall sah entweder unverdaechtig ('belegt') oder
    falsch beschrieben ('kein Zeitstempel gesetzt') aus.
    """
    if not path.exists():
        return CaseTatzeit(
            subject_id=subject_id, username=username, frueheste_ts=None,
            spaeteste_ts=None, quellen=(), befund="ohne_forensic_db",
            detail="forensic_%d.db fehlt (%s)" % (subject_id, path.parent))

    try:
        con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    except sqlite3.Error as exc:
        return CaseTatzeit(
            subject_id=subject_id, username=username, frueheste_ts=None,
            spaeteste_ts=None, quellen=(), befund="nicht_lesbar",
            detail="nicht oeffenbar: %s" % exc)

    try:
        vorhanden = [q for q in ZEITQUELLEN if _table_exists(con, q[0])]
        if not vorhanden:
            art, a_ts, a_beleg, a_fehler = _lese_ersatzanker(con)
            return CaseTatzeit(
                subject_id=subject_id, username=username, frueheste_ts=None,
                spaeteste_ts=None, quellen=(), befund="ohne_zeittabelle",
                detail="weder %s vorhanden"
                       % " noch ".join(q[0] for q in ZEITQUELLEN),
                anker_art=art, anker_ts=a_ts, anker_beleg=a_beleg,
                ersatz_fehler=a_fehler)

        frueheste: Optional[int] = None
        spaeteste: Optional[int] = None
        quellen: List[str] = []
        fehler: List[str] = []
        unplausibel = 0
        for tabelle, spalte, _beleg in vorhanden:
            try:
                # EINE Abfrage, ein Tabellendurchlauf: Spanne der PLAUSIBLEN
                # Werte UND die Zahl der verworfenen. Der Filter steht in SQL
                # und nicht in Python, damit auch bei Millionen Zeilen nur zwei
                # Zahlen zurueckkommen; die verworfenen werden GEZAEHLT und
                # spaeter ausgewiesen (kein stilles Verwerfen).
                row = con.execute(
                    "SELECT MIN(CASE WHEN %s BETWEEN ? AND ? THEN %s END), "
                    "       MAX(CASE WHEN %s BETWEEN ? AND ? THEN %s END), "
                    "       SUM(CASE WHEN %s IS NOT NULL "
                    "                AND (%s < ? OR %s > ?) THEN 1 ELSE 0 END) "
                    "FROM %s"
                    % (spalte, spalte, spalte, spalte, spalte, spalte, spalte,
                       tabelle),
                    (PLAUSIBEL_VON, PLAUSIBEL_BIS, PLAUSIBEL_VON,
                     PLAUSIBEL_BIS, PLAUSIBEL_VON, PLAUSIBEL_BIS)).fetchone()
            except sqlite3.Error as exc:
                # EINE unlesbare Quelle darf die andere nicht mitreissen — aber
                # sie darf auch nicht in einer Protokollzeile verschwinden. Der
                # Grund faehrt am Fall MIT (Build 527). Protokolliert wird hier
                # nur auf DEBUG; die Zusammenfassung macht LimitationRepo EINMAL
                # je Abruf (bei 162 Dateien waren es sonst 162 Warnungen).
                fehler.append("%s.%s: %s" % (tabelle, spalte, exc))
                logger.debug("limitation: %s.%s in %s nicht lesbar (%s)",
                             tabelle, spalte, path.name, exc)
                continue
            if row is not None and row[2]:
                unplausibel += int(row[2])
            if row is None or row[0] is None:
                # Kein plausibler Wert in dieser Quelle. Das ist KEIN Fehler der
                # Quelle — sie kann schlicht leer sein — und wird deshalb hier
                # nicht vermerkt; die Zahl der unplausiblen Werte steht bereits
                # in 'unplausibel'.
                continue
            lo, hi = int(row[0]), int(row[1])
            frueheste = lo if frueheste is None else min(frueheste, lo)
            spaeteste = hi if spaeteste is None else max(spaeteste, hi)
            quellen.append("%s.%s" % (tabelle, spalte))

        if spaeteste is None:
            # KEINE Tathandlung mit Zeitstempel -> jetzt (und NUR jetzt) darf
            # der Ersatzanker herangezogen werden (Build 530).
            art, a_ts, a_beleg, a_fehler = _lese_ersatzanker(con)
            # ZWEI VERSCHIEDENE LAGEN, die frueher beide 'ohne_tatzeit' hiessen.
            if fehler:
                return CaseTatzeit(
                    subject_id=subject_id, username=username,
                    frueheste_ts=None, spaeteste_ts=None, quellen=(),
                    befund="zeitspalte_unlesbar",
                    detail="KEINE Zeitquelle lesbar — es ist damit UNBEKANNT, "
                           "ob Zeitstempel vorliegen: %s" % "; ".join(fehler),
                    quellen_fehler=tuple(fehler),
                    unplausible_werte=unplausibel,
                    anker_art=art, anker_ts=a_ts, anker_beleg=a_beleg,
                    ersatz_fehler=a_fehler)
            return CaseTatzeit(
                subject_id=subject_id, username=username, frueheste_ts=None,
                spaeteste_ts=None, quellen=(), befund="ohne_tatzeit",
                detail="Zeittabelle(n) und Spalten lesbar (%s), aber kein "
                       "einziger Zeitstempel im Plausibilitaetsrahmen "
                       "(%d Wert(e) lagen ausserhalb und sind nicht "
                       "eingegangen)"
                       % (", ".join(q[0] for q in vorhanden), unplausibel),
                unplausible_werte=unplausibel,
                anker_art=art, anker_ts=a_ts, anker_beleg=a_beleg,
                ersatz_fehler=a_fehler)

        if fehler:
            # DER GEFAEHRLICHE FALL: es gibt einen Wert, aber nicht aus allen
            # Quellen. Er ist NIE einfach 'belegt'.
            return CaseTatzeit(
                subject_id=subject_id, username=username,
                frueheste_ts=frueheste, spaeteste_ts=spaeteste,
                quellen=tuple(quellen), befund="belegt_unvollstaendig",
                detail="Fristbeginn NUR aus %s gebildet; nicht lesbar war: %s. "
                       "Fehlen dadurch SPAETERE Handlungen, ist der "
                       "Fristbeginn zu frueh angesetzt und die Frist zu kurz "
                       "gerechnet — der Fall erscheint dringender als er ist."
                       % (", ".join(quellen), "; ".join(fehler)),
                quellen_fehler=tuple(fehler),
                unplausible_werte=unplausibel,
                anker_art="aktivitaet", anker_ts=spaeteste,
                anker_beleg="; ".join(quellen))

        return CaseTatzeit(
            subject_id=subject_id, username=username, frueheste_ts=frueheste,
            spaeteste_ts=spaeteste, quellen=tuple(quellen), befund="belegt",
            detail="Fristbeginn = spaeteste belegte Tathandlung (§ 78a StGB); "
                   "frueheste Handlung zum Vergleich mitgefuehrt",
            unplausible_werte=unplausibel,
            anker_art="aktivitaet", anker_ts=spaeteste,
            anker_beleg="; ".join(quellen))
    except sqlite3.Error as exc:
        return CaseTatzeit(
            subject_id=subject_id, username=username, frueheste_ts=None,
            spaeteste_ts=None, quellen=(), befund="nicht_lesbar",
            detail="nicht lesbar: %s" % exc)
    finally:
        try:
            con.close()
        except sqlite3.Error:               # pragma: no cover
            pass


class LimitationRepo:
    """
    Read-Model: Fristenmonitor ueber alle Faelle.

    coordinator.db liefert die Fallliste (subject_id, username), die
    forensic_<uid>.db den Fristbeginn. NICHT scope-behaftet — die Auswahl der
    Faelle trifft der Endpunkt; Fristenkontrolle ist eine Leitungsaufgabe.
    """

    def __init__(self, con: sqlite3.Connection, forensic_dir: Any,
                 evidence_dir: Any = None) -> None:
        """
        evidence_dir — Verzeichnis der evidence_<uid>.db, aus denen die
        FESTGESTELLTE Tatzeit gelesen wird (Build 535).

        FEHLT ES, WIRD NICHT STILL WEITERGERECHNET. Jede Zeile bekommt dann den
        Befund 'nicht_geprueft' und der Bericht einen Hinweis. Der Unterschied
        zwischen "nachgesehen und nichts gefunden" und "nicht nachgesehen"
        entscheidet darueber, ob jemand nachsieht — er darf nicht in einem
        Vorgabewert verschwinden (Grundregel 1).
        """
        self._con = con
        self._forensic = Path(forensic_dir)
        self._evidence = Path(evidence_dir) if evidence_dir else None

    def _cases(self, subject_ids: Optional[Sequence[int]] = None
               ) -> List[Tuple[int, str]]:
        if subject_ids is not None and len(subject_ids) == 0:
            # Eine LEERE Auswahl ist eine Auswahl und bedeutet ausdruecklich
            # NICHT "alle" (Muster coverage_repo.py:82-83).
            return []
        sql = "SELECT subject_id, username FROM cases"
        args: Tuple[Any, ...] = ()
        if subject_ids is not None:
            sql += " WHERE subject_id IN (%s)" % ",".join(
                "?" * len(subject_ids))
            args = tuple(int(s) for s in subject_ids)
        sql += " ORDER BY subject_id"
        return [(int(r[0]), str(r[1] or "?"))
                for r in self._con.execute(sql, args).fetchall()]

    def _tatzeit_anker(self, subject_id: int) -> TatzeitAnker:
        """
        Die festgestellte Tatzeit eines Falls (Build 535).

        Ohne evidence-Verzeichnis wird NICHT nachgesehen — und das wird auch so
        gesagt. 'nicht_geprueft' ist ein eigener Befund und ausdruecklich nicht
        dasselbe wie 'ohne_feststellung': das eine heisst "nicht nachgesehen",
        das andere "nachgesehen, nichts gefunden". In einer Ermittlungsakte
        duerfen die beiden nicht gleich aussehen.
        """
        if self._evidence is None:
            return nicht_geprueft(
                subject_id,
                "Kein evidence-Verzeichnis uebergeben — die festgestellte "
                "Tatzeit wurde NICHT geprueft.")
        return read_tatzeit_anker(
            self._evidence / ("evidence_%d.db" % subject_id), subject_id)

    def compute(self, *, params: LimitationParams, now_ts: int,
                vorwarn_tage: int = DEFAULT_VORWARN_TAGE,
                subject_ids: Optional[Sequence[int]] = None
                ) -> LimitationReport:
        """
        Der ganze Monitor. Rein lesend, deterministisch fuer festes now_ts.

        SORTIERUNG: das Dringlichste zuerst — 'ueberschritten' vor 'knapp' vor
        dem Rest, innerhalb dessen nach Restlaufzeit. Faelle OHNE Aussage
        ('ohne_tatzeit', 'ohne_fassung') stehen NICHT am Ende, sondern direkt
        hinter den knappen: sie sind ungeprueft, und Ungeprueftes darf nicht
        unter Unverdaechtiges rutschen (Grundregel 1).
        """
        rows: List[LimitationRow] = []
        zaehler: Dict[str, int] = {}
        datenlage: Dict[str, int] = {}
        quellenfehler: Dict[str, int] = {}
        ersatzfehler: Dict[str, int] = {}
        anker_verteilung: Dict[str, int] = {}
        feststellung_verteilung: Dict[str, int] = {}
        # Build 535: die Lage der FESTGESTELLTEN Tatzeit, getrennt gefuehrt von
        # der Datenlage der Aktivitaetsquellen. Zwei Achsen, zwei Zaehlungen —
        # zusammengelegt waere nicht mehr zu sehen, ob ein Fall keine
        # Feststellung hat oder keine Aktivitaetsdaten.
        tatzeit_befunde: Dict[str, int] = {}
        tatzeitfehler: Dict[str, int] = {}
        mehrdeutig_gesamt = 0
        mit_fehler = 0
        unplausibel_gesamt = 0
        mit_unplausiblen = 0

        for subject_id, username in self._cases(subject_ids):
            pfad = self._forensic / ("forensic_%d.db" % subject_id)
            tatzeit = read_tatzeit(pfad, subject_id, username)
            datenlage[tatzeit.befund] = datenlage.get(tatzeit.befund, 0) + 1
            if tatzeit.unplausible_werte:
                unplausibel_gesamt += tatzeit.unplausible_werte
                mit_unplausiblen += 1
            if tatzeit.quellen_fehler:
                mit_fehler += 1
                for eintrag in tatzeit.quellen_fehler:
                    quellenfehler[eintrag] = quellenfehler.get(eintrag, 0) + 1
            for eintrag in tatzeit.ersatz_fehler:
                ersatzfehler[eintrag] = ersatzfehler.get(eintrag, 0) + 1
            # Build 530: gerechnet wird ab dem ANKER, nicht mehr fest ab der
            # spaetesten Tathandlung. Bei 'aktivitaet' sind beide identisch;
            # bei einem Ersatzanker ist anker_ts der einzige verfuegbare Wert.
            #
            # --- Build 535: DIE UMSCHALTUNG ---------------------------------
            # Bis Build 534 stand hier fest 'festgestellt=False', mit dem
            # Vermerk: "eine von einer Ermittlerin FESTGESTELLTE Tatzeit gibt
            # es in den ausgewerteten Datenbanken noch nicht ... Sobald es sie
            # gibt, aendert sich GENAU diese Zeile." Sie gibt es seit Build
            # 533/534, und dies ist die angekuendigte Aenderung.
            #
            # RANGFOLGE: Eine festgestellte Tatzeit SCHLAEGT jeden anderen
            # Anker — auch dann, wenn sie frueher liegt als die spaeteste
            # belegte Tathandlung. Das ist der Sinn der Achse 'feststellung':
            # was ein Mensch festgestellt hat, wiegt schwerer als was aus
            # Aktivitaetsdaten abgeleitet wurde. Der Aktivitaetsbefund
            # ('tatzeit.befund') bleibt davon UNBERUEHRT und wird weiter
            # ausgewiesen — die beiden Achsen werden nicht vermischt.
            anker = self._tatzeit_anker(subject_id)
            tatzeit_befunde[anker.befund] = tatzeit_befunde.get(
                anker.befund, 0) + 1
            for eintrag in anker.fehler:
                tatzeitfehler[eintrag] = tatzeitfehler.get(eintrag, 0) + 1
            if anker.mehrdeutig:
                mehrdeutig_gesamt += 1

            if anker.hat_anker:
                anker_ts = anker.frueheste_beendigung
                anker_art = "tatzeit"
                festgestellt = True
            else:
                anker_ts = tatzeit.anker_ts
                anker_art = tatzeit.anker_art
                festgestellt = False

            # Der Tatzeitteil der Zeile fuehrt DENSELBEN Anker wie die
            # Rechenschicht — sonst schluege die Stimmigkeitspruefung in
            # LimitationRow.to_dict() an, und zwar zu Recht.
            if anker.hat_anker:
                tatzeit = replace(
                    tatzeit, anker_art="tatzeit", anker_ts=anker_ts,
                    anker_beleg="festgestellte Tatzeit aus "
                                "evidence_%d.db (annotation_tatzeit); %s"
                                % (subject_id, anker.detail))

            a = assess_limitation(tatzeit_ts=anker_ts,
                                  params=params, now_ts=now_ts,
                                  vorwarn_tage=vorwarn_tage,
                                  anker_art=anker_art,
                                  festgestellt=festgestellt)
            zaehler[a.ampel] = zaehler.get(a.ampel, 0) + 1
            anker_verteilung[a.anker_art] = (
                anker_verteilung.get(a.anker_art, 0) + 1)
            feststellung_verteilung[a.feststellung] = (
                feststellung_verteilung.get(a.feststellung, 0) + 1)
            rows.append(LimitationRow(tatzeit=tatzeit, assessment=a,
                                      tatzeit_anker=anker))

        rang = {"ueberschritten": 0, "knapp": 1, "ohne_tatzeit": 2,
                "ohne_anker": 3, "ohne_fassung": 4, "ruht": 5, "offen": 6,
                "keine_aussage": 7}
        rows.sort(key=lambda r: (
            rang.get(r.assessment.ampel, 9),
            # Build 527: bei gleicher Ampel steht das EINGESCHRAENKT Belegte
            # vorn. Wer die Liste von oben liest, sieht zuerst die Zeilen, deren
            # Zahl unter Vorbehalt steht.
            0 if r.tatzeit.quellen_fehler else 1,
            # Build 530: danach das auf einem ERSATZANKER Beruhende. Auch das
            # ist eine Zahl unter Vorbehalt, nur eine Stufe schwaecher.
            0 if r.assessment.anker_art in ("registrierung", "anmeldung")
            else 1,
            # Build 535: bei sonst gleichem Rang steht das MEHRDEUTIGE vorn —
            # ein Fall mit mehreren festgestellten Tatzeitraeumen traegt eine
            # Auswahlentscheidung in sich und gehoert vor einen eindeutigen.
            0 if (r.tatzeit_anker is not None and r.tatzeit_anker.mehrdeutig)
            else 1,
            r.assessment.restlaufzeit_tage
            if r.assessment.restlaufzeit_tage is not None else 10 ** 9,
            r.tatzeit.subject_id))

        # EINE Zusammenfassung statt einer Warnung je Datei. Ein Fehler, der bei
        # ALLEN Faellen gleich lautet, ist ein Schema-Befund und keine
        # Dateistoerung — genau das soll die Zeile sagen.
        if quellenfehler:
            logger.warning(
                "limitation: bei %d von %d Faellen war eine Zeitquelle nicht "
                "lesbar. Aufschluesselung: %s", mit_fehler, len(rows),
                "; ".join("%s (%dx)" % (k, v)
                          for k, v in sorted(quellenfehler.items())))

        grund = params.verweigerungsgrund()

        # Der Lesefehler gehoert in die HINWEISE der Antwort, nicht nur ins
        # Protokoll: die Sicht und der Export zeigen die Hinweise, das
        # Serverprotokoll sieht niemand, der die Liste liest.
        hinweise = [HINWEIS_QUELLEN, HINWEIS_FETCHED_AT, HINWEIS_FESTSTELLUNG]

        # --- Build 535: die Lage der festgestellten Tatzeit ------------------
        # Reihenfolge der Einfuegungen: das Dringendste zuletzt eingefuegt,
        # weil insert(0) nach vorne schiebt. Das Dringendste ist hier "gar
        # nicht geprueft" — eine Liste, die aussieht wie ausgewertet, es aber
        # nicht ist, waere der gefaehrlichste denkbare Beleg.
        anzahl_festgestellt = tatzeit_befunde.get("festgestellt", 0)
        if anzahl_festgestellt:
            hinweise.insert(0,
                "%d von %d Faellen rechnen mit einer FESTGESTELLTEN Tatzeit "
                "(Ankerart 'tatzeit'). Bei mehreren festgestellten "
                "Tatzeitraeumen verankert die FRUEHESTE Beendigung die Frist "
                "(Entscheidung mc 2026-07-26); die spaeteste faehrt je Zeile "
                "in 'tatzeit_spaeteste_beendigung' mit und rechnet NICHT. "
                "ACHTUNG — das ist die Gegenrichtung zu den Aktivitaetsdaten, "
                "wo die SPAETESTE Handlung verankert."
                % (anzahl_festgestellt, len(rows)))
        if mehrdeutig_gesamt:
            hinweise.insert(0,
                "%d Fall/Faelle tragen MEHRERE festgestellte Tatzeitraeume mit "
                "verschiedener Beendigung. Dort ist die Auswahl des Ankers "
                "eine Entscheidung und keine Ablesung — ob mehrere Handlungen "
                "eine Tat im Rechtssinne bilden, bewertet dieses Werkzeug "
                "NICHT." % mehrdeutig_gesamt)
        if tatzeitfehler:
            hinweise.insert(0,
                "Beim Lesen der festgestellten Tatzeit war mindestens eine "
                "Abfrage nicht ausfuehrbar: %s. Betroffene Faelle koennen "
                "deshalb ohne Feststellung dastehen, obwohl eine vorhanden "
                "waere."
                % "; ".join("%s (%dx)" % (k, v)
                            for k, v in sorted(tatzeitfehler.items())))
        anzahl_ohne_tabelle = tatzeit_befunde.get("ohne_tabelle", 0)
        if anzahl_ohne_tabelle:
            hinweise.insert(0,
                "%d von %d Beweismitteldatenbanken fuehren die Tabelle "
                "'annotation_tatzeit' NICHT — die evidence-Migration m002 ist "
                "dort nicht angewandt. Fuer diese Faelle ist NICHT gesagt, "
                "dass nichts festgestellt wurde; es wurde nur nichts gefunden, "
                "weil es den Ort dafuer noch nicht gibt."
                % (anzahl_ohne_tabelle, len(rows)))
        anzahl_ungeprueft = tatzeit_befunde.get("nicht_geprueft", 0)
        if anzahl_ungeprueft:
            hinweise.insert(0,
                "DIE FESTGESTELLTE TATZEIT WURDE NICHT GEPRUEFT (%d von %d "
                "Faellen): dem Monitor wurde kein evidence-Verzeichnis "
                "uebergeben. Alle Zeilen beruhen ausschliesslich auf "
                "Aktivitaetsdaten und Ersatzankern und sind damit durchweg "
                "VORLAEUFIG — auch dort, wo eine Feststellung vorliegen mag."
                % (anzahl_ungeprueft, len(rows)))
        ersatz_anzahl = sum(anker_verteilung.get(a, 0)
                            for a in ("registrierung", "anmeldung"))
        if ersatz_anzahl:
            hinweise.insert(0,
                "%d von %d Faellen tragen einen ERSATZANKER (Registrierung: "
                "%d, erste protokollierte Anmeldung: %d) statt einer belegten "
                "Tathandlung. Diese Zeitpunkte liegen am ANFANG der "
                "Zugehoerigkeit, waehrend § 78a StGB an die BEENDIGUNG "
                "anknuepft — die dort ausgewiesenen Fristablaeufe sind ZU FRUEH "
                "und die Faelle erscheinen DRINGENDER, als sie nach den "
                "bekannten Tatsachen sind. Sie sind Arbeitswerte, keine "
                "Fristfeststellungen."
                % (ersatz_anzahl, len(rows),
                   anker_verteilung.get("registrierung", 0),
                   anker_verteilung.get("anmeldung", 0)))
        if ersatzfehler:
            hinweise.insert(0,
                "Bei der Ermittlung des Ersatzankers war mindestens eine Quelle "
                "nicht lesbar: %s. Betroffene Faelle koennen deshalb ohne Anker "
                "dastehen, obwohl einer vorhanden waere."
                % "; ".join("%s (%dx)" % (k, v)
                            for k, v in sorted(ersatzfehler.items())))
        if unplausibel_gesamt:
            hinweise.insert(0,
                "%d Zeitwert(e) in %d Fall/Faellen lagen AUSSERHALB des "
                "Plausibilitaetsrahmens (%s bis %s) und sind nicht in die "
                "Fristrechnung eingegangen. Sie sind damit nicht verschwiegen, "
                "aber auch nicht verwertet — eine hohe Zahl deutet darauf, dass "
                "eine Spalte etwas anderes fuehrt als eine Zeit."
                % (unplausibel_gesamt, mit_unplausiblen,
                   _tag_iso(PLAUSIBEL_VON), _tag_iso(PLAUSIBEL_BIS)))
        if quellenfehler:
            hinweise.insert(0,
                "ACHTUNG — DATENLAGE EINGESCHRAENKT: bei %d von %d Faellen war "
                "eine Zeitquelle nicht lesbar (%s). Faelle mit dem Befund "
                "'belegt_unvollstaendig' tragen einen Fristbeginn, der NUR aus "
                "den lesbaren Quellen gebildet ist; Faelle mit "
                "'zeitspalte_unlesbar' tragen gar keinen. Vor einer "
                "Fristentscheidung ist die Ursache zu klaeren."
                % (mit_fehler, len(rows),
                   "; ".join("%s (%dx)" % (k, v)
                             for k, v in sorted(quellenfehler.items()))))
        hinweise = tuple(hinweise)

        # Der Stichtag kommt aus der Rechenschicht, damit es genau EINE Stelle
        # gibt, die Unix-Sekunden in einen Kalendertag umrechnet.
        stichtag = assess_limitation(
            tatzeit_ts=None, params=params, now_ts=now_ts,
            vorwarn_tage=vorwarn_tage).stichtag

        return LimitationReport(
            stichtag=stichtag, vorwarn_tage=max(0, int(vorwarn_tage)),
            aussage_moeglich=(grund is None), verweigerungsgrund=grund,
            params_stand=params.stand, params_bestaetigt=params.bestaetigt,
            params_bestaetigt_von=params.bestaetigt_von,
            params_bestaetigt_am=params.bestaetigt_am,
            vorgabe_tatbestaende=params.vorgabe_tatbestaende,
            vorbehalte=params.vorbehalte,
            hinweise=hinweise,
            faelle_gesamt=len(rows), zaehler=zaehler, datenlage=datenlage,
            rows=tuple(rows), quellenfehler=quellenfehler,
            faelle_mit_quellenfehler=mit_fehler,
            unplausible_werte=unplausibel_gesamt,
            faelle_mit_unplausiblen=mit_unplausiblen,
            anker_verteilung=anker_verteilung,
            feststellung_verteilung=feststellung_verteilung,
            ersatzfehler=ersatzfehler,
            tatzeit_befunde=tatzeit_befunde,
            tatzeitfehler=tatzeitfehler,
            faelle_mehrdeutig=mehrdeutig_gesamt)
