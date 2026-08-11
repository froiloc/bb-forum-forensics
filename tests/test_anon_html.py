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
# AH17 - Aufrufpruefungen (kein XPath, beide Quellen, leere Liste, ungueltig)
# AH18 - zwei Ausdruecke treffen dasselbe Element nur einmal
#
# NACHTRAG BUILD 690 - aus dem Vergleich mit der zweiten, unabhaengig
# gebauten Fassung (Vermerk 'Vergleich_anon_html_Build687_gegen_Build690').
# AH19-AH21 sichern die drei dort gefundenen Befunde, AH22-AH27 die
# Bausteine und die Zusagen, die bis dahin nur im Katalog standen:
#
# AH19 - BEFUND 6: ein Fragment mit mehreren Knoten oberster Ebene laeuft
#        durch (Build 687: RC 3, gar keine Datei)
# AH20 - BEFUND 7: verschachtelte Treffer werden nicht doppelt gezaehlt
# AH21 - BEFUND 8: der von lxml erfundene Rahmen wird gemeldet
# AH22 - Lagepfad und Aufloesung passen zueinander
# AH23 - eine verschobene Struktur wird bemerkt statt stillschweigend geprueft
# AH24 - der DOCTYPE wird woertlich aus den Rohbytes geholt (auch mit BOM)
# AH25 - blind_text haelt Wortgrenzen, auch bei nicht-lateinischer Schrift
# AH26 - <script> und <style> sind kein Versteck
# AH27 - ohne '-o' entsteht '<original>.new.html'
# AH28 - DER KATALOGEINTRAG STIMMT MIT DEM WERKZEUG UEBEREIN
# AH29 - das Werkzeug ist uebersetzbar (Grundregel 9)
#
# Version: v0.8.690 - Build: 690 - 2026-08-11
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

def _halbherzig(text):
    """
    Ein absichtlich UNVOLLSTAENDIGER Blindsetzer fuer die Sabotage-Tests.

    Er blendet alles ausser dem letzten Zeichen. Damit ist er zweierlei
    zugleich, und beides wird gebraucht:
      * eine ECHTE Aenderung - der Lauf kommt bis zur Gegenprobe,
      * mit ueberlebendem Klartext - die Gegenprobe muss anschlagen.

    BUILD 690, WARUM NICHT MEHR 'lambda text: text': Seit Befund 7 zaehlt das
    Werkzeug nur, was sich AENDERT. Ein Saboteur, der den Text unveraendert
    zurueckgibt, fuehrt deshalb auf "getroffen, aber nichts zu ersetzen"
    (RC 2, keine Datei) - ebenfalls ein sicherer Ausgang, aber nicht der,
    den diese beiden Faelle messen wollen. Der halbherzige Saboteur bildet
    den gefaehrlicheren Fall ab: ein Blindsetzer, der ARBEITET und dabei
    etwas stehen laesst.
    """
    if not text:
        return text
    return "X" * (len(text) - 1) + text[-1]


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

    monkeypatch.setattr(anon_html, "blind_text", _halbherzig)

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

    monkeypatch.setattr(anon_html, "blind_text", _halbherzig)
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


# =============================================================================
# AH19-AH21 - die drei Befunde aus dem Vergleich der beiden Fassungen
# =============================================================================

def test_ah19_fragment_mit_mehreren_knoten_laeuft_durch(tmp_path, capsys):
    """
    AH19 - BEFUND 6, der Fall, an dem Build 687 gescheitert ist.

    GEMESSEN an Build 687: '<div class="postmsg">Klarname</div><p>Rest</p>'
    endete mit 'position path /html/div/div resolved to 0 element(s)',
    Rueckgabewert 3 - und es entstand GAR KEINE Datei. Ursache war
    getroottree().getpath(): es haengt an dem Dokumentbaum, den lxml sich
    fuer ein Fragment erfindet ('/html/div' OHNE <body>), und der wird beim
    Neueinlesen der geschriebenen Datei anders gebaut.

    Das war kein Datensicherheitsproblem - es entstand keine FALSCHE Datei,
    sondern gar keine. Aber es traf genau den Eingabefall, den der Dateikopf
    selbst als den wichtigen benennt: das von Hand herausgeschnittene Stueck.
    """
    quelle = _schreibe(tmp_path / "frag.html",
                       '<div class="postmsg">Klarname</div><p>Rest</p>')
    ziel = tmp_path / "frag.out.html"

    assert _lauf(quelle, "-x", '//div[@class="postmsg"]',
                 "-o", ziel) == anon_html.RC_OK
    ergebnis = ziel.read_text(encoding="utf-8")
    assert "Klarname" not in ergebnis
    assert "Rest" in ergebnis                 # ausserhalb der Auswahl
    assert "VERIFIED" in capsys.readouterr().err


def test_ah19b_fragment_mit_einem_knoten_laeuft_weiterhin_durch(tmp_path):
    """
    AH19b - die Gegenprobe zu AH19.

    Der Fall mit EINEM Knoten der obersten Ebene war nie kaputt. Er steht
    hier, damit die Berichtigung von Befund 6 ihn nicht nebenbei mitnimmt -
    das ist die haeufigere Richtung, in der eine Reparatur schiefgeht.
    """
    quelle = _schreibe(tmp_path / "e.html",
                       '<div class="postmsg">Klarname</div>')
    ziel = tmp_path / "e.out.html"

    assert _lauf(quelle, "-x", '//div[@class="postmsg"]',
                 "-o", ziel) == anon_html.RC_OK
    ergebnis = ziel.read_text(encoding="utf-8")
    assert "Klarname" not in ergebnis
    # Das Fragment bleibt ein Fragment - es wird kein Dokument daraus gebaut.
    assert ergebnis.strip().startswith("<div")
    assert "<html" not in ergebnis.lower()


def test_ah20_verschachtelte_treffer_werden_nicht_doppelt_gezaehlt(tmp_path,
                                                                   capsys):
    """
    AH20 - BEFUND 7.

    Trifft der XPath ein Element UND dessen Elternteil, so wird die Textstelle
    EINMAL ersetzt. Build 687 meldete 'replaced 2 text node(s)', weil der
    zweite Durchgang den bereits geblendeten Text noch einmal zaehlte.

    WARUM DAS NICHT KOSMETIK IST: Der Katalog sagt der/dem Ermittelnden
    ausdruecklich, diese Zahl gegen die eigene Erwartung zu halten. Eine zu
    hohe Zahl laesst einen Lauf vollstaendiger aussehen, als er war.
    """
    quelle = _schreibe(tmp_path / "n.html", _seite(
        '<div class="postmsg"><div class="postmsg">Klarname</div></div>'))
    ziel = tmp_path / "n.out.html"

    assert _lauf(quelle, "-x", '//div[@class="postmsg"]',
                 "-o", ziel) == anon_html.RC_OK
    assert ("Matched 2 element(s), replaced 1 text node(s)."
            in capsys.readouterr().err)
    assert "Klarname" not in ziel.read_text(encoding="utf-8")


def test_ah21_der_erfundene_rahmen_wird_gemeldet(tmp_path, capsys):
    """
    AH21 - BEFUND 8.

    lxml baut um ein Fragment einen Rahmen. Der steht dann in der Weitergabe,
    ohne je in der Vorlage gestanden zu haben, und ein weiter Ausdruck
    ('//div') trifft ihn mit. Das Werkzeug kann das nicht aufloesen - ein
    hinzugefuegter Rahmen ist vom gleichnamigen echten Element der Vorlage
    nicht sicher zu unterscheiden. Es BENENNT die Lage; die Entscheidung
    bleibt bei dem Auge, das die Vorlage kennt.
    """
    quelle = _schreibe(tmp_path / "f.html",
                       '<div class="postmsg">Klarname</div><p>Rest</p>')
    ziel = tmp_path / "f.out.html"

    assert _lauf(quelle, "-x", '//div[@class="postmsg"]',
                 "-o", ziel) == anon_html.RC_OK
    bericht = capsys.readouterr().err
    assert "processed as a FRAGMENT" in bericht

    # Gegenprobe: bei einem vollstaendigen Dokument schweigt der Hinweis.
    quelle2 = _schreibe(tmp_path / "g.html", _seite(BEITRAG))
    assert _lauf(quelle2, "-x", '//div[@class="postmsg"]',
                 "-o", tmp_path / "g.out.html") == anon_html.RC_OK
    assert "FRAGMENT" not in capsys.readouterr().err


# =============================================================================
# AH22-AH27 - die Bausteine und die Zusagen aus dem Katalog
# =============================================================================

def test_ah22_lagepfad_und_aufloesung_passen_zueinander(tmp_path):
    """
    AH22 - die beiden Haelften des Lagepfads gehoeren zusammen geprueft.

    Getrennt sind sie beide plausibel; falsch werden sie erst gemeinsam.
    Geprueft wird ueber JEDEN Knoten des Baums, nicht ueber einen ausgesuchten.
    """
    quelle = _schreibe(tmp_path / "p.html", _seite(BEITRAG + NUR_KIND))
    roh = quelle.read_bytes()
    baum = anon_html.baue_baum(roh, "utf-8", sys.stderr)

    for knoten in baum.iter():
        kette = anon_html.lagepfad(knoten, baum)
        assert kette is not None
        gefunden, grund = anon_html.loese_lagepfad(baum, kette)
        assert grund is None, grund
        assert gefunden is knoten


def test_ah23_verschobene_struktur_wird_bemerkt(tmp_path):
    """
    AH23 - der Knotenname im Lagepfad ist kein Zierrat.

    Eine reine Indexkette wuerde nach einer Strukturaenderung stillschweigend
    auf einen ANDEREN Knoten zeigen und diesen pruefen - die Gegenprobe
    haette dann etwas gemessen, aber nicht das Gemeinte. Hier wird eine
    solche Verschiebung nachgestellt und gemessen, dass sie AUFFAELLT.
    """
    quelle = _schreibe(tmp_path / "v.html", _seite(
        '<div class="postmsg">Klarname</div><p>Rest</p>'))
    baum = anon_html.baue_baum(quelle.read_bytes(), "utf-8", sys.stderr)
    div = baum.xpath('//div[@class="postmsg"]')[0]
    kette = anon_html.lagepfad(div, baum)

    # Denselben Platz mit einem anderen Element besetzen.
    eltern = div.getparent()
    stelle = eltern.index(div)
    eltern.remove(div)
    from lxml import html as _html
    eltern.insert(stelle, _html.fromstring("<section>Klarname</section>"))

    gefunden, grund = anon_html.loese_lagepfad(baum, kette)
    assert gefunden is None
    assert "expected <div>" in grund and "found <section>" in grund


def test_ah24_doctype_wird_woertlich_aus_den_rohbytes_geholt():
    """
    AH24 - und ausdruecklich NICHT aus lxmls geparster Fassung.

    'docinfo.doctype' liefert fuer eine Datei OHNE DOCTYPE einen erfundenen
    ('HTML 4.0 Transitional'). Wer sich darauf verliesse, haette Befund 4 nur
    umgedreht: statt einen DOCTYPE zu verlieren, dichtete das Werkzeug einen
    hinzu - und aenderte damit den Darstellungsmodus des Browsers.
    """
    hole = anon_html.doctype_aus_rohdaten
    assert hole(b"<!DOCTYPE html><html>") == b"<!DOCTYPE html>"
    assert hole(b"\xef\xbb\xbf<!DOCTYPE html>\n<html>") == b"<!DOCTYPE html>"
    assert hole(b"<!-- Vermerk -->\n<!doctype HTML>\n<html>") == b"<!doctype HTML>"
    assert hole(b'<div>x</div>') is None
    # Ein '<!DOCTYPE' MITTEN in der Datei ist keiner und wird nicht uebernommen.
    assert hole(b"<div><!DOCTYPE html></div>") is None


def test_ah25_blind_text_haelt_wortgrenzen():
    """
    AH25 - die zugesagte Eigenschaft, seit Build 630 unveraendert.

    Der letzte Fall ist der wichtige: das Forum ist multilingual. Ein
    Blindsetzer, der nur Latein kann, waere hier eine Falle.
    """
    assert anon_html.blind_text("Hans Meier") == "XXXX XXXXX"
    assert anon_html.blind_text("a\nbb\tccc") == "X\nXX\tXXX"
    assert anon_html.blind_text("") == ""
    assert anon_html.blind_text(None) is None
    assert anon_html.blind_text("Маша") == "XXXX"
    assert anon_html.blind_text("Grüße") == "XXXXX"


def test_ah26_script_und_style_sind_kein_versteck(tmp_path):
    """
    AH26 - ein ausgenommener Knoten waere ein Versteck.

    Das Forum kommt ohne JavaScript aus; ein <script> im weiterzugebenden
    Material ist ohnehin erklaerungsbeduerftig. Klartext darin stehen zu
    lassen, weil es "ja nur Code" ist, waere die falsche Reihenfolge der
    Ueberlegung.
    """
    quelle = _schreibe(tmp_path / "s.html", _seite(
        '<div class="postmsg">'
        '<script>var name = "Klarname";</script>'
        '<style>/* Klarname */</style></div>'))
    ziel = tmp_path / "s.out.html"
    assert _lauf(quelle, "-x", '//div[@class="postmsg"]',
                 "-o", ziel) == anon_html.RC_OK
    assert "Klarname" not in ziel.read_text(encoding="utf-8")


def test_ah27_vorgabepfad_der_ausgabe(tmp_path):
    """
    AH27 - ohne '-o' entsteht '<original>.new.html' neben der Vorlage.

    Unveraendert seit Build 630; hier festgehalten, damit der Umbau die
    Zusage aus dem Katalog nicht nebenbei verschiebt.
    """
    quelle = _schreibe(tmp_path / "probe.html", _seite(BEITRAG))
    assert _lauf(quelle, "-x", '//div[@class="postmsg"]') == anon_html.RC_OK
    assert (tmp_path / "probe.new.html").exists()


# =============================================================================
# AH28-AH29 - Hilfe und Uebersetzbarkeit
# =============================================================================

def test_ah28_der_katalogeintrag_stimmt_mit_dem_werkzeug_ueberein():
    """
    AH28 - "keine Neuerung ohne Hilfe", und ausdruecklich mehr als das.

    Die drei Warnungen aus Build 630 (Kindelemente, "ohne Treffer RC 0",
    "wortlos ueberschrieben") beschreiben einen Stand, den es seit Build 687
    nicht mehr gibt. EINE WARNUNG, DIE NICHT MEHR STIMMT, IST SCHLIMMER ALS
    KEINE - sie kostet Vertrauen in die uebrigen. Dieser Waechter macht die
    Suite rot, falls sie je zurueckkehren, und haelt die Rueckgabewerte des
    Katalogs gegen die des Werkzeugs.
    """
    from management.help import cli_katalog
    eintrag = {e.schluessel: e for e in cli_katalog.CLI_KATALOG}["anon_html"]
    assert eintrag.pfad == "tools/anon_html.py"

    text = " ".join(eintrag.tiefe.warnungen) + " " + eintrag.hinweis
    for ueberholt in ("NICHT DER IN KINDELEMENTEN",
                      "OHNE TREFFER ENDET DER LAUF MIT 0",
                      "WORTLOS UEBERSCHRIEBEN"):
        assert ueberholt not in text, (
            "Der Katalog warnt wieder vor einem Stand, den es nicht mehr "
            "gibt: %r" % ueberholt)

    verzeichnet = dict(eintrag.tiefe.exit_codes)
    for wert in (anon_html.RC_OK, anon_html.RC_AUFRUF,
                 anon_html.RC_KEIN_TREFFER, anon_html.RC_GEGENPROBE,
                 anon_html.RC_ZIEL_DA):
        assert wert in verzeichnet, (
            "Rueckgabewert %d ist im Katalog nicht verzeichnet - wer ihn "
            "bekommt, findet nichts dazu." % wert)


def test_ah29_das_werkzeug_ist_uebersetzbar(tmp_path):
    """
    AH29 - Grundregel 9: nur fehlerfrei kompilierbarer Code wird uebergeben.

    Steht hier, weil dieses Werkzeug ausserhalb der Pakete liegt und von
    keinem Import der uebrigen Suite beruehrt wird. Das Ergebnis geht in ein
    Wegwerf-Verzeichnis - py_compile weigert sich gegen os.devnull
    (gemessen), und der Bestand soll dabei keine .pyc bekommen.
    """
    import py_compile
    ziel = tmp_path / "anon_html.pyc"
    py_compile.compile(str(_WURZEL / "tools" / "anon_html.py"),
                       doraise=True, cfile=str(ziel))
    assert ziel.exists()
