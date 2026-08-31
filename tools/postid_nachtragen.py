#!/usr/bin/env python3
# =============================================================================
# tools/postid_nachtragen.py
# IT-Forensisches Ermittlungswerkzeug - Nachtrag der Beitragsnummer
# =============================================================================
# Zweck:
#   'annotations.post_id' fuer den BESTAND nachtragen. Die Nummer wird aus dem
#   gesicherten Seitenabzug gelesen, nicht erfunden.
#
#   Der Vorgang selbst steht in management/maintenance/postid_nachtrag.py
#   (Grundregel 10). Diese Datei ist die Befehlszeile davor: Argumente,
#   Wartungsvorbehalt, Ausgabe, Protokoll, Rueckgabewert.
#
# ── DIE TROCKENUEBUNG IST DIE VORGABE ────────────────────────────────────────
#
#   Ohne '--ausfuehren' wird die Datenbank mit 'mode=ro' geoeffnet. Es KANN
#   nichts geschrieben werden - nicht "es wird nicht", sondern es geht nicht.
#   Dieselbe Festlegung wie bei tools/migrate-dbs.py (mc, 2026-07-30):
#   Scharfschalten ist ein eigener Handgriff.
#
# ── WARTUNGSVORBEHALT - STUFE A ──────────────────────────────────────────────
#
#   Dieses Werkzeug ist in maintenance/wartungsstufen.py als STUFE A gefuehrt:
#   mit '--ausfuehren' schreibt es in evidence_<uid>.db - annotations.post_id
#   und die Hash-Kette -, also auf ein Beweismittel, das seit dem 01.07.2026
#   unter dem Migrationsvorbehalt steht.
#
#   ES SICHERT VORHER, ABER ES SPIELT NICHTS ZURUECK. Nach einem Abbruch
#   liegt die Sicherung da und ist von Hand einzusetzen. Genau deshalb ist die
#   Sicherung KEIN Ersatz fuer die Ruhepruefung: die Datei, die ein Dienst
#   waehrend des Schreibens offen haelt, ist der Fall, den ein Backup nicht
#   heilt. Vor dem scharfen Lauf wird deshalb geprueft, ob die betroffene
#   Datei ruhig ist; ohne aktives Wartungsfenster geht es nur nach Eingabe
#   eines vollstaendigen Wortes weiter (maintenance/wartungsvorbehalt.py).
#   Die Trockenuebung ist davon NICHT betroffen - sie schreibt nichts.
#
# ── OHNE SICHERUNG GESCHIEHT NICHTS ──────────────────────────────────────────
#
#   Weisung Alex, 28.08.2026: "Dies ist ein kritischer Schritt, weil er den
#   bestehenden Datenbestand in evidence_<uid>.db angeht. Hier ist die
#   unabdingbare Vorbedingung, dass ein Backup vor der Aenderung gemacht
#   wird." Es gibt deshalb KEINEN Schalter '--no-backup'. Die Sicherung
#   entsteht VOR dem ersten schreibfaehigen Oeffnen; schlaegt sie fehl, endet
#   der Lauf mit Rueckgabewert 3 und die Datenbank ist unberuehrt.
#
# ── DAS PROTOKOLL ────────────────────────────────────────────────────────────
#
#   Weisung Alex: "Ebenso benoetige ich ein zusaetzliches Protokoll, das ich
#   mir aber auch per 'tee' von der Konsole holen kann, damit ich im Minimum
#   Stichproben machen kann."
#
#   Deshalb ist die KONSOLENAUSGABE vollstaendig: je gepruefter Annotation
#   eine Zeile mit Beleg-Nummer, Art, Ergebnis, eingetragener Nummer, Weg und
#   Gegenprobe. '--protokoll <PFAD>' schreibt DIESELBEN Zeilen zusaetzlich in
#   eine Datei - eingebautes 'tee', damit die Mitschrift auch dann entsteht,
#   wenn jemand es vergisst. Beides ist gleichwertig; die Datei ist keine
#   andere Auswahl.
#
#   FUER DIE STICHPROBE: die Zeilen mit 'Weg=anker' sind der Sollweg. Die
#   Zeilen mit 'Weg=wortlaut' bzw. 'wortlaut_ein_beitrag' sind der Rueckfall
#   und verdienen die Stichprobe zuerst. 'im Paket: nein' ist KEIN Mangel
#   (s. Kopf des Vorgangsmoduls), sondern der Normalfall bei Markierungen in
#   Beitraegen anderer Nutzer.
#
# ── WAS ES NICHT TUT ─────────────────────────────────────────────────────────
#
#   Es ueberschreibt keine vorhandene post_id, es raet nichts, und es
#   veraendert an der Annotation nichts ausser dieser einen Spalte. Wortlaut,
#   Kategorie, Notiz, Verfasser und Zeit bleiben, wie sie sind.
#
# AUFRUF (in der VM, aus dem Wurzelverzeichnis des Webservers):
#
#   # 1. Trockenuebung - sagt, was geschaehe. Schreibt nichts.
#   python tools/postid_nachtragen.py \
#       --evidence ./data/evidence/evidence_700.db \
#       --forensic ./data/forensic/forensic_700.db | tee nachtrag_700.log
#
#   # 2. Erst wenn die Ausgabe stimmt: scharf, mit Sicherung und Beleg.
#   python tools/postid_nachtragen.py \
#       --evidence ./data/evidence/evidence_700.db \
#       --forensic ./data/forensic/forensic_700.db \
#       --ausfuehren --operator mmuster \
#       --protokoll nachtrag_700.log
#
# Grundregeln: GR1, GR2, GR6, GR10.
# Version: v0.8.751 - Build: 751 - 2026-08-31
# =============================================================================

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.help import cli_epilog                      # noqa: E402
from management.maintenance.laufkopf import Laufkopf        # noqa: E402
from report_render.absatz_finder import GRUND_TEXT          # noqa: E402
#: Die Dateien, die das ERGEBNIS dieses Laufs tragen.
_GETRAGEN_VON = (
    "tools/postid_nachtragen.py",
    "management/maintenance/postid_nachtrag.py",
    "report_render/absatz_finder.py",
    "report_render/html5_zerleger.py",
)

from management.maintenance.postid_nachtrag import (        # noqa: E402
    ERG_GETRAGEN,
    ERG_ANKER_UNBESTAETIGT,
    ERG_MEHRDEUTIG,
    ERG_WIDERSPRUCH,
    ERG_WUERDE,
    PostIdNachtrag,
    WEGE_RUECKFALL,
)

#: Rueckgabewerte. Sie sind AUSSAGEN und nicht bloss "gut/schlecht":
#:   0 - der Lauf ist durch, es blieb nichts Ungeklaertes
#:   1 - der Lauf ist durch, es blieb etwas offen (mehrdeutig, Widerspruch,
#:       nicht gefunden). Kein Fehler des Werkzeugs, aber Arbeit fuer einen
#:       Menschen.
#:   2 - der Lauf ist nicht zustande gekommen (Datei fehlt, keine Hash-Kette,
#:       Abbruch mit Rollback)
#:   3 - der Wartungsvorbehalt hat den scharfen Lauf nicht freigegeben.
#:       DIESE ZAHL IST NICHT FREI GEWAEHLT: maintenance/wartungsvorbehalt.py
#:       fuehrt sie als RUECKGABE_VORBEHALT = 3, und alle Stufe-A-Werkzeuge
#:       geben befund.rueckgabewert unveraendert weiter. Zwei Werkzeuge, die
#:       denselben Sachverhalt verschieden melden, waeren in einem Skript
#:       nicht auseinanderzuhalten.
#:   4 - die Sicherung ist fehlgeschlagen; es wurde nichts angefasst
#: Der bis zum Bruch aufgeloeste Teil des Ankers, aus dem
#: Bruchtext gelesen.
_PFAD_MUSTER = re.compile(r"Aufgeloest bis (\.[^\s.]*(?:\[\d+\])?(?:/[^\s./]+\[\d+\])*)")

CODE_OK = 0
CODE_OFFEN = 1
CODE_ABBRUCH = 2
CODE_KEINE_SICHERUNG = 4


class Mitschrift:
    """
    Sagt alles auf der Konsole und, wenn gewuenscht, zugleich in eine Datei.

    EIN EIGENES KLEINES OBJEKT und kein 'print' mit if: die Datei soll genau
    das enthalten, was der Bediener gesehen hat - keine Zeile mehr und keine
    weniger. Sonst gaebe es zwei Protokolle, die sich unterscheiden koennen,
    und damit die Frage, welches gilt.
    """

    def __init__(self, pfad: Optional[Path]) -> None:
        self._pfad = pfad
        self._zeilen: List[str] = []
        self._datei = None
        if pfad is not None:
            # Bewusst 'w' und nicht 'a': eine angehaengte Mitschrift zweier
            # Laeufe waere nicht mehr eindeutig einem Beleg zuzuordnen.
            self._datei = open(str(pfad), "w", encoding="utf-8")

    def __call__(self, zeile: str = "") -> None:
        print(zeile)
        self.nur_ins_protokoll(zeile)

    def nur_ins_protokoll(self, zeile: str) -> None:
        """
        Eine Zeile festhalten, die bereits AUF ANDEREM WEG auf der Konsole
        stand.

        Es gibt genau einen solchen Fall: den Text des Wartungsvorbehalts.
        tests/test_wartungsvorbehalt_einbau.py (EB02) verlangt dort woertlich
        'print(befund.text)' - und das zu Recht: der Waechter kann nicht
        wissen, ob ein selbstgebautes Ausgabeobjekt wirklich ausgibt. Damit
        die Mitschrift trotzdem vollstaendig bleibt, wird die Zeile hier
        nachgetragen statt ein zweites Mal gedruckt.
        """
        self._zeilen.append(zeile)
        if self._datei is not None:
            self._datei.write(zeile + "\n")
            self._datei.flush()

    def fingerabdruck(self) -> str:
        """SHA-256 ueber alles bisher Gesagte - fuer den Beleg."""
        roh = "\n".join(self._zeilen).encode("utf-8")
        return hashlib.sha256(roh).hexdigest()

    def schliessen(self) -> None:
        if self._datei is not None:
            self._datei.close()
            self._datei = None


def main(argv=None) -> int:
    zerleger = argparse.ArgumentParser(
        description="annotations.post_id aus dem gesicherten Seitenabzug "
                    "nachtragen.",
        epilog=cli_epilog.epilog("postid_nachtragen"),
        formatter_class=cli_epilog.HilfeFormat)
    zerleger.add_argument("--evidence", required=True,
                          help="Pfad zur evidence_<uid>.db (wird geaendert)")
    zerleger.add_argument("--forensic", required=True,
                          help="Pfad zur forensic_<uid>.db (nur gelesen)")
    zerleger.add_argument("--ausfuehren", action="store_true",
                          help="SCHARFSCHALTEN. Ohne diesen Schalter wird "
                               "nur gelesen und berichtet.")
    zerleger.add_argument("--operator", default="",
                          help="Kuerzel des Bedieners - es steht im Beleg.")
    zerleger.add_argument("--protokoll", default=None,
                          help="Datei, in die dieselben Zeilen geschrieben "
                               "werden wie auf die Konsole.")
    zerleger.add_argument("--nur-anker", action="store_true",
                          help="Nur den Sollweg gelten lassen; den Rueckfall "
                               "ueber den markierten Wortlaut NICHT nutzen.")
    zerleger.add_argument("--auch-ersetzte", action="store_true",
                          help="Auch ersetzte Versionen einer Annotation "
                               "nachtragen (Vorgabe: nur aktive).")
    zerleger.add_argument("--beleg", type=int, default=None,
                          help="Nur diese annotations.id ansehen - auch "
                               "dann, wenn sie schon eine post_id traegt.")
    zerleger.add_argument("--grenze", type=int, default=None,
                          help="Hoechstens so viele Annotationen ansehen.")
    zerleger.add_argument("--data-dir", default="./data",
                          help="Datenverzeichnis - nur fuer den "
                               "Wartungsvorbehalt (dort liegt _maintenance/).")
    args = zerleger.parse_args(argv)

    sag = Mitschrift(Path(args.protokoll) if args.protokoll else None)
    try:
        return _lauf(args, sag)
    finally:
        sag.schliessen()


def _vorbehalt(evidence: Path, data_dir: str, sag: Mitschrift):
    """
    Der Wartungsvorbehalt (Stufe A) vor dem scharfen Lauf.

    Rueckgabe: None, wenn es weitergehen darf - sonst der Rueckgabewert, mit
    dem das Werkzeug enden soll.

    DIE DREI ZEILEN SIND DAS HAUSMUSTER und stehen bewusst woertlich so da
    (maintenance/wartungsvorbehalt.py, Aufrufmuster; geprueft von
    tests/test_wartungsvorbehalt_einbau.py, EB02): Befund holen, Text
    ausgeben, bei Verweigerung den Rueckgabewert weiterreichen.

    GEPRUEFT WIRD NUR DIE DATEI, DIE DIESER LAUF WIRKLICH ANFASST. Die
    forensic_<uid>.db wird ausschliesslich lesend geoeffnet und gehoert
    deshalb nicht in die Pruefung. Eine Pruefung, die mehr meldet als der
    Lauf anfasst, erzeugt Fehlalarme - und Fehlalarme bringen genau die
    Gewoehnung hervor, gegen die der Vorbehalt gebaut ist (Begruendung
    wortgleich in tools/migrate-dbs.py).
    """
    from maintenance.wartungsvorbehalt import wartungsvorbehalt

    befund = wartungsvorbehalt(
        Path(data_dir), [evidence],
        werkzeug="postid_nachtragen",
        was_geschieht="traegt in 'annotations' die Spalte 'post_id' dort "
                      "nach, wo sie leer ist. Eine Sicherung wird angelegt; "
                      "die Aenderung wird in der Hash-Kette "
                      "'evidence_audit_log' belegt. Zurueckgespielt wird "
                      "NICHTS von selbst.")
    print(befund.text)
    sag.nur_ins_protokoll(befund.text)
    if not befund.erlaubt:
        return befund.rueckgabewert
    return None


def _gegenprobe_browser(befund, sag: Mitschrift) -> None:
    """
    Die andere Haelfte des Abgleichs: was der BROWSER an derselben Stelle hat.

    WARUM DAS WERKZEUG DAS NICHT SELBST KANN: Es liest den Abzug. Was der
    Browser daraus gemacht hat, sieht nur der Browser - und genau die
    Differenz ist die Frage. Das Werkzeug liefert deshalb den fertigen
    Einzeiler fuer die Entwicklerkonsole und sagt, wann, wo und was zu
    beobachten ist (Projektgebot zum Browser-Debugging: erst
    Console-Ausgabe anfordern, dann fixen).

    ES WERDEN NUR GERUESTANGABEN AUSGEGEBEN - Tag, Kennung, Klasse. Kein
    Beitragstext, weder hier noch drueben.
    """
    # Der haeufigste Bruchpfad ist der aussagekraeftigste: bricht es bei
    # allen Belegen an derselben Stelle, ist die Ursache strukturell und
    # nicht eine Eigenheit einzelner Markierungen.
    pfade = {}
    for z in befund.zeilen:
        if not z.anker_bruch:
            continue
        # Der aufgeloeste Teil steht als './donate[1]/div[1]' im Bruchtext.
        # Ein einfaches split('.') zerlegt ihn falsch - der Pfad BEGINNT mit
        # einem Punkt. Deshalb ein Muster statt einer Trennung.
        marke = _PFAD_MUSTER.search(z.anker_bruch)
        if not marke:
            continue
        pfad = marke.group(1)
        pfade[pfad] = pfade.get(pfad, 0) + 1
    if not pfade:
        return
    haeufigster, anzahl = max(sorted(pfade.items()),
                              key=lambda p: p[1])

    sag("")
    sag("-" * 78)
    sag("SO GLEICHEN WIR AB (Browserseite - das Werkzeug kann sie nicht sehen)")
    sag("")
    sag("  Der Bruch sitzt bei %d von %d Belegen an DERSELBEN Stelle: %s"
        % (anzahl, len(befund.zeilen), haeufigster))
    sag("  Was der Abzug dort hat, steht oben je Beleg ('Im Abzug steht")
    sag("  dort: ...'). Was der BROWSER dort hat, sagt dieser Einzeiler.")
    sag("")
    sag("  WANN:  Nachdem eine der betroffenen Seiten im Ermittlungsfenster")
    sag("         geladen ist - also genau so, wie beim Markieren.")
    sag("  WO:    Entwicklerkonsole des Ermittlungsfensters (F12).")
    sag("  WAS:   Die Liste, die er ausgibt, gegen die Abzug-Liste halten.")
    sag("")
    sag("  var vp = document.getElementById('forensic-viewport');")
    sag("  var ziel = document.evaluate(%r, vp, null, 9, null)"
        % haeufigster)
    sag("            .singleNodeValue || vp;")
    sag("  copy('PFAD %s -> ' + (ziel === vp ? '(nicht aufloesbar, "
        "Viewport)' : 'ok') + '\\n' + Array.from(ziel.children)"
        % haeufigster)
    sag("    .map((e,i) => (i+1) + ': <' + e.tagName.toLowerCase()")
    sag("     + (e.id ? '#'+e.id : '')")
    sag("     + (e.className ? '.'+String(e.className).trim()"
        ".split(/\\s+/).slice(0,2).join('.') : '') + '>'")
    sag("    ).join('\\n'));")
    sag("")
    sag("  ZU BEOBACHTEN: Stehen dort MEHR Elemente als im Abzug, ist")
    sag("  zwischen Abzug und Markierung etwas in die Seite geschrieben")
    sag("  worden - dann nenne mir bitte die zusaetzlichen. Sind es")
    sag("  DIESELBEN, dann stimmt der verglichene Abzug nicht, und die")
    sag("  Ursache liegt bei der Seitenaufloesung, nicht am Anker.")


def _lauf(args, sag: Mitschrift) -> int:
    evidence = Path(args.evidence)
    forensic = Path(args.forensic)

    sag("=" * 78)
    sag("NACHTRAG DER BEITRAGSNUMMER (annotations.post_id)")
    sag("  Beweismittel : %s" % evidence)
    sag("  Seitenabzug  : %s (nur lesend)" % forensic)
    sag("  Betriebsart  : %s"
        % ("SCHARF - es wird geschrieben" if args.ausfuehren
           else "Trockenuebung - es wird NICHTS geschrieben"))
    if args.nur_anker:
        sag("  Rueckfall    : ABGESCHALTET (--nur-anker) - nur der Anker gilt.")
    if args.auch_ersetzte:
        sag("  Umfang       : auch ersetzte Versionen (--auch-ersetzte)")
    sag("=" * 78)
    # HERKUNFT DES LAUFS (Build 746, Grundregel 8). Steht VOR dem
    # Wartungsvorbehalt: wer den Lauf abbricht, soll trotzdem wissen,
    # mit welchem Stand er ihn angefangen hat.
    for zeile in Laufkopf("postid_nachtragen", _GETRAGEN_VON).zeilen():
        sag(zeile)
    sag("=" * 78)

    # --- WARTUNGSVORBEHALT (Stufe A) -------------------------------------
    # Nur im scharfen Lauf, und nur fuer die Datei, die wirklich angefasst
    # wird. Eine Pruefung, die mehr meldet als der Lauf anfasst, erzeugt
    # Fehlalarme - und Fehlalarme bringen genau die Gewoehnung hervor, gegen
    # die der Vorbehalt gebaut ist (Begruendung wortgleich in
    # tools/migrate-dbs.py).
    if args.ausfuehren:
        verweigert = _vorbehalt(evidence, args.data_dir, sag)
        if verweigert is not None:
            return verweigert

    nachtrag = PostIdNachtrag(
        evidence=evidence, forensic=forensic, ausgabe=sag,
        nur_anker=args.nur_anker, auch_ersetzte=args.auch_ersetzte,
        grenze=args.grenze, beleg=args.beleg)

    befund = nachtrag.lauf(
        ausfuehren=args.ausfuehren,
        operator=args.operator,
        protokoll_datei=Path(args.protokoll) if args.protokoll else None,
        protokoll_hash="")

    if befund.abgebrochen and not befund.zeilen:
        sag("")
        sag("ABGEBROCHEN: %s" % befund.abgebrochen)
        # Eine fehlgeschlagene Sicherung ist etwas anderes als eine fehlende
        # Datei - der Rueckgabewert soll das unterscheiden koennen.
        if "Sicherung" in befund.abgebrochen:
            return CODE_KEINE_SICHERUNG
        return CODE_ABBRUCH

    # --- Zeile fuer Zeile. Das ist das Protokoll (s. Kopf). ---------------
    sag("")
    for z in befund.zeilen:
        sag("  " + z.als_protokollzeile())
        # BUILD 729: Wenn der Sollweg nicht getragen hat, steht darunter der
        # GEMESSENE Grund - und bei einem gebrochenen Anker der Schritt, an
        # dem er bricht. Bis Build 728 behauptete das Protokoll pauschal, der
        # Anker loese nicht auf; das war in fuenf verschiedenen Lagen
        # derselbe Satz und in vier davon womoeglich falsch.
        zusatz = z.ankerzeile()
        if zusatz:
            sag("  " + zusatz)

    # --- Was ein Mensch ansehen muss --------------------------------------
    offen = [z for z in befund.zeilen
             # BUILD 751: der unbestaetigte Teilanker gehoert in DIESE
             # Liste. Es wurde nichts eingetragen, und die Zeile bleibt
             # sonst in der Zaehlung stehen, ohne dass jemand sie ansieht.
             if z.ergebnis in (ERG_MEHRDEUTIG, ERG_WIDERSPRUCH,
                               ERG_ANKER_UNBESTAETIGT)]
    rueckfall = [z for z in befund.zeilen
                 if z.weg in WEGE_RUECKFALL
                 and z.ergebnis in (ERG_GETRAGEN, ERG_WUERDE)]

    sag("")
    sag("-" * 78)
    sag("ZAEHLUNG (%d Annotationen geprueft)" % befund.geprueft)
    for ergebnis, anzahl in sorted(befund.zaehlung().items()):
        sag("  %-26s %6d" % (ergebnis, anzahl))
    if befund.wege():
        sag("  davon nach Weg:")
        for weg, anzahl in sorted(befund.wege().items()):
            sag("    %-24s %6d%s"
                % (weg, anzahl,
                   "   <- Rueckfall, Stichprobe empfohlen"
                   if weg in WEGE_RUECKFALL else ""))
    for h in befund.hinweise:
        sag("  Hinweis: %s" % h)

    # BUILD 751: DIE KREUZPROBE ZUM TEILANKER. Sie ist die Zahl, die ueber
    # den scharfen Lauf entscheidet. Der Teilanker (Build 750) nimmt die
    # Nummer aus den ELEMENTINDIZES des Ankers; Alex' Ankerdiagnose vom
    # 31.08.2026 zeigt, dass die auf den PN-Seiten nicht durchweg zum Abzug
    # passen (verlangt 'div[54]' bei 53 Kindern, 'div[1010]' und 'div[1016]'
    # bei 1003). Die Kreuzprobe fragt deshalb nicht den Index, sondern den
    # INHALT: steht der markierte Wortlaut in dem benannten Beitrag?
    proben = befund.kreuzproben()
    if proben:
        sag("")
        sag("KREUZPROBE ZUM TEILANKER - steht der Wortlaut im benannten "
            "Beitrag?")
        for lage, anzahl in sorted(proben.items()):
            sag("  %-24s %6d%s"
                % (lage, anzahl,
                   "   <- NICHTS eingetragen, von Hand ansehen"
                   if lage == "nicht bestanden" else
                   "   <- Nummer allein aus Elementindizes"
                   if lage == "nicht pruefbar" else ""))

    # BUILD 729: DIE ANKER-BILANZ. Sie ist die Antwort auf die Frage, die
    # der Lauf von Build 728 offenlassen musste - dort stand 25-mal
    # 'Weg=wortlaut' und kein Wort darueber, WARUM. Aus dieser Zaehlung geht
    # hervor, ob der Sollweg an einer Stelle systematisch bricht.
    gruende = {}
    for z in befund.zeilen:
        if z.anker_grund:
            gruende[z.anker_grund] = gruende.get(z.anker_grund, 0) + 1
    if gruende:
        sag("")
        sag("ANKERBILANZ - warum der Sollweg nicht getragen hat:")
        for grund, anzahl in sorted(gruende.items(),
                                    key=lambda p: -p[1]):
            sag("  %-16s %6d   %s" % (grund, anzahl,
                                      GRUND_TEXT.get(grund, "")))
        _gegenprobe_browser(befund, sag)

    if befund.abgebrochen:
        sag("")
        sag("ABGEBROCHEN: %s" % befund.abgebrochen)
        return CODE_ABBRUCH

    sag("")
    if args.ausfuehren:
        sag("GESCHRIEBEN: %d Nachtraege." % befund.geschrieben)
        if befund.sicherung:
            sag("Sicherung:   %s" % befund.sicherung)
        if befund.geschrieben:
            sag("Beleg:       evidence_audit_log, Ereignis "
                "'annotation_postid_backfilled'. Er nennt jede einzelne "
                "Beleg-Nummer und die eingetragene Beitragsnummer.")
    else:
        sag("TROCKENUEBUNG - es wurde nichts geschrieben.")
        sag("Zum Anwenden denselben Aufruf mit '--ausfuehren --operator "
            "<Kuerzel>' wiederholen.")

    if rueckfall:
        sag("")
        sag("STICHPROBE ZUERST HIER (%d ueber den Wortlaut statt ueber den "
            "Anker gefunden):" % len(rueckfall))
        sag("  %s" % ", ".join("#%d" % z.annotation_id
                               for z in rueckfall[:40]))
        if len(rueckfall) > 40:
            sag("  ... und %d weitere; sie stehen vollstaendig oben und in "
                "der Protokolldatei." % (len(rueckfall) - 40))

    if offen:
        sag("")
        sag("VON HAND ZU KLAEREN (%d):" % len(offen))
        for z in offen:
            sag("  #%d: %s" % (z.annotation_id, z.bemerkung))
        return CODE_OFFEN

    return CODE_OK


if __name__ == "__main__":
    sys.exit(main())
