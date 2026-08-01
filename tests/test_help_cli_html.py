# =============================================================================
# tests/test_help_cli_html.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H19)
# =============================================================================
# Testsuite fuer Build 621: die Betriebskapitel der Vollhilfe.
#
# WAS HIER GEPRUEFT WIRD - und in welcher Trennung:
#   Der Renderer sieht die ungefilterten Daten nie; er bekommt eine bereits
#   gefilterte Gliederung. Diese Suite prueft deshalb dreierlei GETRENNT:
#   die Sperre (baue_betriebsgliederung), die Vollzaehligkeit (kein Werkzeug
#   faellt hinten runter) und die Darstellung (HTML, Maskierung, Marken).
#
# CH01 - ohne 'ops.view' ist der Betriebsteil LEER: keine Gruppe, kein
#        Verzeichnis, kein Kapitel, kein Suchindex-Eintrag (E1, streng)
# CH02 - mit 'ops.view' erscheint JEDES Werkzeug des Katalogs, in der
#        Gruppenreihenfolge der Konsole
# CH03 - verify_betriebsteil_vollzaehlig schlaegt an, wenn ein Werkzeug fehlt
#        oder eines zuviel dasteht
# CH04 - eine Gruppe ausserhalb von GRUPPEN_REIHENFOLGE wird ANGEHAENGT und
#        nicht verschluckt (Grundregel 1)
# CH05 - Sprungmarken: 'cli-<kennung>' bzw. 'cli-<kennung>-<anker>', und die
#        Kapitelmarke steht wirklich als id im HTML
# CH06 - jedes Kapitel traegt die Kennzeichnung als Betriebskapitel und die
#        Rechtelage 'ops.view' (Regel H-2, Kennzeichnungspflicht)
# CH07 - Pflichtabschnitte stehen IMMER, auch wenn der Katalog nichts fuehrt
# CH08 - ein Werkzeug ohne gefahrenen Beispielaufruf sagt das im Kapitel UND
#        im Verzeichnis - es sieht nicht aus wie ein fertiges
# CH09 - ein Eintrag ganz ohne Tiefe bekommt den Abschnitt 'Ausarbeitung'
# CH10 - Maskierung: '<', '&' und '"' aus Katalogtexten landen escaped
# CH11 - Unterbefehle stehen als Tabelle mit eigener Spalte fuer die Art
# CH12 - Beispiele nennen den Pruefnachweis AM Beispiel
# CH13 - Blaetterleiste: erstes Werkzeug ohne Rueckweg, letztes ohne Weiter;
#        die Kette bleibt im Betriebsteil
# CH14 - Verzeichnis ist markup-gleich mit dem der Sichtkapitel, damit
#        help.js ohne Aenderung mitfiltert
# CH15 - Suchindex: ein Eintrag je Werkzeug, Form wie render_html.suchindex,
#        und jede id hat ein Kapitel mit derselben id
# CH16 - verify_abschnitte_vollstaendig haelt Gliederung und Inhalt zusammen
# CH17 - der Vorspann benennt den Adressatenwechsel und die Zahl der
#        Werkzeuge ohne Beispiellauf
# CH18 - GEGENPROBE ZUM DRIFT: Kennung, Titel, Zweck, Aufruf, Dateipfad und
#        jeder Unterbefehl jedes Katalogeintrags kommen im HTML wirklich vor
#
# Version: v0.8.621 - Build: 621 - 2026-08-01
# =============================================================================

import html
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.help.cli_html import (                      # noqa: E402
    ABSCHNITTE, BETRIEBSMARKE, CLI_RECHT, KAPITEL_PRAEFIX,
    OHNE_BEISPIEL_MARKE, PFLICHTABSCHNITTE, Betriebsgliederung, CliHtmlError,
    abschnitt_id, baue_betriebsgliederung, kapitel_alle_html, kapitel_html,
    kapitel_id, suchindex, verify_abschnitte_vollstaendig,
    verify_betriebsteil_vollzaehlig, verzeichnis_html, vorspann_html,
)
from management.help.cli_katalog import (                   # noqa: E402
    CLI_KATALOG, GRUPPEN_REIHENFOLGE, eintrag, fehlliste_cli_beispiele,
)
from management.help.cli_modell import (                    # noqa: E402
    CliBefehl, CliBeispiel, CliEintrag, CliTiefe,
)

MIT_RECHT = (CLI_RECHT,)
OHNE_RECHT = ("dashboard.view", "reports.approve")


def _gliederung():
    return baue_betriebsgliederung(MIT_RECHT)


def _kunst(schluessel="probe_admin", **kw):
    """Ein Wegwerf-Eintrag. Nicht aus dem Katalog - sonst pruefte der Test
    gegen sich selbst veraenderliche Daten."""
    vorgabe = dict(
        pfad="tools/%s.py" % schluessel,
        aufruf="python tools/%s.py --json" % schluessel,
        titel="Probe",
        gruppe="Diagnose",
        zweck="Ein Wegwerf-Eintrag fuer die Pruefung.",
        art="lesend",
        betrieb="Der Betrieb darf weiterlaufen.",
    )
    vorgabe.update(kw)
    return CliEintrag(schluessel=schluessel, **vorgabe)


# --- CH01 ---------------------------------------------------------------------

def test_ch01_ohne_recht_ist_der_betriebsteil_leer():
    """
    E1 in der strengen Lesart: nicht ausgegraut, nicht angedeutet - leer.
    Eine Ueberschrift ohne Inhalt waere selbst schon eine Auskunft darueber,
    dass es hier etwas gibt, das man nicht sehen darf.
    """
    g = baue_betriebsgliederung(OHNE_RECHT)
    assert g.leer()
    assert g.gruppen == ()
    assert g.eintraege() == ()
    assert verzeichnis_html(g) == ""
    assert kapitel_alle_html(g) == ""
    assert vorspann_html(g) == ""
    assert suchindex(g) == []


def test_ch01b_leere_capabilities_sperren_ebenfalls():
    assert baue_betriebsgliederung(()).leer()
    assert baue_betriebsgliederung([]).leer()


# --- CH02 ---------------------------------------------------------------------

def test_ch02_mit_recht_erscheint_jedes_werkzeug():
    g = _gliederung()
    assert not g.leer()
    gezeigt = [e.schluessel for e in g.eintraege()]
    assert sorted(gezeigt) == sorted(e.schluessel for e in CLI_KATALOG)
    assert len(gezeigt) == len(set(gezeigt)), "ein Werkzeug doppelt gefuehrt"


def test_ch02b_gruppenfolge_ist_die_der_konsole():
    """
    Dieselbe Ordnung wie 'python tools/hilfe.py liste'. Wer beide Ausgaben
    nebeneinanderlegt, soll nicht zweimal suchen muessen.
    """
    g = _gliederung()
    gezeigt = [name for name, _ in g.gruppen]
    erwartet = [name for name in GRUPPEN_REIHENFOLGE
                if any(e.gruppe == name for e in CLI_KATALOG)]
    assert gezeigt == erwartet


# --- CH03 ---------------------------------------------------------------------

def test_ch03_vollzaehligkeit_schlaegt_bei_luecke_an():
    voll = _gliederung()
    verify_betriebsteil_vollzaehlig(voll)          # der Auslieferungsstand

    name, eintraege = voll.gruppen[0]
    beschnitten = Betriebsgliederung(
        ((name, eintraege[1:]),) + voll.gruppen[1:])
    with pytest.raises(CliHtmlError) as exc:
        verify_betriebsteil_vollzaehlig(beschnitten)
    assert eintraege[0].schluessel in str(exc.value)


def test_ch03b_vollzaehligkeit_schlaegt_bei_waisenkapitel_an():
    voll = _gliederung()
    name, eintraege = voll.gruppen[0]
    zuviel = Betriebsgliederung(
        ((name, eintraege + (_kunst("gibt_es_nicht"),)),) + voll.gruppen[1:])
    with pytest.raises(CliHtmlError) as exc:
        verify_betriebsteil_vollzaehlig(zuviel)
    assert "gibt_es_nicht" in str(exc.value)


def test_ch03c_leerer_teil_ist_kein_vollzaehligkeitsfehler():
    """Ohne Recht ist der Teil leer - das ist die Sperre und kein Befund."""
    verify_betriebsteil_vollzaehlig(baue_betriebsgliederung(OHNE_RECHT))


# --- CH04 ---------------------------------------------------------------------

def test_ch04_fremde_gruppe_wird_angehaengt_nicht_verschluckt():
    fremd = _kunst("fremdling", gruppe="Nicht im Katalog")
    g = baue_betriebsgliederung(MIT_RECHT, katalog=(CLI_KATALOG[0], fremd))
    namen = [n for n, _ in g.gruppen]
    assert "Nicht im Katalog" in namen
    assert namen[-1] == "Nicht im Katalog", "fremde Gruppe gehoert ans Ende"
    assert "fremdling" in [e.schluessel for e in g.eintraege()]


# --- CH05 ---------------------------------------------------------------------

def test_ch05_sprungmarken_haben_eine_stelle():
    assert kapitel_id("backup_admin") == "cli-backup_admin"
    assert abschnitt_id("backup_admin", "zweck") == "cli-backup_admin-zweck"
    assert kapitel_id("x").startswith(KAPITEL_PRAEFIX + "-")


def test_ch05b_marken_stehen_wirklich_im_html():
    e = eintrag("backup_admin")
    doc = kapitel_html(e)
    assert 'id="cli-backup_admin"' in doc
    for anker in PFLICHTABSCHNITTE:
        assert 'id="cli-backup_admin-%s"' % anker in doc


def test_ch05c_marken_kollidieren_nicht_mit_sichten():
    """
    Der Praefix trennt die Namensraeume. Keine Kapitelmarke des
    Betriebsteils darf einer Sicht-ID gleichen - sonst spraenge ein Verweis
    aus der Kontexthilfe ins falsche Kapitel.
    """
    from management.help.sicht_katalog import SICHT_KATALOG
    sicht_ids = {s.id for s in SICHT_KATALOG}
    for e in CLI_KATALOG:
        assert kapitel_id(e.schluessel) not in sicht_ids


# --- CH06 ---------------------------------------------------------------------

def test_ch06_jedes_kapitel_ist_als_betriebskapitel_gekennzeichnet():
    """
    Regel H-2 erlaubt die Betriebssprache - unter der Bedingung, dass die
    Kapitel als Betriebskapitel gekennzeichnet sind (rules-help.md). Diese
    Bedingung wird hier fuer JEDES Kapitel geprueft und nicht stichprobenhaft.
    """
    g = _gliederung()
    for e in g.eintraege():
        doc = kapitel_html(e)
        assert BETRIEBSMARKE in doc, e.schluessel
        assert "aiw-h-betrieb" in doc, e.schluessel
        assert CLI_RECHT in doc, e.schluessel
        assert "aiw-h-recht" in doc, e.schluessel


# --- CH07 ---------------------------------------------------------------------

def test_ch07_pflichtabschnitte_stehen_immer():
    """
    Ein Werkzeug ohne Datenbanken, ohne Unterbefehle, ohne Hinweis und ohne
    Tiefe - die Pflichtabschnitte stehen trotzdem, mit einer Aussage darin.
    """
    doc = kapitel_html(_kunst("karg"))
    for anker in PFLICHTABSCHNITTE:
        assert 'id="cli-karg-%s"' % anker in doc, anker
    assert "Keine Datenbank wird geoeffnet." in doc
    assert "Schreibt keine Belege" in doc


def test_ch07b_leere_kuerabschnitte_entfallen():
    """
    Rueckgabewerte und Warnungen sind keine Pflicht: ohne Inhalt erscheint
    keine leere Ueberschrift. Der Unterschied zu 'beispiele' ist Absicht -
    dort IST das Fehlen die Auskunft.
    """
    doc = kapitel_html(_kunst("karg"))
    assert 'id="cli-karg-rueckgabewerte"' not in doc
    assert 'id="cli-karg-zu_beachten"' not in doc
    assert 'id="cli-karg-beispiele"' in doc


# --- CH08 ---------------------------------------------------------------------

def test_ch08_ohne_beispiellauf_wird_gesagt_und_nicht_verschwiegen():
    ohne = fehlliste_cli_beispiele()
    assert ohne, "Erwartung dieses Builds: es gibt solche Werkzeuge"
    for schluessel in ohne:
        doc = kapitel_html(eintrag(schluessel))
        assert 'id="cli-%s-beispiele"' % schluessel in doc
        assert "aiw-h-offen" in doc, schluessel
        assert "kein Beispielaufruf" in doc, schluessel


def test_ch08b_verzeichnis_markiert_die_werkzeuge_ohne_beispiellauf():
    doc = verzeichnis_html(_gliederung())
    ohne = fehlliste_cli_beispiele()
    assert doc.count(OHNE_BEISPIEL_MARKE) == len(ohne)
    for schluessel in ohne:
        # Die Marke steht in demselben Listenpunkt wie die Kennung.
        muster = (r'<li data-sicht="cli-%s">.*?%s.*?</li>'
                  % (re.escape(schluessel), re.escape(OHNE_BEISPIEL_MARKE)))
        assert re.search(muster, doc, re.S), schluessel


def test_ch08c_werkzeuge_mit_beispiel_tragen_die_marke_nicht():
    doc = verzeichnis_html(_gliederung())
    mit = [e for e in CLI_KATALOG if e.hat_beispiele()]
    assert mit
    treffer = re.search(r'<li data-sicht="cli-%s">(.*?)</li>'
                        % re.escape(mit[0].schluessel), doc, re.S)
    assert treffer is not None
    assert OHNE_BEISPIEL_MARKE not in treffer.group(1)


# --- CH09 ---------------------------------------------------------------------

def test_ch09_eintrag_ohne_tiefe_bekommt_den_ausarbeitungsabschnitt():
    """
    Seit Build 620 trifft das keinen Eintrag des Auslieferungskatalogs mehr.
    Der Zustand bleibt trotzdem geprueft: ein NEU aufgenommenes Werkzeug
    faengt genau hier an und darf dann nicht wie ein fertiges aussehen.
    """
    doc = kapitel_html(_kunst("frischling"))
    assert 'id="cli-frischling-ausarbeitung"' in doc
    assert "noch nicht erfasst" in doc


def test_ch09b_eintrag_mit_tiefe_bekommt_ihn_nicht():
    e = _kunst("gereift", tiefe=CliTiefe(exit_codes=((0, "fertig"),)))
    doc = kapitel_html(e)
    assert 'id="cli-gereift-ausarbeitung"' not in doc
    assert 'id="cli-gereift-rueckgabewerte"' in doc


# --- CH10 ---------------------------------------------------------------------

def test_ch10_maskierung():
    """
    Der Katalog ist hausgeschriebener Text - trotzdem laeuft jeder Wert durch
    html.escape(). Dieselbe Disziplin wie in render_html.py, und aus
    demselben Grund: die Hilfe wird druckbar ausgeliefert und soll auch dann
    stimmen, wenn jemand '<' oder '&' schreibt.
    """
    e = _kunst(
        "spitz",
        titel='Titel mit <b> & "Zitat"',
        zweck="Zweck mit <script>alert(1)</script> & Kaufmanns-Und.",
        aufruf="python tools/spitz.py --filter '<alles>'",
        betrieb="Nur bei <Wartung> & Stillstand.",
        hinweis='Ein "Hinweis" mit <spitzen> Klammern.',
        datenbanken=("<keine> & keine",),
        befehle=(CliBefehl(name="<lauf>", art="lesend",
                           zweck="Zweck mit <Klammern> & Und."),),
        art="gemischt",
        tiefe=CliTiefe(
            beispiele=(CliBeispiel(aufruf="tool --x '<y>'",
                                   wirkung="Gibt <nichts> aus.",
                                   geprueft="Build 621 & Handarbeit"),),
            exit_codes=((1, "Befund <gefunden>"),),
            warnungen=("Achtung: <alles> & jedes.",)),
    )
    doc = kapitel_html(e)
    assert "<script>" not in doc
    assert "&lt;script&gt;" in doc
    assert "<b>" not in doc, "roher Auszeichnungscode aus dem Katalogtext"
    assert "&amp;" in doc
    assert "&quot;" in doc
    # Gegenprobe: das erzeugte Markup selbst ist noch da.
    assert '<article class="aiw-h-kapitel aiw-h-betrieb"' in doc


def test_ch10b_maskierung_auch_im_verzeichnis_und_index():
    e = _kunst("spitz2", titel="<b>", zweck="A & B")
    g = baue_betriebsgliederung(MIT_RECHT, katalog=(e,))
    assert "<b>" not in verzeichnis_html(g)
    # Der Index ist Nutzlast fuer JSON, nicht fuer HTML - dort steht der
    # Rohtext, und das ist richtig so: die Maskierung passiert erst beim
    # Einbetten (render_html._index_html).
    assert "a & b" in suchindex(g)[0]["worte"]


# --- CH11 ---------------------------------------------------------------------

def test_ch11_unterbefehle_als_tabelle_mit_eigener_spalte_fuer_die_art():
    e = eintrag("backup_admin")
    assert e.befehle
    doc = kapitel_html(e)
    assert "<table" in doc and "<th>Unterbefehl</th>" in doc
    for b in e.befehle:
        assert html.escape(b.name or "", quote=True) in doc
        erwartet = "schreibend" if b.art == "schreibend" else "lesend"
        assert "aiw-h-cli-art-%s" % erwartet in doc


# --- CH12 ---------------------------------------------------------------------

def test_ch12_beispiele_nennen_den_nachweis_am_beispiel():
    """
    Der Nachweis steht AM Beispiel und nicht in einer Fussnote - die
    Begruendung steht im Kopf von cli_modell.CliBeispiel.
    """
    mit = [e for e in CLI_KATALOG if e.hat_beispiele()]
    assert mit
    for e in mit[:12]:
        doc = kapitel_html(e)
        for bsp in e.tiefe.beispiele:
            assert html.escape(bsp.aufruf, quote=True) in doc, e.schluessel
            assert html.escape(bsp.geprueft, quote=True) in doc, e.schluessel
        assert "aiw-h-cli-nachweis" in doc


# --- CH13 ---------------------------------------------------------------------

def test_ch13_blaetterleiste_am_rand():
    g = _gliederung()
    eintraege = g.eintraege()
    erst = kapitel_html(eintraege[0], vorher=None, nachher=eintraege[1])
    letzt = kapitel_html(eintraege[-1], vorher=eintraege[-2], nachher=None)
    assert "aiw-h-vor" not in erst and "aiw-h-zurueck" in erst
    assert "aiw-h-vor" in letzt and "aiw-h-zurueck" not in letzt


def test_ch13b_die_kette_bleibt_im_betriebsteil():
    """
    Jeder Blaetterverweis des Betriebsteils zeigt auf eine 'cli-'-Marke. Ein
    Verweis in die Sichtkapitel wuerde die Adressatengrenze verwischen, die
    der Betriebshinweis gerade zieht.
    """
    doc = kapitel_alle_html(_gliederung())
    for ziel in re.findall(r'class="aiw-h-(?:vor|zurueck)" href="#([^"]+)"',
                           doc):
        assert ziel.startswith(KAPITEL_PRAEFIX + "-"), ziel


# --- CH14 ---------------------------------------------------------------------

def test_ch14_verzeichnis_ist_markupgleich_mit_dem_der_sichtkapitel():
    """
    help.js filtert ueber 'li[data-sicht]', 'ul[data-gruppe]' und
    'h3[data-gruppe]'. Sind diese drei Formen gleich, filtert die vorhandene
    Suche den Betriebsteil mit - ohne eine Zeile JavaScript.
    """
    doc = verzeichnis_html(_gliederung())
    assert doc.count('<li data-sicht="') == len(CLI_KATALOG)
    gruppen = re.findall(r'<ul data-gruppe="([^"]+)"', doc)
    ueber = re.findall(r'<h3 data-gruppe="([^"]+)"', doc)
    assert gruppen == ueber, "zu jeder Liste gehoert genau eine Ueberschrift"
    assert len(gruppen) == len(set(gruppen)), "Gruppenmarke doppelt"
    for marke in gruppen:
        assert marke.startswith(BETRIEBSMARKE), marke


def test_ch14b_jeder_verzeichniseintrag_verweist_auf_sein_kapitel():
    g = _gliederung()
    verzeichnis = verzeichnis_html(g)
    kapitel = kapitel_alle_html(g)
    for marke in re.findall(r'<li data-sicht="([^"]+)"', verzeichnis):
        assert 'href="#%s"' % marke in verzeichnis, marke
        assert 'id="%s"' % marke in kapitel, marke


# --- CH15 ---------------------------------------------------------------------

def test_ch15_suchindex_form_und_umfang():
    g = _gliederung()
    idx = suchindex(g)
    assert len(idx) == len(CLI_KATALOG)
    for e in idx:
        assert set(e) == {"id", "label", "gruppe", "offen", "worte"}
        assert e["id"].startswith(KAPITEL_PRAEFIX + "-")
        assert e["worte"] == e["worte"].lower()
        assert isinstance(e["offen"], bool)


def test_ch15b_jede_index_id_hat_ein_kapitel():
    g = _gliederung()
    kapitel = kapitel_alle_html(g)
    for e in suchindex(g):
        assert 'id="%s"' % e["id"] in kapitel, e["id"]


def test_ch15c_index_findet_kennung_und_unterbefehl():
    g = _gliederung()
    nach_id = {e["id"]: e for e in suchindex(g)}
    e = nach_id["cli-backup_admin"]
    assert "backup_admin" in e["worte"]
    assert "sicherung" in e["worte"]
    for b in eintrag("backup_admin").befehle:
        assert b.name.lower() in e["worte"]


def test_ch15d_index_und_sichtindex_haben_dieselbe_form():
    """
    Beide Indizes landen in EINEM JSON-Block, den help.js liest. Wichen die
    Schluessel voneinander ab, waere die eine Haelfte still unauffindbar.
    """
    from management.help.modell import (
        Abschnitt, HilfeRegister, PFLICHT_ANKER, PFLICHT_TITEL, Sichthilfe,
    )
    from management.help.render_html import baue_gliederung
    from management.help.render_html import suchindex as sicht_suchindex

    reg = HilfeRegister((Sichthilfe(
        sicht="dashboard", titel="Ueberblick",
        recht_klartext="Recht: dashboard.view",
        abschnitte=tuple(Abschnitt(a, PFLICHT_TITEL[a], ("Text.",))
                         for a in PFLICHT_ANKER),
        kontext=(), stand=621),))
    sicht = sicht_suchindex(baue_gliederung(reg, ["dashboard.view"]))
    assert sicht, "Vorbedingung: der Sichtindex ist nicht leer"
    assert set(sicht[0]) == set(suchindex(_gliederung())[0])


def test_ch15e_ohne_recht_ist_auch_nichts_durchsuchbar():
    """E1 gilt fuer die Suche genauso wie fuer das Verzeichnis."""
    assert suchindex(baue_betriebsgliederung(OHNE_RECHT)) == []


# --- CH16 ---------------------------------------------------------------------

def test_ch16_abschnitte_und_inhalt_decken_sich():
    verify_abschnitte_vollstaendig()
    assert set(PFLICHTABSCHNITTE) <= {a for a, _ in ABSCHNITTE}


# --- CH17 ---------------------------------------------------------------------

def test_ch17_vorspann_benennt_adressatenwechsel_und_luecken():
    g = _gliederung()
    doc = vorspann_html(g)
    assert "Betriebsseite" in doc
    assert str(len(CLI_KATALOG)) in doc
    ohne = g.ohne_beispiele()
    assert ohne, "Erwartung dieses Builds"
    assert str(len(ohne)) in doc
    for schluessel in ohne:
        assert schluessel in doc, schluessel


def test_ch17b_vorspann_ist_kein_verzeichniseintrag():
    """
    Er erklaert die Ueberschrift, unter der die Kapitel stehen - er ist
    keines. Ein Listenpunkt ohne Index-Eintrag waere von help.js dauerhaft
    ausgeblendet worden.
    """
    verzeichnis = verzeichnis_html(_gliederung())
    assert "vorspann" not in verzeichnis


# --- CH18 ---------------------------------------------------------------------

def test_ch18_gegenprobe_kein_katalogfeld_faellt_unter_den_tisch():
    """
    DIE WICHTIGSTE PRUEFUNG DIESER SUITE. Sie geht den Katalog Feld fuer Feld
    durch und verlangt, dass jede Angabe im HTML wirklich vorkommt. Ohne sie
    koennte ein Renderer ein Feld stillschweigend weglassen, und niemandem
    fiele es auf - im Handbuch sieht ein fehlender Absatz aus wie keiner
    (Grundregel 1).
    """
    doc = kapitel_alle_html(_gliederung())

    def drin(text):
        return html.escape(text, quote=True) in doc

    fehlend = []
    for e in CLI_KATALOG:
        for feld, wert in (("schluessel", e.schluessel), ("titel", e.titel),
                           ("zweck", e.zweck), ("aufruf", e.aufruf),
                           ("pfad", e.pfad), ("betrieb", e.betrieb)):
            if not drin(wert):
                fehlend.append("%s.%s" % (e.schluessel, feld))
        if e.hinweis and not drin(e.hinweis):
            fehlend.append("%s.hinweis" % e.schluessel)
        if e.ausgabe and not drin(e.ausgabe):
            fehlend.append("%s.ausgabe" % e.schluessel)
        for d in e.datenbanken:
            if not drin(d):
                fehlend.append("%s.datenbank(%s)" % (e.schluessel, d))
        for b in e.befehle:
            if not drin(b.zweck):
                fehlend.append("%s.befehl(%s)" % (e.schluessel, b.name))
    assert not fehlend, "nicht ausgegeben: %s" % ", ".join(fehlend)


def test_ch18b_gegenprobe_tiefeninhalte():
    doc = kapitel_alle_html(_gliederung())
    fehlend = []
    for e in CLI_KATALOG:
        t = e.tiefe
        if t is None:
            continue
        for bsp in t.beispiele:
            for wert in (bsp.aufruf, bsp.wirkung, bsp.geprueft):
                if html.escape(wert, quote=True) not in doc:
                    fehlend.append("%s.beispiel" % e.schluessel)
        for _, bedeutung in t.exit_codes:
            if html.escape(bedeutung, quote=True) not in doc:
                fehlend.append("%s.exit" % e.schluessel)
        for w in t.warnungen:
            if html.escape(w, quote=True) not in doc:
                fehlend.append("%s.warnung" % e.schluessel)
    assert not fehlend, "nicht ausgegeben: %s" % ", ".join(sorted(set(fehlend)))
