# =============================================================================
# management/maintenance/postid_nachtrag.py
# IT-Forensisches Ermittlungswerkzeug - Nachtrag der Beitragsnummer
# =============================================================================
# Zweck:
#   DIE BEITRAGSNUMMER FUER DEN BESTAND NACHTRAGEN. In evidence_<uid>.db ist
#   'annotations.post_id' bei Textmarkierungen leer. Diese Klasse bestimmt
#   sie aus dem GESICHERTEN SEITENABZUG und traegt sie ein.
#
#   Die Klasse ist der ganze Vorgang; tools/postid_nachtragen.py ist nur die
#   Befehlszeile davor (Grundregel 10). Wer den Nachtrag pruefen will, liest
#   diese Datei - nicht die Argumentaufbereitung.
#
# ── WOHER DIE LUECKE KOMMT ───────────────────────────────────────────────────
#
#   Sie ist KEIN Datenfehler und auch nicht in diesem Auftrag entstanden. Die
#   Spalte gibt es seit Version 0.6.013 (git log -S"post_id" -- db/
#   evidence_db.py -> 9ea67b5). Leer bleibt sie, weil toolbar.js sie fuer
#   Textmarkierungen ausdruecklich nicht gesetzt hat: "XPath-Text-Marken
#   bleiben null, Post-Bezug via XPath" (Build 336). Fuer die Toolbar war das
#   richtig - sie loest den Anker im lebenden DOM auf und braucht die Nummer
#   nicht.
#
#   Fuer die AUSWERTUNG ist es nicht richtig. Der Bericht hat kein DOM. An der
#   post_id haengen im Vollzitat fuenf Angaben auf einmal: Themenbetreff,
#   Originaldatum, der '#p'-Anker der Fundstelle, der PN-Gespraechspartner und
#   die Zusammenfassung mehrerer Belege desselben Beitrags in EINEN
#   Unterblock. Bei der Sichtpruefung am 28.08.2026 fehlten sie bei allen 23
#   Belegen einer echten Gruppe.
#
#   Ab Build 727 schreibt die Toolbar die Nummer beim Markieren mit; Build 728
#   nimmt dafuer auch die innere Kennung 'pp<Nummer>' an. Fuer alles, was
#   VORHER markiert wurde, hilft das nicht. Dafuer ist diese Klasse da.
#
# ── WARUM KEINE MIGRATION ────────────────────────────────────────────────────
#
#   Eine evidence-Migration (M005) haette Sicherung, Register und Flotte
#   mitgebracht. Sie kann die Aufgabe aber nicht erfuellen, und zwar aus zwei
#   nachpruefbaren Gruenden:
#
#   (1) SIE KAEME NICHT AN DEN SEITENABZUG. MigrationRunner._apply ruft
#       mod.up(con) mit GENAU EINER Verbindung - der evidence-Datenbank
#       (management/migrations/runner.py). tools/migrate-dbs.py reicht die
#       zugehoerige forensic_<uid>.db nicht durch; fall_anwenden(pfad, art)
#       oeffnet nur diese eine Datei (Z. 302-334). Eine Migration muesste den
#       Pfad der forensic-Datei erraten. Ein Werkzeug, das den Ablageort eines
#       Beweismittels raet, ist kein Werkzeug.
#
#   (2) ES ENTSTUENDE KEIN BELEG. fall_anwenden() uebergibt dem Runner kein
#       AuditLog (MigrationRunner(con, module) - ohne audit=). Der Runner
#       schreibt seinen MIGRATION_APPLIED-Eintrag deshalb NICHT. Alex hat
#       ausdruecklich einen Eintrag im evidence_audit_log verlangt.
#
#   Ausserdem ist es sachlich keine Migration: das Schema aendert sich nicht,
#   die Spalte steht seit 0.6.013. Es werden DATEN nachgetragen.
#
# ── WARUM IN DER ZEILE GEAENDERT WIRD UND NICHT ALS NEUE VERSION ────────────
#
#   'annotations' ist append-only gefuehrt: eine Aenderung setzt beim
#   Vorgaenger deleted_at und legt eine neue Zeile mit version_nr+1 an
#   (db/evidence_db.py, save_annotation, Build 178). Diesem Muster HIER zu
#   folgen waere ein schwerer Fehler:
#
#     - Die neue Zeile bekaeme eine NEUE id. Die Beweismittelgruppen im
#       Bericht verweisen ueber block_data.evidence_ids auf die ALTE
#       (report_render/report_source.py); 'annotation_tatzeit.annotation_id'
#       ebenso. Jeder Nachtrag risse diese Verweise ab - aus Belegen wuerden
#       "in annotations nicht (mehr) vorhanden".
#     - Beim Vorgaenger stuende deleted_at. Der Vollzitat-Bauer liest aktive
#       Annotationen; ein Bestand mit gesetztem deleted_at erschiene als
#       geloescht.
#
#   Das Append-only-Muster schuetzt die AUSSAGE DES ERMITTLERS - Wortlaut,
#   Kategorie, Notiz, Zeit. Nichts davon wird hier angefasst. Geaendert wird
#   ausschliesslich ein technischer Verweis, der von Anfang an haette gesetzt
#   sein sollen und dessen Wert im versiegelten Seitenabzug nachlesbar ist.
#   Der Beleg dafuer ist der Eintrag in der Hash-Kette; er nennt jede
#   einzelne id und jede eingetragene Nummer, der Nachtrag ist damit Zeile
#   fuer Zeile nachvollziehbar und umkehrbar.
#
#   NUR LEERE FELDER WERDEN GEFUELLT. Eine vorhandene post_id wird NIE
#   ueberschrieben, auch dann nicht, wenn der Seitenabzug etwas anderes sagt.
#   Ein solcher Widerspruch wird GEMELDET (Ergebnis 'widerspruch') und ist von
#   Hand zu klaeren - er waere ein Befund und keine Aufraeumarbeit.
#
# ── DIE FUENF WEGE ZUR NUMMER ────────────────────────────────────────────────
#
#   WEG_ANKER      Der XPath aus selection_json loest im Abzug auf. Der so
#                  gefundene Absatz sitzt in einem Vorfahr mit der Kennung
#                  'p<Nummer>' bzw. 'pp<Nummer>'. DAS IST DER SOLLWEG: der
#                  Anker bezeichnet genau die markierte Stelle.
#   WEG_WORTLAUT   Der Anker loest nicht auf; der markierte Wortlaut kommt im
#                  Abzug GENAU EINMAL vor. Rueckfall - Alex, 28.08.2026: "Aus
#                  diesem Prozess erfolgt auch, dass wir die Heuristik mit der
#                  Suche nach dem markierten Begriff im BLOB nur als Fallback
#                  benoetigen."
#   WEG_WORTLAUT_EINDEUTIG
#                  Der Wortlaut kommt MEHRFACH vor, ABER alle Fundstellen
#                  liegen im SELBEN Beitrag. Fuer die Frage nach dem ABSATZ
#                  ist das mehrdeutig (der Bericht zeigt dann alle
#                  Fundstellen); fuer die Frage nach dem BEITRAG ist es
#                  eindeutig, denn die Antwort ist unabhaengig davon, welche
#                  Fundstelle gemeint war. Der Weg wird trotzdem eigens
#                  benannt, damit die Unterscheidung im Protokoll steht.
#   WEG_UEBERSETZUNG
#                  Die Markierung sitzt in einer maschinellen Uebersetzung.
#                  Dort steht die Nummer bereits IN der Auswahl
#                  (selection_json.postId) - toolbar.js hat sie fuer diesen
#                  Fall immer schon mitgegeben. Sie wird uebernommen, nicht
#                  hergeleitet.
#   WEG_KEINER     Nichts davon traegt. Es wird NICHTS eingetragen.
#
#   MEHRDEUTIGES WIRD NIE GESCHRIEBEN. Liegen die Fundstellen des Wortlauts in
#   VERSCHIEDENEN Beitraegen, bleibt das Feld leer und der Fall wird gemeldet.
#   Eine falsche Nummer braechte falschen Betreff, falsches Datum und falsche
#   Gruppierung mit sich - und saehe dabei vollkommen unauffaellig aus.
#
# ── DIE GEGENPROBE IM PAKET ──────────────────────────────────────────────────
#
#   Zu jeder ermittelten Nummer wird nachgesehen, ob das Paket sie kennt:
#   Forenbeitrag in fdb.uid_posts bzw. fdb.post_aliases, private Nachricht in
#   fdb.uid_pms_posts bzw. fdb.pm_aliases.
#
#   SIE IST BESTAETIGUNG, KEIN VETO - und das ist wichtig: fdb.uid_posts fuehrt
#   nur die Beitraege des UNTERSUCHTEN Benutzers. Eine Markierung im Beitrag
#   eines ANDEREN Nutzers derselben Themenseite ist voellig regulaer, und ihre
#   Nummer steht dann in keiner der uid_-Tabellen. Die Nummer aus dem
#   versiegelten Abzug ist ohnehin der staerkere Beleg; sie steht dort so, wie
#   der Benutzer die Seite gesehen hat. Der Befund der Gegenprobe wandert
#   deshalb ins Protokoll ('im Paket: ja/nein/ungeprueft') und entscheidet
#   nichts.
#
# ── SICHERUNG, BELEG, PROTOKOLL ──────────────────────────────────────────────
#
#   Weisung Alex, 28.08.2026: "Hier ist die unabdingbare Vorbedingung, dass
#   ein Backup vor der Aenderung gemacht wird." Deshalb gibt es KEINEN
#   Schalter '--no-backup'. Ohne erfolgreiche Sicherung wird nicht
#   geschrieben, Punkt.
#
#   Sicherung, alle UPDATEs und der Eintrag in die Hash-Kette laufen in EINER
#   Transaktion (BEGIN IMMEDIATE): Write und Beleg committen gemeinsam oder
#   gar nicht - dieselbe Zusage wie bei CoordinatorWriter.audited_write.
#
# Grundregeln: GR1, GR2, GR6, GR10.
# Version: v0.8.752 - Build: 752 - 2026-08-31
# =============================================================================

from __future__ import annotations

import json
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.logger import get_logger

logger = get_logger(__name__)

# --- Die Wege zur Nummer (s. Kopf) -------------------------------------------
WEG_ANKER = "anker"
WEG_WORTLAUT = "wortlaut"
WEG_WORTLAUT_EINDEUTIG = "wortlaut_ein_beitrag"
#: BUILD 750. Der Anker loest NICHT ganz auf, aber weit genug, um den
#: Beitrag zu benennen - typisch bricht erst die letzte Stufe ('text()[n]').
#: Das ist ein STAERKERER Beleg als der Wortlaut: der Anker ist die
#: Positionsangabe des Ermittlers; loest er bis in den Beitrag hinein auf,
#: ist dieser Beitrag benannt und nicht gesucht.
WEG_ANKER_TEIL = "anker_teil"
#: BUILD 752. Der Teilanker hat die Kreuzprobe NICHT bestanden, der
#: Wortlaut kommt aber im Abzug in genau EINEM Beitrag vor. Dann traegt
#: der Wortlaut - nicht weil er von Haus aus besser waere, sondern weil
#: der Anker auf diesen Seiten messbar danebenzeigt (34 von 34 Faellen
#: benennen einen Beitrag WEITER UNTEN, Alex' Lauf vom 31.08.2026).
WEG_WORTLAUT_ANKER_AB = "wortlaut_anker_abweichend"
WEG_UEBERSETZUNG = "uebersetzung"
WEG_KEINER = "keiner"

#: Die Wege, die als RUECKFALL gelten. Sie werden mit '--nur-anker'
#: abgeschaltet und im Protokoll eigens ausgewiesen.
WEGE_RUECKFALL = (WEG_WORTLAUT, WEG_WORTLAUT_EINDEUTIG,
                  WEG_WORTLAUT_ANKER_AB)

# --- Was mit einer Zeile geschehen ist ---------------------------------------
#: Die Nummer wurde ermittelt und (bei --ausfuehren) eingetragen.
ERG_GETRAGEN = "eingetragen"
#: Die Nummer wurde ermittelt, aber nicht geschrieben (Trockenuebung).
ERG_WUERDE = "wuerde eingetragen"
#: Es gibt keinen Seitenabzug zu annotations.page_url.
ERG_OHNE_ABZUG = "ohne Seitenabzug"
#: selection_json fehlt oder ist unlesbar.
ERG_OHNE_AUSWAHL = "ohne Auswahl"
#: Weder Anker noch Wortlaut fuehren zu einem Beitrag.
ERG_NICHT_GEFUNDEN = "nicht gefunden"
#: Der Wortlaut kommt in MEHREREN Beitraegen vor.
ERG_MEHRDEUTIG = "mehrdeutig"
#: Der Rueckfallweg war noetig, ist aber abgeschaltet (--nur-anker).
ERG_RUECKFALL_AUS = "Rueckfall abgeschaltet"
#: Die Zeile traegt bereits eine post_id, der Abzug nennt eine ANDERE.
ERG_WIDERSPRUCH = "Widerspruch"
#: Die Zeile traegt bereits dieselbe post_id - nichts zu tun.
ERG_SCHON_DA = "bereits gesetzt"
#: BUILD 751. Der Teilanker benennt einen Beitrag, aber der markierte
#: Wortlaut steht NICHT darin (AbsatzFinder.wortlaut_im_beitrag). Es wird
#: nichts eingetragen. Das ist ausdruecklich KEIN Beweis, dass der Anker
#: falsch ist - nur einer, dass er nicht bestaetigt ist; der Unterschied
#: steht in der Bemerkung der Zeile.
ERG_ANKER_UNBESTAETIGT = "Anker unbestaetigt"

#: Ergebnisse, die einen Schreibvorgang bedeuten.
ERGEBNISSE_SCHREIBEND = (ERG_GETRAGEN,)


@dataclass
class Zeilenbefund:
    """
    Was zu EINER Annotation festgestellt wurde.

    Diese Struktur ist zugleich die Zeile des Protokolls und der Eintrag im
    Payload der Hash-Kette. Sie traegt DESHALB keinen Wortlaut und keine
    Notiz: der Payload geht in ein unveraenderliches Protokoll, und der
    Inhalt eines Beitrags aus einem Verfahren nach §§ 176, 184b StGB hat
    dort nichts zu suchen (Sensibilitaetsregel wie M018/M022, s.
    management/audit/event_types.py). Fuer die Stichprobe des Bearbeiters
    genuegt die Beleg-Nummer; der Wortlaut steht in der Annotation.

    Felder:
        annotation_id - annotations.id
        art           - 'beitrag' | 'pn' (aus der Seitenadresse bestimmt)
        weg           - WEG_* - wie die Nummer gefunden wurde
        post_id       - die ermittelte Nummer (None, wenn keine)
        vorher        - der Wert, der in der Spalte STAND (fast immer None)
        ergebnis      - ERG_*
        im_paket      - 'ja' | 'nein' | 'ungeprueft' (Gegenprobe, s. Kopf)
        bemerkung     - Klartext, wenn etwas zu sagen ist; sonst ""
    """
    annotation_id: int
    art: str = ""
    weg: str = WEG_KEINER
    post_id: Optional[int] = None
    vorher: Optional[int] = None
    ergebnis: str = ERG_NICHT_GEFUNDEN
    im_paket: str = "ungeprueft"
    bemerkung: str = ""
    #: BUILD 729 - WARUM der Ankerweg nicht getragen hat, GEMESSEN
    #: (absatz_finder.GRUND_*), und bei GRUND_ANKER_BRICHT der Schritt, an
    #: dem der Ausdruck bricht. Bis Build 728 stand hier nichts, und das
    #: Protokoll behauptete pauschal, der Anker loese nicht auf - eine
    #: Aussage, die es nicht gemessen hatte.
    anker_grund: str = ""
    anker_bruch: str = ""
    #: BUILD 751 - das Ergebnis der Kreuzprobe zum Teilanker, als eines von
    #: "" (nicht gelaufen) | "bestanden" | "nicht bestanden" | "nicht
    #: pruefbar". Es steht als EIGENES Feld da und nicht nur im Fliesstext
    #: der Bemerkung, damit der Lauf es zaehlen kann: die Frage, ob der
    #: Teilanker auf den richtigen Beitrag zeigt, wird von einer ZAHL
    #: beantwortet und nicht von einem Eindruck beim Lesen.
    kreuzprobe: str = ""
    #: BUILD 752 - der gemessene Abstand IN BEITRAEGEN zwischen dem Beitrag,
    #: den der Anker benennt, und dem, in dem der Wortlaut steht. Positiv
    #: heisst: der Anker zeigt weiter unten. None, wenn nicht messbar.
    #: Die Zahl steht als eigenes Feld da, damit der Lauf sie ZAEHLEN kann -
    #: ist sie auf einer Seite durchweg gleich, ist die Verschiebung
    #: systematisch und in einer Zahl zu fassen; ist sie es nicht, dann
    #: nicht. Das ist zu messen und nicht zu schaetzen.
    versatz: Optional[int] = None

    def als_protokollzeile(self) -> str:
        """Eine Zeile fuer Konsole und Protokolldatei."""
        return ("#%-7d %-8s %-22s post_id=%-10s Weg=%-22s im Paket: %-11s %s"
                % (self.annotation_id,
                   self.art or "-",
                   self.ergebnis,
                   self.post_id if self.post_id is not None else "-",
                   self.weg,
                   self.im_paket,
                   self.bemerkung))

    def ankerzeile(self) -> str:
        """
        Die Zusatzzeile zum Ankerweg - oder "" wenn der Sollweg getragen hat.

        SIE IST DER EIGENTLICHE ERTRAG DES LAUFS, wenn der Rueckfall haeufig
        greift: aus ihr geht hervor, OB der Anker bricht und WO. Ohne sie
        blieb nur die Zaehlung 'Weg=wortlaut', und aus der laesst sich die
        Ursache nicht ablesen.
        """
        if not self.anker_grund:
            return ""
        teile = ["Ankerweg: %s" % self.anker_grund]
        if self.anker_bruch:
            teile.append(self.anker_bruch)
        return "          " + " | ".join(teile)

    def als_beleg(self) -> Dict[str, Any]:
        """Der Eintrag im Payload der Hash-Kette - nur Fakten, s. Klassenkopf."""
        beleg = {"id": self.annotation_id, "post_id": self.post_id,
                 "weg": self.weg, "art": self.art, "im_paket": self.im_paket}
        if self.anker_grund:
            # Nur der CODE, nicht der Bruchtext: der nennt Elementnamen aus
            # der Seite und gehoert damit ins Protokoll, nicht in die Kette.
            beleg["anker_grund"] = self.anker_grund
        return beleg


@dataclass
class Laufbefund:
    """Das Ergebnis eines ganzen Laufs."""
    geprueft: int = 0
    zeilen: List[Zeilenbefund] = field(default_factory=list)
    sicherung: Optional[str] = None
    geschrieben: int = 0
    #: Meldungen, die NICHT an einer einzelnen Zeile haengen (fehlende
    #: Tabellen, fehlende Kette). Sie werden nie unterdrueckt (GR1).
    hinweise: List[str] = field(default_factory=list)
    abgebrochen: str = ""

    def zaehlung(self) -> Dict[str, int]:
        """Wie oft welches Ergebnis - fuer die Schlusszeile."""
        aus: Dict[str, int] = {}
        for z in self.zeilen:
            aus[z.ergebnis] = aus.get(z.ergebnis, 0) + 1
        return aus

    def wege(self) -> Dict[str, int]:
        """Wie oft welcher Weg - nur fuer die tatsaechlich getragenen."""
        aus: Dict[str, int] = {}
        for z in self.zeilen:
            if z.ergebnis in (ERG_GETRAGEN, ERG_WUERDE):
                aus[z.weg] = aus.get(z.weg, 0) + 1
        return aus

    def versaetze(self) -> Dict[int, int]:
        """
        Wie oft welcher Versatz gemessen wurde (Build 752).

        IST DIESE VERTEILUNG EINGIPFELIG, ist die Verschiebung systematisch.
        Streut sie, ist sie es nicht - und dann ist an den Ankern dieser
        Altbestaende nichts zu heilen.
        """
        aus: Dict[int, int] = {}
        for z in self.zeilen:
            if z.versatz is not None:
                aus[z.versatz] = aus.get(z.versatz, 0) + 1
        return aus

    def kreuzproben(self) -> Dict[str, int]:
        """
        Wie oft die Kreuzprobe zum Teilanker wie ausgegangen ist (Build 751).

        DAS IST DIE ZAHL, DIE UEBER DEN SCHARFEN LAUF ENTSCHEIDET. Sie sagt,
        ob der Teilanker den Beitrag am Inhalt bestaetigt bekommt oder ob er
        nur auf Elementindizes beruht, deren Uebereinstimmung mit dem Abzug
        auf den PN-Seiten gerade nicht durchweg gegeben ist.
        """
        aus: Dict[str, int] = {}
        for z in self.zeilen:
            if z.kreuzprobe:
                aus[z.kreuzprobe] = aus.get(z.kreuzprobe, 0) + 1
        return aus


class PostIdNachtrag:
    """
    Traegt 'annotations.post_id' aus dem gesicherten Seitenabzug nach.

    Verwendung (s. tools/postid_nachtragen.py):

        nachtrag = PostIdNachtrag(evidence=Path(...), forensic=Path(...),
                                  ausgabe=print)
        befund = nachtrag.lauf(ausfuehren=False)      # Trockenuebung
        befund = nachtrag.lauf(ausfuehren=True, operator="mmuster")

    DIE TROCKENUEBUNG IST DIE VORGABE (dieselbe Festlegung wie bei
    tools/migrate-dbs.py, mc 2026-07-30): ohne ausfuehren=True wird die
    Datenbank nur LESEND geoeffnet. Das ist keine Hoeflichkeit gegenueber dem
    Bediener, sondern gegenueber dem Beweismittel.
    """

    #: Wie viele Nachtraege ein EINZELNER Eintrag der Hash-Kette aufzaehlt.
    #:
    #: DARUEBER WIRD NICHTS WEGGELASSEN, sondern WEITERGEZAEHLT: bei mehr
    #: Nachtraegen entstehen mehrere Eintraege in derselben Transaktion, jeder
    #: mit seinem Abschnitt und mit 'abschnitt: n von m'. So bleibt jede
    #: einzelne Beleg-Nummer im Protokoll (GR1) und trotzdem bleibt eine
    #: einzelne Zeile der Kette lesbar. Die Alternative - ein Eintrag mit
    #: 40.000 Zeilen - waere zwar vollstaendig, aber ein Beleg, den niemand
    #: mehr oeffnet, ist kein besserer Beleg (dieselbe Ueberlegung wie bei
    #: _buendeln() in report_render/vollzitat_bauer.py).
    BELEG_GRENZE = 2000

    def __init__(
        self,
        *,
        evidence: Path,
        forensic: Path,
        ausgabe: Optional[Callable[[str], None]] = None,
        nur_anker: bool = False,
        auch_ersetzte: bool = False,
        grenze: Optional[int] = None,
        beleg: Optional[int] = None,
    ) -> None:
        self._evidence = Path(evidence)
        self._forensic = Path(forensic)
        self._sag = ausgabe if ausgabe is not None else (lambda _z: None)
        self._nur_anker = bool(nur_anker)
        self._auch_ersetzte = bool(auch_ersetzte)
        self._grenze = grenze
        self._beleg = beleg
        #: Seitenabzuege je Adresse EINMAL zerlegen - eine Themenseite mit bis
        #: zu 500 Beitraegen ist der teuerste Einzelschritt.
        self._finder: Dict[str, Any] = {}
        #: Gegenprobe: die Tabellen, die es in diesem Paket wirklich gibt.
        self._tabellen: Optional[set] = None

    # ------------------------------------------------------------------
    # Lauf
    # ------------------------------------------------------------------
    def lauf(self, *, ausfuehren: bool = False,
             operator: str = "", protokoll_datei: Optional[Path] = None,
             protokoll_hash: str = "") -> Laufbefund:
        """
        Den ganzen Nachtrag durchfuehren.

        ausfuehren=False - Trockenuebung. Die Datenbank wird mit 'mode=ro'
                           geoeffnet; es KANN nichts geschrieben werden.
        ausfuehren=True  - scharf. Vorher wird gesichert; ohne erfolgreiche
                           Sicherung bricht der Lauf ab (Weisung Alex).
        protokoll_datei / protokoll_hash - Name (und, wenn bekannt, SHA-256)
                           der Konsolenmitschrift. Sie wandern in den Beleg,
                           damit sich Kette und Mitschrift spaeter zuordnen
                           lassen; massgeblich ist immer die Kette.
        """
        befund = Laufbefund()

        if not self._evidence.is_file():
            befund.abgebrochen = ("Die Beweismitteldatenbank gibt es nicht: %s"
                                  % self._evidence)
            return befund
        if not self._forensic.is_file():
            befund.abgebrochen = ("Der Seitenabzug gibt es nicht: %s. OHNE IHN "
                                  "IST DER NACHTRAG NICHT MOEGLICH - die "
                                  "Nummer steht dort und nirgends sonst."
                                  % self._forensic)
            return befund

        # --- Sicherung. VOR dem Oeffnen und vor jedem Schreibversuch. ------
        if ausfuehren:
            try:
                befund.sicherung = str(self._sichern())
            except OSError as exc:
                befund.abgebrochen = (
                    "Die Sicherung ist fehlgeschlagen (%s). Es wurde NICHTS "
                    "geaendert. Eine Sicherung ist die unabdingbare "
                    "Vorbedingung dieses Werkzeugs (Weisung Alex, "
                    "28.08.2026)." % exc)
                return befund
            self._sag("Sicherung: %s" % befund.sicherung)

        con = self._oeffnen(schreibend=ausfuehren)
        # _seite()/_blob() lesen ueber DIESELBE Verbindung - der Abzug haengt
        # als 'fdb' daran. Der Zeiger wird am Ende wieder geloescht, damit
        # eine geschlossene Verbindung nicht als offene missverstanden wird.
        self._con_blob = con
        try:
            self._pruefen(con, befund)
            if befund.abgebrochen:
                return befund
            zeilen = self._kandidaten(con)
            befund.geprueft = len(zeilen)
            if not zeilen:
                befund.hinweise.append(
                    "Keine Annotation ohne Beitragsnummer gefunden. Entweder "
                    "ist der Nachtrag bereits gelaufen, oder alle "
                    "Markierungen sind nach Build 727 entstanden.")
                return befund

            for r in zeilen:
                befund.zeilen.append(self._eine_zeile(con, r, ausfuehren))

            if ausfuehren:
                self._schreiben(con, befund, operator,
                                protokoll_datei, protokoll_hash)
        finally:
            self._con_blob = None
            con.close()
        return befund

    # ------------------------------------------------------------------
    # Datenbank
    # ------------------------------------------------------------------
    def _sichern(self) -> Path:
        """
        Dateikopie neben dem Original - Schreibweise wie tools/migrate-dbs.py.

        WARUM shutil.copy2 UND NICHT DIE SQLITE-BACKUP-API: Die Kopie
        entsteht, BEVOR dieses Werkzeug die Datei ueberhaupt schreibfaehig
        oeffnet. Sie ist damit ein Abbild des Zustands vor dem Lauf,
        einschliesslich Zeitstempel. Etwaige -wal/-shm-Dateien werden
        mitgenommen, wenn es sie gibt: ohne sie waere die Kopie im
        WAL-Betrieb um die noch nicht gefalteten Aenderungen aermer.
        """
        marke = int(time.time())
        ziel = self._evidence.with_suffix(
            self._evidence.suffix + ".vor-postid-nachtrag-%d.bak" % marke)
        shutil.copy2(str(self._evidence), str(ziel))
        for anhang in ("-wal", "-shm"):
            quelle = Path(str(self._evidence) + anhang)
            if quelle.is_file():
                shutil.copy2(str(quelle), str(ziel) + anhang)
        return ziel

    def _oeffnen(self, *, schreibend: bool) -> sqlite3.Connection:
        """
        Die Beweismitteldatenbank als Hauptverbindung, der Abzug als 'fdb'.

        DER ABZUG WIRD IMMER 'mode=ro' ANGEBUNDEN, auch im scharfen Lauf.
        forensic_<uid>.db ist das versiegelte Beweismittel; kein Weg dieses
        Werkzeugs darf dort schreiben koennen (dieselbe Grenze wie in
        tools/migrate-dbs.py, Kopf: "WARUM forensic_<uid>.db NIE MIGRIERT
        WIRD").

        In der Trockenuebung ist AUCH die Hauptverbindung 'mode=ro' - dann
        gibt es keinen schreibfaehigen Griff auf ein Beweismittel, und der
        Waechter tests/test_py4_lesend.py sieht das ebenso.
        """
        if schreibend:
            con = sqlite3.connect(str(self._evidence))
        else:
            con = sqlite3.connect(
                "file:%s?mode=ro" % self._evidence.resolve(), uri=True)
        con.row_factory = sqlite3.Row
        # Explizite Transaktionssteuerung wie im MigrationRunner: BEGIN
        # IMMEDIATE / COMMIT / ROLLBACK setzen wir selbst.
        con.isolation_level = None
        con.execute("ATTACH DATABASE ? AS fdb",
                    ("file:%s?mode=ro" % self._forensic.resolve(),))
        return con

    def _pruefen(self, con: sqlite3.Connection, befund: Laufbefund) -> None:
        """
        Die Voraussetzungen, ohne die nicht geschrieben werden darf.

        DIE HASH-KETTE IST EINE DAVON. Fehlt sie (Migration M003 nicht
        angewandt), gaebe es keinen Beleg fuer die Aenderung - und eine
        unbelegte Aenderung an einem Beweismittel darf es nicht geben. Das
        ist dieselbe Regel, nach der M004 im Zweifelsfall lieber abbricht als
        zu konvertieren (Regel SI09, m004_sort_index_integer.py).
        """
        try:
            spalten = {r["name"] for r in
                       con.execute("PRAGMA table_info(annotations)")}
        except sqlite3.Error as exc:
            befund.abgebrochen = ("Die Tabelle 'annotations' ist nicht "
                                  "lesbar: %s" % exc)
            return
        if not spalten:
            befund.abgebrochen = ("Die Datei fuehrt keine Tabelle "
                                  "'annotations'. Ist das wirklich eine "
                                  "evidence_<uid>.db?")
            return
        fehlend = {"id", "page_url", "post_id", "selection_json"} - spalten
        if fehlend:
            befund.abgebrochen = ("'annotations' fuehrt die Spalte(n) %s "
                                  "nicht." % ", ".join(sorted(fehlend)))
            return

        try:
            con.execute("SELECT 1 FROM fdb.pages LIMIT 1").fetchone()
        except sqlite3.Error as exc:
            befund.abgebrochen = ("fdb.pages ist nicht lesbar (%s). Ohne die "
                                  "Seitenabzuege gibt es nichts nachzutragen."
                                  % exc)
            return

        try:
            kette = con.execute(
                "SELECT COUNT(*) AS n FROM evidence_audit_log").fetchone()
        except sqlite3.Error:
            befund.abgebrochen = (
                "In dieser Datenbank gibt es keine Tabelle "
                "'evidence_audit_log' - die evidence-Migration M003 ist nicht "
                "angewandt. OHNE DIE HASH-KETTE WIRD NICHTS GESCHRIEBEN: eine "
                "Aenderung an einem Beweismittel ohne Beleg darf es nicht "
                "geben. Abhilfe: python3 tools/migrate-dbs.py --db evidence "
                "--subject-id <uid> --apply")
            return
        if not kette or int(kette["n"]) == 0:
            befund.abgebrochen = (
                "Die Kette 'evidence_audit_log' ist leer - der "
                "Genesis-Eintrag fehlt. EvidenceAuditLog.append() koennte "
                "nicht anhaengen, und der Nachtrag bliebe unbelegt. Es wurde "
                "nichts geaendert.")
            return

    # ------------------------------------------------------------------
    def _kandidaten(self, con: sqlite3.Connection) -> List[sqlite3.Row]:
        """
        Die Zeilen, um die es geht.

        VORGABE: nur AKTIVE Annotationen (deleted_at IS NULL). Ersetzte
        Versionen sind Vergangenheit; sie in eine Auswertung zu heben, waere
        eine Aenderung an etwas, das niemand mehr liest. Mit --auch-ersetzte
        laesst sich der Bestand vollstaendig nachziehen - das ist eine
        bewusste Entscheidung und keine Vorgabe.

        Zeilen MIT post_id werden ausdruecklich MITGENOMMEN, wenn ein
        einzelner Beleg geprueft wird (--beleg): dann will der Bearbeiter
        wissen, was das Werkzeug zu genau dieser Zeile sagt, und nicht eine
        leere Liste. Im Regellauf bleiben sie draussen - dort gibt es nichts
        zu tun.
        """
        bedingungen = ["selection_json IS NOT NULL"]
        parameter: List[Any] = []
        if not self._auch_ersetzte:
            bedingungen.append("deleted_at IS NULL")
        if self._beleg is not None:
            bedingungen.append("id = ?")
            parameter.append(int(self._beleg))
        else:
            bedingungen.append("post_id IS NULL")

        sql = ("SELECT id, page_url, element_id, post_id, selection_json "
               "FROM annotations WHERE %s ORDER BY id"
               % " AND ".join(bedingungen))
        if self._grenze:
            sql += " LIMIT %d" % int(self._grenze)
        return list(con.execute(sql, parameter).fetchall())

    # ------------------------------------------------------------------
    # Eine Zeile
    # ------------------------------------------------------------------
    def _eine_zeile(self, con: sqlite3.Connection, r: sqlite3.Row,
                    ausfuehren: bool) -> Zeilenbefund:
        from forensic_api.annotations import _is_pm_url

        beleg_id = int(r["id"])
        vorher = r["post_id"]
        vorher = int(vorher) if vorher is not None else None
        art = "pn" if _is_pm_url(r["page_url"]) else "beitrag"
        z = Zeilenbefund(annotation_id=beleg_id, art=art, vorher=vorher)

        selection = self._auswahl(r["selection_json"], beleg_id)
        if selection is None:
            z.ergebnis = ERG_OHNE_AUSWAHL
            z.bemerkung = ("selection_json fehlt oder ist kein gueltiges "
                           "JSON - es gibt keinen Anker und keinen Wortlaut.")
            return z

        gefunden = self._nummer_bestimmen(r, selection, z)
        if gefunden is None:
            return z          # z.ergebnis/bemerkung sind dort gesetzt
        z.post_id = gefunden

        # --- Gegenprobe im Paket. Bestaetigung, kein Veto (s. Kopf). ------
        z.im_paket = self._im_paket(con, art, gefunden)

        # --- Widerspruch? Dann wird NICHTS ueberschrieben. -----------------
        if vorher is not None:
            if vorher == gefunden:
                z.ergebnis = ERG_SCHON_DA
            else:
                z.ergebnis = ERG_WIDERSPRUCH
                z.bemerkung = ("Die Zeile traegt bereits post_id=%d, der "
                               "Seitenabzug nennt %d. ES WIRD NICHTS "
                               "GEAENDERT - das ist ein Befund und keine "
                               "Aufraeumarbeit; bitte von Hand klaeren."
                               % (vorher, gefunden))
            return z

        if self._nur_anker and z.weg in WEGE_RUECKFALL:
            z.ergebnis = ERG_RUECKFALL_AUS
            z.bemerkung = ("Die Nummer %d waere ueber den Wortlaut zu finden; "
                           "'--nur-anker' laesst nur den Anker gelten."
                           % gefunden)
            z.post_id = None
            return z

        z.ergebnis = ERG_GETRAGEN if ausfuehren else ERG_WUERDE
        return z

    # ------------------------------------------------------------------
    @staticmethod
    def _nummer_aus_teilanker(finder, selection):
        """
        (Beitragsnummer oder None, Hinweis im Klartext, Beitragselement).

        BUILD 751: der dritte Rueckgabewert ist das ELEMENT, das die
        Beitragskennung traegt. Er wird fuer die Kreuzprobe gebraucht
        (AbsatzFinder.wortlaut_im_beitrag) - ohne ihn liesse sich nur die
        Nummer weiterreichen, und an einer Nummer ist nicht zu pruefen, ob
        der markierte Wortlaut in diesem Beitrag steht.

        BUILD 750. Der Anker wird Schritt fuer Schritt gegangen; vom am
        weitesten erreichten ELEMENT aus wird der naechste Vorfahr mit einer
        Beitragskennung gesucht.

        ZWEI SCHRANKEN, damit daraus kein Raten wird:

          * ES MUSS EIN ANKER DA SEIN. Ohne 'xpathStart' gibt es nichts zu
            gehen.
          * DER ANKER MUSS WEIT GENUG GEKOMMEN SEIN. Bricht er schon im
            Seitengeruest, sagt der erreichte Knoten nichts ueber einen
            Beitrag - dann traegt auch kein Vorfahr eine Beitragskennung,
            und die Suche liefert von selbst None. Eine zusaetzliche
            Mindesttiefe waere eine geratene Zahl und steht deshalb nicht
            hier.
        """
        from report_render.absatz_finder import AbsatzFinder
        if not isinstance(selection, dict):
            return None, "", None
        ausdruck = str(selection.get("xpathStart") or "")
        if not ausdruck:
            return None, "", None
        knoten, gegangen, gesamt = finder.anker_teilknoten(ausdruck)
        if knoten is None or gegangen >= gesamt:
            # Ganz aufgeloest? Dann hat der Sollweg getragen und dieser
            # Zweig hat nichts beizutragen.
            return None, "", None
        behaelter = AbsatzFinder.post_behaelter_von(knoten)
        if behaelter is None:
            return None, "", None
        nummer = AbsatzFinder.post_id_von(behaelter)
        if nummer is None:
            return None, "", None
        return nummer, (
            "Der Anker loest %d von %d Schritten auf und endet damit INNERHALB "
            "des Beitrags; die Nummer stammt aus dem Anker und nicht aus der "
            "Wortlautsuche. Gebrochen ist erst die letzte Stufe - typisch die "
            "Zaehlung der Textknoten." % (gegangen, gesamt)), behaelter

    # ------------------------------------------------------------------
    def _nummer_bestimmen(self, r: sqlite3.Row, selection: Any,
                          z: Zeilenbefund) -> Optional[int]:
        """
        Die Nummer aus der Auswahl und dem Abzug. None, wenn keine.

        Setzt bei Misserfolg ergebnis und bemerkung in z - der Aufrufer gibt
        die Zeile dann unveraendert weiter. Kein Zweig endet stumm (GR1).
        """
        from report_render.absatz_finder import (
            AbsatzFinder, WEG_XPATH, auswahl_text, ist_uebersetzungsauswahl)

        # (a) Uebersetzung: die Nummer steht bereits in der Auswahl.
        if ist_uebersetzungsauswahl(selection):
            roh = selection.get("postId") if isinstance(selection, dict) else None
            try:
                nummer = int(roh)
            except (TypeError, ValueError):
                z.weg = WEG_UEBERSETZUNG
                z.ergebnis = ERG_NICHT_GEFUNDEN
                z.bemerkung = ("Die Markierung sitzt in einer maschinellen "
                               "Uebersetzung, aber selection_json fuehrt "
                               "keine brauchbare 'postId' (%r). Im Abzug "
                               "steht die Uebersetzung nicht; es gibt hier "
                               "nichts herzuleiten." % (roh,))
                return None
            z.weg = WEG_UEBERSETZUNG
            return nummer

        # (b) Der Seitenabzug.
        finder = self._seite(r["page_url"])
        if finder is None or not finder.brauchbar:
            z.ergebnis = ERG_OHNE_ABZUG
            z.bemerkung = ("Zu %r gibt es in fdb.pages keinen zerlegbaren "
                           "Seitenabzug." % (r["page_url"],))
            return None

        fundstelle = finder.finde(selection, r["element_id"])
        # BUILD 729: der GEMESSENE Grund wandert mit, auch wenn der Wortlaut
        # danach getragen hat. Genau dann ist er die Auskunft, die fehlte.
        z.anker_grund = getattr(fundstelle, "anker_grund", "") or ""
        z.anker_bruch = getattr(fundstelle, "anker_bruch", "") or ""

        # -- (c) DER TEILWEISE AUFGELOESTE ANKER ---------------------------
        #
        # BUILD 750, aus Alex' Gesamtlauf ueber zwoelf Beweismitteldaten-
        # banken (31.08.2026): Der haeufigste Bruch sitzt in der LETZTEN
        # Stufe. Die Meldung sagt das selbst - "Schritt 16 von 16 bricht bei
        # 'text()[24]': der Browser hat 24 Textknoten gezaehlt, der Abzug
        # hat 23. Aufgeloest bis .../div[52]/.../p[1]."
        #
        # DER BEITRAG STEHT DAMIT FEST. Er ist der naechste Vorfahr mit
        # einer Beitragskennung; der Textknotenindex wird dafuer nicht
        # gebraucht. Bis Build 749 fiel das Werkzeug trotzdem auf die
        # WORTLAUTSUCHE zurueck - und die ist schwaecher: sie sucht eine
        # Fundstelle mit demselben Wortlaut, notfalls in einem anderen
        # Beitrag, und liefert bei mehrfach vorkommendem Wortlaut gar nichts
        # ('mehrdeutig'), obwohl der Anker den Beitrag benennt.
        #
        # DIE PRUEFUNG STEHT VOR DER AUSWERTUNG DER FUNDSTELLE und nicht
        # dahinter: sie soll den Wortlaut ERSETZEN, wo der Anker traegt,
        # nicht ihn im Nachhinein bestaetigen.
        teilnummer, teilhinweis, teilbehaelter = \
            self._nummer_aus_teilanker(finder, selection)
        # ZWEI SCHRANKEN, UND DAS IST ABSICHT - aber sie decken einander,
        # und das gehoert gesagt: '_nummer_aus_teilanker' gibt bei einem
        # ganz aufgeloesten Anker schon nichts zurueck (PN54), und die
        # zweite Bedingung hier faengt denselben Fall noch einmal ab. Beim
        # Gegenprobenlauf zu Build 750 wurde deshalb KEIN Test rot, als eine
        # der beiden stillgelegt wurde. Die Doppelung bleibt - sie kostet
        # nichts und schuetzt den Fall, dass der Sollweg aus einem anderen
        # Grund als dem Anker traegt -, aber sie ist als Doppelung benannt
        # und nicht als zweite gepruefte Regel ausgegeben.
        if teilnummer is not None and fundstelle.weg != WEG_XPATH:
            z.weg = WEG_ANKER_TEIL
            z.bemerkung = teilhinweis

            # -- DIE KREUZPROBE (BUILD 751) -------------------------------
            #
            # SIE STEHT VOR ALLEM ANDEREN, weil sie ueber die Nummer selbst
            # entscheidet und nicht ueber ihre Darstellung.
            #
            # Build 750 hat die Nummer aus dem teilweise aufgeloesten Anker
            # genommen und dabei UNTERSTELLT, dass die Elementindizes des
            # Ankers und die des Abzugs dieselben Elemente treffen. Alex'
            # Ankerdiagnose vom 31.08.2026 zeigt, dass das nicht durchweg
            # gilt: auf '/forum/pmsnew.php?mdl=topic&tid=64200' verlangt ein
            # Anker 'div[54]' auf einer Ebene, die im Abzug 53 Kinder hat;
            # auf '...&tid=57358' verlangen zwei Anker 'div[1010]' und
            # 'div[1016]', wo der Abzug 1003 Kinder hat. DER BROWSER HATTE
            # DORT MEHR ZEILEN ALS DER ABZUG - und ob die fehlenden am Ende
            # oder davor stehen, ist NICHT gemessen. Stehen sie davor, zeigt
            # jeder groessere Index lautlos auf den falschen Beitrag.
            #
            # Deshalb wird die Nummer nicht mehr geglaubt, sondern geprueft,
            # und zwar am INHALT: steht der markierte Wortlaut in dem
            # Beitrag, den der Anker benennt? Steht er dort nicht, wird
            # NICHTS eingetragen. Eine falsche Nummer braechte falschen
            # Betreff, falsches Datum und falsche Gruppierung mit sich und
            # saehe dabei unauffaellig aus - dieselbe Ueberlegung wie beim
            # mehrdeutigen Wortlaut weiter unten.
            wortlaut = auswahl_text(selection)
            probe = AbsatzFinder.wortlaut_im_beitrag(teilbehaelter, wortlaut)

            # Der Wortlaut auf seine Beitraege gebracht - fuer den
            # Widerspruch UND fuer die Auskunft im Misserfolgsfall.
            wortlautnummern = []
            for treffer in fundstelle.treffer:
                nummer = AbsatzFinder.post_id_von(treffer.block)
                if nummer is not None and nummer not in wortlautnummern:
                    wortlautnummern.append(nummer)
            gefunden_bei = (", ".join("#%d" % n for n in wortlautnummern)
                            if wortlautnummern else "keinem Beitrag")

            # WIE VIELE Beitraege den Wortlaut tragen, ist die Staerke
            # der Probe und gehoert deshalb in jede Auskunft. BUILD 752, aus
            # Alex' Lauf: Beleg #65 in evidence_2948078 hat die Kreuzprobe
            # BESTANDEN - waehrend 13 andere Belege AM SELBEN Ankerknoten
            # (div[52], derselbe Beitrag #291411) sie NICHT bestanden. Der
            # Unterschied liegt nicht am Anker, sondern am Wortlaut: der von
            # #65 kommt in vielen Beitraegen vor, und in vielen Beitraegen
            # vorzukommen heisst auch, im falschen vorzukommen. EIN TREFFER
            # IN EINEM VON VIELEN BEITRAEGEN BESTAETIGT NICHTS.
            traeger = len(wortlautnummern)
            z.kreuzprobe = {True: "bestanden", False: "nicht bestanden",
                            None: "nicht pruefbar"}[probe]

            # Der VERSATZ - die Messung, die entscheidet, ob sich die
            # Verschiebung in einer Zahl fassen laesst (s. beitragsversatz).
            if traeger == 1:
                z.versatz = finder.beitragsversatz(teilnummer,
                                                   wortlautnummern[0])

            if probe is True and traeger == 1:
                # DER STARKE FALL: der Wortlaut kommt im ganzen Abzug in
                # GENAU EINEM Beitrag vor, und das ist der, den der Anker
                # benennt. Anker und Inhalt sagen dasselbe.
                z.bemerkung += (
                    " KREUZPROBE BESTANDEN, und zwar eindeutig: der "
                    "markierte Wortlaut kommt im Abzug in genau EINEM "
                    "Beitrag vor - #%d, dem der Anker benennt." % teilnummer)
                return teilnummer

            if probe is True:
                # Bestanden, aber der Wortlaut steht in %d Beitraegen. Dass
                # er auch im angezeigten steht, ist dann kein Beleg.
                z.kreuzprobe = "schwach"
                z.ergebnis = ERG_ANKER_UNBESTAETIGT
                z.bemerkung = (
                    "%s Der markierte Wortlaut steht zwar im Klartext des "
                    "Beitrags #%d - er steht aber auch in %d anderen (%s). "
                    "DAS BESTAETIGT NICHTS: wo ein Wortlaut in vielen "
                    "Beitraegen vorkommt, kommt er auch im falschen vor. Es "
                    "wird NICHTS eingetragen. BITTE VON HAND ANSEHEN."
                    % (teilhinweis, teilnummer, traeger - 1, gefunden_bei))
                return None

            if probe is None:
                # Ohne Wortlaut ist nichts zu pruefen - und ohne Pruefung
                # bleibt nur der Elementindex, dem nach dem Befund vom
                # 31.08.2026 nicht mehr zu trauen ist.
                z.ergebnis = ERG_ANKER_UNBESTAETIGT
                z.bemerkung += (
                    " Die Kreuzprobe war nicht moeglich (kein brauchbarer "
                    "Wortlaut in der Auswahl). Damit bliebe nur der "
                    "Elementindex des Ankers, und der ist auf diesen Seiten "
                    "nachweislich verschoben. Es wird NICHTS eingetragen. "
                    "BITTE VON HAND ANSEHEN.")
                return None

            # -- probe is False: DER ANKER IST WIDERLEGT ------------------
            #
            # BUILD 752, und das ist die Kehrtwende gegenueber Build 750.
            # Alex' Lauf mit Build 751 ueber 462 Annotationen: von 37
            # Teilankern haben 36 die Kreuzprobe NICHT bestanden. Und der
            # Fehler hat eine RICHTUNG - in allen 34 Faellen, in denen der
            # Wortlaut genau einen Beitrag nennt, benennt der Anker einen
            # Beitrag mit HOEHERER Nummer, also einen weiter unten auf der
            # Seite. Kein einziger Gegenfall.
            #
            # Damit ist die Frage aus Build 751 beantwortet: die fehlenden
            # Zeilen des Abzugs stehen NICHT am Ende, sondern DAVOR. Der
            # Elementindex des Ankers zaehlt Zeilen mit, die der Abzug nicht
            # hat, und landet deshalb zu weit unten.
            #
            # DER WORTLAUT IST AUF DIESEN SEITEN DAS STAERKERE BELEGSTUECK -
            # nicht weil er von Haus aus besser waere (er ist es nicht, s.
            # Kopf), sondern weil der Anker hier MESSBAR danebenzeigt,
            # waehrend der Wortlaut das einzige inhaltliche Band zwischen
            # der Markierung und einem Beitrag ist. Kommt er in genau einem
            # Beitrag vor, ist die Frage nach dem Beitrag beantwortet.
            z.ergebnis = ERG_ANKER_UNBESTAETIGT
            if traeger == 1:
                z.weg = WEG_WORTLAUT_ANKER_AB
                z.ergebnis = ERG_WUERDE
                z.bemerkung = (
                    "%s ABER: der markierte Wortlaut steht im Klartext des "
                    "Beitrags #%d NICHT - er steht im Abzug in genau einem "
                    "Beitrag, und das ist #%d. EINGETRAGEN WIRD DER "
                    "WORTLAUT, nicht der Anker: der Anker zeigt auf dieser "
                    "Seite messbar daneben (der Abzug traegt weniger Zeilen "
                    "als der Browser hatte), der Wortlaut ist das einzige "
                    "inhaltliche Band zur Markierung, und er ist hier "
                    "eindeutig.%s DIE STELLE GEHOERT IN DIE STICHPROBE."
                    % (teilhinweis, teilnummer, wortlautnummern[0],
                       ("" if z.versatz is None else
                        " Gemessener Versatz: der Anker benennt den %d. "
                        "Beitrag NACH dem, in dem der Wortlaut steht."
                        % z.versatz)))
                return wortlautnummern[0]

            z.bemerkung = (
                "%s ABER: der markierte Wortlaut steht im Klartext des "
                "Beitrags #%d NICHT, und er ist auch sonst nicht eindeutig - "
                "er kommt im Abzug in %s vor. Es wird NICHTS eingetragen: "
                "der Anker ist widerlegt und der Wortlaut entscheidet nicht. "
                "BITTE VON HAND ANSEHEN."
                % (teilhinweis, teilnummer,
                   ("keinem Beitrag" if traeger == 0
                    else "%d Beitraegen (%s)" % (traeger, gefunden_bei))))
            return None
        if not fundstelle.treffer:
            z.ergebnis = ERG_NICHT_GEFUNDEN
            z.bemerkung = (fundstelle.hinweis
                           or "Weder der Anker noch der Wortlaut fuehren im "
                              "Abzug auf eine Stelle.")
            return None

        # ALLE Fundstellen auf ihren Beitrag bringen. Erst die MENGE der
        # Antworten entscheidet, ob die Frage eindeutig beantwortet ist -
        # nicht die Zahl der Fundstellen.
        nummern = []
        for treffer in fundstelle.treffer:
            nummer = AbsatzFinder.post_id_von(treffer.block)
            if nummer is not None and nummer not in nummern:
                nummern.append(nummer)

        if not nummern:
            z.ergebnis = ERG_NICHT_GEFUNDEN
            z.weg = (WEG_ANKER if fundstelle.weg == WEG_XPATH
                     else WEG_WORTLAUT)
            z.bemerkung = ("Die Stelle wurde im Abzug gefunden, aber kein "
                           "Vorfahr traegt eine Beitragskennung "
                           "('p<Nummer>' / 'pp<Nummer>'). Das ist bei "
                           "Uebersichts-, Such- und Profilseiten der "
                           "Regelfall.")
            return None

        if len(nummern) > 1:
            z.ergebnis = ERG_MEHRDEUTIG
            z.weg = WEG_WORTLAUT
            z.bemerkung = ("Der markierte Wortlaut kommt im Abzug in %d "
                           "VERSCHIEDENEN Beitraegen vor (%s). Es wird "
                           "NICHTS eingetragen - eine geratene Nummer braechte "
                           "falschen Betreff, falsches Datum und falsche "
                           "Gruppierung mit sich und saehe dabei unauffaellig "
                           "aus." % (len(nummern),
                                     ", ".join("#%d" % n for n in nummern)))
            return None

        if fundstelle.weg == WEG_XPATH:
            z.weg = WEG_ANKER
        elif fundstelle.mehrdeutig:
            z.weg = WEG_WORTLAUT_EINDEUTIG
            z.bemerkung = ("Der Wortlaut kommt %d-mal vor, alle Fundstellen "
                           "liegen aber im SELBEN Beitrag - fuer die Frage "
                           "nach dem Beitrag ist das eindeutig."
                           % len(fundstelle.treffer))
        else:
            z.weg = WEG_WORTLAUT
        return nummern[0]

    # ------------------------------------------------------------------
    def _seite(self, page_url: Any):
        """Den AbsatzFinder zu einer Adresse holen - je Adresse einmal."""
        from report_render.absatz_finder import AbsatzFinder

        schluessel = str(page_url or "")
        if schluessel in self._finder:
            return self._finder[schluessel]
        roh = self._blob(schluessel)
        finder = AbsatzFinder.aus_seiten_html(roh)
        self._finder[schluessel] = finder
        return finder

    def _blob(self, url: str) -> Optional[bytes]:
        """
        Den Seitenabzug zu einer Adresse holen.

        WARUM NICHT ForensicDb.get_page(): dessen Konstruktor legt die
        TEMP-VIEW 'blob_lookup' NEU an und wirft die vorhandene vorher weg
        (db/forensic_db.py, _setup_view) - im laufenden Betrieb zoege das dem
        Auslieferungspfad die Sicht unter den Fuessen weg (dieselbe
        Ueberlegung wie im Kopf von report_render/vollzitat_bauer.py). Dieses
        Werkzeug oeffnet ohnehin eine eigene Verbindung; die Abfrage bleibt
        deshalb bei den beiden Tabellen, aus denen der View gebildet wird.
        """
        if not url or self._con_blob is None:
            return None
        # BUILD 731 - FEHLER IN MEINEM EIGENEN WERKZEUG, gefunden beim
        # Nachgehen von Alex' Ankerbefund.
        #
        # 'fdb.pages' fuehrt zu DERSELBEN Adresse bis zu ZWEI Abzuege: den
        # gewoehnlichen (method='GET') und den einer Formularabsendung
        # (method='POST' - das Ergebnis einer Umfrageabstimmung; Beleg
        # db/forensic_db.py:415-436 und der dortige Kopf, "Projektgespraech
        # 2026-04-19"). Der AUSLIEFERUNGSPFAD nimmt ausdruecklich den
        # GET-Abzug: get_page(url, method='GET'). MEINE ABFRAGEN TATEN DAS
        # NICHT - ohne Filter und ohne ORDER BY entscheidet SQLite, welche
        # Zeile 'LIMIT 1' erwischt.
        #
        # WAS DAS ANRICHTET: Der Ermittler hat den GET-Abzug im Browser
        # gesehen und seinen Anker dagegen gerechnet. Bekam der Nachtrag den
        # POST-Abzug, verglich er den Anker mit einer ANDEREN Seite - und
        # meldete pflichtgemaess, der Anker loese nicht auf. Die Meldung waere
        # richtig gewesen und die Diagnose trotzdem falsch.
        #
        # Ob das Alex' Befund erklaert, ist damit NICHT gesagt - es ist eine
        # Fehlerquelle weniger, mehr behaupte ich nicht.
        for sql, parameter in (
            ("SELECT html FROM fdb.pages WHERE url_canonical = ? "
             "AND method = 'GET' LIMIT 1", (url,)),
            ("SELECT p.html FROM fdb.pages p JOIN fdb.page_aliases a "
             "ON a.page_id = p.id WHERE a.url_raw = ? AND p.method = 'GET' "
             "LIMIT 1", (url,)),
            # Die Adressen im Paket koennen die vollstaendige Onion-Adresse
            # tragen, annotations.page_url dagegen nur den Pfad
            # (_make_blob_lookup_sql entfernt den Vorspann ueber REPLACE).
            # Deshalb zuletzt der Vergleich auf das Ende.
            ("SELECT html FROM fdb.pages WHERE url_canonical LIKE ? "
             "AND method = 'GET' LIMIT 1", ("%" + url,)),
            ("SELECT p.html FROM fdb.pages p JOIN fdb.page_aliases a "
             "ON a.page_id = p.id WHERE a.url_raw LIKE ? "
             "AND p.method = 'GET' LIMIT 1", ("%" + url,)),
        ):
            try:
                zeile = self._con_blob.execute(sql, parameter).fetchone()
            except sqlite3.Error as exc:
                logger.warning("postid_nachtrag: Abfrage fehlgeschlagen "
                               "(%s): %s", exc, sql)
                continue
            if zeile is not None and zeile[0]:
                return zeile[0]
        return None

    #: Die Verbindung, ueber die _blob() liest. Sie wird von lauf() gesetzt;
    #: als Klassenattribut vorbelegt, damit _blob() auch dann eine
    #: verstaendliche Antwort gibt, wenn jemand die Klasse ohne Lauf benutzt.
    _con_blob: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    def _im_paket(self, con: sqlite3.Connection, art: str,
                  post_id: int) -> str:
        """
        Kennt das Paket diese Nummer? 'ja' | 'nein' | 'ungeprueft'.

        Gefragt werden je Art ZWEI Tabellen: die uid_-Tabelle fuehrt nur die
        Beitraege des untersuchten Benutzers, die alias-Tabelle auch fremde.
        Ein 'nein' ist deshalb KEIN Gegenbeweis (s. Kopf) - es steht im
        Protokoll und entscheidet nichts.
        """
        if self._tabellen is None:
            try:
                self._tabellen = {
                    r["name"] for r in con.execute(
                        "SELECT name FROM fdb.sqlite_master "
                        "WHERE type = 'table'")}
            except sqlite3.Error:
                self._tabellen = set()

        if art == "pn":
            paare = (("uid_pms_posts", "pm_post_id"),
                     ("pm_aliases", "pm_post_id"))
        else:
            paare = (("uid_posts", "post_id"), ("post_aliases", "post_id"))

        gefragt = False
        for tabelle, spalte in paare:
            if tabelle not in self._tabellen:
                continue
            gefragt = True
            try:
                zeile = con.execute(
                    "SELECT 1 FROM fdb.%s WHERE %s = ? LIMIT 1"
                    % (tabelle, spalte), (post_id,)).fetchone()
            except sqlite3.Error:
                continue
            if zeile is not None:
                return "ja"
        return "nein" if gefragt else "ungeprueft"

    # ------------------------------------------------------------------
    @staticmethod
    def _auswahl(roh: Any, beleg_id: int) -> Any:
        if not roh:
            return None
        try:
            return json.loads(roh)
        except (ValueError, TypeError):
            logger.warning("postid_nachtrag: selection_json der Annotation "
                           "%s ist kein gueltiges JSON.", beleg_id)
            return None

    # ------------------------------------------------------------------
    # Schreiben
    # ------------------------------------------------------------------
    def _schreiben(self, con: sqlite3.Connection, befund: Laufbefund,
                   operator: str, protokoll_datei: Optional[Path],
                   protokoll_hash: str) -> None:
        """
        Alle Nachtraege UND den Beleg in EINER Transaktion.

        ENTWEDER BEIDES ODER NICHTS. Ein Nachtrag ohne Eintrag in der
        Hash-Kette waere eine unbelegte Aenderung am Beweismittel; ein
        Eintrag ohne Nachtrag waere eine Falschaussage im Protokoll. Beides
        ist in derselben Datei, also in derselben Transaktion moeglich -
        genau die Zusage, die CoordinatorWriter.audited_write fuer die
        coordinator.db gibt.
        """
        from management.audit.evidence_audit_log import EvidenceAuditLog
        from management.audit.event_types import EventType

        zu_tun = [z for z in befund.zeilen if z.ergebnis in ERGEBNISSE_SCHREIBEND]
        if not zu_tun:
            befund.hinweise.append(
                "Es gab nichts einzutragen - die Datenbank wurde NICHT "
                "veraendert. Die Sicherung bleibt trotzdem liegen; sie zu "
                "loeschen ist Sache des Bedieners.")
            return

        con.execute("BEGIN IMMEDIATE")
        try:
            for z in zu_tun:
                # 'AND post_id IS NULL' ist die zweite Sperre gegen das
                # Ueberschreiben: zwischen Lesen und Schreiben koennte ein
                # Ermittler dieselbe Zeile bearbeitet haben. Dann greift
                # dieses UPDATE nicht - und das ist richtig so.
                zeiger = con.execute(
                    "UPDATE annotations SET post_id = ? "
                    "WHERE id = ? AND post_id IS NULL",
                    (z.post_id, z.annotation_id))
                if zeiger.rowcount != 1:
                    raise RuntimeError(
                        "Beleg #%d liess sich nicht eintragen (rowcount=%d). "
                        "Wurde die Zeile waehrend des Laufs von anderer Seite "
                        "geaendert? Der ganze Lauf wird zurueckgenommen."
                        % (z.annotation_id, zeiger.rowcount))

            abschnitte = [zu_tun[i:i + self.BELEG_GRENZE]
                          for i in range(0, len(zu_tun), self.BELEG_GRENZE)]
            kette = EvidenceAuditLog(con)
            marke = int(time.time())
            for nr, abschnitt in enumerate(abschnitte, 1):
                nutzlast: Dict[str, Any] = {
                    "werkzeug": "tools/postid_nachtragen.py",
                    "build": 728,
                    "lauf": marke,      # verbindet die Abschnitte EINES Laufs
                    "abschnitt": nr,
                    "abschnitte": len(abschnitte),
                    "evidence": self._evidence.name,
                    "forensic": self._forensic.name,
                    "sicherung": (Path(befund.sicherung).name
                                  if befund.sicherung else None),
                    "operator": operator or None,
                    "geprueft": befund.geprueft,
                    "eingetragen_gesamt": len(zu_tun),
                    "wege": befund.wege(),
                    "nur_anker": self._nur_anker,
                    "auch_ersetzte": self._auch_ersetzte,
                    "aenderungen": [z.als_beleg() for z in abschnitt],
                }
                if protokoll_datei is not None:
                    # Der Name der Protokolldatei steht mit im Beleg, damit
                    # sich Kette und Konsolenmitschrift spaeter zuordnen
                    # lassen. Der Inhalt der Datei ist NICHT massgeblich -
                    # massgeblich ist die Kette.
                    nutzlast["protokoll"] = Path(protokoll_datei).name
                    if protokoll_hash:
                        nutzlast["protokoll_sha256"] = protokoll_hash
                kette.append(
                    event_type=EventType.ANNOTATION_POSTID_BACKFILLED,
                    actor_id=None,      # Wartungslauf, kein angemeldeter
                                        # Ermittler - der Bediener steht als
                                        # 'operator' im Payload.
                    target_type="annotations",
                    target_id="post_id",
                    payload=nutzlast)

            con.execute("COMMIT")
        except Exception as exc:
            con.execute("ROLLBACK")
            befund.abgebrochen = (
                "ABGEBROCHEN, NICHTS GEAENDERT (%s). Die Datenbank steht "
                "unveraendert; die Sicherung %s ist damit nicht noetig, "
                "schadet aber nicht."
                % (exc, befund.sicherung or "(keine)"))
            for z in befund.zeilen:
                if z.ergebnis == ERG_GETRAGEN:
                    z.ergebnis = ERG_WUERDE
            logger.exception("postid_nachtrag: Rollback.")
            return

        befund.geschrieben = len(zu_tun)
