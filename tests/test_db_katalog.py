# =============================================================================
# tests/test_db_katalog.py
# IT-Forensisches Ermittlungswerkzeug — Anlagenpflege
# =============================================================================
# Gegenstand: management/db_katalog.py und management/db_startbefund.py
# (Build 657).
#
# ANLASS: Vorfall 2026-08-02. Die Sicht "Baustein-Module" antwortete mit
# HTTP 500 und schwieg dazu; Ursache war die nicht angewandte Migration aus
# Build 655. Der Serverstart prueft seit Build 376 den Migrationsstand - aber
# NUR den der coordinator.db. Der Servercode liest zehn Datenbankpfade.
#
# DK01 — der Katalog ist in sich stimmig (Kennungen eindeutig, Werte gueltig).
# DK02 — JEDER Eintrag traegt eine Begruendung. Auch die, bei denen nichts
#        zu pruefen ist: 'nicht geprueft' muss als ENTSCHEIDUNG erkennbar
#        sein und nicht als Versaeumnis.
# DK03 — Startbefund auf einer templates.db im Rueckstand: benennt die
#        fehlende Migration UND den Befehl. GEGEN DEN ECHTEN VORFALL GEMESSEN.
# DK04 — Startbefund WIRFT NIE, auch nicht bei unbrauchbarer Konfiguration.
# DK05 — DIE VOLLZAEHLIGKEITSSPERRE: jeder im Servercode benutzte
#        config.yaml-Datenbankpfad steht im Katalog.
# DK06 — meldezeilen(): schweigt bei 'alles gut', nennt sonst Pfad und Befehl.
# DK07 — der Befund heilt nicht und kann es nicht: keine Schreibverbindung.
#
# DK08 — Transportdateien loesen keinen Fehlalarm aus (Build 658).
# DK09 — fehlt das Namensmuster, wird gemeldet statt geraten (Build 658).
# DK10 — das Muster passt zur kanonischen Bildung im Bestand (Build 658).
#
# Version: v0.8.658 · Build: 658 · 2026-08-02
# =============================================================================

from __future__ import annotations

import os
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from management.db_katalog import (
    ART_ANLAGE,
    ART_FALL,
    DB_KATALOG,
    STAND_FREMD,
    STAND_OHNE,
    STAND_REGISTER,
    STAND_SPUREN,
    STAND_VERSIEGELT,
    config_schluessel_alle,
    eintrag,
    nach_config_schluessel,
    pruefbare,
)
from management.db_startbefund import (
    BEFUND_OK,
    BEFUND_RUECKSTAND,
    DbStartbefund,
    blockierende,
    meldezeilen,
    zusammenfassung,
)

_WURZEL = Path(__file__).resolve().parent.parent


class _StubConfig:
    """Ein ConfigLoader-Ersatz. Nur .get(schluessel, vorgabe)."""

    def __init__(self, werte=None, wirft=False):
        self._werte = werte or {}
        self._wirft = wirft

    def get(self, schluessel, vorgabe=None):
        if self._wirft:
            raise RuntimeError("config.yaml unlesbar (nachgestellt)")
        return self._werte.get(schluessel, vorgabe)


def _templates_db(pfad: str, mit_655: bool) -> str:
    """Eine templates.db im Zustand mit/ohne die Migration aus Build 655."""
    sql = (_WURZEL / "tests" / "fixtures_templates_schema.sql").read_text(
        encoding="utf-8")
    if not mit_655:
        # Die beiden Spalten wieder herausnehmen - der Zustand, in dem die
        # Anlage am 2026-08-02 war.
        sql = re.sub(
            r'\t"block_type"[^\n]*\n\t"block_data" TEXT, PRIMARY KEY',
            "\tPRIMARY KEY", sql)
        assert "block_type" not in sql, "Vorrichtung greift nicht mehr"
    con = sqlite3.connect(pfad)
    con.executescript(sql)
    con.commit()
    con.close()
    return pfad


class KatalogTests(unittest.TestCase):

    # DK01 -----------------------------------------------------------------
    def test_dk01_katalog_ist_stimmig(self):
        kennungen = [e.kennung for e in DB_KATALOG]
        self.assertEqual(len(kennungen), len(set(kennungen)),
                         "Doppelte Kennung im Katalog")
        for e in DB_KATALOG:
            self.assertIn(e.art, (ART_ANLAGE, ART_FALL), e.kennung)
            self.assertIn(e.stand, (STAND_REGISTER, STAND_SPUREN,
                                    STAND_VERSIEGELT, STAND_FREMD,
                                    STAND_OHNE), e.kennung)
            for s in e.server:
                self.assertIn(s, ("verwaltung", "ermittler"), e.kennung)
            self.assertTrue(e.name.strip(), e.kennung)
            # Ein Heilbefehl ohne etwas zu heilen waere irrefuehrend.
            if e.stand in (STAND_FREMD, STAND_OHNE, STAND_VERSIEGELT):
                self.assertIsNone(e.befehl, e.kennung)
        self.assertIsNotNone(eintrag("templates"))
        self.assertIsNone(eintrag("gibtsnicht"))

    # DK02 -----------------------------------------------------------------
    def test_dk02_jeder_eintrag_hat_eine_begruendung(self):
        """
        DER KERN DIESES KATALOGS. Am 2026-08-02 war nicht erkennbar, ob
        'templates.db wird beim Start nicht geprueft' eine Entscheidung war
        oder ein Versaeumnis. Genau dieser Unterschied hat die Zeit gekostet.
        """
        for e in DB_KATALOG:
            self.assertTrue(
                e.begruendung and len(e.begruendung.strip()) >= 40,
                "Eintrag '%s' ohne tragfaehige Begruendung: %r"
                % (e.kennung, e.begruendung))

    # DK03 -----------------------------------------------------------------
    def test_dk03_rueckstand_wird_benannt_mit_befehl(self):
        """GEGEN DEN ECHTEN VORFALL GEMESSEN."""
        tmp = tempfile.mkdtemp()
        pfad = _templates_db(os.path.join(tmp, "templates.db"), mit_655=False)
        cfg = _StubConfig({"paths.templates_db": pfad})

        befunde = DbStartbefund("verwaltung", cfg).erhebe()
        tpl = [b for b in befunde if b.kennung == "templates"][0]

        self.assertEqual(tpl.lage, BEFUND_RUECKSTAND)
        # Die Meldung nennt die MIGRATION, nicht nur 'irgendetwas fehlt'.
        self.assertIn("655", tpl.text)
        self.assertIn("Blocktyp", tpl.text)
        # Und sie nennt das WERKZEUG, nicht das Einzelskript: der Pfad kommt
        # dann aus config.yaml und kann nicht verfehlt werden. Das ist die
        # Lehre aus dem Vorfall - die Migration lief gegen einen von Hand
        # getippten Pfad und traf die falsche Datei.
        self.assertIn("tools/migrate-dbs.py", tpl.befehl)
        self.assertNotIn("--templates-db", tpl.befehl)

        # Nach der Migration ist Ruhe.
        from management.migrate_templates_blocktyp import apply_migration
        con = sqlite3.connect(pfad)
        apply_migration(con, changed_by="test")
        con.close()
        tpl2 = [b for b in DbStartbefund("verwaltung", cfg).erhebe()
                if b.kennung == "templates"][0]
        self.assertEqual(tpl2.lage, BEFUND_OK)
        self.assertTrue(tpl2.ok)

    # DK04 -----------------------------------------------------------------
    def test_dk04_erhebe_wirft_nie(self):
        """
        Eine Startpruefung, die den Start verhindert, weil SIE einen Fehler
        hat, ist schlimmer als keine.
        """
        for cfg in (_StubConfig(wirft=True),
                    _StubConfig({"paths.templates_db": "/gibt/es/nicht.db"}),
                    _StubConfig({"paths.templates_db": None})):
            befunde = DbStartbefund("verwaltung", cfg).erhebe()
            self.assertTrue(befunde)
            # Kein Befund darf blockierend sein - der Verwaltungsserver hat
            # keinen solchen Eintrag, und ein Fehler der Pruefung selbst darf
            # es erst recht nicht werden.
            self.assertEqual(blockierende(befunde), [])

        # Eine Datei, die zwar da, aber keine Datenbank ist.
        tmp = tempfile.mkdtemp()
        kaputt = os.path.join(tmp, "templates.db")
        with open(kaputt, "w", encoding="utf-8") as fh:
            fh.write("das ist keine Datenbank")
        befunde = DbStartbefund(
            "verwaltung", _StubConfig({"paths.templates_db": kaputt})).erhebe()
        tpl = [b for b in befunde if b.kennung == "templates"][0]
        self.assertFalse(tpl.ok)
        self.assertTrue(tpl.text.strip())

    # DK05 -----------------------------------------------------------------
    def test_dk05_vollzaehligkeit(self):
        """
        DIE SPERRE. Sie erhebt aus dem QUELLTEXT der Server, welche
        config.yaml-Datenbankpfade tatsaechlich gelesen werden, und haelt sie
        gegen den Katalog.

        Verfahren wie UX10 (handgebaute Tabellen) und PY08 (schreibfaehige
        Module): nicht eine Liste pflegen und hoffen, sondern den Bestand
        messen. Wer kuenftig eine Datenbank anbindet und sie nicht eintraegt,
        faellt hier auf - und nicht erst, wenn jemand mit HTTP 500 davorsteht.
        """
        quellen = [
            _WURZEL / "management" / "server" / "management_app.py",
            _WURZEL / "management.py",
            _WURZEL / "main.py",
            _WURZEL / "db" / "connection_manager.py",
        ]
        benutzt = set()
        muster = re.compile(r'["\'](paths\.[a-z_]*db[a-z_]*)["\']')
        for q in quellen:
            if not q.exists():
                continue
            for treffer in muster.findall(q.read_text(encoding="utf-8")):
                benutzt.add(treffer)

        self.assertTrue(benutzt, "Die Erhebung hat NICHTS gefunden - dann "
                                 "misst sie auch nichts. Muster pruefen.")
        bekannt = set(config_schluessel_alle())
        ohne = sorted(benutzt - bekannt)
        self.assertEqual(
            ohne, [],
            "Datenbankpfade OHNE Eintrag in management/db_katalog.py: %s. "
            "Jede Datenbank, die der Server anfasst, gehoert in den Katalog - "
            "auch wenn es an ihr nichts zu pruefen gibt. Dann steht dort der "
            "Grund." % ", ".join(ohne))

        # Und die Gegenrichtung: ein Katalogeintrag, den niemand mehr
        # benutzt, ist Ballast - er wird GEMELDET, aber er bricht nicht.
        # (Kein assert: 'migration' steht bewusst darin, obwohl die Flotte
        # auf dieser Anlage nicht laeuft.)
        for s in sorted(bekannt - benutzt):
            e = nach_config_schluessel(s)
            self.assertTrue(e.begruendung, s)

    # DK06 -----------------------------------------------------------------
    def test_dk06_meldung(self):
        tmp = tempfile.mkdtemp()
        pfad = _templates_db(os.path.join(tmp, "templates.db"), mit_655=False)
        befunde = DbStartbefund(
            "verwaltung", _StubConfig({"paths.templates_db": pfad})).erhebe()
        tpl = [b for b in befunde if b.kennung == "templates"]

        # Alles gut -> KEINE Zeile. Eine Erfolgsmeldung je Datenbank waere
        # eine Wand, in der die naechste echte Warnung untergeht.
        gut = [b for b in befunde if b.ok]
        self.assertEqual(meldezeilen(gut), [])

        text = "\n".join(meldezeilen(tpl))
        self.assertIn("templates.db", text)
        self.assertIn(pfad, text)                    # der aufgeloeste Pfad
        self.assertIn("tools/migrate-dbs.py", text)  # das Werkzeug
        self.assertIn("MIGRIERT BEWUSST NICHT SELBST", text)
        # Der Hinweis, der den eigentlichen Fehler des Vorfalls benennt.
        self.assertIn("KEINEN Pfad von Hand", text)

        self.assertIn("mit Befund", zusammenfassung(tpl))
        self.assertIn("alle auf Stand", zusammenfassung(gut) if gut
                      else "alle auf Stand")

    # DK07 -----------------------------------------------------------------
    def test_dk07_der_befund_kann_nicht_heilen(self):
        """
        Der Server heilt nicht - und das ist keine Selbstbeschraenkung,
        sondern die Bauart. Der Nachweis am Quelltext: es gibt in
        db_startbefund.py keine schreibfaehige Verbindung.
        """
        quelle = (_WURZEL / "management" / "db_startbefund.py").read_text(
            encoding="utf-8")
        for verbindung in re.findall(r"sqlite3\.connect\([^)]*\)", quelle):
            self.assertIn("mode=ro", verbindung,
                          "Verbindung ohne mode=ro: %s" % verbindung)
        for verboten in ("apply_migration", "executescript", "commit()",
                         "INSERT ", "UPDATE ", "ALTER "):
            self.assertNotIn(verboten, quelle,
                             "db_startbefund.py enthaelt '%s' - es darf "
                             "NICHTS schreiben." % verboten)


if __name__ == "__main__":
    unittest.main()


# =============================================================================
# BUILD 658 — DER FEHLALARM DER FALLDATENBANKEN (Ticket c48b0d76).
#
# Der Startbefund aus Build 657 nahm im evidence-Verzeichnis ALLES, was auf
# .db endete, und zaehlte damit die TRANSPORTDATEIEN des
# Cross-Annotation-Integrators ("evidence_<uid>_<iid>.db") als
# Falldatenbanken ohne Register. Sieben Stueck, bei jedem Serverstart, auf
# einer Anlage, die am naechsten Tag in Betrieb ging.
#
# WARUM ES DURCH MEINE PRUEFUNG KAM: auf dem Baucontainer gibt es das
# evidence-Verzeichnis gar nicht - die Pruefung lief dort gegen 'fehlt'. Ein
# Pfad, den die Vorrichtung nicht beruehrt, ist ungeprueft. Das ist die Lehre
# aus Build 651, und ich habe sie hier nicht angewandt. DIESER FALL BAUT DAS
# VERZEICHNIS DESHALB WIRKLICH.
#
# DK08 — nur die kanonische Form wird geprueft, das Uebergangene wird GENANNT.
# DK09 — fehlt das Muster im Katalog, wird das gemeldet statt alles zu nehmen.
# =============================================================================
class FalldatenbankenTests(unittest.TestCase):

    def _verzeichnis(self, echte=5, transport=3, ohne_register=0):
        tmp = tempfile.mkdtemp()
        ev = os.path.join(tmp, "evidence")
        os.makedirs(ev)

        def _db(name, register=True):
            con = sqlite3.connect(os.path.join(ev, name))
            if register:
                con.execute("CREATE TABLE schema_migrations (version INTEGER)")
            else:
                # Das Schema einer Transportdatei: Annotationen, kein Register.
                con.execute("CREATE TABLE annotations (id INTEGER)")
            con.commit()
            con.close()

        for n in range(echte):
            _db("evidence_%d.db" % (1000 + n))
        for n in range(ohne_register):
            _db("evidence_%d.db" % (2000 + n), register=False)
        for n in range(transport):
            # Die Form, die den Fehlalarm ausgeloest hat.
            _db("evidence_%d_3.db" % (1486482 + n), register=False)
        return ev

    def _befund(self, ev, kennung="evidence"):
        cfg = _StubConfig({"paths.evidence_db_dir": ev,
                           "paths.assets_db_dir": ev})
        return [b for b in DbStartbefund("verwaltung", cfg).erhebe()
                if b.kennung == kennung][0]

    # DK08 -----------------------------------------------------------------
    def test_dk08_transportdateien_loesen_keinen_alarm_aus(self):
        b = self._befund(self._verzeichnis(echte=5, transport=3))

        # KEIN Warnbalken - das ist der ganze Punkt. Ein Balken, der bei
        # jedem Start etwas Richtiges meldet, wird nach der dritten Woche
        # nicht mehr gelesen; dann faellt auch die echte Meldung nicht auf.
        self.assertTrue(b.ok, b.text)
        self.assertEqual(meldezeilen([b]), [])

        # Gezaehlt werden die fuenf echten, nicht die acht Dateien.
        self.assertIn("5 Falldatenbank(en)", b.text)
        # GRUNDREGEL 1: das Uebergangene wird GENANNT, nicht verschwiegen.
        # Eine Pruefung, die Dateien wortlos auslaesst, ist von einer
        # unvollstaendigen nicht zu unterscheiden.
        self.assertIn("3 weitere Datei(en)", b.text)
        self.assertIn("uebergangen", b.text)

        # Und die ECHTEN Befunde gehen dabei nicht verloren.
        b2 = self._befund(self._verzeichnis(echte=4, transport=3,
                                            ohne_register=2))
        self.assertFalse(b2.ok)
        self.assertIn("6 Falldatenbank(en)", b2.text)   # 4 + 2
        self.assertIn("2 ohne Register", b2.text)
        self.assertIn("3 weitere Datei(en)", b2.text)

        # Ein Verzeichnis NUR mit Transportdateien ist in Ordnung - und sagt
        # trotzdem, was es gesehen hat.
        b3 = self._befund(self._verzeichnis(echte=0, transport=2))
        self.assertTrue(b3.ok)
        self.assertIn("Keine Falldatenbanken", b3.text)
        self.assertIn("2 weitere", b3.text)

    # DK09 -----------------------------------------------------------------
    def test_dk09_ohne_muster_wird_nichts_geraten(self):
        """
        Fehlt im Katalog das Namensmuster, darf der Pruefer NICHT einfach
        alles nehmen - dann waere der Fehlalarm zurueck. Er meldet, dass er
        es nicht entscheiden kann.
        """
        import dataclasses
        from management.db_katalog import eintrag as _eintrag

        ev = self._verzeichnis(echte=3, transport=2)
        ohne = dataclasses.replace(_eintrag("evidence"), datei_muster=None)
        befund = DbStartbefund(
            "verwaltung",
            _StubConfig({"paths.evidence_db_dir": ev}))._falldatenbanken(
                ohne, ev)

        self.assertFalse(befund.ok)
        self.assertIn("fehlt das Dateinamensmuster", befund.text)
        self.assertIn("5", befund.text)      # es nennt, worueber es raet

    # DK10 -----------------------------------------------------------------
    def test_dk10_das_muster_passt_zur_kanonischen_bildung(self):
        """
        Das Muster im Katalog und die Stelle, die den Namen BILDET, muessen
        zusammenpassen. management_app.py und annotation_stats_repo.py bilden
        'evidence_%d.db'; wer das Muster aendert, ohne dort nachzusehen,
        prueft an der Wirklichkeit vorbei.
        """
        import re as _re
        from management.db_katalog import eintrag as _eintrag

        muster = _re.compile(_eintrag("evidence").datei_muster)
        self.assertTrue(muster.match("evidence_%d.db" % 1488))
        self.assertTrue(muster.match("evidence_0.db"))
        # Transportdateien und Addendum-Dateien: zwei Zahlen, nicht gemeint.
        self.assertFalse(muster.match("evidence_1488_3.db"))
        self.assertFalse(muster.match("evidence_1488_12345.db"))
        # Und nichts, was nur so aehnlich heisst.
        self.assertFalse(muster.match("evidence_.db"))
        self.assertFalse(muster.match("evidence_1488.db.bak"))
        self.assertFalse(muster.match("assets_1488.db"))
        self.assertFalse(muster.match("xevidence_1488.db"))

        amuster = _re.compile(_eintrag("assets").datei_muster)
        self.assertTrue(amuster.match("assets_1488.db"))
        self.assertFalse(amuster.match("assets_1488_3.db"))
