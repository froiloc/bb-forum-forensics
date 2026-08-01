# =============================================================================
# tests/test_help_cli_katalog.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H15)
# =============================================================================
# Testsuite fuer Build 606: der CLI-Katalog und sein Abgleich mit dem Bestand.
#
# WAS DIESE SUITE LEISTET - UND WAS SIE NICHT KANN:
#   Sie erzwingt VOLLZAEHLIGKEIT: kein Werkzeug ohne Katalogeintrag, kein
#   Katalogeintrag ohne Werkzeug. Damit kann ein kuenftig hinzukommendes
#   Werkzeug nicht mehr unbemerkt liegen bleiben - der Bau bricht, bis es
#   einen Eintrag hat.
#   Sie kann NICHT pruefen, ob die INHALTE eines Eintrags stimmen. Ob ein
#   Werkzeug wirklich nur liest, steht in seinem Quelltext und wurde beim
#   Verfassen dort geprueft; ein Test, der das nachrechnen wollte, muesste
#   den Code interpretieren. Die inhaltliche Sicherung ist und bleibt die
#   Vier-Augen-Lesung.
#
# CK01 - der Katalog ist in sich stimmig (Kennungen, Pfade, Gruppen)
# CK02 - VOLLZAEHLIGKEIT in beide Richtungen (der Kernfall)
# CK03 - die Scan-Regel ist ehrlich: sie findet die Werkzeuge, die es gibt
# CK04 - 'art' und die Unterbefehle widersprechen einander nicht
# CK05 - wer eine BEWEISMITTEL-Datenbank schreibt, traegt einen Hinweis
# CK06 - jeder Eintrag nennt eine Betriebsvoraussetzung
# CK07 - die Fehlliste der Tiefe ist abgeleitet und schrumpft nur
#
# Version: v0.8.606 - Build: 606 - 2026-07-31
# =============================================================================

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.help.cli_katalog import (                # noqa: E402
    CLI_KATALOG, CliKatalogError, eintrag, eintrag_zu_pfad,
    fehlliste_cli_beispiele, fehlliste_cli_tiefe, gruppen, suche,
    verify_cli_abgedeckt,
    verify_katalog_konsistent,
)

WURZEL = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STAND = os.path.join(os.path.dirname(__file__), "hilfe_fehlliste_stand.json")


# -----------------------------------------------------------------------------
# DIE SCAN-REGEL. Sie steht hier und nirgends sonst, damit sie EINE Fassung
# hat und man sie lesen kann, ohne sie zu suchen.
#
# WAS ALS WERKZEUG GILT:
#   * management/**/*_admin.py und management/**/*_cli.py - die
#     Verwaltungswerkzeuge der Fachbereiche,
#   * management/*.py - die Einzelskripte unmittelbar im Paket
#     (Migrationen, Reparaturen, Statusabfragen),
#   * tools/*.py - die Betriebs- und Diagnosewerkzeuge,
#   * *.py im Wurzelverzeichnis - die Startskripte.
#
# WAS AUSDRUECKLICH NICHT ALS WERKZEUG GILT (benannt, nicht stillschweigend
# uebergangen - Grundregel 1):
#   * __init__.py - Paketkennung, kein Werkzeug.
# -----------------------------------------------------------------------------

AUSGENOMMEN = {
    "management/__init__.py": "Paketkennung, kein Werkzeug",
}

# -----------------------------------------------------------------------------
# UNGEKLAERTE DATEIEN (Build 607, Befund aus dem Regressionslauf von mc).
#
# WAS PASSIERT IST: Der Vollzaehligkeitstest hat in der Anlage eine Datei
# gefunden, die es im Paket nicht gibt - 'anon_html.py'. Er hat damit genau
# das getan, wofuer er gebaut wurde. Nur war die Folge unbrauchbar: der
# gesamte Regressionslauf stand still wegen EINER Datei, deren Einordnung
# schlicht noch offen ist.
#
# DIE LOESUNG IST DIESELBE WIE BEI DEN HILFETEXTEN: eine ausdrueckliche,
# namentliche Fehlliste statt einer stillen Ausnahme. Wer hier steht, ist
# NICHT eingeordnet - er ist nur nicht mehr blockierend. Ein Test erzwingt,
# dass die Liste nur schrumpft; bis zum Abschluss der Baustelle (H22) MUSS
# sie leer sein.
#
# WAS ZU TUN IST, damit ein Eintrag hier verschwindet - eines von dreien:
#   (a) Die Datei ist ein Werkzeug -> Eintrag in cli_katalog.py.
#   (b) Die Datei gehoert nicht zum Bestand (oertliche Handreichung,
#       Wegwerfskript) -> nach AUSGENOMMEN mit Begruendung, oder loeschen.
#   (c) Die Datei gehoert ins Paket, fehlt dort aber -> einchecken.
# -----------------------------------------------------------------------------

UNGEKLAERT = {
    "anon_html.py": (
        "Liegt in der Anlage, ist im Paket nicht vorhanden (kein Eintrag in "
        "der Versionsverwaltung, Stand Build 606). Der Name legt ein "
        "Werkzeug zur Unverfaenglichmachung von HTML nahe - das waere ein "
        "Werkzeug mit Katalogeintrag. Geklaert wird das anhand des "
        "Dateikopfes; siehe Issue 'anon_html.py ohne Katalogeintrag'."
    ),
}


def _dateien():
    """Alle Werkzeugdateien nach der oben beschriebenen Regel."""
    treffer = set()

    for wurzel, _verz, dateien in os.walk(os.path.join(WURZEL, "management")):
        for name in dateien:
            if not name.endswith(".py"):
                continue
            voll = os.path.join(wurzel, name)
            rel = os.path.relpath(voll, WURZEL).replace("\\", "/")
            tief = rel.count("/") > 1
            if tief and not (name.endswith("_admin.py")
                             or name.endswith("_cli.py")):
                continue
            treffer.add(rel)

    for verz in ("tools",):
        pfad = os.path.join(WURZEL, verz)
        if os.path.isdir(pfad):
            for name in sorted(os.listdir(pfad)):
                if name.endswith(".py"):
                    treffer.add("%s/%s" % (verz, name))

    for name in sorted(os.listdir(WURZEL)):
        if name.endswith(".py") and os.path.isfile(os.path.join(WURZEL, name)):
            treffer.add(name)

    return {r for r in treffer
            if r not in AUSGENOMMEN and r not in UNGEKLAERT}


def _dateien_roh():
    """
    Wie _dateien(), aber OHNE die ungeklaerten herauszunehmen. Nur fuer den
    Test, der die Fehlliste selbst prueft - sonst koennte sie nie schrumpfen,
    weil niemand mehr hinsieht.
    """
    treffer = _dateien()
    for name in UNGEKLAERT:
        if os.path.exists(os.path.join(WURZEL, name)):
            treffer.add(name)
    return treffer


# --- CK01 ---------------------------------------------------------------------

def test_ck01_katalog_in_sich_stimmig():
    verify_katalog_konsistent()
    assert len(CLI_KATALOG) > 50, "Der Katalog ist verdaechtig klein."
    # Die Zugriffswege liefern dasselbe wie die Liste.
    for e in CLI_KATALOG:
        assert eintrag(e.schluessel) is e
        assert eintrag_zu_pfad(e.pfad) is e
    assert eintrag("gibt-es-nicht") is None
    assert eintrag_zu_pfad("tools/gibt_es_nicht.py") is None


# --- CK02: der Kernfall -------------------------------------------------------

def test_ck02_vollzaehligkeit_in_beide_richtungen():
    """
    Kein Werkzeug ohne Eintrag, kein Eintrag ohne Werkzeug.

    Das ist der eigentliche Zweck dieses Katalogs: Ein Werkzeug, von dem
    niemand weiss, ist im Betrieb dasselbe wie keines - nur gefaehrlicher,
    weil es trotzdem laufen kann.
    """
    verify_cli_abgedeckt(_dateien())


def test_ck02b_fehlende_datei_faellt_auf():
    """Die Gegenprobe: ein erfundener Bestand bricht die Pruefung."""
    with pytest.raises(CliKatalogError) as exc:
        verify_cli_abgedeckt(list(_dateien()) + ["tools/neu_und_unbekannt.py"])
    assert "OHNE Katalogeintrag" in str(exc.value)

    # BEFUND mc 2026-07-31 (Build 606): Die erste Fassung liess hier
    # schlicht "das erste Element" der sortierten Liste weg. Das setzte
    # voraus, dass die gefundene Menge GENAU dem Katalog entspricht. In der
    # Anlage lag zusaetzlich 'anon_html.py' - alphabetisch vor allem
    # anderen. Weggelassen wurde also die ueberzaehlige Datei, und der Rest
    # war stimmig: der Test meldete "DID NOT RAISE".
    #
    # Ein Test, der von der Umgebung abhaengt, ist kein Test. Deshalb wird
    # jetzt ein NAMENTLICH bekannter Katalogeintrag weggelassen.
    fehlt = "management/rbac/rbac_admin.py"
    assert fehlt in _dateien(), (
        "Die Probe setzt voraus, dass %s im Bestand liegt." % fehlt)
    zu_wenig = sorted(p for p in _dateien() if p != fehlt)
    with pytest.raises(CliKatalogError) as exc2:
        verify_cli_abgedeckt(zu_wenig)
    assert "OHNE Datei im Bestand" in str(exc2.value)
    assert fehlt in str(exc2.value)


# --- CK03 ---------------------------------------------------------------------

def test_ck03_scanregel_findet_die_bekannten_werkzeuge():
    """
    Die Scan-Regel selbst ist pruefbar: sie muss die Werkzeuge finden, von
    denen wir mit Sicherheit wissen, dass es sie gibt. Eine Regel, die zu
    eng greift, macht die Vollzaehligkeitspruefung wertlos - sie waere dann
    gruen, weil sie nichts sieht.
    """
    gefunden = _dateien()
    for pflicht in ("management/rbac/rbac_admin.py",
                    "management/search/index_cli.py",
                    "management/migrate.py",
                    "tools/maintenance.py",
                    "run_tests.py"):
        assert pflicht in gefunden, "Scan-Regel findet %s nicht" % pflicht
    # Und sie nimmt die Paketkennung ausdruecklich aus.
    assert "management/__init__.py" not in gefunden
    for pfad in AUSGENOMMEN:
        assert os.path.exists(os.path.join(WURZEL, pfad)), (
            "Die Ausnahmeliste nennt %s, aber die Datei gibt es nicht mehr - "
            "eine veraltete Ausnahme ist eine Luecke." % pfad)


# --- CK04 ---------------------------------------------------------------------

def test_ck04_art_und_unterbefehle_widersprechen_sich_nicht():
    """
    'gemischt' heisst: es gibt lesende UND schreibende Unterbefehle.
    'lesend' heisst: KEIN Unterbefehl schreibt.
    Ein Widerspruch hier waere die schlimmste Sorte Fehler in diesem
    Katalog - jemand liest 'lesend' und fuehrt eine Aenderung aus.
    """
    fehler = []
    for e in CLI_KATALOG:
        arten = {b.art for b in e.befehle}
        if e.art == "gemischt" and arten != {"lesend", "schreibend"}:
            fehler.append("%s: 'gemischt', aber Unterbefehle sind %s"
                          % (e.schluessel, sorted(arten) or "keine"))
        if e.art == "lesend" and "schreibend" in arten:
            fehler.append("%s: als 'lesend' gefuehrt, hat aber einen "
                          "schreibenden Unterbefehl" % e.schluessel)
        if e.art == "schreibend" and "lesend" in arten:
            fehler.append("%s: als 'schreibend' gefuehrt, hat aber einen "
                          "rein lesenden Unterbefehl - dann ist es "
                          "'gemischt'" % e.schluessel)
    assert not fehler, "\n  ".join([""] + fehler)


# --- CK05 ---------------------------------------------------------------------

def test_ck05_schreiben_an_beweismitteln_traegt_einen_hinweis():
    """
    Wer eine evidence-, forensic- oder assets-Datenbank SCHREIBEND anfasst,
    beruehrt den Migrationsvorbehalt. Ein solcher Eintrag ohne ausdrueckliche
    Einordnung waere eine stille Einladung.
    """
    # JE ZEILE pruefen, nicht ueber den ganzen Eintrag hinweg. Die erste
    # Fassung fasste alle Datenbankangaben zu einem Text zusammen und hielt
    # deshalb 'promotion_admin' faelschlich fuer gefaehrlich: dort steht
    # 'coordinator.db (schreibend)' in der einen Zeile und 'Verzeichnisse der
    # Fall-Datenbanken werden nur abgezaehlt' in der anderen. Zusammengefasst
    # ergab das 'Fall-Datenbanken ... schreibend'. Ein Test, der so misst,
    # meldet Falsches - und ein Test, der Falsches meldet, wird abgeschaltet.
    ohne = []
    for e in CLI_KATALOG:
        if not e.schreibt():
            continue
        gefaehrlich = False
        for zeile in e.datenbanken:
            beweismittel = ("evidence_" in zeile or "forensic_" in zeile
                            or "assets_" in zeile
                            or "Fall-Datenbanken" in zeile)
            if beweismittel and "schreibend" in zeile:
                gefaehrlich = True
        if gefaehrlich and not e.hinweis.strip():
            ohne.append(e.schluessel)
    assert not ohne, (
        "Werkzeuge, die an Beweismitteldatenbanken schreiben, aber keinen "
        "Hinweis tragen: %s" % ", ".join(sorted(ohne)))


# --- CK06 ---------------------------------------------------------------------

def test_ck06_jeder_eintrag_nennt_die_betriebsvoraussetzung():
    """
    'Darf die Anlage dabei weiterlaufen?' ist die Frage, die vor jedem
    Aufruf zaehlt. Sie darf in keinem Eintrag offenbleiben - auch nicht
    dadurch, dass sie unbeantwortet WIRKT: wo der Bestand nichts hergibt,
    sagt der Eintrag genau das.
    """
    leer = [e.schluessel for e in CLI_KATALOG if not e.betrieb.strip()]
    assert not leer, "Eintraege ohne Betriebsvoraussetzung: %s" % leer


# --- CK07 ---------------------------------------------------------------------

def test_ck07_fehlliste_tiefe_ist_abgeleitet_und_schrumpft():
    """
    Die Fehlliste der Tiefeninhalte wird gerechnet, nicht gepflegt - und sie
    darf gegenueber dem eingecheckten Stand nur schrumpfen.

    ERSTBEFUELLUNG (Build 606): Bis hierher stand in der Standdatei eine
    LEERE Liste. Das hiess nicht 'alle Werkzeuge sind ausgearbeitet', sondern
    'es wurde noch keines gefuehrt' - eine stille Unwahrheit, die mit diesem
    Build endet. Der Vergleich beginnt deshalb mit dem heutigen, vollen
    Stand; von hier an kann er nur besser werden.
    """
    with open(STAND, encoding="utf-8") as fh:
        stand = json.load(fh)
    eingecheckt = set(stand.get("cli_ohne_tiefe", []))
    aktuell = set(fehlliste_cli_tiefe())

    # BUILD 620 - DAS ZIEL IST ERREICHT, und der Test musste es lernen.
    # Bis hierher hat er verlangt, dass die eingecheckte Liste NICHT leer ist:
    # bis Build 606 hiess eine leere Liste 'es wurde noch keines gefuehrt' und
    # war damit eine stille Unwahrheit. Seit H18 abgeschlossen ist, heisst sie
    # das Gegenteil - JEDES Werkzeug ist ausgearbeitet.
    #
    # Unterschieden wird am STANDBUILD. Der Schrumpfvergleich darunter bleibt
    # unveraendert in Kraft: eine spaeter wieder wachsende Liste faellt
    # weiterhin auf, und genau dafuer ist er da.
    if stand.get("stand_build", 0) < 620:
        assert eingecheckt, (
            "Die eingecheckte CLI-Fehlliste ist leer. Bis Build 619 hiesse "
            "das, dass sie nie gefuehrt wurde.")
    else:
        assert not aktuell, (
            "Der Stand ist ab Build 620 eingecheckt, aber es gibt wieder "
            "Werkzeuge ohne Tiefeninhalt: %s" % ", ".join(sorted(aktuell)))

    neu = sorted(aktuell - eingecheckt)
    assert not neu, (
        "Die CLI-Fehlliste ist GEWACHSEN um: %s. Entweder ist ein Werkzeug "
        "ohne Tiefeninhalt hinzugekommen, oder ein Tiefeninhalt ist "
        "verlorengegangen." % ", ".join(neu))


# --- Zugaben ------------------------------------------------------------------

def test_ck08_gruppen_und_suche():
    """Die beiden Wege in den Katalog liefern Brauchbares."""
    g = gruppen()
    assert g, "Keine Gruppen"
    summe = sum(len(eintraege) for _name, eintraege in g)
    assert summe == len(CLI_KATALOG), (
        "Nicht jeder Eintrag ist einer Gruppe zugeordnet: %d von %d"
        % (summe, len(CLI_KATALOG)))

    assert any(e.schluessel == "rbac_admin" for e in suche("rechte"))
    assert any(e.schluessel == "backup_admin" for e in suche("sicherung"))
    assert suche("") == ()
    assert suche("voellig-unbekannter-begriff") == ()


# --- CK09 ---------------------------------------------------------------------

def test_ck09_ungeklaerte_dateien_sind_benannt_und_schrumpfen():
    """
    Die Fehlliste der ungeklaerten Dateien ist ehrlich und wird kleiner.

    Sie darf existieren - eine offene Einordnung ist ein normaler
    Zwischenstand. Sie darf nur nicht STILL sein: jeder Eintrag traegt eine
    Begruendung, und ein Eintrag, dessen Datei es gar nicht mehr gibt, ist
    ein veralteter Freibrief und faellt hier auf.
    """
    # WARUM HIER NICHT AUF EXISTENZ GEPRUEFT WIRD: Der Anlass dieser Liste
    # ist gerade eine Datei, die in der ANLAGE liegt und im PAKET fehlt. Sie
    # ist also je nach Installation da oder nicht. Eine Existenzpruefung
    # waere in der einen Umgebung gruen und in der anderen rot - und damit
    # kein Test, sondern ein Wuerfel.
    #
    # Was stattdessen erzwungen wird: jeder Eintrag traegt eine Begruendung
    # UND einen Verweis auf den Vorgang, unter dem er geklaert wird. Ohne
    # diesen Verweis waere die Liste ein Ablageort fuer Vergessenes.
    for name, grund in UNGEKLAERT.items():
        assert grund.strip(), (
            "%s steht ohne Begruendung auf der Liste der ungeklaerten "
            "Dateien. Eine Ausnahme ohne Grund ist eine Luecke." % name)
        assert "Issue" in grund, (
            "%s steht auf der Liste der ungeklaerten Dateien, ohne einen "
            "Vorgang zu nennen, unter dem die Klaerung laeuft. Ohne diesen "
            "Verweis wird die Liste zum Ablageort fuer Vergessenes." % name)

    # Die ungeklaerten sind AUSSERHALB des Katalogs - sonst waeren sie ja
    # geklaert, und der Eintrag hier waere eine Doppelfuehrung.
    doppelt = sorted(set(UNGEKLAERT) & set(_dateien()))
    assert not doppelt, (
        "Diese Dateien stehen als ungeklaert UND werden vom Scan gefunden: "
        "%s" % ", ".join(doppelt))


def test_ck10_der_scan_sieht_die_ungeklaerten_weiterhin():
    """
    Gegenprobe: die ungeklaerten Dateien verschwinden nicht aus der Welt,
    sie sind nur nicht blockierend. Wer sie mitzaehlt, bekommt weiterhin
    den Befund - das ist der Beweis, dass hier nichts stillgelegt wurde.
    """
    vorhanden = [n for n in UNGEKLAERT
                 if os.path.exists(os.path.join(WURZEL, n))]
    if not vorhanden:
        pytest.skip("Keine ungeklaerte Datei im Bestand - nichts zu zeigen.")
    with pytest.raises(CliKatalogError) as exc:
        verify_cli_abgedeckt(_dateien_roh())
    for name in vorhanden:
        assert name in str(exc.value)


# --- CK11 ---------------------------------------------------------------------

def test_ck11_fehlliste_beispiele_schrumpft_nur():
    """
    Die zweite Fehlliste: Werkzeuge ohne GEPRUEFTE Beispielaufrufe.

    Sie ist die teurere von beiden. Exit-Codes und Warnungen kann man am
    Quelltext belegen; ein Beispiel muss gefahren werden. Ohne diese Liste
    saehe ein Eintrag mit Exit-Codes fertig aus, obwohl der Nachweis fehlt.
    """
    with open(STAND, encoding="utf-8") as fh:
        stand = json.load(fh)
    eingecheckt = set(stand.get("cli_ohne_beispiele", []))
    assert eingecheckt, (
        "Die eingecheckte Liste 'cli_ohne_beispiele' ist leer. Ab Build 609 "
        "wird sie gefuehrt; leer hiesse, jedes Werkzeug haette ein "
        "geprueftes Beispiel.")
    neu = sorted(set(fehlliste_cli_beispiele()) - eingecheckt)
    assert not neu, (
        "Die Beispiel-Fehlliste ist GEWACHSEN um: %s." % ", ".join(neu))


def test_ck12_jedes_beispiel_traegt_seinen_nachweis():
    """
    Ein Beispiel ohne Nachweis, dass es gelaufen ist, gehoert nicht in den
    Katalog (Grundregel 9, sinngemaess). Das Modell erzwingt ein nichtleeres
    Feld; hier wird zusaetzlich verlangt, dass der Nachweis eine Buildnummer
    ODER ein Datum nennt - 'geprueft: ja' waere keiner.
    """
    import re as _re
    duenn = []
    for e in CLI_KATALOG:
        if not e.hat_beispiele():
            continue
        for bsp in e.tiefe.beispiele:
            if not _re.search(r"(Build\s*\d{3}|\d{4}-\d{2}-\d{2})",
                              bsp.geprueft):
                duenn.append("%s: %s" % (e.schluessel, bsp.geprueft[:60]))
    assert not duenn, (
        "Beispiele, deren Nachweis weder Build noch Datum nennt:\n  "
        + "\n  ".join(duenn))


def test_ck13_kein_beispiel_ohne_wirkung():
    """Ein Beispiel ohne die erwartete Wirkung laesst offen, ob es klappte."""
    for e in CLI_KATALOG:
        if not e.hat_beispiele():
            continue
        for bsp in e.tiefe.beispiele:
            assert len(bsp.wirkung.split()) >= 4, (
                "%s: Wirkung zu knapp: %r" % (e.schluessel, bsp.wirkung))
