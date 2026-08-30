#!/usr/bin/env python3
# =============================================================================
# tools/seite_ausleiten.py
# IT-Forensisches Ermittlungswerkzeug - Gegenprobe im Browser
# =============================================================================
# Zweck:
#   DEN GESICHERTEN SEITENABZUG ZU EINEM BELEG ALS DATEI HERAUSSCHREIBEN,
#   damit er von Hand in einem Browser angesehen werden kann - und dazu die
#   Positionsangabe (den Anker) dieses Belegs sowie einen fertigen
#   Konsolen-Einzeiler, der den Anker im Browser Schritt fuer Schritt
#   abschreitet.
#
# ── WARUM ES DAS GIBT ────────────────────────────────────────────────────────
#
#   Seit fuenf Builds wird gemessen, wie ZWEI SERVERSEITIGE ZERLEGER den
#   Abzug lesen. Beide sind nicht der Browser. Der Browser ist aber der
#   einzige, der beim Markieren dabei war - er hat den Anker erzeugt. Was er
#   an der verlangten Stelle sieht, ist deshalb kein weiterer Messwert
#   neben anderen, sondern DER MASSSTAB.
#
#   Dieses Werkzeug macht ihn zugaenglich, ohne dass der Webserver laufen
#   muss und ohne dass irgendjemand ausser dem Ermittler den Inhalt sieht.
#
# ── ES SCHREIBT NICHT IN DIE DATENBANKEN ─────────────────────────────────────
#
#   Beide werden mit 'mode=ro' geoeffnet. Wartungsstufe C.
#
# ── WARUM ES IN DIE LIEFERUNG GEHOERT ────────────────────────────────────────
#
#   Es hat am 31.08.2026 den Streit entschieden, an dem fuenf Builds
#   gescheitert sind: der Anker ist richtig, der Abzug ist vollstaendig,
#   falsch war die Zerlegung. Diese Gegenprobe ist damit das Verfahren, mit
#   dem ein Zweifel an einem Anker kuenftig ausgeraeumt wird - und ein
#   Verfahren, das in der Akte steht, gehoert auch in den Bestand und nicht
#   auf einen Zuruf. Beleg:
#   management/Befund_Ankerbruch_Browsergegenprobe_v1_0.md
#
# ── ACHTUNG: DIE ERZEUGTE DATEI IST BEWEISMITTELINHALT ───────────────────────
#
#   Sie enthaelt die Seite im Klartext - Beitraege, Benutzernamen, alles.
#   Sie gehoert in ein Verzeichnis, das denselben Schutz geniesst wie die
#   Datenbanken, und sie ist nach der Sichtung zu loeschen. Das Werkzeug
#   legt sie deshalb NICHT von sich aus irgendwohin, sondern nur dorthin,
#   wo es ausdruecklich angewiesen wird.
#
# AUFRUF (in der VM, aus dem Wurzelverzeichnis des Webservers):
#
#   python tools/seite_ausleiten.py \
#       --evidence ./data/evidence/evidence_155955.db \
#       --forensic ./data/forensic/forensic_155955.db \
#       --beleg 16 \
#       --ziel ./sichtung/beleg_16.html
#
# Version: v0.8.747 - Build: 747 - 2026-08-31
# =============================================================================

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# Damit das Werkzeug aus dem Wurzelverzeichnis heraus laeuft, ohne dass
# jemand PYTHONPATH setzen muss - dasselbe Muster wie in den uebrigen
# Werkzeugen unter tools/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.help import cli_epilog                       # noqa: E402
from management.maintenance.laufkopf import Laufkopf         # noqa: E402


#: Die Dateien, die das ERGEBNIS dieses Laufs tragen.
_GETRAGEN_VON = (
    "tools/seite_ausleiten.py",
)


def _oeffnen(evidence: Path, forensic: Path) -> sqlite3.Connection:
    """Beide Datenbanken NUR LESEND - 'mode=ro' laesst kein Schreiben zu."""
    con = sqlite3.connect("file:%s?mode=ro" % evidence, uri=True)
    con.row_factory = sqlite3.Row
    con.execute("ATTACH DATABASE ? AS fdb", ("file:%s?mode=ro" % forensic,))
    return con


def _anker_und_url(con: sqlite3.Connection, beleg: int):
    """(Anker, Adresse, markierter Wortlaut) zu einem Beleg."""
    zeile = con.execute(
        "SELECT page_url, selection_json FROM annotations WHERE id = ?",
        (beleg,)).fetchone()
    if zeile is None:
        return None, None, None
    try:
        sel = json.loads(zeile["selection_json"] or "{}")
    except (ValueError, TypeError):
        sel = {}
    return (str(sel.get("xpathStart") or ""), zeile["page_url"],
            str(sel.get("textContent") or ""))


def _blob(con: sqlite3.Connection, url: str):
    """
    Der GET-Abzug zu einer Adresse - DIESELBEN VIER ABFRAGEN wie im
    Nachtrag, einschliesslich des Filters auf method='GET'. Ein anderer
    Abzug hier waere eine andere Messung.
    """
    for sql, par in (
        ("SELECT html FROM fdb.pages WHERE url_canonical = ? "
         "AND method = 'GET' LIMIT 1", (url,)),
        ("SELECT p.html FROM fdb.pages p JOIN fdb.page_aliases a "
         "ON a.page_id = p.id WHERE a.url_raw = ? AND p.method = 'GET' "
         "LIMIT 1", (url,)),
        ("SELECT html FROM fdb.pages WHERE url_canonical LIKE ? "
         "AND method = 'GET' LIMIT 1", ("%" + url,)),
        ("SELECT p.html FROM fdb.pages p JOIN fdb.page_aliases a "
         "ON a.page_id = p.id WHERE a.url_raw LIKE ? AND p.method = 'GET' "
         "LIMIT 1", ("%" + url,)),
    ):
        try:
            z = con.execute(sql, par).fetchone()
        except sqlite3.Error:
            continue
        if z is not None and z[0]:
            return z[0]
    return None


def _rumpf(roh: bytes) -> str:
    """
    Der Inhalt des <body> - GENAU wie BlobHandler._extract_body() ihn nimmt.

    Reine Zeichenkettensuche, kein Zerleger. Das ist Absicht: das
    Ermittlungsfenster bekommt denselben String, und ein Zerleger hier
    wuerde genau den Unterschied einfuehren, den wir gerade suchen.
    """
    text = roh.decode("utf-8", errors="replace")
    unten = text.lower()
    a = unten.find("<body")
    if a < 0:
        return text
    a = text.find(">", a)
    b = unten.rfind("</body>")
    return text[a + 1:b] if b > a else text[a + 1:]


#: Die Huelle um den Rumpf. '#forensic-viewport' heisst hier genauso wie im
#: Ermittlungsfenster - nur dann trifft der Anker, der DORT gerechnet wurde,
#: hier auf dieselbe Ausgangslage.
_HUELLE = """<!DOCTYPE html>
<meta charset="utf-8">
<title>Sichtung Beleg %(beleg)s</title>
<div id="forensic-viewport">%(rumpf)s</div>
<script>
// ---------------------------------------------------------------------------
// ANKERPRUEFUNG IM BROWSER - der einzige Zerleger, der beim Markieren dabei
// war. Was hier steht, ist der Massstab; alles Serverseitige misst sich
// daran und nicht umgekehrt.
//
// Ausgabe erscheint in der Entwicklerkonsole (F12). Sie traegt NUR
// Tagnamen, Kennungen, Klassen und Zahlen - keinen Beitragstext.
// ---------------------------------------------------------------------------
(function () {
  'use strict';
  var ANKER = %(anker)s;
  var vp = document.getElementById('forensic-viewport');
  var zeilen = [];

  function benenne(el) {
    if (!el) { return '(nichts)'; }
    var s = el.tagName.toLowerCase();
    if (el.id) { s += '#' + el.id; }
    if (el.className && typeof el.className === 'string') {
      s += '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.');
    }
    return s;
  }

  zeilen.push('ANKER: ' + ANKER);
  zeilen.push('Viewport traegt ' + vp.children.length + ' Kinder: ' +
              Array.prototype.map.call(vp.children, benenne).join(', '));
  zeilen.push('');

  // Schritt fuer Schritt abschreiten - mit DENSELBEN Regeln wie toolbar.js:
  // gezaehlt wird unter GLEICHNAMIGEN Geschwistern, 1-basiert.
  var schritte = ANKER.split('/').filter(function (t) {
    return t && t !== '.';
  });
  var knoten = vp, bisher = '.';
  for (var i = 0; i < schritte.length; i++) {
    var m = /^([A-Za-z_][\\w.-]*|text\\(\\))\\[(\\d+)\\]$/.exec(schritte[i]);
    if (!m) { zeilen.push('Schritt ' + (i + 1) + ': ' + schritte[i] +
                          ' - nicht lesbar, Abbruch'); break; }
    var marke = m[1], nr = parseInt(m[2], 10);
    if (marke === 'text()') {
      var t = Array.prototype.filter.call(knoten.childNodes, function (k) {
        return k.nodeType === 3;
      });
      zeilen.push('Schritt ' + (i + 1) + ': text()[' + nr + '] - ' +
                  t.length + ' Textknoten vorhanden -> ' +
                  (nr <= t.length ? 'LOEST AUF' : 'BRICHT'));
      break;
    }
    var gleiche = Array.prototype.filter.call(knoten.children, function (k) {
      return k.tagName.toLowerCase() === marke;
    });
    var naechster = (nr >= 1 && nr <= gleiche.length) ? gleiche[nr - 1] : null;
    zeilen.push('Schritt ' + (i + 1) + ' bei ' + bisher + ': <' + marke +
                '>[' + nr + '] - dort stehen ' + gleiche.length +
                ' -> ' + (naechster ? benenne(naechster) : 'BRICHT HIER'));
    if (!naechster) {
      zeilen.push('   Vorhanden waeren: ' +
                  Array.prototype.map.call(knoten.children, benenne)
                       .slice(0, 12).join(', '));
      break;
    }
    knoten = naechster;
    bisher += '/' + schritte[i];
  }

  zeilen.push('');
  zeilen.push('Die ganze Seite traegt ' +
              document.querySelectorAll('article').length + ' <article>.');
  var body = document.getElementById('page-body');
  zeilen.push('#page-body ist ' + (body ? 'vorhanden' : 'NICHT vorhanden') +
              (body ? ', Elternteil: ' + benenne(body.parentElement) +
                      ', direkte <article> darin: ' +
                      Array.prototype.filter.call(body.children, function (k) {
                        return k.tagName.toLowerCase() === 'article';
                      }).length
                    : ''));

  var text = zeilen.join('\\n');
  console.log(text);
  try { if (window.copy) { window.copy(text); } } catch (e) { }
})();
</script>
"""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="seite_ausleiten",
        description="Den gesicherten Seitenabzug zu einem Beleg als Datei "
                    "herausschreiben und den Anker im Browser pruefbar "
                    "machen. Rein lesend.",
        epilog=cli_epilog.epilog("seite_ausleiten"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--evidence", required=True)
    p.add_argument("--forensic", required=True)
    p.add_argument("--beleg", type=int, required=True)
    p.add_argument("--ziel", required=True,
                   help="Zieldatei (.html). ACHTUNG: enthaelt "
                        "Beweismittelinhalt im Klartext.")
    a = p.parse_args(sys.argv[1:] if argv is None else argv)

    for zeile in Laufkopf("seite_ausleiten", _GETRAGEN_VON).zeilen():
        print(zeile)
    print()

    ev, fo, ziel = Path(a.evidence), Path(a.forensic), Path(a.ziel)
    for pfad in (ev, fo):
        if not pfad.exists():
            print("Datei fehlt: %s" % pfad)
            return 1

    con = _oeffnen(ev, fo)
    try:
        anker, url, wortlaut = _anker_und_url(con, a.beleg)
        if url is None:
            print("Beleg %d gibt es in %s nicht." % (a.beleg, ev.name))
            return 1
        print("Beleg     : %d" % a.beleg)
        print("Adresse   : %s" % url)
        print("Anker     : %s" % (anker or "(keiner)"))
        print("Wortlaut  : %d Zeichen (wird NICHT ausgegeben)"
              % len(wortlaut or ""))

        roh = _blob(con, url)
        if not roh:
            print("Kein GET-Abzug zu dieser Adresse - nichts auszuleiten.")
            return 1
        print("Abzug     : %d Bytes" % len(roh))
    finally:
        con.close()

    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(
        _HUELLE % {"beleg": a.beleg,
                   "rumpf": _rumpf(roh),
                   "anker": json.dumps(anker or "")},
        encoding="utf-8")
    print()
    print("Geschrieben: %s" % ziel)
    print()
    print("SO GEHT ES WEITER")
    print("  1. Die Datei im Browser der VM oeffnen (Doppelklick genuegt).")
    print("  2. F12 -> Reiter 'Konsole'. Die Ankerpruefung laeuft von")
    print("     selbst und legt ihre Ausgabe zusaetzlich in die")
    print("     Zwischenablage.")
    print("  3. NUR DIESE KONSOLENAUSGABE ist weiterzugeben - sie traegt")
    print("     Tagnamen, Kennungen und Zahlen, keinen Beitragstext.")
    print()
    print("ACHTUNG: %s ENTHAELT BEWEISMITTELINHALT IM KLARTEXT." % ziel.name)
    print("Nach der Sichtung loeschen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
