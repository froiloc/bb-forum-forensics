# =============================================================================
# management/backup/backup_pruefer.py
# IT-Forensisches Ermittlungswerkzeug - Datensicherung
# =============================================================================
# Zweck:
#   NACHSEHEN, WAS IM SICHERUNGSORDNER WIRKLICH LIEGT - und je Datenbank
#   sagen, wie viele BRAUCHBARE Generationen davon uebrig sind.
#
# DER ANLASS (mc, 2026-08-01): Auf die Frage, ob im Sicherungsordner der
#   Produktionsumgebung Abbruchreste liegen, lautete die Antwort JA. Damit ist
#   der in Build 625 behobene Fehler nicht nur eine Moeglichkeit gewesen - er
#   hat gewirkt. Wie weit, weiss niemand: es gibt bis heute kein Werkzeug, das
#   den Ordner ansieht.
#
# WARUM 'backup_admin list' DIESE FRAGE NICHT BEANTWORTET: Es liest die
#   REGISTRIERUNG in der coordinator.db, nicht das Verzeichnis. Was nie
#   registriert wurde - und ein Abbruchrest wird es nie -, kommt darin nicht
#   vor. Umgekehrt kann die Registrierung eine Sicherung fuehren, deren Datei
#   laengst geloescht ist. Die Registrierung sagt, was GESCHEHEN IST; dieses
#   Bauteil sagt, was DA IST. Beides zusammen ist die Auskunft.
#
# WAS SICH NACHTRAEGLICH PRUEFEN LAESST - UND WAS NICHT:
#   Beim Sichern wird die Kopie gegen die QUELLE gemessen (Build 625:
#   user_version, Schemaumfang, nicht leer). NACHTRAEGLICH geht das nicht mehr:
#   die Quelle ist inzwischen weitergewandert, eine Migration kann die
#   user_version erhoeht und Tabellen hinzugefuegt haben. Eine Abweichung
#   waere dann kein Befund, sondern der normale Lauf der Dinge.
#
#   NACHTRAEGLICH PRUEFBAR ist deshalb nur, was aus der Datei selbst folgt:
#     * ist sie leer (0 Byte oder 0 Seiten)?  -> genau der Abbruchrest
#     * ist sie lesbar?
#     * besteht sie 'PRAGMA integrity_check'?
#     * hat sie ueberhaupt ein Schema?
#   UND, wenn die Registrierung dazu etwas weiss:
#     * stimmt die Pruefsumme noch mit der beim Sichern erhobenen ueberein?
#
#   DIE PRUEFSUMME IST DER EIGENTLICHE GEWINN. Sie wird seit Build 354 bei
#   jeder Sicherung erhoben und abgelegt - und wurde bis Build 626 nie wieder
#   ausgewertet (Vorgang 2785556a). Eine Sicherung alterte damit unbeobachtet.
#   Hier wird sie erstmals gegengerechnet; seit Build 680 rechnet auch der
#   Rueckweg sie gegen ('backup_admin restore'). WEIL DAS TEUER IST (die
#   Datei wird ganz gelesen), ist es eine ausdrueckliche Option; dass es
#   NICHT geschehen ist, steht im Befund (Grundregel 1).
#
# REIN LESEND. Kein Schreiben, kein Umbenennen, kein Loeschen, keine
#   Datenbankverbindung ausser lesend auf die Sicherungsdateien selbst. Das
#   ist Absicht: Ein Werkzeug, das eine Lage BEURTEILEN soll, darf sie nicht
#   veraendern. Aufgeraeumt wird beim naechsten 'run' - dort ist es belegt und
#   auditiert.
#
# KEINE DATENBANKANBINDUNG IN DIESEM MODUL. Die Angaben aus der Registrierung
#   werden HEREINGEREICHT (Woerterbuch Pfad -> Pruefsumme). Damit bleibt das
#   Bauteil ohne coordinator.db pruefbar, und die Route zur Registrierung
#   liegt an einer Stelle: im Werkzeug.
#
# Build 680: Der Schlusssatz des Berichts ist berichtigt. Bis hierher stand
#   dort 'fuer eine Wiederherstellung gibt es im Bestand keinen erprobten
#   Weg' - das war richtig und ist es seit 'backup_admin restore' nicht mehr.
#   Eine stehengebliebene Aussage waere ein Fehlbeleg in die falsche
#   Richtung: sie liesse jemanden glauben, es gebe nichts zu fahren.
# Version: v0.8.680 - Build: 680 - 2026-08-05
# =============================================================================

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from management.backup.backup_executor import (
    DEFEKT_ENDUNG, _BACKUP_NAME_RE, _DEFEKT_NAME_RE,
)
from management.migration_fleet.harness.hashing import sha512_file

#: Rueckgabewerte des Werkzeugs. Sie stehen HIER und nicht im Werkzeug, damit
#: Text, Befund und Rueckgabewert dieselbe Quelle haben.
RC_OK = 0
RC_BEFUND = 1
RC_OHNE_SICHERUNG = 2
RC_UNLESBAR = 3


@dataclass(frozen=True)
class Dateibefund:
    """Was ueber EINE Datei im Sicherungsordner festzustellen war."""
    name: str
    pfad: str
    label: str
    ts: str
    groesse: int
    brauchbar: bool
    grund: str
    beiseitegelegt: bool = False
    seiten: int = 0
    user_version: int = 0
    schema_objekte: int = 0
    #: None = nicht geprueft (Option nicht gesetzt oder keine Angabe in der
    #: Registrierung). True/False = geprueft. Der Unterschied zwischen
    #: 'stimmt nicht' und 'wurde nicht angesehen' muss sichtbar bleiben.
    pruefsumme_stimmt: Optional[bool] = None
    registriert: Optional[bool] = None


@dataclass(frozen=True)
class Labelbefund:
    """Die Lage EINER Datenbank im Sicherungsordner."""
    label: str
    brauchbar: Tuple[Dateibefund, ...] = ()
    unbrauchbar: Tuple[Dateibefund, ...] = ()
    beiseite: Tuple[Dateibefund, ...] = ()

    @property
    def ohne_sicherung(self) -> bool:
        """
        Keine einzige brauchbare Generation.

        DAS IST DER BEFUND, WEGEN DEM ES DIESES BAUTEIL GIBT. Alles andere
        ist Buchhaltung; dieser eine Satz entscheidet, ob im Ernstfall etwas
        da ist.
        """
        return not self.brauchbar

    @property
    def juengste(self) -> Optional[Dateibefund]:
        return self.brauchbar[0] if self.brauchbar else None


@dataclass(frozen=True)
class Bestandsbefund:
    """Die Lage des ganzen Sicherungsordners."""
    verzeichnis: str
    lesbar: bool
    labels: Tuple[Labelbefund, ...] = ()
    #: Registrierte Sicherungen, deren Datei fehlt. Die Gegenrichtung: die
    #: Registrierung fuehrt etwas, das es nicht mehr gibt.
    fehlende_dateien: Tuple[str, ...] = ()
    #: Ob die Pruefsummen gegengerechnet wurden. Steht im Befund, damit
    #: niemand ein 'alles in Ordnung' liest, das nur die halbe Pruefung war.
    pruefsummen_geprueft: bool = False
    fehler: Tuple[str, ...] = ()

    @property
    def ohne_sicherung(self) -> Tuple[str, ...]:
        return tuple(l.label for l in self.labels if l.ohne_sicherung)

    @property
    def unbrauchbare(self) -> Tuple[Dateibefund, ...]:
        """
        Alles, was nicht als Generation taugt - EINSCHLIESSLICH der
        beiseitegelegten Dateien.

        WARUM AUCH DIESE ZAEHLEN: Eine '.defekt'-Datei ist zwar ein bereits
        behandelter Fall, aber sie sagt, dass ein Sicherungslauf gescheitert
        ist. Das ist ein Befund und gehoert in den Rueckgabewert. Er bleibt
        auch nicht dauerhaft stehen: nach retention_count gelungenen Laeufen
        sind die Reste ausgerollt, und die Meldung verschwindet von selbst.
        Ein Rueckgabewert, der dauerhaft auf 1 stuende, waere das schlechtere
        Ende - wer oft ohne Anlass gewarnt wird, sieht irgendwann nicht mehr
        hin.
        """
        raus: List[Dateibefund] = []
        for l in self.labels:
            raus.extend(l.unbrauchbar)
            raus.extend(l.beiseite)
        return tuple(raus)

    def rueckgabewert(self) -> int:
        """
        Der Rueckgabewert - damit eine Ueberwachung ihn auswerten kann, ohne
        die Ausgabe zu lesen.

        DIE REIHENFOLGE IST NACH SCHWERE GEORDNET und nicht nach Zufall:
          3  der Ordner ist nicht lesbar - es ist gar nichts festgestellt
          2  MINDESTENS EINE DATENBANK HAT KEINE BRAUCHBARE SICHERUNG
          1  es gibt Befunde, aber jede Datenbank hat noch mindestens eine
          0  nichts zu beanstanden
        Der Fall 2 ist der Ernstfall und bekommt deshalb den hoeheren Wert:
        eine Ueberwachung, die auf '>= 2' schaltet, trifft genau ihn.
        """
        if not self.lesbar:
            return RC_UNLESBAR
        if self.ohne_sicherung:
            return RC_OHNE_SICHERUNG
        if self.unbrauchbare or self.fehlende_dateien or self.fehler:
            return RC_BEFUND
        return RC_OK


class SicherungsPruefer:
    """
    Sieht einen Sicherungsordner durch. REIN LESEND.

    Der Konstruktor tut nichts ausser sich das Verzeichnis zu merken - alle
    Arbeit steckt in pruefen(), damit ein Aufruf, der nur das Objekt baut,
    keine Platte anfasst.
    """

    def __init__(self, verzeichnis: str) -> None:
        self._dir = verzeichnis

    # ------------------------------------------------------------- pruefen
    def pruefen(self,
                registrierte: Optional[Dict[str, Optional[str]]] = None,
                mit_pruefsummen: bool = False) -> Bestandsbefund:
        """
        registrierte     - Pfad -> erhobene Pruefsumme (oder None), aus der
                           Registrierung. Leer heisst: keine Angaben da.
        mit_pruefsummen  - die Dateien ganz lesen und gegenrechnen.
        """
        registrierte = dict(registrierte or {})
        try:
            namen = sorted(os.listdir(self._dir))
        except OSError as exc:
            return Bestandsbefund(
                verzeichnis=self._dir, lesbar=False,
                fehler=("Sicherungsverzeichnis nicht lesbar: %s" % exc,))

        je_label: Dict[str, Dict[str, List[Dateibefund]]] = {}
        gesehen: set = set()
        fehler: List[str] = []

        for name in namen:
            m = _BACKUP_NAME_RE.match(name)
            beiseite = False
            if m is None:
                m = _DEFEKT_NAME_RE.match(name)
                beiseite = m is not None
            if m is None:
                continue                       # Manifest o. ae. - nicht unser
            pfad = os.path.join(self._dir, name)
            gesehen.add(os.path.abspath(pfad))
            befund = self._datei_pruefen(
                pfad, name, m.group("label"), m.group("ts"), beiseite,
                registrierte, mit_pruefsummen)
            eimer = je_label.setdefault(
                befund.label, {"brauchbar": [], "unbrauchbar": [],
                               "beiseite": []})
            if befund.beiseitegelegt:
                eimer["beiseite"].append(befund)
            elif befund.brauchbar:
                eimer["brauchbar"].append(befund)
            else:
                eimer["unbrauchbar"].append(befund)

        # DIE GEGENRICHTUNG: registriert, aber nicht da. Ohne sie liesse
        # sich aus einem leeren Ordner nicht ablesen, dass er einmal voll war.
        fehlende = tuple(sorted(
            p for p in registrierte
            if p and os.path.abspath(p) not in gesehen
            and os.path.dirname(os.path.abspath(p)) == os.path.abspath(self._dir)
            and not os.path.exists(p)))

        labels = []
        for label in sorted(je_label):
            e = je_label[label]
            labels.append(Labelbefund(
                label=label,
                brauchbar=tuple(sorted(e["brauchbar"],
                                       key=lambda b: b.ts, reverse=True)),
                unbrauchbar=tuple(sorted(e["unbrauchbar"],
                                         key=lambda b: b.ts, reverse=True)),
                beiseite=tuple(sorted(e["beiseite"],
                                      key=lambda b: b.ts, reverse=True))))

        return Bestandsbefund(
            verzeichnis=self._dir, lesbar=True, labels=tuple(labels),
            fehlende_dateien=fehlende,
            pruefsummen_geprueft=mit_pruefsummen, fehler=tuple(fehler))

    # ------------------------------------------------------- eine Datei
    def _datei_pruefen(self, pfad: str, name: str, label: str, ts: str,
                       beiseite: bool,
                       registrierte: Dict[str, Optional[str]],
                       mit_pruefsummen: bool) -> Dateibefund:
        """
        Eine Datei beurteilen. Die Reihenfolge ist die der Kosten: erst der
        Dateikopf, dann das Schema, zuletzt - und nur auf Wunsch - die
        Pruefsumme ueber den ganzen Inhalt.
        """
        registriert = None
        if registrierte:
            registriert = any(
                os.path.abspath(p) == os.path.abspath(pfad)
                for p in registrierte if p)

        def _nein(grund, **kw):
            return Dateibefund(name=name, pfad=pfad, label=label, ts=ts,
                               groesse=groesse, brauchbar=False, grund=grund,
                               beiseitegelegt=beiseite,
                               registriert=registriert, **kw)

        try:
            groesse = os.path.getsize(pfad)
        except OSError as exc:
            groesse = 0
            return _nein("nicht lesbar: %s" % exc)

        if groesse == 0:
            # GENAU DER ABBRUCHREST. Eine 0-Byte-Datei besteht
            # 'PRAGMA integrity_check' - die Groesse ist hier die
            # aussagekraeftigere Angabe, und sie kostet nichts.
            return _nein("LEER (0 Byte) - das ist die Signatur einer "
                         "abgebrochenen Sicherung")

        # EIN HEISSES JOURNAL WIRD NICHT ANGEFASST - und das ist der Punkt,
        # an dem die Zusage 'rein lesend' steht oder faellt. Gemessen am
        # 2026-08-01: eine gewoehnlich geoeffnete Teildatei mit '-journal'
        # wird von SQLite ZURUECKGEROLLT; aus 34 MB werden 0 Byte. Eine
        # Pruefung, die den Beleg vernichtet, den sie beurteilen soll, ist
        # keine. Das Journal ist hier ohnehin schon die Antwort.
        heiss = [a for a in ("-journal", "-wal") if os.path.exists(pfad + a)]
        if heiss:
            return _nein(
                "ABGEBROCHENE SICHERUNG - daneben liegt ein heisses Journal "
                "(%s). Die Datei wurde NICHT geoeffnet: SQLite wuerde das "
                "Journal zurueckspielen und die Teildatei dabei auf 0 Byte "
                "verkuerzen. So bleibt ablesbar, wie weit der Lauf gekommen "
                "ist." % ", ".join(heiss))

        try:
            # NUR-LESEND. Damit kann diese Pruefung unter keinen Umstaenden
            # etwas an einer Sicherung veraendern.
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
            return _nein("keine lesbare Datenbank: %s" % exc)

        merkmale = dict(seiten=seiten, user_version=uv, schema_objekte=objekte)

        if seiten == 0:
            # Kann auftreten, nachdem SQLite ein Journal zurueckgerollt hat -
            # die Datei ist dann auf der Platte noch gross, aber leer.
            return _nein("LEER (0 Seiten) - zurueckgerollte Teildatei",
                         **merkmale)
        if not (len(zeilen) == 1 and zeilen[0][0] == "ok"):
            return _nein("integrity_check: " + "; ".join(
                str(z[0]) for z in zeilen[:5]), **merkmale)
        if objekte == 0:
            return _nein("kein Schema - die Datei ist formal in Ordnung, "
                         "enthaelt aber nichts", **merkmale)

        summe_stimmt = None
        if mit_pruefsummen:
            erwartet = None
            for p, s in registrierte.items():
                if p and os.path.abspath(p) == os.path.abspath(pfad):
                    erwartet = s
                    break
            if erwartet:
                try:
                    summe_stimmt = (sha512_file(pfad) == erwartet)
                except OSError as exc:
                    return _nein("Pruefsumme nicht bildbar: %s" % exc,
                                 **merkmale)
                if not summe_stimmt:
                    # EINE SICHERUNG, DIE NICHT MEHR DIE IST, DIE
                    # ZERTIFIZIERT WURDE, IST KEINE. Streng, und mit Absicht:
                    # im Ernstfall gibt es keine Gelegenheit mehr, das zu
                    # klaeren.
                    return Dateibefund(
                        name=name, pfad=pfad, label=label, ts=ts,
                        groesse=groesse, brauchbar=False,
                        grund=("Pruefsumme weicht von der beim Sichern "
                               "erhobenen ab - die Datei ist nicht mehr die "
                               "zertifizierte"),
                        beiseitegelegt=beiseite, registriert=registriert,
                        pruefsumme_stimmt=False, **merkmale)

        if beiseite:
            return Dateibefund(
                name=name, pfad=pfad, label=label, ts=ts, groesse=groesse,
                brauchbar=False,
                grund=("beiseitegelegt ('%s') - zaehlt nicht als Generation"
                       % DEFEKT_ENDUNG),
                beiseitegelegt=True, registriert=registriert,
                pruefsumme_stimmt=summe_stimmt, **merkmale)

        return Dateibefund(
            name=name, pfad=pfad, label=label, ts=ts, groesse=groesse,
            brauchbar=True, grund="ok", beiseitegelegt=False,
            registriert=registriert, pruefsumme_stimmt=summe_stimmt,
            **merkmale)


# -----------------------------------------------------------------------------
# Ausgabe
# -----------------------------------------------------------------------------
# REINE FUNKTION, kein print. Damit ist jede Zeile Rueckgabewert und direkt
# vergleichbar - dieselbe Trennung wie in management/help/cli_text.py, und aus
# demselben Grund. Sie steht in DIESER Datei und nicht in einer eigenen: der
# Bericht hat genau einen Gegenstand und keinen zweiten Abnehmer; ein weiteres
# Modul waere hier Ordnung um ihrer selbst willen.
#
# ASCII und 78 Zeichen, wie ueberall auf der Kommandozeile dieser Anlage.

_BREITE = 78


def _kurz(pfad: str) -> str:
    return os.path.basename(pfad)


def _mb(bytes_: int) -> str:
    return "%.1f MB" % (bytes_ / (1024.0 * 1024.0))


def _umbruch(text: str, einzug: str = "      ") -> List[str]:
    """
    Fliesstext auf _BREITE umbrechen. Von Hand und nicht ueber textwrap: der
    Einzug soll frei waehlbar sein, und ein ueberlanges Wort - ein Dateiname,
    ein Pfad - wird NICHT zerschnitten. Dieselbe Regel wie in
    management/help/cli_text.py, und aus demselben Grund.
    """
    zeilen: List[str] = []
    aktuell = einzug
    leer = True
    for wort in (text or "").split():
        if not leer and len(aktuell) + 1 + len(wort) > _BREITE:
            zeilen.append(aktuell)
            aktuell = einzug + wort
        else:
            aktuell = (einzug + wort) if leer else (aktuell + " " + wort)
        leer = False
    if not leer:
        zeilen.append(aktuell)
    return zeilen


def bericht_text(b: Bestandsbefund) -> str:
    """Der Befund als Text."""
    z: List[str] = []
    z.append("Sicherungsbestand")
    z.append("=" * _BREITE)
    z.append("")
    z.append("Verzeichnis: %s" % b.verzeichnis)

    if not b.lesbar:
        z.append("")
        for f in b.fehler:
            z.append("  " + f)
        return "\n".join(z)

    z.append("Pruefsummen gegengerechnet: %s"
             % ("ja" if b.pruefsummen_geprueft else
                "NEIN (Option --pruefsummen nicht gesetzt)"))
    z.append("")

    if not b.labels:
        z.append("Keine Sicherungsdateien der Namenskonvention gefunden.")
        z.append("")
        z.append("Das heisst NICHT, dass der Ordner leer ist - gesucht wurde "
                 "nach")
        z.append("'<label>_v<version>_<zeitstempel>_<host>.backup.db'.")
        return "\n".join(z)

    # --- DER ERNSTFALL ZUERST ---------------------------------------------
    # Was ohne Sicherung dasteht, gehoert an den ANFANG. Am Ende einer langen
    # Liste liest es niemand, der schnell nachsehen wollte.
    if b.ohne_sicherung:
        z.append("!" * _BREITE)
        z.append("OHNE BRAUCHBARE SICHERUNG (%d):" % len(b.ohne_sicherung))
        for label in b.ohne_sicherung:
            z.append("  %s" % label)
        z.append("")
        z.append("Von diesen Datenbanken liegt im Ordner keine einzige Datei,")
        z.append("die sich als Sicherung verwenden liesse.")
        z.append("!" * _BREITE)
        z.append("")

    kopf = "%-24s %9s %11s  %s" % ("Datenbank", "brauchbar", "unbrauchbar",
                                   "juengste brauchbare")
    z.append(kopf)
    z.append("-" * _BREITE)
    for l in b.labels:
        juengste = l.juengste.ts if l.juengste else "-"
        z.append("%-24s %9d %11d  %s"
                 % (l.label[:24], len(l.brauchbar),
                    len(l.unbrauchbar) + len(l.beiseite), juengste))
    z.append("-" * _BREITE)
    z.append("")

    # --- Die Einzelbefunde --------------------------------------------------
    unbrauchbar = [(l, d) for l in b.labels
                   for d in list(l.unbrauchbar) + list(l.beiseite)]
    if unbrauchbar:
        z.append("Nicht als Generation verwendbar (%d):" % len(unbrauchbar))
        for _l, d in unbrauchbar:
            z.append("  %s  (%s)" % (_kurz(d.pfad), _mb(d.groesse)))
            z.extend(_umbruch(d.grund))
        z.append("")

    if b.fehlende_dateien:
        z.append("Registriert, aber im Ordner NICHT vorhanden (%d):"
                 % len(b.fehlende_dateien))
        for p in b.fehlende_dateien:
            z.append("  %s" % p)
        z.append("")

    # --- Was diese Pruefung NICHT sagen kann --------------------------------
    # Sie gehoert dazu. Ohne sie liest sich ein '0 Befunde' als Zusicherung,
    # die diese Pruefung nicht geben kann (Grundregel 1).
    z.append("-" * _BREITE)
    z.append("Was hier NICHT geprueft ist:")
    z.append("  - Ob eine Sicherung INHALTLICH zu ihrer Quelle passt. Das ist")
    z.append("    nachtraeglich nicht feststellbar: die Quelle ist seither")
    z.append("    weitergewandert, eine Migration aendert user_version und")
    z.append("    Schema. Gemessen wird beim Sichern, nicht hier.")
    if not b.pruefsummen_geprueft:
        z.append("  - Ob die Datei noch die ist, die zertifiziert wurde.")
        z.append("    Dafuer '--pruefsummen' setzen (liest jede Datei ganz).")
    # BUILD 680: Hier stand bis zum Rueckweg 'dafuer gibt es im Bestand
    # keinen erprobten Weg'. Das war richtig und ist es nicht mehr - eine
    # stehengebliebene Aussage waere ein Fehlbeleg, und zwar einer, der in
    # die falsche Richtung zeigt (Grundregel 1).
    z.append("  - Ob eine Wiederherstellung gelingt. Diese Pruefung sieht")
    z.append("    die Sicherung nur an. Fahren laesst sich der Rueckweg mit")
    z.append("    'backup_admin restore --trocken' - er prueft die")
    z.append("    Pruefsumme, probt die Zieldatei auf Ruhe und schreibt")
    z.append("    dabei nichts (Build 680, Vorgang 2785556a).")
    return "\n".join(z)


def bericht_json(b: Bestandsbefund) -> dict:
    """Derselbe Befund als Woerterbuch - fuer Skripte und Ueberwachung."""
    return {
        "verzeichnis": b.verzeichnis,
        "lesbar": b.lesbar,
        "pruefsummen_geprueft": b.pruefsummen_geprueft,
        "rueckgabewert": b.rueckgabewert(),
        "ohne_brauchbare_sicherung": list(b.ohne_sicherung),
        "fehlende_dateien": list(b.fehlende_dateien),
        "fehler": list(b.fehler),
        "labels": [
            {
                "label": l.label,
                "brauchbar": len(l.brauchbar),
                "unbrauchbar": len(l.unbrauchbar) + len(l.beiseite),
                "juengste_brauchbare": l.juengste.ts if l.juengste else None,
                "dateien": [
                    {"name": d.name, "ts": d.ts, "groesse": d.groesse,
                     "brauchbar": d.brauchbar, "grund": d.grund,
                     "beiseitegelegt": d.beiseitegelegt,
                     "seiten": d.seiten, "user_version": d.user_version,
                     "schema_objekte": d.schema_objekte,
                     "pruefsumme_stimmt": d.pruefsumme_stimmt,
                     "registriert": d.registriert}
                    for d in list(l.brauchbar) + list(l.unbrauchbar)
                    + list(l.beiseite)
                ],
            }
            for l in b.labels
        ],
    }
