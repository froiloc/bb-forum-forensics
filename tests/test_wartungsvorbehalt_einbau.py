# =============================================================================
# tests/test_wartungsvorbehalt_einbau.py
# IT-Forensisches Ermittlungswerkzeug - Wartungsvorbehalt (Build 612/615)
# =============================================================================
# Prueft, dass JEDES Werkzeug der Stufe A den Wartungsvorbehalt tatsaechlich
# aufruft - und dass er wirkt.
#
# WARUM ES DIESEN TEST BRAUCHT, obwohl der Einbau doch gerade gemacht wurde:
#   Ein Bauteil, das nur an einer Handvoll Stellen aufgerufen wird, verschwindet beim
#   naechsten Umbau still. Kein Fehler, keine Meldung - es faellt nur eine
#   Zeile weg, und die Sicherung ist weg. Genau das ist der Grund, aus dem
#   der Vorbehalt ueberhaupt gebaut wurde: was man sich merken muss, vergisst
#   man. Dieser Test erinnert sich statt unser.
#
# ZWEI EBENEN, weil eine allein nicht traegt:
#   EB01-EB05  AM QUELLTEXT: der Aufruf steht da, und sein Ergebnis wird
#              ausgewertet. Das faengt den Fall "jemand hat die Zeile
#              geloescht" - auch dann, wenn es fuer das Werkzeug gerade
#              keinen ausfuehrbaren Testaufbau gibt.
#   EB06-EB11  AM VERHALTEN: das Werkzeug wird mit einer BELEGTEN Datei
#              aufgerufen und muss 3 zurueckgeben, ohne etwas anzufassen.
#              Das faengt den Fall "der Aufruf steht da, wirkt aber nicht"
#              - etwa weil er hinter dem scharfen Lauf gelandet ist.
#
# Eine Quelltextpruefung allein waere Buchstabenzaehlerei, eine
# Verhaltenspruefung allein liesse die Werkzeuge ungedeckt, fuer die ein
# vollstaendiger Aufbau (migration.db, Katalog, Sicherungsverzeichnis) mehr
# Gestell als Aussage waere. Zusammen decken sie beide Richtungen ab.
#
# BUILD 615: convert_journal_mode ist nachtraeglich aufgenommen worden. Es war
# in der Analyse K1-K8 nicht dabei, weil sein Dateikopf die Frage schon zu
# beantworten schien - eine Zusage im Kommentar ist aber keine Sperre. mc hat
# das am 2026-07-31 angestossen ("das benoetigt den Wartungsmodus, sonst kann
# die Aenderung nicht zurueckgeschrieben werden").
#
# BUILD 686: Die Stufenlisten sind nach maintenance/wartungsstufen.py
# umgezogen (Begruendung unten), EB04 prueft den AUFRUF statt des WORTES,
# und die Abgrenzung deckt jetzt alle 26 Nicht-A-Werkzeuge statt einem.
#
# Version: v0.8.686 - Build: 686 - 2026-08-05
# =============================================================================

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

_WURZEL = Path(__file__).resolve().parent.parent
if str(_WURZEL) not in sys.path:
    sys.path.insert(0, str(_WURZEL))

from maintenance.paths import MaintenancePaths            # noqa: E402
from maintenance.wartungsvorbehalt import (               # noqa: E402
    RUECKGABE_VORBEHALT, datenwurzel,
)


# -----------------------------------------------------------------------------
# DIE LISTE DER STUFE-A-WERKZEUGE - SEIT BUILD 686 NICHT MEHR HIER.
#
# Sie stand bis Build 680 an dieser Stelle, mit der Begruendung: "Sie steht
# hier und nirgends sonst, damit sie EINE Fassung hat." DIESE BEGRUENDUNG
# BLEIBT RICHTIG - die eine Fassung ist nur umgezogen, nach
# maintenance/wartungsstufen.py.
#
# DER GRUND FUER DEN UMZUG: Ab Build 686 wird die Liste von zweierlei
# gebraucht - von diesem Einbautest UND vom Vollstaendigkeitswaechter
# (tests/test_wartungsstufen_vollstaendig.py), der prueft, ob ueberhaupt
# jedes schreibende Werkzeug eingestuft ist. Eine Liste, die in einer
# Testdatei wohnt, ist fuer den zweiten Abnehmer nur erreichbar, indem ein
# Test einen anderen Test importiert. Betriebswissen gehoert nicht in eine
# Testdatei.
#
# WS05 haelt fest, dass hier wirklich DIESELBE Abbildung benutzt wird und
# nicht wieder eine zweite entsteht.
#
# WER DAZUKOMMT, kommt nicht in eine Fehlliste: er wird eingebaut. Eine
# Fehlliste waere hier das falsche Mittel - sie ist gut fuer Inhalte, die noch
# entstehen muessen, und schlecht fuer eine Sicherung, die entweder greift
# oder nicht.
# -----------------------------------------------------------------------------

from maintenance.wartungsstufen import (                   # noqa: E402
    WERKZEUGE_A as STUFE_A, WERKZEUGE_B, WERKZEUGE_C,
)

#: Die Abgrenzung: Werkzeuge, die ausdruecklich NICHT Stufe A sind.
#:
#: BIS BUILD 680 stand hier EIN Eintrag (index_cli). Seit Build 686 sind es
#: alle 26 - Stufe B und Stufe C zusammen. Das ist kein Zuwachs an Arbeit,
#: sondern das Ergebnis der Vollstaendigkeitspruefung: die 26 gab es vorher
#: auch schon, sie waren nur nicht beurteilt.
NICHT_STUFE_A = dict(WERKZEUGE_B)
NICHT_STUFE_A.update(WERKZEUGE_C)


def _quelle(relpfad: str) -> str:
    return (_WURZEL / relpfad).read_text(encoding="utf-8")


def _lade(relpfad: str, name: str):
    """Ein Werkzeug als Modul laden (Muster aus test_maintenance_cli.py)."""
    spec = importlib.util.spec_from_file_location(name, _WURZEL / relpfad)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _db(pfad: Path) -> Path:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(pfad))
    con.execute("CREATE TABLE IF NOT EXISTS t (a INTEGER)")
    con.commit()
    con.close()
    return pfad


class _Halter:
    """Haelt eine exklusive Sperre auf einer Datei - der belegte Zustand."""

    def __init__(self, pfad: Path):
        self._con = sqlite3.connect(str(pfad))

    def __enter__(self):
        self._con.execute("BEGIN EXCLUSIVE")
        return self

    def __exit__(self, *_a):
        self._con.rollback()
        self._con.close()
        return False


@pytest.fixture
def anlage(tmp_path):
    """Ein Wegwerf-Datenverzeichnis mit _maintenance und leeren Datenbanken."""
    d = tmp_path / "data"
    MaintenancePaths(d).verzeichnisse_anlegen()
    return d


# -----------------------------------------------------------------------------
# EB01-EB05 - am Quelltext
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("relpfad", sorted(STUFE_A))
def test_eb01_stufe_a_ruft_den_vorbehalt(relpfad):
    """
    EB01 - Jedes Stufe-A-Werkzeug importiert das Bauteil und ruft es auf.
    """
    quelle = _quelle(relpfad)
    assert "from maintenance.wartungsvorbehalt import" in quelle, (
        "%s (%s) importiert den Wartungsvorbehalt nicht."
        % (relpfad, STUFE_A[relpfad]))
    assert "wartungsvorbehalt(" in quelle, (
        "%s importiert das Bauteil, ruft es aber nicht auf." % relpfad)


@pytest.mark.parametrize("relpfad", sorted(STUFE_A))
def test_eb02_das_ergebnis_wird_ausgewertet(relpfad):
    """
    EB02 - Der Rueckgabewert wird nicht nur geholt, sondern befolgt.

    Ein Aufruf ohne Auswertung waere die teuerste Form von Sicherheit: sie
    kostet Rechenzeit und Bildschirm und verhindert nichts.
    """
    quelle = _quelle(relpfad)
    assert "not befund.erlaubt" in quelle, (
        "%s wertet 'befund.erlaubt' nicht aus." % relpfad)
    assert "return befund.rueckgabewert" in quelle, (
        "%s reicht 'befund.rueckgabewert' nicht nach aussen weiter - ein "
        "Skript koennte den Abbruch dann nicht erkennen." % relpfad)
    assert "print(befund.text)" in quelle, (
        "%s gibt den Befundtext nicht aus. Dann stuende die aufrufende "
        "Person vor einem stillen Abbruch." % relpfad)


@pytest.mark.parametrize("relpfad", sorted(STUFE_A))
def test_eb03_der_dateikopf_nennt_die_einstufung(relpfad):
    """
    EB03 - Die Einstufung steht im Kopf des Werkzeugs, nicht nur im Vermerk.

    Wer die Datei oeffnet, um sie zu aendern, liest den Kopf. Wer den Vermerk
    im Projektspeicher liest, aendert gerade keine Datei.
    """
    kopf = "\n".join(_quelle(relpfad).split("\n")[:80])
    assert "WARTUNGSVORBEHALT" in kopf, (
        "%s nennt den Wartungsvorbehalt nicht im Dateikopf." % relpfad)
    assert "STUFE A" in kopf, (
        "%s nennt die Stufe nicht im Dateikopf." % relpfad)
    assert "3" in kopf, "%s nennt den Rueckgabewert 3 nicht." % relpfad


@pytest.mark.parametrize("relpfad", sorted(NICHT_STUFE_A))
def test_eb04_abgrenzung_ist_geprueft_und_nicht_behauptet(relpfad):
    """
    EB04 - Ein Werkzeug, das NICHT Stufe A ist, ruft den Vorbehalt auch nicht.

    Das ist keine Formalie: Ein Vorbehalt an einer Stelle, an der er nicht
    hingehoert, erzeugt Rueckfragen ohne Anlass - und wer oft ohne Anlass
    gefragt wird, tippt das Wort irgendwann, ohne zu lesen. Dann ist die
    Sicherung genau dort wirkungslos, wo sie gebraucht wird.
    """
    quelle = _quelle(relpfad)
    # BUILD 686 - GEPRUEFT WIRD DER AUFRUF, NICHT DAS WORT.
    #
    # Bis Build 680 stand hier 'assert "wartungsvorbehalt" not in quelle'
    # ueber den GANZEN Quelltext. Das prueft etwas anderes als das, was
    # gemeint ist: Es verbietet einem Stufe-B-Werkzeug auch, seine
    # Einstufung im DATEIKOPF zu nennen - und genau das ist bei Stufe B
    # gefordert. Der Wächter stand damit der Regel im Weg, die er sichern
    # soll. Aufgefallen bei der Vollstaendigkeitspruefung, als index_cli
    # seinen Kopfeintrag bekommen sollte.
    verboten = ("from maintenance.wartungsvorbehalt import",
                "import maintenance.wartungsvorbehalt")
    treffer = [z for z in verboten if z in quelle]
    assert treffer == [], (
        "%s ist als '%s' eingestuft und darf den Vorbehalt nicht aufrufen "
        "(gefunden: %s)." % (relpfad, NICHT_STUFE_A[relpfad][:70], treffer))


#: Die Werkzeuge, die die Analyse K1-K8 (Build 609) und ihr Nachtrag
#: (Build 615) benannt haben. Sie stehen hier NAMENTLICH und nicht als Zahl:
#: Bis Build 680 pruefte EB05 'len(STUFE_A) == 6'. Eine Zahl sagt nicht, WER
#: fehlt - und sie geht bei jedem berechtigten Zuwachs kaputt, ohne dass
#: jemand sieht, ob der Zuwachs richtig war. Ein Name laesst sich pruefen.
_AUS_DER_ANALYSE = (
    "management/migrate.py",
    "tools/migrate-dbs.py",
    "management/migration_fleet/migration_fleet_admin.py",
    "management/consolidate_default_db.py",
    "tools/forensic_index_upgrade.py",
    "tools/convert_journal_mode.py",           # Nachtrag Build 615
)


def test_eb05_die_liste_deckt_sich_mit_dem_vermerk():
    """
    EB05 - Die Werkzeuge aus dem Vermerk sind alle noch da, und jeder
    Eintrag zeigt auf eine wirkliche Datei.

    Ein Eintrag, der auf keine Datei zeigt, waere eine Sicherung, die niemand
    vermisst - der Test ueber ihn liefe gruen, weil er nichts findet.

    DIE LISTE DARF WACHSEN, und sie ist in Build 686 gewachsen (drei
    Nachtraege aus der Vollstaendigkeitspruefung). Was sie NICHT darf, ist
    schrumpfen: wer ein Werkzeug aus der Analyse herausnimmt, muss das
    ausdruecklich tun und diesen Test dabei anfassen.
    """
    fehlend = [p for p in _AUS_DER_ANALYSE if p not in STUFE_A]
    assert fehlend == [], (
        "Aus der Analyse K1-K8 verschwunden: %s. Ein Werkzeug faellt nicht "
        "beilaeufig aus der Stufe A heraus." % fehlend)
    for relpfad in list(STUFE_A) + list(NICHT_STUFE_A):
        assert (_WURZEL / relpfad).is_file(), \
            "%s ist eingetragen, existiert aber nicht." % relpfad


# -----------------------------------------------------------------------------
# EB06-EB09 - am Verhalten
#
# In allen vier Faellen wird eine betroffene Datei EXKLUSIV GESPERRT gehalten.
# Der Vorbehalt muss dann abbrechen, und zwar OHNE Rueckfrage - der belegte
# Zustand ist ein Messwert und keine Ermessensfrage. Deshalb braucht keiner
# dieser Tests ein Terminal, und keiner haengt an einer Eingabe.
# -----------------------------------------------------------------------------

def test_eb06_migrate_bricht_bei_belegter_coordinator_ab(anlage, capsys):
    """EB06 - management/migrate.py gibt 3 zurueck und fasst nichts an."""
    db = _db(anlage / "coordinator.db")
    from management import migrate

    with _Halter(db):
        rc = migrate.main(["--coordinator-db", str(db)])

    assert rc == RUECKGABE_VORBEHALT
    ausgabe = capsys.readouterr().out
    assert "WARTUNGSVORBEHALT" in ausgabe
    assert "coordinator.db" in ausgabe
    # Die Migration selbst ist gar nicht erst angelaufen.
    assert "Angewandte Migrationen" not in ausgabe
    with sqlite3.connect(str(db)) as con:
        namen = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
    assert namen == ["t"], \
        "Der Vorbehalt hat den Lauf nicht vor der ersten Schreiboperation " \
        "angehalten: %s" % namen


def test_eb07_consolidate_bricht_bei_belegtem_ziel_ab(anlage, capsys):
    """EB07 - management/consolidate_default_db.py gibt 3 zurueck."""
    ziel = _db(anlage / "default.db")
    quelle = _db(anlage / "quelle" / "default.db")
    from management import consolidate_default_db as tool

    with _Halter(ziel):
        rc = tool.main(["--target", str(ziel), "--source", str(quelle),
                        "--overwrite"])

    assert rc == RUECKGABE_VORBEHALT
    ausgabe = capsys.readouterr().out
    assert "WARTUNGSVORBEHALT" in ausgabe
    # Die Ziel-Datei ist NICHT geloescht worden - genau der Befund, wegen
    # dessen das Werkzeug Stufe A ist.
    assert ziel.is_file()


def test_eb08_forensic_index_upgrade_bricht_bei_belegter_datei_ab(anlage,
                                                                 capsys):
    """
    EB08 - tools/forensic_index_upgrade.py --ausfuehren gibt 3 zurueck.

    Zusaetzlich die Gegenprobe: der TROCKENLAUF laeuft weiterhin ohne
    Vorbehalt durch. Eine Vorschau, die erst nach einer Rueckfrage kommt,
    wird uebersprungen - und dann sieht niemand mehr, was passieren wuerde.
    """
    verz = anlage / "forensic"
    db = _db(verz / "forensic_1488.db")
    werkzeug = _lade("tools/forensic_index_upgrade.py", "fiu_einbau")

    with _Halter(db):
        rc = werkzeug.main(["--forensic-dir", str(verz), "--ausfuehren"])
        assert rc == RUECKGABE_VORBEHALT
        assert "WARTUNGSVORBEHALT" in capsys.readouterr().out

        rc_trocken = werkzeug.main(["--forensic-dir", str(verz)])
    trocken = capsys.readouterr().out
    assert rc_trocken != RUECKGABE_VORBEHALT
    assert "WARTUNGSVORBEHALT" not in trocken, \
        "Der Trockenlauf darf keinen Vorbehalt ausloesen."


def test_eb09_migrate_dbs_trockenuebung_bleibt_frei(anlage, capsys):
    """
    EB09 - tools/migrate-dbs.py ohne --apply loest keinen Vorbehalt aus.

    Der scharfe Lauf dieses Werkzeugs braucht einen vollstaendigen
    Migrationsstand als Aufbau; hier wird die andere Richtung gesichert - dass
    die Trockenuebung ungestoert bleibt. Der scharfe Zweig ist ueber EB01/EB02
    am Quelltext gedeckt und ueber die Stelle des Aufrufs: er steht NACH der
    Abfrage 'nicht args.apply' und VOR der ersten Sicherung.
    """
    _db(anlage / "templates.db")
    werkzeug = _lade("tools/migrate-dbs.py", "migrate_dbs_einbau")

    rc = werkzeug.main(["--data-dir", str(anlage)])
    ausgabe = capsys.readouterr().out
    assert rc != RUECKGABE_VORBEHALT
    assert "WARTUNGSVORBEHALT" not in ausgabe

    # Die Reihenfolge im Quelltext, als Beleg fuer den scharfen Zweig.
    quelle = _quelle("tools/migrate-dbs.py")
    vorbehalt = quelle.index("befund = wartungsvorbehalt(")
    assert quelle.index("if not args.apply:") < vorbehalt, \
        "Der Vorbehalt liegt vor der Trockenuebungs-Abfrage - dann wuerde " \
        "auch die Vorschau nachfragen."
    assert vorbehalt < quelle.index('print("SCHARFGESCHALTET'), \
        "Der Vorbehalt liegt hinter dem Beginn des scharfen Laufs."


def test_eb10_datenwurzel_findet_das_wartungsverzeichnis(anlage, tmp_path):
    """
    EB10 - Alle fuenf Werkzeuge finden dasselbe Wartungsverzeichnis.

    Sie bekommen ganz verschiedene Pfade genannt - eine Datei, ein
    Datenverzeichnis, ein Unterverzeichnis. Wuerde jedes fuer sich raten, wo
    die Wurzel liegt, waere das fuenfmal dieselbe Annahme an fuenf Stellen.
    """
    tief = anlage / "forensic"
    tief.mkdir(exist_ok=True)
    datei = _db(anlage / "coordinator.db")

    assert datenwurzel(datei) == anlage
    assert datenwurzel(anlage) == anlage
    assert datenwurzel(tief) == anlage

    # Ohne _maintenance in der Naehe: Rueckfall auf den Ausgangspunkt. Dort
    # gibt es dann kein Fenster - der Vorbehalt fragt nach, er laesst nicht
    # etwa durch.
    fremd = tmp_path / "woanders"
    fremd.mkdir()
    assert datenwurzel(fremd) == fremd


def test_eb11_convert_journal_mode_bricht_bei_belegter_datei_ab(anlage,
                                                                capsys):
    """
    EB11 - tools/convert_journal_mode.py --apply gibt 3 zurueck und stempelt
    nichts um.

    Zusaetzlich die Gegenprobe: der TROCKENLAUF bleibt frei. Er ist der Weg,
    auf dem man vorher sieht, welche Dateien ueberhaupt umzustempeln waeren -
    ihn hinter eine Rueckfrage zu setzen, hiesse ihn abzuschaffen.
    """
    db = _db(anlage / "coordinator.db")
    werkzeug = _lade("tools/convert_journal_mode.py", "cjm_einbau")
    stempel_vorher = werkzeug.header_stempel(db)

    with _Halter(db):
        rc = werkzeug.main(["--data-dir", str(anlage), "--apply"])
        assert rc == RUECKGABE_VORBEHALT
        ausgabe = capsys.readouterr().out
        assert "WARTUNGSVORBEHALT" in ausgabe
        assert "coordinator.db" in ausgabe
        # Es darf nicht einmal begonnen haben.
        assert "FERTIG:" not in ausgabe

        rc_trocken = werkzeug.main(["--data-dir", str(anlage)])
    trocken = capsys.readouterr().out
    assert rc_trocken != RUECKGABE_VORBEHALT
    assert "WARTUNGSVORBEHALT" not in trocken, \
        "Der Trockenlauf darf keinen Vorbehalt ausloesen."
    assert werkzeug.header_stempel(db) == stempel_vorher, \
        "Der Journalstempel wurde veraendert, obwohl der Vorbehalt griff."



# -----------------------------------------------------------------------------
# EB12-EB14 - die drei Nachtraege aus Build 686, am VERHALTEN
#
# Fuer alle drei gilt dasselbe wie fuer EB06-EB11: eine betroffene Datei wird
# EXKLUSIV GESPERRT gehalten, und das Werkzeug muss 3 zurueckgeben, ohne
# etwas anzufassen. Bei den beiden Templates-Werkzeugen ist das besonders
# wichtig, weil ihr scharfer Lauf eine Tabelle DROPPT: waere der Vorbehalt
# hinter dem Umbau gelandet, sähe die Quelltextpruefung (EB01) trotzdem
# gruen aus.
# -----------------------------------------------------------------------------

def _templates_db(pfad: Path) -> Path:
    """Eine templates.db mit genau den Tabellen, die die beiden anfassen."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(pfad))
    con.executescript("""
        CREATE TABLE templates_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL, target_id TEXT NOT NULL,
            target_type TEXT NOT NULL CHECK (target_type IN ('module','query')),
            changed_by TEXT NOT NULL, changed_at INTEGER NOT NULL,
            old_value TEXT, new_value TEXT);
        CREATE TABLE placeholder_queries (
            id TEXT PRIMARY KEY, title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', sql_query TEXT,
            tags TEXT, return_type TEXT NOT NULL DEFAULT 'scalar',
            is_active INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL,
            created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
    """)
    con.commit()
    con.close()
    return pfad


def test_eb12_audit_check_bricht_bei_belegter_templates_db_ab(anlage, capsys):
    """
    EB12 - migrate_templates_audit_check gibt 3 zurueck, und die Tabelle
    steht danach unveraendert da.

    DIE GEGENPROBE IST DER PUNKT: Ein Rebuild, der bis zum 'DROP TABLE'
    gekommen waere, liesse sich am fehlenden Namen ablesen. Hier muss beides
    noch da sein.
    """
    db = _templates_db(anlage / "templates.db")
    from management import migrate_templates_audit_check as tool

    with _Halter(db):
        rc = tool.main(["--templates-db", str(db)])

    assert rc == RUECKGABE_VORBEHALT
    assert "WARTUNGSVORBEHALT" in capsys.readouterr().out
    with sqlite3.connect(str(db)) as con:
        ddl = con.execute(
            "SELECT sql FROM sqlite_master WHERE name='templates_audit_log'"
        ).fetchone()[0]
        rest = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE '%__new'")]
    assert "'template'" not in ddl, "Der Rebuild ist trotzdem gelaufen."
    assert rest == [], "Eine Zwischentabelle blieb liegen: %s" % rest


def test_eb13_placeholders_bricht_ab_und_legt_kein_backup(anlage, capsys):
    """
    EB13 - migrate_templates_placeholders gibt 3 zurueck - UND legt keine
    Sicherungskopie an.

    DAS BACKUP IST HIER DIE EIGENTLICHE PRUEFUNG: Der Vorbehalt steht mit
    Absicht VOR der Kopie. Eine '.pre489.bak' ohne zugehoerigen Lauf waere
    spaeter nicht von einer mit zu unterscheiden - und wer sie findet,
    schliesst daraus, der Umbau habe stattgefunden.
    """
    db = _templates_db(anlage / "templates.db")
    from management import migrate_templates_placeholders as tool

    with _Halter(db):
        rc = tool.main(["--templates-db", str(db)])

    assert rc == RUECKGABE_VORBEHALT
    assert "WARTUNGSVORBEHALT" in capsys.readouterr().out
    assert not (anlage / "templates.db.pre489.bak").exists(), \
        "Der Vorbehalt steht hinter der Sicherungskopie statt davor."
    with sqlite3.connect(str(db)) as con:
        # 'sqlite_sequence' bleibt aussen vor: SQLite legt sie wegen des
        # AUTOINCREMENT im Testaufbau selbst an, sie sagt ueber den Umbau
        # nichts.
        namen = sorted(r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"))
    assert namen == ["placeholder_queries", "templates_audit_log"], \
        "Der Umbau ist trotzdem angelaufen: %s" % namen


def test_eb14_repair_block_types_bricht_bei_belegter_evidence_ab(
        anlage, capsys):
    """
    EB14 - repair_block_types --apply gibt 3 zurueck, wenn eine
    evidence-Datenbank belegt ist.

    UND DER TROCKENLAUF BLEIBT FREI: derselbe Aufruf ohne '--apply' laeuft
    auch bei belegter Datei durch. Das ist Absicht - wer das Nachsehen so
    teuer macht wie das Handeln, erreicht, dass niemand mehr nachsieht.
    """
    ev = anlage / "evidence"
    ev.mkdir(parents=True, exist_ok=True)
    db = ev / "evidence_18.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE report_blocks (block_id TEXT, report_id TEXT, "
                "block_type TEXT, block_data TEXT, updated_at INTEGER)")
    con.commit()
    con.close()

    from management import repair_block_types as tool

    with _Halter(db):
        rc = tool.main(["--evidence-dir", str(ev), "--apply",
                        "--ja-backup-vorhanden"])
    assert rc == RUECKGABE_VORBEHALT
    assert "WARTUNGSVORBEHALT" in capsys.readouterr().out

    with _Halter(db):
        rc_trocken = tool.main(["--evidence-dir", str(ev)])
    assert rc_trocken == 0, (
        "Der Trockenlauf muss auch bei belegter Datei durchlaufen - er "
        "liest nur.")
