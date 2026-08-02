# =============================================================================
# management/db_startbefund.py
# IT-Forensisches Ermittlungswerkzeug — Anlagenpflege
# =============================================================================
# Zweck (Build 657):
#   DIE PRUEFUNG zum Katalog aus management/db_katalog.py. Sie beantwortet
#   beim Serverstart EINE Frage je Datenbank: "Ist sie auf Stand?" - und wenn
#   nicht, mit welchem Befehl das zu beheben ist.
#
# ── WAS SIE NICHT TUT ───────────────────────────────────────────────────────
#
#   SIE HEILT NICHT. Die Begruendung steht im Kopf des Katalogs; hier nur die
#   Folge daraus: erhebe() oeffnet jede Datei NUR LESEND (mode=ro). Es gibt in
#   dieser Datei keinen Schreibweg, und das ist keine Selbstbeschraenkung,
#   sondern die Bauart.
#
#   SIE VERHINDERT DEN START NICHT (ausser bei blockierend=True im Katalog -
#   heute nur forensic_<uid>.db, und deren Pruefung liegt weiterhin in
#   core/startup_checks.py, wo sie hingehoert). Ein Rueckstand der
#   templates.db kostet drei Sichten; den ganzen Server deswegen
#   anzuhalten waere unverhaeltnismaessig.
#
#   SIE DARF NIE WERFEN. Eine Startpruefung, die den Start verhindert, weil
#   SIE SELBST einen Fehler hat, ist schlimmer als keine. Jede Erhebung
#   laeuft deshalb in einem eigenen try; ein Fehler wird zum Befund
#   'nicht pruefbar' und nicht zur Ausnahme. Muster: management.py Schritt 3b
#   ("Pruefung darf nie den Start verhindern, aber sie schweigt auch nicht").
#
# ── DIE ZUSAMMENFASSUNG BEI FALLDATENBANKEN ─────────────────────────────────
#
#   evidence_<uid>.db und assets_<uid>.db gibt es je Fall. Sie einzeln beim
#   Start aufzuzaehlen waere bei vielen Faellen eine Wand aus Text, die
#   niemand liest - und eine Meldung, die niemand liest, ist keine. Deshalb
#   wird gezaehlt und zusammengefasst; wer es genau wissen will, bekommt vom
#   genannten Werkzeug die Einzelaufstellung.
#
# Version: v0.8.658 · Build: 658 · 2026-08-02
#   Build 658: _falldatenbanken nimmt nur noch die kanonische Form und nennt,
#   was es uebergangen hat (Ticket c48b0d76).
# =============================================================================

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from management.db_katalog import (
    ART_FALL,
    STAND_REGISTER,
    STAND_SPUREN,
    STAND_VERSIEGELT,
    WERKZEUG,
    DbEintrag,
    pruefbare,
)

#: Die moeglichen Befunde je Datenbank.
BEFUND_OK = "ok"                 #: auf Stand
BEFUND_RUECKSTAND = "rueckstand"  #: Migration(en) fehlen
BEFUND_FEHLT = "fehlt"           #: Datei nicht vorhanden
BEFUND_UNPRUEFBAR = "unpruefbar"  #: Datei da, aber nicht lesbar/auswertbar
BEFUND_UEBERSPRUNGEN = "uebersprungen"  #: bewusst nicht geprueft (s. Grund)


@dataclass(frozen=True)
class Befund:
    """Ergebnis EINER Datenbankpruefung. Reines Datenobjekt."""
    kennung: str
    name: str
    art: str
    pfad: str
    lage: str
    #: Klartext: was gefunden wurde.
    text: str
    #: Der Behebungsbefehl, oder None.
    befehl: Optional[str]
    blockierend: bool

    @property
    def ok(self) -> bool:
        return self.lage in (BEFUND_OK, BEFUND_UEBERSPRUNGEN)


class DbStartbefund:
    """
    Erhebt den Schemastand aller Datenbanken EINES Servers.

    server: 'verwaltung' oder 'ermittler'.
    config: ein Objekt mit .get(schluessel, vorgabe) - der ConfigLoader.
            Injizierbar, damit die Pruefung ohne config.yaml testbar bleibt.
    """

    def __init__(self, server: str, config) -> None:
        self._server = server
        self._config = config

    # ------------------------------------------------------------------
    def _pfad(self, e: DbEintrag) -> Optional[str]:
        """Der aufgeloeste Pfad, oder None wenn nicht ermittelbar."""
        if not e.config_schluessel:
            return None
        try:
            wert = self._config.get(e.config_schluessel, e.vorgabe)
        except Exception:
            wert = e.vorgabe
        return str(wert) if wert else None

    # ------------------------------------------------------------------
    def erhebe(self) -> List[Befund]:
        """Alle Befunde. WIRFT NIE."""
        raus: List[Befund] = []
        for e in pruefbare(self._server):
            try:
                raus.append(self._einer(e))
            except Exception as exc:                     # noqa: BLE001
                # Grundregel 1: ein Fehler der Pruefung wird BENANNT, nicht
                # verschwiegen - und er wird nicht zur Ausnahme, die den
                # Start kostet.
                raus.append(Befund(
                    kennung=e.kennung, name=e.name, art=e.art,
                    pfad=self._pfad(e) or "?", lage=BEFUND_UNPRUEFBAR,
                    text="Der Stand liess sich nicht feststellen: %s" % exc,
                    befehl=e.befehl, blockierend=False))
        return raus

    # ------------------------------------------------------------------
    def _einer(self, e: DbEintrag) -> Befund:
        pfad = self._pfad(e)
        if not pfad:
            return Befund(e.kennung, e.name, e.art, "?", BEFUND_UNPRUEFBAR,
                          "Kein Pfad ermittelbar (%s)." % e.config_schluessel,
                          e.befehl, False)

        if e.art == ART_FALL:
            return self._falldatenbanken(e, pfad)

        if not os.path.exists(pfad):
            return Befund(e.kennung, e.name, e.art, pfad, BEFUND_FEHLT,
                          "Die Datei gibt es nicht.", e.befehl, e.blockierend)

        if e.stand == STAND_SPUREN:
            return self._spuren(e, pfad)
        if e.stand == STAND_REGISTER:
            return self._register(e, pfad)
        # STAND_VERSIEGELT bei einer Anlagendatenbank kommt heute nicht vor;
        # der Fall wird trotzdem benannt statt stillschweigend als 'ok'
        # durchgereicht.
        return Befund(e.kennung, e.name, e.art, pfad, BEFUND_UEBERSPRUNGEN,
                      "Fuer diese Art ist an dieser Stelle keine Pruefung "
                      "vorgesehen (siehe Katalog).", None, False)

    # ------------------------------------------------------------------
    def _spuren(self, e: DbEintrag, pfad: str) -> Befund:
        """
        templates.db: der Stand wird an Spuren abgelesen. Die Liste der
        Migrationen und ihrer Spuren steht in management/templates_db_status.py
        und wird von DORT geholt - eine zweite Liste hier waere die
        Doppelwahrheit, die diese ganze Datei vermeiden soll.
        """
        from management.templates_db_status import MIGRATIONEN, spur_gefunden

        con = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
        try:
            offen = [(name, build) for name, build, spur, _ in MIGRATIONEN
                     if not spur_gefunden(con, spur)]
        finally:
            con.close()

        if not offen:
            return Befund(e.kennung, e.name, e.art, pfad, BEFUND_OK,
                          "Alle %d bekannten Migrationen sind angewandt."
                          % len(MIGRATIONEN), None, False)
        namen = ", ".join("Build %d (%s)" % (b, n) for n, b in offen)
        return Befund(e.kennung, e.name, e.art, pfad, BEFUND_RUECKSTAND,
                      "%d von %d Migrationen fehlen: %s"
                      % (len(offen), len(MIGRATIONEN), namen),
                      e.befehl, e.blockierend)

    # ------------------------------------------------------------------
    def _register(self, e: DbEintrag, pfad: str) -> Befund:
        """
        coordinator.db: das Register schema_migrations ist massgeblich. Die
        vorhandenen Migrationen kommen aus dem Code - dieselbe Quelle, die
        MigrationStatusCheck seit Build 376 benutzt.
        """
        import management.migrations.coordinator as coordinator_migrations
        from management.migrations.runner import discover

        vorhanden = sorted(m.VERSION for m in discover(coordinator_migrations))
        con = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
        try:
            try:
                angewandt = sorted(
                    r[0] for r in con.execute(
                        "SELECT version FROM schema_migrations"))
            except sqlite3.OperationalError:
                # KEIN Register. Bei coordinator.db heisst das: nicht
                # eingerichtet - anders als bei den Falldatenbanken, wo ein
                # fehlendes Register auch bedeuten kann, dass die Wirkungen
                # laengst da sind (Befund Build 586).
                return Befund(e.kennung, e.name, e.art, pfad,
                              BEFUND_RUECKSTAND,
                              "Das Register schema_migrations fehlt - die "
                              "Datenbank ist nicht eingerichtet.",
                              e.befehl, e.blockierend)
        finally:
            con.close()

        offen = [v for v in vorhanden if v not in set(angewandt)]
        if not offen:
            return Befund(e.kennung, e.name, e.art, pfad, BEFUND_OK,
                          "Alle %d Migrationen sind angewandt."
                          % len(vorhanden), None, False)
        return Befund(e.kennung, e.name, e.art, pfad, BEFUND_RUECKSTAND,
                      "%d Migration(en) fehlen: %s"
                      % (len(offen), ", ".join("m%03d" % v for v in offen)),
                      e.befehl, e.blockierend)

    # ------------------------------------------------------------------
    def _falldatenbanken(self, e: DbEintrag, verzeichnis: str) -> Befund:
        """
        Eine Datei JE FALL. Es wird GEZAEHLT, nicht aufgezaehlt (s. Kopf).

        Die Pruefung ist bewusst grob: vorhanden ist das Register oder nicht.
        Eine feinere Aussage kostet das Oeffnen jeder Datei und gehoert in
        tools/migrate-dbs.py, das sie je Fall liefert.
        """
        p = Path(verzeichnis)
        if not p.is_dir():
            return Befund(e.kennung, e.name, e.art, verzeichnis, BEFUND_FEHLT,
                          "Das Verzeichnis gibt es nicht.", None, False)

        # ------------------------------------------------------------------
        # BUILD 658 - NUR DIE KANONISCHE FORM.
        #
        # Bis Build 657 stand hier glob("*.db") und nahm damit ALLES. Im
        # evidence-Verzeichnis liegen aber auch die TRANSPORTDATEIEN des
        # Cross-Annotation-Integrators ("evidence_<uid>_<iid>.db"): sie sind
        # voruebergehend, tragen ein anderes Schema und haben zu Recht kein
        # Register. Sieben davon erzeugten auf der Anlage von mc bei JEDEM
        # Serverstart einen Warnbalken.
        #
        # DER SCHADEN WAR NICHT DER FALSCHE ZAEHLER, SONDERN DIE ABSTUMPFUNG.
        # Ein Balken, der bei jedem Start etwas meldet, das in Ordnung ist,
        # wird nach der dritten Woche nicht mehr gelesen - und dann faellt
        # auch die echte Meldung nicht mehr auf. Genau die Falle, die dieser
        # Startbefund schliessen sollte.
        #
        # DAS MUSTER KOMMT AUS DEM KATALOG, nicht von hier: es gehoert zum
        # Wesen der Datenbank wie ihr Pfad. Fehlt es, wird NICHT stillschweigend
        # alles genommen - dann ist der Katalog unvollstaendig, und das ist
        # ein Befund.
        # ------------------------------------------------------------------
        alle = sorted(x for x in p.glob("*.db") if x.is_file())
        if not e.datei_muster:
            return Befund(e.kennung, e.name, e.art, verzeichnis,
                          BEFUND_UNPRUEFBAR,
                          "Im Katalog fehlt das Dateinamensmuster fuer diese "
                          "Art - es laesst sich nicht entscheiden, welche "
                          "der %d Dateien gemeint sind." % len(alle),
                          None, False)
        muster = re.compile(e.datei_muster)
        dateien = [x for x in alle if muster.match(x.name)]
        beiseite = len(alle) - len(dateien)
        # GRUNDREGEL 1: was uebergangen wird, wird GEZAEHLT und GENANNT. Eine
        # Pruefung, die Dateien wortlos auslaesst, ist von einer
        # unvollstaendigen nicht zu unterscheiden.
        nachsatz = ("" if not beiseite else
                    " %d weitere Datei(en) im Verzeichnis tragen nicht die "
                    "Form '%s' und sind uebergangen worden (z. B. "
                    "Transportdateien der Fremd-Annotationen)."
                    % (beiseite, e.name))

        if not dateien:
            return Befund(e.kennung, e.name, e.art, verzeichnis, BEFUND_OK,
                          "Keine Falldatenbanken vorhanden." + nachsatz,
                          None, False)

        ohne_register: List[str] = []
        unlesbar: List[str] = []
        for datei in dateien:
            try:
                con = sqlite3.connect("file:%s?mode=ro" % datei, uri=True)
                try:
                    con.execute(
                        "SELECT 1 FROM schema_migrations LIMIT 1").fetchone()
                except sqlite3.OperationalError:
                    ohne_register.append(datei.name)
                finally:
                    con.close()
            except sqlite3.Error:
                unlesbar.append(datei.name)

        if not ohne_register and not unlesbar:
            return Befund(e.kennung, e.name, e.art, verzeichnis, BEFUND_OK,
                          "%d Falldatenbank(en), alle mit Register."
                          % len(dateien) + nachsatz, None, False)

        teile = ["%d Falldatenbank(en) gefunden" % len(dateien)]
        if ohne_register:
            teile.append("%d ohne Register (%s)"
                         % (len(ohne_register), ", ".join(ohne_register[:5])
                            + (" …" if len(ohne_register) > 5 else "")))
        if unlesbar:
            teile.append("%d nicht lesbar (%s)"
                         % (len(unlesbar), ", ".join(unlesbar[:5])))
        # BEWUSST KEIN 'rueckstand': ein fehlendes Register kann auch heissen,
        # dass die Wirkungen laengst da sind - der Befund aus Build 586. Die
        # Meldung sagt, was gesehen wurde, und ueberlaesst das Urteil dem
        # Werkzeug, das genauer hinsehen kann.
        return Befund(e.kennung, e.name, e.art, verzeichnis, BEFUND_UNPRUEFBAR,
                      "; ".join(teile) + ". Ein fehlendes Register bedeutet "
                      "NICHT zwingend einen Rueckstand - genaueres sagt das "
                      "Werkzeug je Fall." + nachsatz,
                      WERKZEUG + " --subject-id <uid>", False)


# =============================================================================
# Die Ausgabe.
# =============================================================================
#: Breite des Warnbalkens - gleich wie in migration_status.py, damit die
#: beiden Meldungen am Bildschirm nicht wie zwei verschiedene Werkzeuge
#: aussehen.
_BALKEN = "!" * 72


def meldezeilen(befunde: List[Befund]) -> List[str]:
    """
    Die Startmeldung. LEERE LISTE, WENN ALLES IN ORDNUNG IST - eine
    Erfolgsmeldung je Datenbank waere bei zehn Eintraegen eine Wand, und die
    naechste echte Warnung ginge darin unter.

    Die Zusammenfassung 'alles auf Stand' gibt zusammenfassung() aus.
    """
    schlecht = [b for b in befunde if not b.ok]
    if not schlecht:
        return []

    zeilen = [_BALKEN,
              "!! ACHTUNG: Nicht alle Datenbanken sind auf dem erwarteten "
              "Stand.", "!!"]
    for b in schlecht:
        zeilen.append("!! %-18s %s" % (b.name, b.text))
        zeilen.append("!!   Pfad: %s" % b.pfad)
        if b.befehl:
            zeilen.append("!!   Abhilfe: %s" % b.befehl)
        zeilen.append("!!")
    zeilen.extend([
        "!! Der Server MIGRIERT BEWUSST NICHT SELBST: das Anwenden von",
        "!! Migrationen bleibt eine bewusste, protokollierte Handlung.",
        "!! Die genannten Befehle holen den Pfad aus config.yaml - bitte",
        "!! KEINEN Pfad von Hand eintippen (Vorfall 2026-08-02).",
        _BALKEN,
    ])
    return zeilen


def zusammenfassung(befunde: List[Befund]) -> str:
    """Eine Zeile fuer den Regelfall."""
    if not befunde:
        return "[db] Keine pruefbaren Datenbanken im Katalog."
    schlecht = [b for b in befunde if not b.ok]
    if not schlecht:
        return ("[db] Schemastand geprueft: %d Datenbanken, alle auf Stand."
                % len(befunde))
    return ("[db] Schemastand geprueft: %d Datenbanken, %d mit Befund."
            % (len(befunde), len(schlecht)))


def blockierende(befunde: List[Befund]) -> List[Befund]:
    """Die Befunde, die den Start verhindern muessen."""
    return [b for b in befunde if not b.ok and b.blockierend]
