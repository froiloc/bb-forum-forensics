#!/usr/bin/env python3
# =============================================================================
# tools/anker_diagnose.py
# IT-Forensisches Ermittlungswerkzeug - Diagnose des Ankerbruchs
# =============================================================================
# Zweck:
#   MESSEN, WARUM DIE ANKER DER TEXTMARKIERUNGEN IM SEITENABZUG NICHT
#   AUFLOESEN - und pruefen, ob eine Annaeherung an die Browser-Zerlegung sie
#   heilt.
#
#   Der Vorgang selbst steht in management/maintenance/anker_diagnose.py
#   (Grundregel 10). Diese Datei ist die Befehlszeile davor.
#
# ── ES SCHREIBT NICHTS. ES KANN NICHTS SCHREIBEN. ────────────────────────────
#
#   Beide Datenbanken werden mit 'mode=ro' geoeffnet. Es gibt kein
#   '--ausfuehren', kein UPDATE und kein INSERT. Wartungsstufe C: der Betrieb
#   darf weiterlaufen, ein Wartungsfenster ist nicht noetig, und die
#   Beweismitteldatenbank bleibt unberuehrt.
#
#   Es gibt trotzdem eine Sicherung? NEIN - und das ist richtig so. Eine
#   Sicherung vor einem Lauf, der nichts anfassen kann, waere eine Geste, und
#   Gesten verwaessern die Regel, die vor den scharfen Laeufen steht.
#
# ── WOZU ES DA IST ───────────────────────────────────────────────────────────
#
#   tools/postid_nachtragen.py loeste in Alex' Laeufen vom 28.08.2026 KEINEN
#   einzigen Beleg ueber den Anker auf - alle 25 gingen ueber den Wortlaut,
#   den Notfall-Rueckfall. Die Sonde vom 29.08.2026 zeigte: die Anker sind
#   RICHTIG, im Browser loesen sie auf. Der zerlegte Abzug hat an derselben
#   Stelle weniger Elemente als der Browser.
#
#   Am 31.08.2026 entschied die Gegenprobe im Browser am echten Abzug die
#   Sache: alle zwoelf Ankerschritte loesen dort auf, '#page-body' haengt
#   unter 'div#wrap' und traegt 500 direkte <article>. Der Anker war richtig,
#   der Abzug vollstaendig - falsch war allein die ZERLEGUNG. Seit Build 747
#   zerlegt das System nach dem HTML5-Standard (html5lib).
#
#   DIESES WERKZEUG SAGT, OB DAS IM VORLIEGENDEN ABZUG DER FALL IST. Es
#   behauptet es nicht - es misst es.
#
# ── WAS DER LAUF AUSGIBT ─────────────────────────────────────────────────────
#
#   Je Beleg eine Zeile: loest der Anker mit libxml2 auf? Loest er mit dem
#   HTML5-Zerleger auf? Die Zeilen mit 'roh=nein angenaehert=JA' sind der
#   Befund, um dessentwillen es das Werkzeug gibt.
#
#   Je Seite: der Ebenenbericht (welche Stufe des Ankers bricht, und was
#   steht dort), die Rohtext-Elemente und was die Annaeherung getan hat.
#
#   DIE AUSGABE IST WEITERGEBBAR. Es erscheinen Tagnamen, Kennungen,
#   Klassen, Zahlen und Pfade - keine Beitragsinhalte. Wo Quelltext gezeigt
#   wird, sind Textknoten und die nicht freigegebenen Attributwerte verdeckt.
#
# AUFRUF (in der VM, aus dem Wurzelverzeichnis des Webservers):
#
#   python tools/anker_diagnose.py \
#       --evidence ./data/evidence/evidence_700.db \
#       --forensic ./data/forensic/forensic_700.db | tee anker_700.log
#
#   # Nur einen einzelnen Beleg ansehen:
#   python tools/anker_diagnose.py --evidence ... --forensic ... --beleg 32
#
# RUECKGABEWERTE
#   0  gelaufen (auch beim Leerbefund - der ist kein Fehler)
#   1  Fachfehler (Datei fehlt, Datenbank nicht lesbar)
#   2  Aufruffehler (fehlende oder unbrauchbare Argumente)
#
# Version: 0.8.747 - Build 747 (Laufkopf, M7)
# =============================================================================

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Damit das Werkzeug aus dem Wurzelverzeichnis heraus laeuft, ohne dass
# jemand PYTHONPATH setzen muss - dasselbe Muster wie in den uebrigen
# Werkzeugen unter tools/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import werkzeug_konfig                                # noqa: E402
from core.config_loader import coded_default                    # noqa: E402
from management.help import cli_epilog                          # noqa: E402
from management.maintenance import bestandsliste                # noqa: E402
from management.maintenance.bestandsliste import (              # noqa: E402
    bestaende_finden)
from management.maintenance.laufkopf import Laufkopf            # noqa: E402
from management.maintenance.anker_diagnose import AnkerDiagnose  # noqa: E402
from management.maintenance.anker_postbezug import FALL_TEXT     # noqa: E402


#: Die Dateien, die das ERGEBNIS dieses Laufs tragen. Nicht alle
#: importierten - eine Liste, in der die entscheidende Datei zwischen
#: zwanzig beilaeufigen steht, wird nicht gelesen.
_GETRAGEN_VON = (
    "tools/anker_diagnose.py",
    "management/maintenance/anker_diagnose.py",
    "management/maintenance/anker_postbezug.py",
    "report_render/html5_zerleger.py",
    "report_render/absatz_finder.py",
)


class Mitschrift:
    """
    Konsole und - wahlweise - Datei zugleich.

    Eingebautes 'tee': die Mitschrift entsteht auch dann, wenn jemand die
    Weiterleitung vergisst. Dieselbe Ueberlegung wie in
    tools/postid_nachtragen.py; die Datei traegt dieselben Zeilen wie die
    Konsole, keine andere Auswahl.
    """

    def __init__(self, pfad: str = "") -> None:
        self._datei = None
        if pfad:
            try:
                self._datei = open(pfad, "w", encoding="utf-8")
            except OSError as exc:
                print("Protokolldatei nicht schreibbar (%s) - der Lauf geht "
                      "weiter, die Ausgabe steht nur auf der Konsole." % exc)

    def __call__(self, zeile: str = "") -> None:
        print(zeile)
        if self._datei is not None:
            self._datei.write(zeile + "\n")

    def schliessen(self) -> None:
        if self._datei is not None:
            self._datei.close()
            self._datei = None


def _argumente(argv):
    # Der Epilog kommt aus dem CLI-Katalog und nicht aus dieser Datei: so
    # steht die Auskunft EINMAL da und laeuft nicht zwischen Werkzeug und
    # Hilfe auseinander (Waechter CE10).
    p = argparse.ArgumentParser(
        prog="anker_diagnose",
        description="Messen, warum die Anker der Textmarkierungen im "
                    "Seitenabzug nicht aufloesen. Rein lesend.",
        epilog=cli_epilog.epilog("anker_diagnose"),
        formatter_class=cli_epilog.HilfeFormat)
    # EINZELBESTAND - der Aufruf, den es seit Build 739 gibt. Er bleibt
    # unveraendert; die Katalogbeispiele und die Waechter AD03/AD05/AD08
    # nennen ihn. Er ist nur nicht mehr PFLICHT.
    p.add_argument("--evidence", default=None,
                   help="Pfad zu evidence_<uid>.db (wird NUR gelesen)")
    p.add_argument("--forensic", default=None,
                   help="Pfad zu forensic_<uid>.db (wird NUR gelesen)")
    # ALLE BESTAENDE - Build 763. Ohne --uid werden alle gefahren; die
    # Verzeichnisse kommen aus der config.yaml, damit sie EINMAL im Projekt
    # stehen (Waechter PH04).
    p.add_argument("--config", default="./config.yaml",
                   help="Konfigurationsdatei fuer die Verzeichnisvorgaben")
    p.add_argument("--evidence-dir", default=None,
                   help="Verzeichnis der evidence_<uid>.db; "
                        "ueberstimmt paths.evidence_db_dir")
    p.add_argument("--forensic-dir", default=None,
                   help="Verzeichnis der forensic_<uid>.db; "
                        "ueberstimmt paths.forensic_db_dir")
    p.add_argument("--uid", action="append", default=[],
                   help="nur diesen Bestand (mehrfach angebbar); "
                        "ohne Angabe alle im Verzeichnis")
    p.add_argument("--beleg", type=int, default=None,
                   help="nur diesen einen Beleg ansehen")
    # VORGABE ABHAENGIG VOM BETRIEB, s. _grenze_bestimmen(): 50 im
    # Einzelbestand, OHNE GRENZE ueber alle Bestaende. Eine feste 50 haette
    # beim Gesamtlauf still abgeschnitten.
    p.add_argument("--grenze", type=int, default=None,
                   help="hoechstens so viele Belege je Bestand; 0 = alle. "
                        "Vorgabe: 50 bei --evidence/--forensic, sonst 0")
    p.add_argument("--protokoll", default="",
                   help="die Ausgabe zusaetzlich in diese Datei schreiben")
    p.add_argument("--json", dest="json_ziel", default=None,
                   help="den Befund zusaetzlich maschinenlesbar hierhin "
                        "schreiben")
    return p.parse_args(argv)


def _grenze_bestimmen(a) -> int:
    """
    Die Grenze, mit der gelesen wird.

    Der Einzelbestandsaufruf behaelt seine Vorgabe 50 - er dient dem
    schnellen Blick auf einen Bestand, und daran soll sich nichts aendern.
    Der Lauf ueber alle Bestaende hat keine Vorgabe, weil eine Obergrenze
    dort ein stilles Weglassen waere (Grundregel 1). Wo die Grenze doch
    greift, sagt es der Bericht.
    """
    if a.grenze is not None:
        return int(a.grenze)
    return 50 if (a.evidence or a.forensic) else 0


def _bestaende_bestimmen(a, m):
    """
    Die Liste (uid, evidence_pfad, forensic_pfad), die gefahren wird.

    Zwei Betriebsarten, die sich nicht mischen: entweder ein ausdruecklich
    genannter Bestand (--evidence/--forensic) oder das Verzeichnis. Wer
    beides angibt, bekommt eine Ansage statt einer stillen Vorrangregel.
    """
    if a.evidence or a.forensic:
        if not (a.evidence and a.forensic):
            m("Aufruffehler: --evidence und --forensic gehoeren zusammen.")
            return None
        if a.uid:
            m("Aufruffehler: --uid gilt dem Verzeichnisbetrieb und passt "
              "nicht zu --evidence/--forensic.")
            return None
        uid = _uid_aus_pfad(a.evidence)
        return [(uid, a.evidence, a.forensic)]

    # Vorrang Argument > config.yaml > Vorgabewert - derselbe Aufloeser wie
    # in tools/annotationen_bestand.py, damit beide Werkzeuge dieselben
    # Verzeichnisse finden und dieselbe Herkunftszeile schreiben.
    aufl = werkzeug_konfig.resolver(a)
    evidence_dir = werkzeug_konfig.wert(
        "anker_diagnose", a, arg_attribut="evidence_dir",
        arg_name="--evidence-dir", config_schluessel="paths.evidence_db_dir",
        default=coded_default("paths.evidence_db_dir"),
        name="evidence_db_dir", r=aufl)
    forensic_dir = werkzeug_konfig.wert(
        "anker_diagnose", a, arg_attribut="forensic_dir",
        arg_name="--forensic-dir", config_schluessel="paths.forensic_db_dir",
        default=coded_default("paths.forensic_db_dir"),
        name="forensic_db_dir", r=aufl)

    gefunden = bestaende_finden(evidence_dir)
    if not gefunden:
        m("Keine evidence_<uid>.db in %s gefunden." % evidence_dir)
        return None
    if a.uid:
        gewuenscht = {str(u) for u in a.uid}
        gefunden = [g for g in gefunden if g[0] in gewuenscht]
        if not gefunden:
            m("Keiner der genannten Bestaende liegt in %s." % evidence_dir)
            return None
    return [(uid, pfad, str(Path(forensic_dir) / ("forensic_%s.db" % uid)))
            for uid, pfad in gefunden]


def _uid_aus_pfad(pfad: str) -> str:
    """Die Kennung aus 'evidence_<uid>.db'. Leer, wenn nicht ablesbar."""
    treffer = bestandsliste.RE_EVIDENCE.match(Path(pfad).name)
    return treffer.group(1) if treffer else ""


def main(argv=None) -> int:
    a = _argumente(sys.argv[1:] if argv is None else argv)
    m = Mitschrift(a.protokoll)
    try:
        m("=" * 78)
        m("ANKER-DIAGNOSE - rein lesend, es wird nichts veraendert")
        m("=" * 78)
        # HERKUNFT ZUERST (Build 746). Am 31.08.2026 lag eine Ausgabe vor,
        # die zeichengleich mit der aus dem Build davor war - 'nicht
        # eingespielt' und 'eingespielt, aber ohne Wirkung an dieser Stelle'
        # waren nicht zu unterscheiden. Das darf sich nicht wiederholen.
        for zeile in Laufkopf("anker_diagnose", _GETRAGEN_VON).zeilen():
            m(zeile)
        m()

        bestaende = _bestaende_bestimmen(a, m)
        if bestaende is None:
            return 2
        grenze = _grenze_bestimmen(a)

        # EIN FEHLSCHLAG BEENDET DEN LAUF NICHT. Ein Bestand, der nicht
        # lesbar ist, ist ein BEFUND und kein Grund, die uebrigen dreizehn
        # wegzulassen (Grundregel 1). Der Rueckgabewert traegt ihn trotzdem.
        rueck = 0
        befunde = []
        for uid, ev_pfad, fo_pfad in bestaende:
            code, befund = _ein_bestand(m, a, uid, ev_pfad, fo_pfad, grenze)
            if befund is not None:
                befunde.append(befund)
            rueck = max(rueck, code)

        if len(bestaende) > 1:
            _gesamtzaehlung(m, befunde)
        if a.json_ziel:
            if not _json_schreiben(m, a.json_ziel, befunde):
                rueck = max(rueck, 1)
        return rueck
    finally:
        m.schliessen()


def _ein_bestand(m, a, uid: str, ev_pfad: str, fo_pfad: str, grenze: int):
    """
    Ein Bestand - der Ablauf, der bis Build 762 den ganzen Lauf ausmachte.

    Rueckgabe: (rueckgabewert, Laufbefund oder None).
    """
    m("=" * 78)
    m("BESTAND %s" % (uid or "(Kennung nicht ablesbar)"))
    m("=" * 78)
    m("evidence: %s" % ev_pfad)
    m("forensic: %s" % fo_pfad)
    m()

    d = AnkerDiagnose(evidence=Path(ev_pfad), forensic=Path(fo_pfad),
                      nur_beleg=a.beleg)
    befund = d.lauf(grenze=grenze)
    befund.uid = uid

    if befund.fehler:
        m("BEFUND: %s" % befund.fehler)
        m()
        # Ein Leerbefund ist KEIN Fehler - er sagt, dass es nichts zu
        # diagnostizieren gibt, und das ist eine Auskunft.
        leer = befund.fehler.startswith("Keine Markierung")
        return (0 if leer else 1), befund

    if befund.abgeschnitten:
        # Grundregel 1: die Grenze hat wirklich abgeschnitten, und das steht
        # da - nicht nur als Vermutung aus der Trefferzahl.
        m("ACHTUNG: Die Grenze hat abgeschnitten. Der Bestand haelt %d "
          "Markierungen mit Anker, gelesen wurden %d. Mit '--grenze 0' "
          "werden alle gelesen."
          % (befund.gesamtzahl, len(befund.belege)))
        m()

    _bericht(m, befund)
    return 0, befund


def _bericht(m, befund) -> None:
    """Der Klartextbericht zu EINEM Bestand. Deutsch, ohne Beitragstext."""
    # -- Die Belege ---------------------------------------------------
    m("-" * 78)
    m("DIE BELEGE")
    m("-" * 78)
    for b in befund.belege:
        if b.hinweis:
            m("Beleg %-6d %s" % (b.beleg_id, b.hinweis))
            continue
        roh = "JA " if (b.lxml and b.lxml.position_vorhanden) else "nein"
        gen = "JA " if (b.zweite and b.zweite.position_vorhanden) else "nein"
        marke = "   <== DIE ANNAEHERUNG HEILT DIESEN" if b.entscheidend \
            else ""
        # BUILD 754: 'POSITION' statt 'traegt'. Die alte Beschriftung hat
        # gesagt, was gemessen wurde, und ist gelesen worden als das,
        # was NICHT gemessen wurde. Ein Feld, das 'traegt' heisst, wird
        # als 'stimmt' gelesen - das hat dieses Projekt eine Woche
        # gekostet.
        m("Beleg %-6d POSITION roh=%s  html5=%s%s"
          % (b.beleg_id, roh, gen, marke))
        if b.lxml and not b.lxml.position_vorhanden:
            m("             roh: %s" % b.lxml.kurz)
        if b.zweite and not b.zweite.position_vorhanden:
            m("             html5: %s" % b.zweite.kurz)
        # -- DIE INHALTSPROBE ---------------------------------------
        #
        # SIE STEHT UNMITTELBAR UNTER DER POSITIONSANGABE und nicht in
        # einer eigenen Rubrik weiter unten: die beiden Angaben gehoeren
        # zusammengelesen, sonst entsteht wieder der Eindruck, eine
        # vorhandene Position sei ein Beleg.
        p = getattr(b, "pruefung", None)
        if p is None:
            m("             INHALT   nicht geprueft (kein Abzug oder "
              "Pruefung fehlgeschlagen - s. Protokoll)")
        else:
            wl = ("#%d" % p.beitraege_wortlaut[0]
                  if len(p.beitraege_wortlaut) == 1
                  else ("%d Beitraege" % len(p.beitraege_wortlaut)
                        if p.beitraege_wortlaut else "kein Beitrag"))
            m("             INHALT   %s   Anker->%s, Wortlaut->%s, "
              "Textprobe: %s"
              % (p.urteil,
                 "#%d" % p.beitrag_anker if p.beitrag_anker is not None
                 else "-", wl, p.textprobe))
            if p.urteil in ("WIDERLEGT", "UNKLAR"):
                m("             %s" % p.bemerkung)
        # -- BUILD 763: DER POST-BEZUG UND DIE FALLZUORDNUNG -------------
        #
        # Sie steht UNTER der Inhaltsprobe, weil sie eine andere Frage
        # beantwortet: nicht 'stimmt der Ausdruck', sondern 'welchen Umfang
        # hat die Markierung'. Die Fallnummer ist ABGELEITET; die Messung
        # sind die beiden Zustaende und die Spanne, und die stehen daneben.
        m("             LAGE     Start=%s  Ende=%s  dazwischen=%s"
          % (_lage(b.bezug_start), _lage(b.bezug_end),
             _spanne_kurz(b.spanne)))
        m("             FALL %d   %s"
          % (b.fall, FALL_TEXT.get(b.fall, "")))
        if b.fall:
            m("             Vorschlag: %s%s   (%s)"
              % (b.fall_typ,
                 (" fuer " + ", ".join("#%d" % n for n in b.fall_posts))
                 if b.fall_posts else "",
                 b.fall_grund))
        else:
            m("             %s" % b.fall_grund)
        if b.anker_end_fehlt:
            m("             ACHTUNG: 'xpathEnd' fehlt - der Anfang wurde "
              "auch als Ende gemessen.")
    m()

    # -- Die Seiten ---------------------------------------------------
    m("-" * 78)
    m("DIE SEITEN")
    m("-" * 78)
    for s in befund.seiten:
        m("Seite %s" % s.page_url)
        if not s.vorhanden:
            m("   kein GET-Abzug zu dieser Adresse")
            m()
            continue
        m("   Abzug: %d Zeichen im <body>" % s.laenge)
        # -- BUILD 763: Seitenart und post container ---------------------
        m("   Seitenart: %s   post container im Abzug: %d"
          % (s.seitenklasse, s.container_zahl))
        if s.widerspruch:
            m("   WIDERSPRUCH: %s" % s.widerspruch)
        if s.verschachtelungen:
            # DER FALL, DEN VERSCHRAENKTER BB-CODE ERZEUGEN KANN. Gleiche
            # Nummer aussen und innen ('pN' / 'ppN') ist der Regelfall und
            # erscheint hier NICHT - nur verschiedene Nummern.
            m("   VERSCHACHTELTE post container mit VERSCHIEDENEN Nummern "
              "(%d):" % len(s.verschachtelungen))
            for v in s.verschachtelungen[:12]:
                m("      #%d liegt in #%d" % (v.innen, v.aussen))
            if len(s.verschachtelungen) > 12:
                m("      ... (%d weitere)" % (len(s.verschachtelungen) - 12))
        # M4 zuerst: das Fehlerprotokoll von libxml2 benennt die Ursache
        # oft unmittelbar und ist deshalb die wichtigste Zeile der Seite.
        m("   M4 Fehlerprotokoll des Zerlegers:")
        for zeile in s.fehlerprotokoll[:12]:
            m("      %s" % zeile)
        if len(s.fehlerprotokoll) > 12:
            m("      ... (%d weitere)" % (len(s.fehlerprotokoll) - 12))
        m("   M5 Wo die bekannten Kennungen WIRKLICH stehen:")
        for zeile in s.verortung:
            m("      %s" % zeile.replace("\n", "\n   "))
        if s.quelltext:
            m("   M6 Die Quelltextzeilen, die der Zerleger genannt hat:")
            for zeile in s.quelltext:
                m("      %s" % zeile)
        if s.verteilung_marke:
            # M7 steht VOR M3: wenn ein Anker bricht, ist die Frage
            # 'wo stehen die verlangten Elemente' die naechste, die
            # gestellt wird - und die Antwort entscheidet, ob ueberhaupt
            # noch ein Zerlegungsfehler in Betracht kommt.
            m("   M7 Wo die <%s> WIRKLICH stehen:" % s.verteilung_marke)
            m("      -- roh (libxml2) --")
            for zeile in s.verteilung_roh:
                m("      %s" % zeile)
            m("      -- nach der Annaeherung (der Weg des Berichts) --")
            for zeile in s.verteilung_genaehert:
                m("      %s" % zeile)
        if s.rohtext:
            m("   M3 %s" % s.rohtext)
        for zeile in s.annaeherung:
            m("   Annaeherung: %s" % zeile)
        for zeile in s.zeilen:
            m("   %s" % zeile)
        m()

    # -- Die Zaehlung -------------------------------------------------
    z = befund.zaehlung()
    m("=" * 78)
    m("ZAEHLUNG")
    m("=" * 78)
    m("Belege mit Anker geprueft:        %d" % z["belege"])
    m("davon roh aufgeloest:             %d" % z["lxml_traegt"])
    m("davon nach Annaeherung:           %d" % z["genaehert_traegt"])
    m("davon NUR nach Annaeherung:       %d" % z["entscheidend"])
    m("Seiten:                           %d" % z["seiten"])
    m()
    # -- BUILD 763: die Fallverteilung -----------------------------------
    m("FALLZUORDNUNG (abgeleitet aus Lage und Spanne):")
    for nummer, zahl in sorted(befund.fallzaehlung().items()):
        if zahl or nummer == 0:
            m("   Fall %d  %-4d %s" % (nummer, zahl, FALL_TEXT.get(nummer, "")))
    m()
    # -- BUILD 763: welche Seitenarten kommen ueberhaupt vor? -------------
    #
    # Die Liste der beitragsfreien Seitenarten ist bisher eine Erwartung.
    # Erst diese Verteilung sagt, welche Arten der Bestand wirklich traegt -
    # damit die Liste gemessen und nicht angenommen ist.
    m("SEITENARTEN der geprueften Belege:")
    for name, zahl in sorted(befund.klassenzaehlung().items()):
        m("   %-22s %d" % (name, zahl))
    verschachtelt = sum(len(s.verschachtelungen) for s in befund.seiten)
    widersprueche = sum(1 for s in befund.seiten if s.widerspruch)
    m()
    m("Verschachtelte post container mit verschiedenen Nummern: %d"
      % verschachtelt)
    m("Seiten mit Widerspruch zwischen Seitenart und Abzug:     %d"
      % widersprueche)
    m()
    m(_urteil(z))
    m()
    m(_gegenprobe_browser())


def _lage(bezug) -> str:
    """Der post-Bezug eines Endpunkts in einer Zeile."""
    if bezug is None:
        return "nicht gemessen"
    if bezug.zustand == "in_post":
        return "in #%d" % bezug.post_id
    if bezug.zustand == "above":
        return ("oberhalb (%d container darunter, #%s..#%s)"
                % (bezug.nachkommen_zahl, bezug.erste_nummer,
                   bezug.letzte_nummer))
    return "ausserhalb" + (" [%s]" % bezug.hinweis if bezug.hinweis else "")


def _spanne_kurz(spanne) -> str:
    """Die container zwischen den Endpunkten in einer Zeile."""
    if spanne is None:
        return "nicht gemessen"
    if not spanne.messbar:
        return "nicht messbar (%s)" % spanne.grund
    if not spanne.posts_dazwischen:
        return "keine"
    if len(spanne.posts_dazwischen) <= 6:
        return ", ".join("#%d" % n for n in spanne.posts_dazwischen)
    return ("%d container (#%d..#%d)"
            % (len(spanne.posts_dazwischen), spanne.posts_dazwischen[0],
               spanne.posts_dazwischen[-1]))


def _gesamtzaehlung(m, befunde) -> None:
    """
    Die Summe ueber ALLE Bestaende.

    Sie steht am Ende und nicht am Anfang: wer sie zuerst liest, liest sie
    ohne die Einzelbefunde, aus denen sie entsteht. Ausgewiesen wird auch,
    wie viele Bestaende ueberhaupt gelesen werden konnten - eine Summe ueber
    dreizehn von vierzehn Bestaenden, die wie eine ueber vierzehn aussieht,
    waere ein stiller Verlust (Grundregel 1).
    """
    m("=" * 78)
    m("GESAMTZAEHLUNG UEBER ALLE BESTAENDE")
    m("=" * 78)
    lesbar = [b for b in befunde if not b.fehler]
    m("Bestaende angesehen:              %d" % len(befunde))
    m("davon gelesen:                    %d" % len(lesbar))
    if len(lesbar) != len(befunde):
        for b in befunde:
            if b.fehler:
                m("   Bestand %s: %s" % (b.uid, b.fehler))
    m("Markierungen mit Anker gelesen:   %d"
      % sum(len(b.belege) for b in lesbar))
    abgeschnitten = [b.uid for b in lesbar if b.abgeschnitten]
    if abgeschnitten:
        m("ACHTUNG - abgeschnitten in Bestand: %s" % ", ".join(abgeschnitten))
    m()
    m("FALLZUORDNUNG ueber alle Bestaende:")
    gesamt = {}
    for b in lesbar:
        for nummer, zahl in b.fallzaehlung().items():
            gesamt[nummer] = gesamt.get(nummer, 0) + zahl
    for nummer, zahl in sorted(gesamt.items()):
        if zahl or nummer == 0:
            m("   Fall %d  %-4d %s" % (nummer, zahl, FALL_TEXT.get(nummer, "")))
    m()
    m("SEITENARTEN ueber alle Bestaende:")
    klassen = {}
    for b in lesbar:
        for name, zahl in b.klassenzaehlung().items():
            klassen[name] = klassen.get(name, 0) + zahl
    for name, zahl in sorted(klassen.items()):
        m("   %-22s %d" % (name, zahl))
    m()


def _json_schreiben(m, ziel: str, befunde) -> bool:
    """
    Der maschinenlesbare Befund. True bei Erfolg.

    ensure_ascii=True: die Datei wird zwischen Umgebungen weitergereicht
    (Linux-Entwicklung, Windows-VM) und darf dabei nicht von der
    Zeichensatzeinstellung der Konsole abhaengen.
    """
    inhalt = {
        "werkzeug": "anker_diagnose",
        "build": _buildnummer(),
        "bestaende": [b.als_dict() for b in befunde],
    }
    try:
        with open(ziel, "w", encoding="utf-8") as fh:
            json.dump(inhalt, fh, ensure_ascii=True, indent=1, sort_keys=True)
    except OSError as exc:
        m("JSON-Datei nicht schreibbar: %s" % exc)
        return False
    m("JSON geschrieben: %s" % ziel)
    return True


def _buildnummer() -> str:
    """Die Buildnummer aus build.json - leer, wenn sie nicht lesbar ist."""
    try:
        pfad = Path(__file__).resolve().parent.parent / "build.json"
        with open(pfad, "r", encoding="utf-8") as fh:
            return str(json.load(fh).get("build", ""))
    except Exception:                             # pragma: no cover - defensiv
        return ""


def _urteil(z) -> str:
    """
    Das Urteil zur Zaehlung - in ganzen Saetzen und ohne Ueberdehnung.

    KEIN URTEIL OHNE MESSUNG, aber auch keine Messung ohne Urteil: eine
    Zahlenreihe, die niemand einordnet, wird eingeordnet, und zwar von dem,
    der sie zuerst deutet. Dann lieber hier, mit den Grenzen daneben.
    """
    if z["belege"] == 0:
        return "Nichts geprueft - kein Urteil."
    if z["entscheidend"] > 0:
        return (
            "BEFUND: %d von %d Ankern loesen NUR nach der Annaeherung auf.\n"
            "Damit ist belegt, dass der Abzug vollstaendig ist und die "
            "ZERLEGUNG die Elemente falsch ablegt.\n"
            "Es ist ein Auswertungsfehler und KEIN Datenschaden - an den "
            "gesicherten Seiten fehlt nichts.\n"
            "Der Zerleger ist report_render/html5_zerleger.py, und er ist in "
            "report_render/absatz_finder.py bereits eingebaut."
            % (z["entscheidend"], z["belege"]))
    if z["lxml_traegt"] == z["belege"]:
        return ("BEFUND: alle Anker loesen schon roh auf. Auf DIESEM Bestand "
                "gibt es das Problem nicht.")
    return (
        "BEFUND: die Annaeherung aendert an diesem Bestand NICHTS - %d von %d "
        "Ankern bleiben gebrochen.\n"
        "Das schliesst <noscript> und <template> als Ursache AUS und ist "
        "damit ein Ergebnis, kein Fehlschlag.\n"
        "\n"
        "WEITERLESEN BEI M4, M5 UND M6 - in dieser Reihenfolge:\n"
        "  M4 sagt, ob der Zerleger selbst etwas beanstandet hat. "
        "'ERR_RESOURCE_LIMIT: Excessive depth' heisst, dass er die "
        "Schachtelung abgebrochen und den Rest der Seite WEGGELASSEN hat - "
        "eine Grenze, die ein Browser nicht kennt. "
        "'ERR_TAG_NAME_MISMATCH' heisst, dass ein Element offen geblieben "
        "ist.\n"
        "  M5 sagt, ob '#page-body' im Baum TIEFER steht (verschluckt) oder "
        "GANZ FEHLT, obwohl es im Quelltext steht (weggelassen). Das sind "
        "zwei verschiedene Ursachen mit zwei verschiedenen Abhilfen. Die "
        "KETTE nennt dabei das Element, das es aufgenommen hat.\n"
        "  M6 zeigt die Quelltextzeilen, die der Zerleger in M4 genannt hat "
        "- verdeckt, aber mit vollstaendigem Geruest. Erst daran laesst sich "
        "der Konstrukt nachstellen."
        % (z["belege"] - z["lxml_traegt"], z["belege"]))


def _gegenprobe_browser() -> str:
    """
    Der Einzeiler fuer die Browserkonsole - die DRITTE Meinung.

    Weder libxml2 noch ein zweiter Zerleger in Python bauen den Baum so auf
    wie ein Browser. Der einzige Browser, der den fraglichen Abzug wirklich
    vor sich hat, steht im Ermittlungsfenster. Deshalb geht der Lauf nicht zu
    Ende, ohne zu sagen, wie man ihn fragt.
    """
    return (
        "GEGENPROBE IM BROWSER (Ermittlungsfenster, F12 -> Console, auf der\n"
        "betroffenen Seite). Sie zeigt, was der Browser an derselben Stelle\n"
        "hat - die Ausgabe traegt nur Tagnamen und Kennungen:\n"
        "\n"
        "  (function(){var v=document.getElementById('forensic-viewport');"
        "var o=[],e=v;while(e){o.push([].map.call(e.children,function(k){"
        "return k.tagName.toLowerCase()+(k.id?'#'+k.id:'');}).join(', '));"
        "e=e.children[0];if(o.length>6)break;}console.log(o.join('\\n'));})()"
        "\n\n"
        "Die erste Zeile sind die Kinder des Viewports, die zweite deren\n"
        "erstes Kind und so fort. Sie gehoert gegen den Ebenenbericht oben\n"
        "gehalten.")


if __name__ == "__main__":          # pragma: no cover - Einstieg
    sys.exit(main())
