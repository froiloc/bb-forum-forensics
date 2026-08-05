# =============================================================================
# management/backup/backup_wiederhersteller.py
# IT-Forensisches Ermittlungswerkzeug - Datensicherung
# =============================================================================
# Zweck:
#   DER RUECKWEG - und zwar der, den man vor dem Ernstfall einmal gefahren
#   hat.
#
# DER ANLASS (Vorgang 2785556a, Befund B3 der Nachpruefung vom 2026-07-31):
#   'management/backup/' kannte plan, run, list, pruefen - KEINEN Rueckweg.
#   Im ganzen Bestand gab es nur einen, und der gehoert der Migrationsflotte,
#   arbeitet auf deren eigenen Sicherungen und ist selbst Gegenstand eines
#   offenen Vorgangs (69ede1c7: er kopiert ueber die Originaldatei, ohne die
#   Exklusivitaet zu pruefen).
#
#   Eine Sicherung, deren Rueckweg nie gefahren wurde, ist eine Vermutung und
#   kein Beleg. Das ist dieselbe Ueberlegung, aus der im Projekt gilt, dass
#   ein Beispielaufruf gefahren sein muss, bevor er in die Hilfe kommt - nur
#   mit erheblich groesserem Einsatz.
#
# =============================================================================
# DIE ENTSCHEIDUNG, DIE DIESES BAUTEIL ZUSCHNEIDET (Alex, 2026-08-05)
# =============================================================================
#   DIESES WERKZEUG UEBERSCHREIBT NIEMALS EINE DATENBANK IM BETRIEB.
#
#   Es legt die wiederhergestellte Datei NEBEN das Original, unter dem Namen
#   '<original>.wiederhergestellt'. Der Tausch selbst bleibt Handarbeit nach
#   Anleitung - die Anleitung wird ausgegeben, mit den konkreten Befehlen und
#   in der richtigen Reihenfolge.
#
#   WARUM DAS SO GEWOLLT IST und nicht bloss Vorsicht: Ab dem 01.07.2026
#   stehen echte Ermittlerdaten in evidence_<uid>.db, forensic_<uid>.db und
#   assets_<uid>.db. Ein Werkzeug, das ein Beweismittel ueberschreiben KANN,
#   ist damit auch eine Angriffsflaeche und ein Bedienfehler-Risiko - und
#   zwar dauerhaft, nicht nur im Ernstfall. Der Rueckweg wird trotzdem
#   vollstaendig gefahren und belegt: der Test (tests/test_backup_restore.py,
#   Fall WH01) sichert, beschaedigt das Original, spielt zurueck, TAUSCHT und
#   prueft gegen. Was hier fehlt, ist allein der letzte Handgriff - und der
#   ist derjenige, den ein Mensch verantworten soll.
#
#   DIE TRENNUNG IST TECHNISCH ERZWUNGEN und steht nicht nur im Kommentar:
#   zielpfad() bildet den Schreibpfad, und _schreiben() bricht ab, wenn er
#   mit dem Original zusammenfaellt (Grundregel: keine Zusage, die nichts
#   durchsetzt - derselbe Befundtyp wie e9522fe2 und 906ede75).
#
# =============================================================================
# DIE REIHENFOLGE DER PRUEFUNGEN IST NICHT BELIEBIG
# =============================================================================
#   1. Die SICHERUNG: vorhanden, nicht leer, kein heisses Journal daneben.
#   2. Die PRUEFSUMME der Sicherung gegen die beim Sichern erhobene. Fehlt
#      sie, ist das ein BEFUND und kein Durchmarsch - genau dafuer wird sie
#      seit Build 354 erhoben (2785556a, zweiter Teil).
#   3. Die Sicherung INNEN: integrity_check, Seitenzahl, Schema.
#   4. Das ZIEL: erst auf ein heisses Journal sehen, DANN die Sperrprobe.
#      DIESE REIHENFOLGE IST DER PUNKT. Die Sperrprobe oeffnet die Datei
#      gewoehnlich; liegt daneben ein '-journal', rollt SQLite es dabei
#      zurueck. Am 2026-08-01 gemessen (backup_pruefer.py Z. 300-313): aus
#      34 MB werden 0 Byte. Ein Rueckweg, der beim HINSEHEN das Original
#      vernichtet, waere die schlimmste aller Antworten - das Original ist
#      im Ernstfall das einzige Stueck, das noch Daten aus der Zeit NACH der
#      Sicherung tragen koennte.
#   5. Der PLATZ am Zielort.
#   6. Erst dann wird geschrieben - und das Geschriebene wird gegengeprueft.
#
# WAS DIESES BAUTEIL NICHT KANN, und das gehoert in jeden Befund:
#   Es kann nicht sagen, ob die Sicherung INHALTLICH die richtige ist. Sie
#   ist der Stand ihres Zeitpunkts; alles, was danach erfasst wurde, ist in
#   ihr nicht enthalten. Und der Sicherungssatz ist nicht punktgleich
#   (Befund B2, Entscheidung mc 2026-07-31: Kennzeichnung statt
#   Wartungsfenster) - wer den ganzen Bestand zurueckspielt, bekommt einen
#   Zustand, den es so nie gegeben hat.
#
# KEINE DATENBANKANBINDUNG IN DIESEM MODUL. Die erwartete Pruefsumme wird
#   HEREINGEREICHT. Damit bleibt das Bauteil ohne coordinator.db pruefbar,
#   und die Route zur Registrierung liegt an einer Stelle: im Werkzeug.
#   Dasselbe Muster wie backup_pruefer.py, und aus demselben Grund.
#
# WARUM DIE DATENKLASSEN HIER STEHEN und nicht je in einer eigenen Datei:
#   Sie haben genau einen Gegenstand und keinen zweiten Abnehmer - wie in
#   backup_pruefer.py (Dateibefund/Labelbefund/Bestandsbefund neben
#   SicherungsPruefer). Eine Aufteilung waere hier Ordnung um ihrer selbst
#   willen und wuerde den Befund von seiner Erhebung trennen.
#
# Version: v0.8.680 - Build: 680 - 2026-08-05
# =============================================================================

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from typing import List, Optional, Tuple

from maintenance.exklusiv_befund import ExklusivBefund
from maintenance.cli_support import exklusiv_beurteilen
from management.migration_fleet.harness.hashing import sha512_file

#: Die Endung der wiederhergestellten Datei. Sie haengt HINTER dem
#: vollstaendigen Originalnamen ('evidence_18.db.wiederhergestellt'), damit
#: zweierlei gilt: der Name der Zieldatenbank bleibt lesbar, UND die Datei
#: endet nicht auf '.db' - kein Werkzeug und kein Dienst dieser Anlage
#: greift sie damit versehentlich auf.
ENDUNG_WIEDERHERGESTELLT = ".wiederhergestellt"

#: Die Endung, unter der das Original beim Tausch beiseitegelegt wird. Sie
#: wird von diesem Werkzeug NICHT geschrieben - sie steht hier, weil die
#: ausgegebene Anleitung sie nennt und beide dieselbe Quelle haben sollen.
ENDUNG_VORHER = ".vor_wiederherstellung"

#: Wie viel Platz am Zielort frei sein muss, als Vielfaches der
#: Sicherungsgroesse. Der Aufschlag deckt den voruebergehenden Mehrbedarf
#: waehrend des Schreibens ab (erst Teildatei, dann Umbenennen) und den
#: spaeteren Tausch, bei dem Original UND Kopie kurzzeitig nebeneinander
#: liegen. Dieselbe Ueberlegung wie backup.min_free_factor beim Sichern.
PLATZ_FAKTOR = 2.2

#: Rueckgabewerte. Sie stehen HIER und nicht im Werkzeug, damit Text, Befund
#: und Rueckgabewert dieselbe Quelle haben (Muster backup_pruefer.py).
RC_OK = 0
RC_BEFUND = 1
RC_VERWEIGERT = 2
RC_UNBRAUCHBAR = 3


class WiederherstellungsFehler(Exception):
    """
    Eine Zusage dieses Bauteils waere verletzt worden.

    Sie wird NICHT fuer die gewoehnlichen Verweigerungen benutzt - die sind
    ein Befund und kein Programmfehler, genauso wie ein Leerbefund bei
    'hilfe.py suche'. Sie fliegt allein dann, wenn das Bauteil im Begriff
    waere, etwas zu tun, was es zugesagtermassen nie tut: auf das Original
    zu schreiben.
    """


# -----------------------------------------------------------------------------
# Der Befund
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Pruefschritt:
    """
    EIN Pruefschritt und sein Ausgang.

    'geprueft=False' ist ausdruecklich ein eigener Zustand und faellt NICHT
    mit 'bestanden=False' zusammen. Der Unterschied zwischen 'stimmt nicht'
    und 'wurde nicht angesehen' muss sichtbar bleiben (Grundregel 1) -
    dieselbe Unterscheidung wie 'pruefsumme_stimmt' im SicherungsPruefer.
    """
    name: str
    bestanden: bool
    grund: str
    geprueft: bool = True

    @property
    def marke(self) -> str:
        """Sechs Zeichen fuer die Konsole - eine Spalte, die steht."""
        if not self.geprueft:
            return "OFFEN "
        return "OK    " if self.bestanden else "BEFUND"


@dataclass(frozen=True)
class Wiederherstellungsbefund:
    """Was bei EINEM Rueckweg festzustellen war."""
    sicherung: str
    ziel: str
    #: Die geschriebene Datei - oder None, wenn nichts geschrieben wurde.
    geschrieben: Optional[str] = None
    schritte: Tuple[Pruefschritt, ...] = ()
    #: Der Sperrbefund des ZIELS. None, wenn es nicht so weit kam.
    ruhe: Optional[ExklusivBefund] = None
    groesse: int = 0
    user_version: int = 0
    seiten: int = 0
    schema_objekte: int = 0
    #: True, wenn nur geprueft und ausdruecklich nicht geschrieben werden
    #: sollte. Der Unterschied zu 'konnte nicht schreiben' gehoert in den
    #: Befund - sonst liest sich ein Trockenlauf wie ein Fehlschlag.
    trockenlauf: bool = False
    #: True, wenn die ZIELDATENBANK selbst nicht mehr als Datenbank zu
    #: oeffnen ist. Ein eigenes Feld und keine Zeichenkettensuche im Grund:
    #: an dieser Feststellung haengt, ob die Tauschanleitung erscheint
    #: (siehe 'tauschbereit'), und das darf nicht von einer Wortwahl
    #: abhaengen, die jemand spaeter umformuliert.
    ziel_beschaedigt: bool = False
    fehler: Tuple[str, ...] = ()

    @property
    def offene_befunde(self) -> Tuple[Pruefschritt, ...]:
        return tuple(s for s in self.schritte
                     if s.geprueft and not s.bestanden)

    @property
    def ok(self) -> bool:
        """Kein einziger Pruefschritt hat einen Befund ergeben."""
        return not self.offene_befunde and not self.fehler

    @property
    def tauschbereit(self) -> bool:
        """
        Ob am ZIEL nichts entgegensteht, was sich AUSRAEUMEN liesse.

        Das ist eine andere Frage als 'ist die Kopie in Ordnung' - siehe die
        Ueberlegung bei _SCHRITTE_TAUSCH. Sie entscheidet, ob die
        Tauschanleitung ausgegeben wird.

        DIE AUSNAHME IST DER WICHTIGE TEIL, und sie ist am eigenen Probelauf
        vom 2026-08-05 aufgefallen: Ist die Zieldatenbank SELBST beschaedigt,
        kann die Sperrprobe an ihr NIE 'ruhig' melden - SQLite oeffnet sie
        nicht. Wer diesen Fall wie einen Halter behandelt, schickt den
        Ermittler in eine Sackgasse: er bekaeme die Tauschanleitung niemals
        zu sehen, ausgerechnet im haeufigsten Ernstfall.
        Ein beschaedigtes Ziel zeigt keinen Halter an - es zeigt den ANLASS
        an. Der Vorbehalt bleibt und wird der Anleitung vorangestellt.
        """
        namen = {s.name for s in self.offene_befunde}
        if Z_KEIN_JOURNAL in namen:
            return False
        if Z_RUHE in namen and not self.ziel_beschaedigt:
            return False
        return True

    def rueckgabewert(self) -> int:
        """
        Der Rueckgabewert - damit eine Ueberwachung ihn auswerten kann, ohne
        die Ausgabe zu lesen.

        NACH SCHWERE GEORDNET, nicht nach Zufall:
          3  DIE SICHERUNG SELBST TAUGT NICHT - falsche Pruefsumme, nicht
             integer, leer, gar nicht da. Der schwerste Fall: hier ist nicht
             der Rueckweg gescheitert, sondern das, worauf man sich
             verlassen wollte.
          2  ES LIEGT KEINE KOPIE BEREIT, obwohl die Sicherung taugt - der
             Platz fehlt, das Schreiben ist gescheitert, oder die Kopie hat
             die Gegenprobe nicht bestanden.
          1  DIE KOPIE LIEGT BEREIT, ABER DAS ZIEL IST NICHT TAUSCHBEREIT.
             Etwas ist zu tun, bevor getauscht wird - und im haeufigsten
             Ernstfall ist genau das die Nachricht: 'deine Zieldatenbank ist
             beschaedigt, die Ersatzdatei steht daneben'.
          0  Nichts zu beanstanden.
        """
        if self.fehler:
            return RC_UNBRAUCHBAR
        schwer = {s.name for s in self.offene_befunde}
        if schwer & _SCHRITTE_SICHERUNG:
            return RC_UNBRAUCHBAR
        if schwer & _SCHRITTE_KOPIE:
            return RC_VERWEIGERT
        if schwer:
            return RC_BEFUND
        return RC_OK


# =============================================================================
# WELCHER SCHRITT WAS VERHINDERT - die Unterscheidung, um die es geht
# =============================================================================
# Sie ist beim Bau dieses Bauteils erst am eigenen Test WH01 aufgefallen, und
# sie ist wichtig genug, um hier ausgeschrieben zu stehen.
#
# DER ERSTE ENTWURF liess JEDEN Befund das Schreiben der Kopie verhindern -
# auch einen am ZIEL. Damit verweigerte der Rueckweg ausgerechnet den
# haeufigsten Ernstfall: Ist die Zieldatenbank zerstoert, kann SQLite sie
# nicht oeffnen, die Sperrprobe meldet 'nicht messbar' - und das Werkzeug
# haette die Arbeit eingestellt. Ein Rueckweg, der bei einer kaputten
# Zieldatenbank nichts tut, ist kein Rueckweg.
#
# ES SIND ZWEI VERSCHIEDENE FRAGEN, und sie gehoeren getrennt beantwortet:
#
#   (1) DARF DIE KOPIE ENTSTEHEN? Sie wird NEBEN das Original gelegt und
#       fasst es nicht an. Dagegen spricht nur etwas, das die Kopie selbst
#       betrifft: eine untaugliche Sicherung (dann waere die Kopie eine
#       Falle) oder fehlender Platz (dann geht es technisch nicht).
#
#   (2) DARF GETAUSCHT WERDEN? Das ist die gefaehrliche Frage, und sie
#       haengt am ZIEL: haelt es noch jemand, liegt ein heisses Journal
#       daneben. Ihre Antwort steuert, ob die Tauschanleitung ueberhaupt
#       ausgegeben wird - und sie ist ohnehin nur eine Momentaufnahme,
#       weshalb Schritt 1 der Anleitung sie vor dem Tausch WIEDERHOLEN
#       laesst.
#
# Als Mengen und nicht als Zahlen am Schritt: so steht die Zuordnung an
# EINER Stelle und ist nachlesbar, ohne alle Erzeugungsstellen durchzusehen.
S_VORHANDEN = "sicherung_vorhanden"
S_NICHT_LEER = "sicherung_nicht_leer"
S_KEIN_JOURNAL = "sicherung_ohne_journal"
S_PRUEFSUMME = "pruefsumme"
S_INTEGRITAET = "integritaet"
S_SCHEMA = "schema"
Z_KEIN_JOURNAL = "ziel_ohne_journal"
Z_RUHE = "ziel_in_ruhe"
Z_PLATZ = "platz"
W_GESCHRIEBEN = "kopie_geschrieben"
W_GEGENPROBE = "gegenprobe"

#: Befunde an der SICHERUNG. Sie verhindern die Kopie - eine Kopie aus einer
#: untauglichen Sicherung waere eine Falle: sie sieht aus wie ein Ergebnis.
_SCHRITTE_SICHERUNG = {S_VORHANDEN, S_NICHT_LEER, S_KEIN_JOURNAL,
                       S_PRUEFSUMME, S_INTEGRITAET, S_SCHEMA}

#: Befunde, die die KOPIE betreffen. Auch sie verhindern ein Ergebnis - hier
#: aber aus technischen Gruenden, nicht aus Misstrauen gegen die Sicherung.
_SCHRITTE_KOPIE = {Z_PLATZ, W_GESCHRIEBEN, W_GEGENPROBE}

#: Befunde am ZIEL. Sie verhindern den TAUSCH und NICHT die Kopie. Genau
#: hier lag der erste Entwurf falsch - siehe die Ueberlegung oben.
_SCHRITTE_TAUSCH = {Z_KEIN_JOURNAL, Z_RUHE}


# -----------------------------------------------------------------------------
# Das Bauteil
# -----------------------------------------------------------------------------

class Wiederhersteller:
    """
    Spielt EINE Sicherung neben ihr Original zurueck - nach Pruefung.

    Der Konstruktor tut nichts ausser sich die beiden Pfade zu merken; alle
    Arbeit steckt in fahren(), damit ein Aufruf, der nur das Objekt baut,
    keine Platte anfasst (Muster SicherungsPruefer).
    """

    def __init__(self, sicherung: str, ziel: str) -> None:
        self._sicherung = str(sicherung)
        self._ziel = str(ziel)

    # ------------------------------------------------------------- Zielpfad
    def zielpfad(self) -> str:
        """
        Wohin geschrieben wuerde. Oeffentlich, weil die Anleitung und der
        Test denselben Namen brauchen - abgeschrieben liefe er auseinander.
        """
        return self._ziel + ENDUNG_WIEDERHERGESTELLT

    # ---------------------------------------------------------------- fahren
    def fahren(self, erwartete_summe: Optional[str] = None,
               schreiben: bool = True) -> Wiederherstellungsbefund:
        """
        Der Rueckweg.

        erwartete_summe - die beim Sichern erhobene SHA512 aus der
                          Registrierung. None heisst: es liegt keine vor -
                          das ist ein BEFUND und kein Grund, sie wegzulassen.
        schreiben       - False fuehrt alle Pruefungen aus und schreibt
                          NICHTS (Trockenlauf).

        Es wird IMMER die vollstaendige Prueffolge gefahren, soweit sie ohne
        die vorherige noch etwas aussagen kann. Ein Abbruch beim ersten
        Befund waere hier falsch: wer im Ernstfall wissen will, was zu tun
        ist, braucht ALLE Hindernisse auf einmal und nicht eines pro Versuch.
        Nur dort, wo ein Schritt den naechsten technisch unmoeglich macht
        (eine nicht vorhandene Datei hat keine Pruefsumme), wird der
        Folgeschritt als 'nicht geprueft' vermerkt statt als bestanden.
        """
        schritte: List[Pruefschritt] = []
        fehler: List[str] = []
        merkmale = dict(groesse=0, user_version=0, seiten=0, schema_objekte=0)

        # ---------------------------------------------------- 1. Die Datei
        vorhanden = os.path.isfile(self._sicherung)
        schritte.append(Pruefschritt(
            S_VORHANDEN, vorhanden,
            "Sicherungsdatei vorhanden" if vorhanden else
            "Sicherungsdatei nicht gefunden: %s" % self._sicherung))

        if not vorhanden:
            # Alles Weitere haette keinen Gegenstand. Es wird als OFFEN
            # vermerkt und nicht ausgelassen - eine Prueffolge mit Luecken
            # laesst sich sonst nicht von einer bestandenen unterscheiden.
            for name in (S_NICHT_LEER, S_KEIN_JOURNAL, S_PRUEFSUMME,
                         S_INTEGRITAET, S_SCHEMA, Z_KEIN_JOURNAL, Z_RUHE,
                         Z_PLATZ):
                schritte.append(Pruefschritt(
                    name, False, "ohne Sicherungsdatei nicht pruefbar",
                    geprueft=False))
            return Wiederherstellungsbefund(
                sicherung=self._sicherung, ziel=self._ziel,
                schritte=tuple(schritte), trockenlauf=not schreiben,
                **merkmale)

        groesse = os.path.getsize(self._sicherung)
        merkmale["groesse"] = groesse
        schritte.append(Pruefschritt(
            S_NICHT_LEER, groesse > 0,
            "%d Byte" % groesse if groesse > 0 else
            "LEER (0 Byte) - das ist die Signatur einer abgebrochenen "
            "Sicherung, nicht eine Sicherung ohne Inhalt"))

        # -------------------------------------- 2. Heisses Journal daneben
        # Wie im SicherungsPruefer: eine Datei mit heissem Journal wird
        # NICHT geoeffnet. SQLite wuerde das Journal zurueckspielen und die
        # Teildatei dabei auf 0 Byte verkuerzen - der Beleg, den wir
        # beurteilen wollen, waere dann weg.
        heiss = self._heisse_journale(self._sicherung)
        schritte.append(Pruefschritt(
            S_KEIN_JOURNAL, not heiss,
            "kein Journal daneben" if not heiss else
            "ABGEBROCHENE SICHERUNG - daneben liegt ein heisses Journal "
            "(%s). Die Datei wurde NICHT geoeffnet." % ", ".join(heiss)))

        anfassbar = bool(groesse) and not heiss

        # -------------------------------------------------- 3. Pruefsumme
        # SIE IST DER GRUND, WARUM ES DIESEN VORGANG GIBT. Seit Build 354
        # wird sie bei jeder Sicherung erhoben - und wurde bis Build 626
        # nie wieder ausgewertet. Hier ist sie die Eintrittskarte: ohne sie
        # wird nicht zurueckgespielt.
        if not anfassbar:
            schritte.append(Pruefschritt(
                S_PRUEFSUMME, False,
                "an einer leeren oder abgebrochenen Datei nicht sinnvoll",
                geprueft=False))
        elif not erwartete_summe:
            # KEIN DURCHMARSCH. Eine fehlende Vergleichssumme ist genau der
            # Zustand, den dieser Vorgang beklagt - sie hier stillschweigend
            # zu uebergehen, hiesse ihn fortzuschreiben.
            schritte.append(Pruefschritt(
                S_PRUEFSUMME, False,
                "KEINE erhobene Pruefsumme vorgelegt. Damit ist nicht "
                "feststellbar, ob diese Datei noch die ist, die beim "
                "Sichern zertifiziert wurde. Sie steht in der "
                "Registrierung (coordinator.db, Tabelle 'backups')."))
        else:
            try:
                ist = sha512_file(self._sicherung)
            except OSError as exc:
                ist = ""
                fehler.append("Pruefsumme nicht bildbar: %s" % exc)
            stimmt = bool(ist) and (ist == erwartete_summe)
            schritte.append(Pruefschritt(
                S_PRUEFSUMME, stimmt,
                "SHA512 stimmt mit der beim Sichern erhobenen ueberein"
                if stimmt else
                "SHA512 WEICHT AB - die Datei ist nicht mehr die "
                "zertifizierte.\n        erwartet: %s\n        gefunden: %s"
                % (erwartete_summe, ist or "(nicht bildbar)")))

        # ------------------------------------------- 4. Die Sicherung innen
        if not anfassbar:
            for name in (S_INTEGRITAET, S_SCHEMA):
                schritte.append(Pruefschritt(
                    name, False, "die Datei wurde nicht geoeffnet",
                    geprueft=False))
        else:
            innen, innenfehler, innenmerkmale = self._innen_pruefen(
                self._sicherung)
            schritte.extend(innen)
            fehler.extend(innenfehler)
            merkmale.update(innenmerkmale)

        # ------------------------------------------------------- 5. Das Ziel
        # ERST DAS JOURNAL, DANN DIE SPERRPROBE. Die Sperrprobe oeffnet die
        # Datei gewoehnlich (maintenance/cli_support.py: sqlite3.connect
        # ohne 'mode=ro' - sie MUSS schreibfaehig oeffnen, sonst misst sie
        # nichts). Laege daneben ein heisses Journal, rollte SQLite es beim
        # Oeffnen zurueck. Diese Reihenfolge ist deshalb keine Stilfrage.
        ziel_heiss = self._heisse_journale(self._ziel)
        schritte.append(Pruefschritt(
            Z_KEIN_JOURNAL, not ziel_heiss,
            "kein Journal neben der Zieldatei" if not ziel_heiss else
            "NEBEN DER ZIELDATENBANK LIEGT EIN HEISSES JOURNAL (%s). Dort "
            "ist etwas offen oder abgebrochen. Zweierlei folgt daraus: die "
            "Sperrprobe wurde NICHT gefahren (sie wuerde das Journal "
            "zurueckrollen), und ein Tausch waere jetzt gefaehrlich - das "
            "liegengebliebene Journal wuerde beim naechsten Oeffnen auf die "
            "EINGESETZTE Datei angewandt." % ", ".join(ziel_heiss)))

        ruhe: Optional[ExklusivBefund] = None
        ziel_beschaedigt = False
        if ziel_heiss:
            schritte.append(Pruefschritt(
                Z_RUHE, False,
                "wegen des heissen Journals nicht gefahren", geprueft=False))
        else:
            ruhe = exklusiv_beurteilen(self._ziel)
            ziel_beschaedigt = (not ruhe.ist_ruhig
                                and self._ist_beschaedigt(ruhe.grund))
            # NUR 'ruhig' IST RUHE. 'nicht messbar' zaehlt ausdruecklich
            # nicht (Vorgang 96f2b18f, Build 648): eine Ruhe, die nie
            # gemessen wurde, ist keine.
            #
            # DER GRUND WIRD HIER NOCH EINGEORDNET, und das ist mehr als
            # Kosmetik: Meldet die Probe 'file is not a database', dann ist
            # die Zieldatenbank SELBST BESCHAEDIGT - und das ist nicht
            # irgendein Hindernis, sondern der haeufigste Anlass, aus dem
            # jemand diesen Weg ueberhaupt faehrt. Wer im Ernstfall nur
            # 'nicht pruefbar' liest, sucht den Fehler bei sich.
            schritte.append(Pruefschritt(
                Z_RUHE, ruhe.ist_ruhig,
                ("Zieldatei in Ruhe (%s)" % ruhe.grund) if ruhe.ist_ruhig
                else ("Zieldatei NICHT nachweislich in Ruhe [%s]: %s%s"
                      % (ruhe.marke.strip(), ruhe.grund,
                         self._einordnung(ruhe.grund)))))

        # ------------------------------------------------------- 6. Der Platz
        platz_ok, platz_grund = self._platz_pruefen(groesse)
        schritte.append(Pruefschritt(Z_PLATZ, platz_ok, platz_grund))

        # ------------------------------------------------------ 7. Schreiben
        #
        # WAS DAS SCHREIBEN ANHAELT, ist NICHT jeder Befund - siehe die
        # Ueberlegung bei _SCHRITTE_TAUSCH. Ein Befund am ZIEL verhindert
        # den Tausch und nicht die Kopie; sonst verweigerte dieses Werkzeug
        # ausgerechnet den Ernstfall, fuer den es gebaut ist.
        geschrieben: Optional[str] = None
        dagegen = _SCHRITTE_SICHERUNG | _SCHRITTE_KOPIE
        vor_dem_schreiben = [s for s in schritte
                             if s.geprueft and not s.bestanden
                             and s.name in dagegen]

        if not schreiben:
            # TROCKENLAUF. Kein 'nicht geschrieben, weil gescheitert' -
            # es sollte gar nicht geschrieben werden, und das ist etwas
            # anderes.
            schritte.append(Pruefschritt(
                W_GESCHRIEBEN, False, "Trockenlauf - es wurde nichts "
                "geschrieben (--trocken)", geprueft=False))
            schritte.append(Pruefschritt(
                W_GEGENPROBE, False, "ohne geschriebene Datei kein "
                "Gegenlesen", geprueft=False))
        elif vor_dem_schreiben:
            schritte.append(Pruefschritt(
                W_GESCHRIEBEN, False,
                "NICHT GESCHRIEBEN - %d Befund(e) stehen dagegen. Ein "
                "Rueckweg, der ueber einen Befund hinweggeht, ist keiner."
                % len(vor_dem_schreiben), geprueft=False))
            schritte.append(Pruefschritt(
                W_GEGENPROBE, False, "ohne geschriebene Datei kein "
                "Gegenlesen", geprueft=False))
        else:
            pfad, schreibfehler = self._schreiben()
            if schreibfehler:
                schritte.append(Pruefschritt(
                    W_GESCHRIEBEN, False, schreibfehler))
                schritte.append(Pruefschritt(
                    W_GEGENPROBE, False, "ohne geschriebene Datei kein "
                    "Gegenlesen", geprueft=False))
            else:
                geschrieben = pfad
                schritte.append(Pruefschritt(
                    W_GESCHRIEBEN, True,
                    "Kopie liegt bereit: %s" % pfad))
                # DIE GEGENPROBE. Eine Kopie, die niemand nachgelesen hat,
                # ist genau die Vermutung, gegen die dieser Vorgang
                # geschrieben ist. Geprueft wird gegen die SUMME DER
                # SICHERUNG - byteweise kopiert, also muss sie gleich sein.
                schritte.append(self._gegenprobe(pfad))

        return Wiederherstellungsbefund(
            sicherung=self._sicherung, ziel=self._ziel,
            geschrieben=geschrieben, schritte=tuple(schritte), ruhe=ruhe,
            trockenlauf=not schreiben, ziel_beschaedigt=ziel_beschaedigt,
            fehler=tuple(fehler), **merkmale)

    # ------------------------------------------------------------- Helfer
    @staticmethod
    def _heisse_journale(pfad: str) -> List[str]:
        """Welche Journaldateien neben 'pfad' liegen. Reine Namensfrage."""
        return [a for a in ("-journal", "-wal") if os.path.exists(pfad + a)]

    @staticmethod
    def _ist_beschaedigt(grund: str) -> bool:
        """
        Ob der Sperrbefund davon spricht, dass die ZIELDATEI keine Datenbank
        mehr ist.

        Die Meldungen stammen von SQLite und sind in Anfuehrungszeichen
        stabil; geprueft wird deshalb auf die englischen Originalwendungen
        und nicht auf uebersetzten Text.
        """
        kurz = (grund or "").lower()
        return ("not a database" in kurz or "malformed" in kurz
                or "encrypted" in kurz)

    @classmethod
    def _einordnung(cls, grund: str) -> str:
        """
        Was ein unmessbarer Sperrbefund am ZIEL fuer diesen Weg bedeutet.

        Die Sperrprobe kennt ihren Anlass nicht - sie sagt, was sie
        gemessen hat, und das ist richtig so. Hier ist der Ort, an dem ihr
        Ergebnis in den Zusammenhang gestellt wird, und der Zusammenhang
        ist ein anderer als bei der Wartung: dort will jemand die Datenbank
        BENUTZEN, hier will jemand sie ERSETZEN.
        """
        kurz = (grund or "").lower()
        if cls._ist_beschaedigt(grund):
            return ("  ||  EINORDNUNG: Die Zieldatenbank ist SELBST "
                    "beschaedigt - SQLite kann sie nicht als Datenbank "
                    "oeffnen. Das ist kein Hindernis dieses Weges, sondern "
                    "sein haeufigster Anlass. Die Kopie wird deshalb "
                    "trotzdem abgelegt, und die Tauschanleitung erscheint - "
                    "denn die Sperrprobe wird an dieser Datei NIE 'frei' "
                    "melden. Ob noch jemand sie haelt, bleibt ungemessen; "
                    "der Nachweis der Ruhe ist deshalb ueber das Anhalten "
                    "der Dienste zu fuehren (Schritt 1 der Anleitung) und "
                    "nicht an dieser Datei.")
        if "schreibrecht" in kurz:
            return ("  ||  EINORDNUNG: Gemessen wurde nichts - der "
                    "ausfuehrende Benutzer darf die Zieldatei nicht "
                    "beschreiben. Das ist auf einem geteilten Laufwerk der "
                    "Normalfall und sagt ueber Halter nichts aus.")
        return ""

    def _innen_pruefen(self, pfad: str):
        """
        Die Sicherung von innen: integrity_check, Seitenzahl, Schema.

        Liefert (Schritte, Fehler, Merkmale). Die Merkmale werden
        ZURUECKGEGEBEN und nicht am Objekt abgelegt: ein Bauteil, das sein
        Zwischenergebnis in sich merkt, liefert beim zweiten Aufruf
        stillschweigend das erste - und ein stiller Fehlbeleg ist genau das,
        was hier nie entstehen darf (Grundregel 1).

        NUR-LESEND geoeffnet ('mode=ro'). Damit kann diese Pruefung unter
        keinen Umstaenden etwas an einer Sicherung veraendern - dieselbe
        Zusage wie im SicherungsPruefer, und wie dort technisch erzwungen
        statt nur behauptet.
        """
        schritte: List[Pruefschritt] = []
        fehler: List[str] = []
        try:
            con = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
            try:
                zeilen = con.execute("PRAGMA integrity_check").fetchall()
                seiten = int(con.execute("PRAGMA page_count").fetchone()[0])
                uv = int(con.execute("PRAGMA user_version").fetchone()[0])
                objekte = int(con.execute(
                    "SELECT count(*) FROM sqlite_master").fetchone()[0])
            finally:
                con.close()
        except sqlite3.Error as exc:
            schritte.append(Pruefschritt(
                S_INTEGRITAET, False,
                "keine lesbare Datenbank: %s" % exc))
            schritte.append(Pruefschritt(
                S_SCHEMA, False, "nicht lesbar", geprueft=False))
            return schritte, fehler, {}

        merkmale = dict(seiten=seiten, user_version=uv,
                        schema_objekte=objekte)

        integer = (len(zeilen) == 1 and zeilen[0][0] == "ok" and seiten > 0)
        if seiten == 0:
            grund = ("LEER (0 Seiten) - eine zurueckgerollte Teildatei. Sie "
                     "besteht 'integrity_check' und ist trotzdem nichts wert.")
        elif integer:
            grund = ("integrity_check: ok, %d Seiten, user_version=%d"
                     % (seiten, uv))
        else:
            grund = "integrity_check: " + "; ".join(
                str(z[0]) for z in zeilen[:5])
        schritte.append(Pruefschritt(S_INTEGRITAET, integer, grund))

        schritte.append(Pruefschritt(
            S_SCHEMA, objekte > 0,
            "%d Schemaobjekte" % objekte if objekte > 0 else
            "KEIN SCHEMA - die Datei ist formal in Ordnung, enthaelt aber "
            "nichts"))
        return schritte, fehler, merkmale

    def _platz_pruefen(self, groesse: int):
        """
        Ob am Zielort genug Platz ist.

        Gemessen wird am VERZEICHNIS des Ziels und nicht am Sicherungsort:
        dorthin wird geschrieben. Der Aufschlag (PLATZ_FAKTOR) deckt den
        spaeteren Tausch mit ab, bei dem Original und Kopie kurzzeitig
        nebeneinander liegen.
        """
        verzeichnis = os.path.dirname(os.path.abspath(self._ziel)) or "."
        try:
            frei = shutil.disk_usage(verzeichnis).free
        except OSError as exc:
            return False, ("Freier Platz an '%s' nicht feststellbar: %s"
                           % (verzeichnis, exc))
        noetig = int(groesse * PLATZ_FAKTOR)
        ok = frei >= noetig
        return ok, (
            "%d Byte frei, %d benoetigt (Faktor %.1f)"
            % (frei, noetig, PLATZ_FAKTOR) if ok else
            "ZU WENIG PLATZ an '%s': %d Byte frei, %d benoetigt (Faktor "
            "%.1f - er deckt den spaeteren Tausch mit ab, bei dem Original "
            "und Kopie nebeneinander liegen)."
            % (verzeichnis, frei, noetig, PLATZ_FAKTOR))

    def _schreiben(self):
        """
        Die Kopie NEBEN das Original legen.

        ZWEI ZUSAGEN, BEIDE HIER DURCHGESETZT:

        (1) NIEMALS AUF DAS ORIGINAL. Der Schreibpfad wird gebildet, nicht
            uebergeben, und er wird davor noch einmal gegen das Original
            gehalten. Faellt beides zusammen - etwa weil jemand
            ENDUNG_WIEDERHERGESTELLT auf "" gesetzt hat -, fliegt eine
            Ausnahme und es wird NICHTS geschrieben. Eine Zusage, die nichts
            durchsetzt, ist im Bestand dieses Projekts schon zweimal
            aufgefallen (e9522fe2, 906ede75); sie soll hier nicht ein
            drittes Mal entstehen.

        (2) KEINE HALBE DATEI. Geschrieben wird in eine Teildatei im
            ZIELVERZEICHNIS, dann fsync, dann os.replace - das ist auf einem
            Dateisystem unteilbar. Bricht der Lauf mittendrin ab, liegt eine
            '.teil'-Datei da und KEINE halbe '.wiederhergestellt'. Sonst
            entstuende genau der Zustand, den 'pruefen' im Sicherungsordner
            aufgedeckt hat: ein Abbruchrest, der wie ein Ergebnis aussieht.
        """
        ziel_neu = self.zielpfad()
        if os.path.abspath(ziel_neu) == os.path.abspath(self._ziel):
            raise WiederherstellungsFehler(
                "Der Schreibpfad faellt mit der Originaldatei zusammen (%s). "
                "Dieses Werkzeug ueberschreibt keine Datenbank im Betrieb; "
                "es wurde nichts geschrieben." % self._ziel)

        verzeichnis = os.path.dirname(os.path.abspath(ziel_neu)) or "."
        teil = None
        try:
            fd, teil = tempfile.mkstemp(
                dir=verzeichnis,
                prefix=os.path.basename(ziel_neu) + ".",
                suffix=".teil")
            os.close(fd)
            with open(self._sicherung, "rb") as quelle, \
                    open(teil, "wb") as senke:
                shutil.copyfileobj(quelle, senke, 1024 * 1024)
                senke.flush()
                # AUF DIE PLATTE, nicht nur in den Zwischenspeicher des
                # Betriebssystems. Ohne das kann ein Stromausfall unmittelbar
                # nach dem Umbenennen eine leere Datei unter dem fertigen
                # Namen hinterlassen.
                os.fsync(senke.fileno())
            os.replace(teil, ziel_neu)
            teil = None
        except OSError as exc:
            return None, ("Die Kopie konnte nicht geschrieben werden: %s"
                          % exc)
        finally:
            if teil and os.path.exists(teil):
                try:
                    os.unlink(teil)
                except OSError:            # pragma: no cover
                    pass
        return ziel_neu, ""

    def _gegenprobe(self, pfad: str) -> Pruefschritt:
        """
        Die geschriebene Datei nachlesen: gleiche Summe wie die Sicherung,
        und innen unversehrt.

        WARUM BEIDES: Die Summe belegt, dass die Kopie vollstaendig ist; der
        integrity_check belegt, dass das Ergebnis auch als Datenbank taugt.
        Die Summe allein genuegte theoretisch - praktisch ist der zweite
        Blick billig, und er ist genau der Blick, den man im Ernstfall
        keine zweite Gelegenheit hat zu tun.
        """
        try:
            summe_kopie = sha512_file(pfad)
            summe_quelle = sha512_file(self._sicherung)
        except OSError as exc:
            return Pruefschritt(W_GEGENPROBE, False,
                                "Gegenprobe nicht moeglich: %s" % exc)
        if summe_kopie != summe_quelle:
            return Pruefschritt(
                W_GEGENPROBE, False,
                "DIE KOPIE WEICHT VON DER SICHERUNG AB - sie ist unbrauchbar "
                "und darf nicht eingesetzt werden.")
        try:
            con = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
            try:
                zeilen = con.execute("PRAGMA integrity_check").fetchall()
            finally:
                con.close()
        except sqlite3.Error as exc:
            return Pruefschritt(W_GEGENPROBE, False,
                                "Die Kopie ist nicht lesbar: %s" % exc)
        if not (len(zeilen) == 1 and zeilen[0][0] == "ok"):
            return Pruefschritt(
                W_GEGENPROBE, False,
                "integrity_check der Kopie: " + "; ".join(
                    str(z[0]) for z in zeilen[:5]))
        return Pruefschritt(
            W_GEGENPROBE, True,
            "Kopie nachgelesen: SHA512 gleich der Sicherung, "
            "integrity_check ok")


# -----------------------------------------------------------------------------
# Ausgabe
# -----------------------------------------------------------------------------
# REINE FUNKTIONEN, kein print - dieselbe Trennung wie in backup_pruefer.py
# und management/help/cli_text.py, und aus demselben Grund: so ist jede Zeile
# Rueckgabewert und damit vergleichbar.
#
# ASCII und 78 Zeichen, wie ueberall auf der Kommandozeile dieser Anlage.

_BREITE = 78

#: Womit eine KOPIERBARE BEFEHLSZEILE beginnt (nach dem Einzug).
#:
#: SIE IST VON DER BREITENREGEL AUSGENOMMEN, und zwar ausdruecklich und
#: nicht aus Nachlaessigkeit: Ein umgebrochener Befehl ist ein FALSCHER
#: Befehl. Wer eine Zeile aus einer Anleitung kopiert, kopiert sie ganz -
#: und in der Produktivumgebung stehen dort UNC-Pfade, die fuer sich allein
#: schon breiter sind als jede Spalte. Dieselbe Ueberlegung wie bei den
#: Pfaden im Kopf des Berichts, nur zwingender.
#:
#: Die Marken stehen HIER, damit der Bericht und der Test (WH09) dieselbe
#: Quelle haben - abgeschrieben liefen sie beim naechsten Umbau auseinander.
BEFEHLSMARKEN: Tuple[str, ...] = ("Windows:", "Linux:", "python -m", "--ziel")


def _umbruch(text: str, einzug: str = "        ") -> List[str]:
    """
    Fliesstext umbrechen. Ueberlange Woerter - Pfade, Pruefsummen - werden
    NICHT zerschnitten; eine zerschnittene Pruefsumme waere unbrauchbar.
    Zeilenumbrueche im Text bleiben erhalten.
    """
    zeilen: List[str] = []
    for absatz in (text or "").split("\n"):
        aktuell = einzug
        leer = True
        for wort in absatz.split():
            if not leer and len(aktuell) + 1 + len(wort) > _BREITE:
                zeilen.append(aktuell)
                aktuell = einzug + wort
            else:
                aktuell = (einzug + wort) if leer else (aktuell + " " + wort)
            leer = False
        if not leer:
            zeilen.append(aktuell)
    return zeilen


def anleitung(befund: Wiederherstellungsbefund) -> List[str]:
    """
    DER HANDGRIFF, DEN DIESES WERKZEUG BEWUSST NICHT TUT.

    Sie wird nur ausgegeben, wenn tatsaechlich eine gegengelesene Kopie
    bereitliegt. Eine Anleitung zum Tausch neben einem Befund waere eine
    Einladung, den Befund zu uebergehen.

    DIE REIHENFOLGE IST DER INHALT: Das Original wird BEISEITEGELEGT und
    NICHT geloescht. Es ist im Ernstfall das einzige Stueck, das noch Daten
    aus der Zeit nach der Sicherung tragen koennte - und sei es nur in
    Bruchstuecken, die ein Sachverstaendiger noch herausholt.
    """
    z: List[str] = []
    z.append("-" * _BREITE)
    z.append("DER TAUSCH - VON HAND, IN DIESER REIHENFOLGE")
    z.append("")
    z.extend(_umbruch(
        "Dieses Werkzeug ueberschreibt keine Datenbank. Was jetzt folgt, "
        "verantwortet ein Mensch. Vier Augen sind hier keine Foermelei: "
        "der Schritt ist nicht rueckgaengig zu machen, wenn Schritt 2 "
        "uebersprungen wird.", einzug="  "))
    z.append("")

    # DER VORBEHALT BEI BESCHAEDIGTEM ZIEL. Er steht VOR Schritt 1 und
    # nicht darunter: Schritt 1 verlangt einen Nachweis, den diese Datei
    # nicht mehr hergeben kann, und wer das erst hinterher liest, hat es
    # schon vergeblich versucht.
    if befund.ziel_beschaedigt:
        z.append("  !! VORBEHALT - DIE ZIELDATENBANK IST SELBST BESCHAEDIGT")
        z.extend(_umbruch(
            "Die Sperrprobe wird an dieser Datei NIE 'frei' melden; SQLite "
            "kann sie nicht oeffnen. Der Nachweis der Ruhe ist deshalb "
            "NICHT an ihr zu fuehren, sondern am Betrieb: alle Dienste "
            "anhalten und das erst dann bestaetigen, wenn keiner mehr "
            "laeuft. Ohne diesen Nachweis nicht tauschen.", einzug="     "))
        z.append("")
    z.append("  1. Alle Dienste anhalten, die auf die Datenbank zugreifen.")
    z.append("     Nachweis: 'python -m tools.maintenance' - erst wenn die")
    z.append("     Sperrprobe FREI meldet, ist wirklich Ruhe.")
    z.append("")
    z.append("  2. Das Original BEISEITELEGEN (nicht loeschen):")
    z.append("       Windows:  move \"%s\" \"%s\""
             % (befund.ziel, befund.ziel + ENDUNG_VORHER))
    z.append("       Linux:    mv '%s' '%s'"
             % (befund.ziel, befund.ziel + ENDUNG_VORHER))
    z.append("")
    z.append("  3. Die gepruefte Kopie an seine Stelle setzen:")
    z.append("       Windows:  move \"%s\" \"%s\""
             % (befund.geschrieben, befund.ziel))
    z.append("       Linux:    mv '%s' '%s'"
             % (befund.geschrieben, befund.ziel))
    z.append("")
    z.append("  4. Gegenlesen, BEVOR die Dienste wieder anlaufen:")
    z.append("       python -m management.backup.backup_admin restore \\")
    z.append("         --ziel \"%s\" --sicherung \"%s\" --trocken"
             % (befund.ziel, befund.sicherung))
    z.append("     Die Pruefsummenzeile muss jetzt uebereinstimmen - dann")
    z.append("     liegt genau die zertifizierte Sicherung an ihrem Platz.")
    z.append("")
    z.extend(_umbruch(
        "5. Die beiseitegelegte Datei '" + ENDUNG_VORHER + "' AUFHEBEN und "
        "nicht loeschen. Sie ist das einzige Stueck, das noch Daten aus der "
        "Zeit NACH dem Sicherungszeitpunkt tragen koennte.", einzug="  "))
    z.append("-" * _BREITE)
    return z


def vor_dem_tausch(befund: Wiederherstellungsbefund) -> List[str]:
    """
    Was zu tun ist, BEVOR getauscht werden darf - wenn am Ziel etwas
    entgegensteht.

    Sie tritt an die Stelle der Tauschanleitung und nicht neben sie. Wer
    beides nebeneinander liest, nimmt erfahrungsgemaess das, was ihn
    weiterbringt - und das waere hier das Falsche.
    """
    z: List[str] = []
    z.append("-" * _BREITE)
    z.append("NOCH NICHT TAUSCHEN - AM ZIEL STEHT ETWAS ENTGEGEN")
    z.append("")
    z.extend(_umbruch(
        "Die Kopie ist geprueft und liegt bereit. Der Tausch ist damit "
        "NICHT freigegeben: am Ziel ist zuerst etwas zu klaeren. Es folgt, "
        "was festgestellt wurde.", einzug="  "))
    z.append("")
    for s in befund.schritte:
        if s.name in _SCHRITTE_TAUSCH and s.geprueft and not s.bestanden:
            z.append("  * %s" % s.name)
            z.extend(_umbruch(s.grund, einzug="    "))
            z.append("")
    z.extend(_umbruch(
        "IST DAS GEKLAERT, liefert derselbe Aufruf mit '--trocken' die "
        "vollstaendige Tauschanleitung - er schreibt dabei nichts und "
        "aendert an der bereitliegenden Kopie nichts.", einzug="  "))
    z.append("-" * _BREITE)
    return z


def bericht_text(befund: Wiederherstellungsbefund) -> str:
    """Der Befund als Text."""
    z: List[str] = []
    z.append("Wiederherstellung aus Sicherung")
    z.append("=" * _BREITE)
    z.append("")
    # PFADE AUF EIGENE ZEILEN. Sie sind in der Produktivumgebung UNC-Pfade
    # und sprengen jede Spalte; zerschnitten waeren sie unbrauchbar, und ein
    # unbrauchbarer Pfad in einem forensischen Befund ist schlimmer als eine
    # zu lange Zeile.
    z.append("Sicherung:")
    z.append("  %s" % befund.sicherung)
    z.append("Ziel:")
    z.append("  %s" % befund.ziel)
    z.append("Betriebsart: %s"
             % ("TROCKENLAUF - es wird nichts geschrieben"
                if befund.trockenlauf else "Kopie neben das Original"))
    z.append("")

    z.append("Marke   Schritt und Befund")
    z.append("-" * _BREITE)
    for s in befund.schritte:
        # OHNE FUELLZEICHEN AM ZEILENENDE. Ein forensischer Befund wird
        # abgelegt, verglichen und zitiert; nachlaufende Leerzeichen machen
        # zwei gleiche Berichte ungleich.
        z.append("%s  %s" % (s.marke, s.name))
        z.extend(_umbruch(s.grund))
    z.append("-" * _BREITE)
    z.append("")

    if befund.fehler:
        z.append("Fehler:")
        for f in befund.fehler:
            z.extend(_umbruch(f, einzug="  "))
        z.append("")

    if befund.geschrieben:
        z.append("GESCHRIEBEN:")
        z.append("  %s" % befund.geschrieben)
        z.append("")
        # DIE ANLEITUNG NUR BEI TAUSCHBEREITEM ZIEL. Sie neben einem Befund
        # am Ziel auszugeben waere eine Einladung, ihn zu uebergehen - und
        # ausgerechnet der Tausch ist der Schritt, der nicht rueckgaengig
        # zu machen ist.
        if befund.tauschbereit:
            z.extend(anleitung(befund))
        else:
            z.extend(vor_dem_tausch(befund))
    elif befund.trockenlauf and befund.ok:
        z.append("TROCKENLAUF BESTANDEN - derselbe Aufruf ohne '--trocken'")
        z.append("legt die Kopie hier ab:")
        z.append("  %s" % (befund.ziel + ENDUNG_WIEDERHERGESTELLT))
        z.append("")
    else:
        z.append("NICHTS GESCHRIEBEN.")
        z.append("")

    # --- Was dieser Weg NICHT sagen kann -----------------------------------
    # Sie gehoert dazu. Ohne sie liest sich ein 'alles ok' als Zusicherung,
    # die dieser Weg nicht geben kann (Grundregel 1).
    z.append("-" * _BREITE)
    z.append("Was hier NICHT geprueft ist:")
    z.append("  - Ob diese Sicherung die INHALTLICH richtige ist. Sie ist der")
    z.append("    Stand ihres Zeitpunkts; alles, was danach erfasst wurde,")
    z.append("    steht nicht in ihr.")
    z.append("  - Ob der SATZ zusammenpasst. Der Sicherungssatz ist nicht")
    z.append("    punktgleich (Entscheidung mc 2026-07-31: Kennzeichnung")
    z.append("    statt Wartungsfenster). Wer mehrere Datenbanken desselben")
    z.append("    Laufs zurueckspielt, bekommt einen Zustand, den es so nie")
    z.append("    gegeben hat - siehe 'punktgleich' im Manifest des Laufs.")
    z.append("  - Ob der Tausch gelungen ist. Den tut ein Mensch; Schritt 4")
    z.append("    der Anleitung ist die Gegenprobe dazu.")
    return "\n".join(z)


def bericht_json(befund: Wiederherstellungsbefund) -> dict:
    """Derselbe Befund als Woerterbuch - fuer Skripte und Ueberwachung."""
    return {
        "sicherung": befund.sicherung,
        "ziel": befund.ziel,
        "geschrieben": befund.geschrieben,
        "trockenlauf": befund.trockenlauf,
        "rueckgabewert": befund.rueckgabewert(),
        "ok": befund.ok,
        "tauschbereit": befund.tauschbereit,
        "groesse": befund.groesse,
        "seiten": befund.seiten,
        "user_version": befund.user_version,
        "schema_objekte": befund.schema_objekte,
        "ziel_beschaedigt": befund.ziel_beschaedigt,
        "ruhe": (None if befund.ruhe is None else
                 {"zustand": befund.ruhe.zustand,
                  "grund": befund.ruhe.grund}),
        "schritte": [
            {"name": s.name, "geprueft": s.geprueft,
             "bestanden": s.bestanden, "grund": s.grund}
            for s in befund.schritte
        ],
        "fehler": list(befund.fehler),
    }
