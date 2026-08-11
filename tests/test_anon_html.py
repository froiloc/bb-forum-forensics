# =============================================================================
# tests/test_anon_html.py
# IT-Forensisches Ermittlungswerkzeug - Weitergabe unverfaenglich machen
# =============================================================================
# DIE WAECHTER ZU VORGANG ad88708d (Build 687).
#
# WARUM ES SIE BRAUCHT: 'tools/anon_html.py' stellt her, was die Projektregel
# "Inhalte nur nach Pruefung auf Unverfaenglichkeit" verlangt. Es hatte bis
# Build 686 KEINEN einzigen Test. Zwei gemessene Befunde (Kindelemente blieben
# im Klartext; ohne Treffer meldete der Lauf Erfolg und schrieb mit '-v' eine
# unveraenderte Kopie namens 'anonymized') standen seit dem 2026-08-01 nur als
# Warnung im Katalog. Eine Warnung verhindert nichts.
#
# WAS HIER GEMESSEN WIRD - und was ausdruecklich nicht:
#   Gemessen wird das VERHALTEN gegen echte Dateien unter tmp_path: Aufruf,
#   Rueckgabewert, und dann der INHALT dessen, was auf der Platte gelandet
#   ist. Nicht gemessen wird der Quelltext. Ein Test, der prueft, ob eine
#   bestimmte Funktion aufgerufen wird, waere gruen geblieben, waehrend die
#   geschriebene Datei Klartext enthaelt - und genau darum geht es hier.
#
# AH01 - der Ticketfall: Kindelement und tail werden mit ersetzt
# AH02 - ein Element, dessen Inhalt ganz im Kindelement steckt
# AH03 - Text AUSSERHALB der Auswahl bleibt unangetastet
# AH04 - kein Treffer ist ein BEFUND: RC 2, keine Datei
# AH05 - kein Treffer MIT '-v' ebenso (der gefaehrliche Fall aus dem Ticket)
# AH06 - getroffen, aber nichts zu ersetzen: ebenfalls BEFUND, keine Datei
# AH07 - eine vorhandene Zieldatei wird nicht wortlos ueberschrieben
# AH08 - '--overwrite' laesst es zu
# AH09 - UTF-8 ohne '<meta charset>' beschaedigt nichts mehr
# AH10 - eine falsch angesagte Kodierung bricht ab, statt zu beschaedigen
# AH11 - der DOCTYPE wird erhalten, aber nicht erfunden
# AH12 - Kommentare werden geblendet, Attribute bleiben und werden GEMELDET
# AH13 - Nicht-Element-Treffer werden benannt statt verworfen
# AH14 - DIE GEGENPROBE KANN SCHEITERN, und dann entsteht keine Datei
# AH15 - der Trockenlauf schreibt nichts
# AH16 - es bleibt keine Nebendatei liegen
#
# Version: v0.8.687 - Build: 687 - 2026-08-11
# =============================================================================

import importlib.util
import sys
from pathlib import Path

import pytest

_WURZEL = Path(__file__).resolve().parent.parent
if str(_WURZEL) not in sys.path:
    sys.path.insert(0, str(_WURZEL))

# 'tools' ist kein Paket (kein __init__.py) - dasselbe Ladeverfahren wie in
# tests/test_convert_journal_mode.py und tests/test_cli_vorrang.py.
_spec = importlib.util.spec_from_file_location(
    "anon_html", _WURZEL / "tools" / "anon_html.py")
anon_html = importlib.util.module_from_spec(_spec)
sys.modules["anon_html"] = anon_html
_spec.loader.exec_module(anon_html)

# Ohne lxml gibt es nichts zu messen. Ein uebersprungener Test SAGT das, ein
# fehlender verschweigt es (Grundregel 1).
pytest.importorskip("lxml", reason="anon_html setzt lxml voraus")


#: Der Beitrag aus dem Vorgang - woertlich, damit der Test und das Ticket
#: ueber dieselbe Zeile sprechen.
BEITRAG = (
    '<div class="postmsg">Vorname <b>Nachname</b> wohnt in Musterstadt.</div>')
NUR_KIND = (
    '<div class="postmsg"><span>Nur im Kindelement: Klarname</span></div>')


def _seite(inhalt, doctype=True, meta=True):
    """Eine kleine, vollstaendige Seite um den Pruefinhalt herum."""
    kopf = '<!DOCTYPE html>\n' if doctype else ''
    charset = '<meta charset="utf-8">' if meta else ''
    return ('%s<html><head>%s</head><body>\n%s\n</body></html>\n'
            % (kopf, charset, inhalt))


def _schreibe(pfad, text):
    pfad.write_bytes(text.encode("utf-8"))
    return pfad


def _lauf(*argv):
    """Das Werkzeug aufrufen und den Rueckgabewert liefern."""
    return anon_html.main([str(a) for a in argv])


# -----------------------------------------------------------------------------
# AH01-AH03 - Befund 1: der Teilbaum, nicht nur der erste Textknoten
# -----------------------------------------------------------------------------

def test_ah01_kindelement_und_tail_werden_mit_ersetzt(tmp_path):
    """
    AH01 - der Ticketfall, woertlich.

    Bis Build 686 gemessen:
      <div class="postmsg">XXXXXXX <b>Nachname</b> wohnt in Musterstadt.</div>
    Name und Ort standen also im Klartext in einer Datei, die 'anonymized'
    hiess.
    """
    quelle = _schreibe(tmp_path / "a.html", _seite(BEITRAG))
    ziel = tmp_path / "a.out.html"

    rc = _lauf(quelle, "-x", '//div[@class="postmsg"]', "-o", ziel)

    assert rc == anon_html.RC_OK
    ergebnis = ziel.read_text(encoding="utf-8")
    for klartext in ("Vorname", "Nachname", "Musterstadt"):
        assert klartext not in ergebnis, (
            "'%s' steht noch im Klartext in der Ausgabe:\n%s"
            % (klartext, ergebnis))
    # Die Gestalt bleibt: das Kindelement selbst ist noch da.
    assert "<b>" in ergebnis
    assert "XXXXXXXX" in ergebnis          # 'Nachname', geblendet


def test_ah02_inhalt_ganz_im_kindelement(tmp_path):
    """
    AH02 - bis Build 686 blieb ein solches Element GAR NICHT anonymisiert.
    """
    quelle = _schreibe(tmp_path / "b.html", _seite(NUR_KIND))
    ziel = tmp_path / "b.out.html"

    assert _lauf(quelle, "-x", '//div[@class="postmsg"]',
                 "-o", ziel) == anon_html.RC_OK
    assert "Klarname" not in ziel.read_text(encoding="utf-8")


def test_ah03_text_ausserhalb_der_auswahl_bleibt(tmp_path):
    """
    AH03 - die Gegenrichtung. Ein Werkzeug, das mehr blendet als ausgewaehlt
    wurde, waere genauso unbrauchbar: der Bediener kann dann nicht mehr
    beurteilen, was er weitergibt.

    Insbesondere darf 'elem.tail' - der Text HINTER dem getroffenen Element -
    nicht mitgeblendet werden; er gehoert dem Elternteil.
    """
    quelle = _schreibe(tmp_path / "c.html", _seite(
        BEITRAG + "Text direkt hinter dem Element."
        + '<p id="aussen">Bleibt stehen</p>'))
    ziel = tmp_path / "c.out.html"

    assert _lauf(quelle, "-x", '//div[@class="postmsg"]',
                 "-o", ziel) == anon_html.RC_OK
    ergebnis = ziel.read_text(encoding="utf-8")
    assert "Bleibt stehen" in ergebnis
    assert "Text direkt hinter dem Element." in ergebnis


# -----------------------------------------------------------------------------
# AH04-AH06 - Befund 2: kein Treffer ist ein Befund, kein Erfolg
# -----------------------------------------------------------------------------

def test_ah04_kein_treffer_ist_ein_befund(tmp_path):
    """AH04 - RC 2, und vor allem: KEINE Datei."""
    quelle = _schreibe(tmp_path / "d.html", _seite(BEITRAG))
    ziel = tmp_path / "d.out.html"

    assert _lauf(quelle, "-x", '//div[@class="gibtesnicht"]',
                 "-o", ziel) == anon_html.RC_KEIN_TREFFER
    assert not ziel.exists(), (
        "Ohne Treffer darf keine Datei entstehen - sie waere eine "
        "unveraenderte Kopie unter einem Namen, der das Gegenteil behauptet.")


def test_ah05_kein_treffer_mit_verbose_schreibt_erst_recht_nichts(tmp_path):
    """
    AH05 - DER FALL AUS DEM TICKET. Bis Build 686 fiel der Lauf mit '-v'
    nicht in den fruehen sys.exit(0) und schrieb eine UNVERAENDERTE Kopie
    mit der Meldung 'Written anonymized HTML to: ...'.
    """
    quelle = _schreibe(tmp_path / "e.html", _seite(BEITRAG))
    ziel = tmp_path / "e.out.html"

    assert _lauf(quelle, "-x", '//div[@class="gibtesnicht"]', "-v",
                 "-o", ziel) == anon_html.RC_KEIN_TREFFER
    assert not ziel.exists()


def test_ah06_getroffen_aber_nichts_zu_ersetzen(tmp_path):
    """
    AH06 - der zweite Weg zu einer unveraenderten Kopie: der Ausdruck trifft,
    die Treffer sind aber leer. Das Ergebnis waere Byte fuer Byte das
    Original gewesen.
    """
    quelle = _schreibe(tmp_path / "f.html",
                       _seite('<div class="postmsg"></div>'))
    ziel = tmp_path / "f.out.html"

    assert _lauf(quelle, "-x", '//div[@class="postmsg"]',
                 "-o", ziel) == anon_html.RC_KEIN_TREFFER
    assert not ziel.exists()


# -----------------------------------------------------------------------------
# AH07-AH08 - die Zieldatei
# -----------------------------------------------------------------------------

def test_ah07_vorhandene_zieldatei_wird_nicht_ueberschrieben(tmp_path):
    """AH07 - und der Inhalt der Vorgaengerdatei bleibt unangetastet."""
    quelle = _schreibe(tmp_path / "g.html", _seite(BEITRAG))
    ziel = tmp_path / "g.out.html"
    ziel.write_text("VORGAENGER", encoding="utf-8")

    assert _lauf(quelle, "-x", '//div[@class="postmsg"]',
                 "-o", ziel) == anon_html.RC_ZIEL_DA
    assert ziel.read_text(encoding="utf-8") == "VORGAENGER"


def test_ah08_overwrite_laesst_es_zu(tmp_path):
    quelle = _schreibe(tmp_path / "h.html", _seite(BEITRAG))
    ziel = tmp_path / "h.out.html"
    ziel.write_text("VORGAENGER", encoding="utf-8")

    assert _lauf(quelle, "-x", '//div[@class="postmsg"]', "-o", ziel,
                 "--overwrite") == anon_html.RC_OK
    assert "VORGAENGER" not in ziel.read_text(encoding="utf-8")


# -----------------------------------------------------------------------------
# AH09-AH10 - Befund 3: die Kodierung wird angesagt, nicht geraten
# -----------------------------------------------------------------------------

def test_ah09_utf8_ohne_meta_charset(tmp_path):
    """
    AH09 - bis Build 686 raet lxml ohne '<meta charset>' und landet bei
    Latin-1. GEMESSEN: der gar nicht getroffene Absatz stand danach doppelt
    kodiert in der Ausgabe, und der Blindtext war 40 statt 25 Zeichen lang.

    Das Forum ist multilingual; ein von Hand herausgeschnittenes Fragment
    traegt regelmaessig keine Deklaration.
    """
    aussen = "Gr\u00fc\u00dfe aus K\u00f6ln"
    innen = "\u00dcberraschung \u041a\u043b\u0430\u0440\u043d\u0430\u043c\u0435"
    quelle = _schreibe(tmp_path / "i.html", _seite(
        '<p id="aussen">%s</p><div class="postmsg">%s</div>' % (aussen, innen),
        meta=False))
    ziel = tmp_path / "i.out.html"

    assert _lauf(quelle, "-x", '//div[@class="postmsg"]',
                 "-o", ziel) == anon_html.RC_OK

    ergebnis = ziel.read_text(encoding="utf-8")
    assert aussen in ergebnis, (
        "Nicht getroffener Text wurde beim Durchlauf beschaedigt.")
    # Laengentreue: so viele X wie Zeichen, Leerraum erhalten.
    erwartet = "".join(c if c.isspace() else "X" for c in innen)
    assert erwartet in ergebnis


def test_ah10_falsche_kodierung_bricht_ab(tmp_path):
    """
    AH10 - lieber gar kein Ergebnis als ein beschaedigtes. Ohne die strenge
    Vorabpruefung wuerde lxml ungueltige Bytes stillschweigend ersetzen.
    """
    quelle = _schreibe(tmp_path / "j.html",
                       _seite('<div class="postmsg">K\u00f6ln</div>'))
    ziel = tmp_path / "j.out.html"

    assert _lauf(quelle, "-x", '//div[@class="postmsg"]', "-o", ziel,
                 "--encoding", "ascii") == anon_html.RC_AUFRUF
    assert not ziel.exists()


# -----------------------------------------------------------------------------
# AH11 - Befund 4: der DOCTYPE
# -----------------------------------------------------------------------------

def test_ah11_doctype_wird_erhalten_aber_nicht_erfunden(tmp_path):
    """
    AH11 - beide Richtungen in einem Test, weil sie zusammengehoeren.

    Verlieren aendert den Darstellungsmodus des Browsers (Quirks) - dann ist
    die Gestalt der Seite nicht mehr beurteilbar, wofuer der laengentreue
    Blindtext gerade da ist. HINZUDICHTEN aendert ihn genauso: lxml haengt
    beim Serialisieren des Baums einen HTML-4.0-Transitional-DOCTYPE an,
    wenn die Eingabe keinen hatte (gemessen Build 687).
    """
    mit = _schreibe(tmp_path / "k1.html", _seite(BEITRAG, doctype=True))
    ohne = _schreibe(tmp_path / "k2.html", _seite(BEITRAG, doctype=False))
    z1, z2 = tmp_path / "k1.out.html", tmp_path / "k2.out.html"

    assert _lauf(mit, "-x", '//div[@class="postmsg"]',
                 "-o", z1) == anon_html.RC_OK
    assert _lauf(ohne, "-x", '//div[@class="postmsg"]',
                 "-o", z2) == anon_html.RC_OK

    assert z1.read_text(encoding="utf-8").lstrip().lower().startswith(
        "<!doctype html>")
    assert "<!doctype" not in z2.read_text(encoding="utf-8").lower()


# -----------------------------------------------------------------------------
# AH12-AH13 - Befund 5: Kommentare, Attribute, Nicht-Element-Treffer
# -----------------------------------------------------------------------------

def test_ah12_kommentar_geblendet_attribute_gemeldet(tmp_path, capsys):
    """
    AH12 - ein Kommentar im Teilbaum ist Inhalt und wird geblendet. Attribute
    bleiben ABSICHTLICH stehen ('class' und 'href' blind zu ueberschreiben
    zerstoert die Gestalt) - dann muessen sie aber benannt werden, sonst ist
    das Restrisiko verschwiegen.
    """
    quelle = _schreibe(tmp_path / "l.html", _seite(
        '<div class="postmsg" title="Klarname im Attribut">'
        '<a href="mailto:klar@example.com">Mail</a>'
        '<!-- Kommentar: Klarname --></div>'))
    ziel = tmp_path / "l.out.html"

    assert _lauf(quelle, "-x", '//div[@class="postmsg"]',
                 "-o", ziel) == anon_html.RC_OK

    ergebnis = ziel.read_text(encoding="utf-8")
    assert "Kommentar: Klarname" not in ergebnis
    assert "<!--" in ergebnis                       # Struktur erhalten
    assert 'title="Klarname im Attribut"' in ergebnis
    bericht = capsys.readouterr().err
    assert "attribute value(s)" in bericht
    assert "NOT anonymized" in bericht


def test_ah13_nicht_element_treffer_werden_benannt(tmp_path, capsys):
    """
    AH13 - '.../text()' liefert Zeichenketten, keine Elemente. Bis Build 686
    wurden sie STILLSCHWEIGEND verworfen; der Bediener bekam dieselbe Meldung
    wie bei einem Ausdruck, der ins Leere ging (Grundregel 1).
    """
    quelle = _schreibe(tmp_path / "m.html", _seite(BEITRAG))
    ziel = tmp_path / "m.out.html"

    rc = _lauf(quelle, "-x", '//div[@class="postmsg"]/text()', "-o", ziel)

    assert rc == anon_html.RC_KEIN_TREFFER
    assert not ziel.exists()
    bericht = capsys.readouterr().err
    assert "not an element" in bericht


# -----------------------------------------------------------------------------
# AH14 - die Gegenprobe
# -----------------------------------------------------------------------------

def test_ah14_gegenprobe_kann_scheitern_und_verhindert_die_datei(
        tmp_path, monkeypatch, capsys):
    """
    AH14 - DER WICHTIGSTE TEST DIESER DATEI.

    Eine Gegenprobe, die nicht scheitern KANN, ist keine Pruefung, sondern
    eine Beruhigung. Hier wird das Blenden absichtlich unvollstaendig
    gemacht (blind_text gibt den Text zurueck, statt ihn zu ersetzen) und
    gemessen, dass das Werkzeug das SELBST bemerkt.

    Erwartet: RC 3, keine Zieldatei, und die vorhandene Vorgaengerdatei
    unangetastet - der Trick mit der Nebendatei traegt genau hier.
    """
    quelle = _schreibe(tmp_path / "n.html", _seite(BEITRAG))
    ziel = tmp_path / "n.out.html"
    ziel.write_text("VORGAENGER", encoding="utf-8")

    monkeypatch.setattr(anon_html, "blind_text", lambda text: text)

    rc = _lauf(quelle, "-x", '//div[@class="postmsg"]', "-o", ziel,
               "--overwrite")

    assert rc == anon_html.RC_GEGENPROBE
    assert ziel.read_text(encoding="utf-8") == "VORGAENGER", (
        "Die Vorgaengerdatei wurde zerstoert, obwohl das Ergebnis die "
        "Gegenprobe nicht bestanden hat.")
    bericht = capsys.readouterr().err
    assert "verification pass FAILED" in bericht
    assert "still contains plain text" in bericht


def test_ah14b_gegenprobe_prueft_die_geschriebene_datei(tmp_path):
    """
    AH14b - die Probe laeuft gegen die DATEI, nicht gegen den Baum im
    Speicher. Zwischen beiden liegen Serialisierung und Kodierung, also
    genau die Schritte, an denen Befund 3 und 4 haengen.

    Belegt am Verhalten: der Lauf meldet, wie viele Teilbaeume er WIEDER
    EINGELESEN und geprueft hat, und diese Zahl stimmt mit der Zahl der
    Treffer ueberein.
    """
    quelle = _schreibe(tmp_path / "o.html", _seite(BEITRAG + NUR_KIND))
    ziel = tmp_path / "o.out.html"

    assert _lauf(quelle, "-x", '//div[@class="postmsg"]',
                 "-o", ziel) == anon_html.RC_OK

    roh = ziel.read_bytes()
    from lxml import html as _html
    baum = _html.fromstring(roh, parser=_html.HTMLParser(encoding="utf-8"))
    for elem in baum.xpath('//div[@class="postmsg"]'):
        assert not anon_html.pruefe_teilbaum(elem)


# -----------------------------------------------------------------------------
# AH15-AH16 - Trockenlauf und Aufraeumen
# -----------------------------------------------------------------------------

def test_ah15_trockenlauf_schreibt_nichts(tmp_path):
    quelle = _schreibe(tmp_path / "p.html", _seite(BEITRAG))
    ziel = tmp_path / "p.out.html"

    assert _lauf(quelle, "-x", '//div[@class="postmsg"]', "-o", ziel,
                 "--dry-run") == anon_html.RC_OK
    assert not ziel.exists()


def test_ah15b_trockenlauf_ohne_treffer_ist_auch_ein_befund(tmp_path):
    """
    AH15b - wer den Trockenlauf benutzt, prueft gerade seinen Ausdruck. Ihm
    dabei 0 zu melden, waere die Wiederholung von Befund 2 an der Stelle,
    an der er am meisten schadet.
    """
    quelle = _schreibe(tmp_path / "q.html", _seite(BEITRAG))
    assert _lauf(quelle, "-x", '//div[@class="nix"]',
                 "--dry-run") == anon_html.RC_KEIN_TREFFER


def test_ah16_keine_nebendatei_bleibt_liegen(tmp_path, monkeypatch):
    """
    AH16 - weder im Erfolgs- noch im Befundfall. Eine liegengebliebene
    '.anon-tmp-<pid>' waere eine Datei mit ungeklaertem Inhalt neben einer,
    die als geprueft gilt.
    """
    quelle = _schreibe(tmp_path / "r.html", _seite(BEITRAG))
    ziel = tmp_path / "r.out.html"

    assert _lauf(quelle, "-x", '//div[@class="postmsg"]',
                 "-o", ziel) == anon_html.RC_OK
    assert not list(tmp_path.glob("*.anon-tmp-*"))

    monkeypatch.setattr(anon_html, "blind_text", lambda text: text)
    assert _lauf(quelle, "-x", '//div[@class="postmsg"]', "-o", ziel,
                 "--overwrite") == anon_html.RC_GEGENPROBE
    assert not list(tmp_path.glob("*.anon-tmp-*"))


# -----------------------------------------------------------------------------
# Aufrufpruefungen - unveraendertes Verhalten, hier erstmals abgesichert
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("argv,erwartet", [
    ([], anon_html.RC_AUFRUF),                      # kein XPath
])
def test_ah17_aufruffehler(tmp_path, argv, erwartet):
    quelle = _schreibe(tmp_path / "s.html", _seite(BEITRAG))
    assert anon_html.main([str(quelle)] + argv) == erwartet


def test_ah17b_beide_xpath_quellen_zugleich(tmp_path):
    quelle = _schreibe(tmp_path / "t.html", _seite(BEITRAG))
    liste = tmp_path / "xp.txt"
    liste.write_text("//div\n", encoding="utf-8")
    assert _lauf(quelle, "-x", "//div", "-f", liste) == anon_html.RC_AUFRUF


def test_ah17c_leere_ausdrucksdatei_ist_ein_aufruffehler(tmp_path):
    """
    Eine leere Liste ist NICHT 'nichts getroffen': es wurde nicht gesucht.
    Die beiden auseinanderzuhalten ist der ganze Sinn der Rueckgabewerte.
    """
    quelle = _schreibe(tmp_path / "u.html", _seite(BEITRAG))
    liste = tmp_path / "leer.txt"
    liste.write_text("\n  \n", encoding="utf-8")
    assert _lauf(quelle, "-f", liste) == anon_html.RC_AUFRUF


def test_ah17d_ungueltiger_xpath(tmp_path):
    quelle = _schreibe(tmp_path / "v.html", _seite(BEITRAG))
    assert _lauf(quelle, "-x", "//div[") == anon_html.RC_AUFRUF


def test_ah18_zwei_ausdruecke_treffen_dasselbe_element_einmal(tmp_path,
                                                             capsys):
    """
    AH18 - ein Element, das zwei Ausdruecke treffen, wird EINMAL bearbeitet.
    Sonst zaehlte der Bericht doppelt, und die Zahl, an der der Bediener
    seine Erwartung prueft, waere wertlos.
    """
    quelle = _schreibe(tmp_path / "w.html", _seite(BEITRAG))
    liste = tmp_path / "xp.txt"
    liste.write_text('//div[@class="postmsg"]\n//div\n', encoding="utf-8")
    ziel = tmp_path / "w.out.html"

    assert _lauf(quelle, "-f", liste, "-o", ziel) == anon_html.RC_OK
    assert "Matched 1 element(s)" in capsys.readouterr().err
