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
#   Am 30.08.2026 wurden zehn HTML-Konstrukte gegen Chromium und gegen
#   libxml2 gehalten. Zwei erzeugen GENAU dieses Bild - ein <noscript> und
#   ein <template>, deren Inhalt nicht ausgeglichen ist. Der Browser stellt
#   den Inhalt beider nicht in den Baum, libxml2 schon; ein offenes Tag darin
#   verschluckt dann alles, was folgt.
#
#   DIESES WERKZEUG SAGT, OB DAS IM VORLIEGENDEN ABZUG DER FALL IST. Es
#   behauptet es nicht - es misst es.
#
# ── WAS DER LAUF AUSGIBT ─────────────────────────────────────────────────────
#
#   Je Beleg eine Zeile: loest der Anker roh auf? Loest er nach der
#   Annaeherung auf? Die Zeilen mit 'roh=nein angenaehert=JA' sind der
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
# Version: 0.8.737 - Build 737
# =============================================================================

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Damit das Werkzeug aus dem Wurzelverzeichnis heraus laeuft, ohne dass
# jemand PYTHONPATH setzen muss - dasselbe Muster wie in den uebrigen
# Werkzeugen unter tools/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.help import cli_epilog                          # noqa: E402
from management.maintenance.anker_diagnose import AnkerDiagnose  # noqa: E402


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
    p.add_argument("--evidence", required=True,
                   help="Pfad zu evidence_<uid>.db (wird NUR gelesen)")
    p.add_argument("--forensic", required=True,
                   help="Pfad zu forensic_<uid>.db (wird NUR gelesen)")
    p.add_argument("--beleg", type=int, default=None,
                   help="nur diesen einen Beleg ansehen")
    p.add_argument("--grenze", type=int, default=50,
                   help="hoechstens so viele Belege (Vorgabe 50)")
    p.add_argument("--protokoll", default="",
                   help="die Ausgabe zusaetzlich in diese Datei schreiben")
    return p.parse_args(argv)


def main(argv=None) -> int:
    a = _argumente(sys.argv[1:] if argv is None else argv)
    m = Mitschrift(a.protokoll)
    try:
        m("=" * 78)
        m("ANKER-DIAGNOSE - rein lesend, es wird nichts veraendert")
        m("=" * 78)
        m("evidence: %s" % a.evidence)
        m("forensic: %s" % a.forensic)
        m()

        d = AnkerDiagnose(evidence=Path(a.evidence), forensic=Path(a.forensic),
                          nur_beleg=a.beleg)
        befund = d.lauf(grenze=a.grenze)

        if befund.fehler:
            m("BEFUND: %s" % befund.fehler)
            # Ein Leerbefund ist KEIN Fehler - er sagt, dass es nichts zu
            # diagnostizieren gibt, und das ist eine Auskunft.
            leer = befund.fehler.startswith("Keine Markierung")
            m.schliessen()
            return 0 if leer else 1

        # -- Die Belege ---------------------------------------------------
        m("-" * 78)
        m("DIE BELEGE")
        m("-" * 78)
        for b in befund.belege:
            if b.hinweis:
                m("Beleg %-6d %s" % (b.beleg_id, b.hinweis))
                continue
            roh = "JA " if (b.lxml and b.lxml.traegt) else "nein"
            gen = "JA " if (b.zweite and b.zweite.traegt) else "nein"
            marke = "   <== DIE ANNAEHERUNG HEILT DIESEN" if b.entscheidend \
                else ""
            m("Beleg %-6d roh=%s  angenaehert=%s%s" % (b.beleg_id, roh, gen,
                                                       marke))
            if b.lxml and not b.lxml.traegt:
                m("             roh: %s" % b.lxml.kurz)
            if b.zweite and not b.zweite.traegt:
                m("             angenaehert: %s" % b.zweite.kurz)
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
        m(_urteil(z))
        m()
        m(_gegenprobe_browser())
        return 0
    finally:
        m.schliessen()


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
            "Der Fix ist report_render/html5_annaeherung.py, und er ist in "
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
