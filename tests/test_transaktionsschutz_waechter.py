# =============================================================================
# tests/test_transaktionsschutz_waechter.py
# IT-Forensisches Ermittlungswerkzeug — Waechter Transaktionsschutz (Build 774)
# =============================================================================
# Liest den Quelltext des WEBSERVERS (nicht des Managements) und erzwingt zwei
# Regeln fuer jede Funktion, die commit() aufruft (jeweils die innerste):
#
#   R1  Sie laeuft in 'with Schreibvorgang(...)' (db/schreibvorgang.py) —
#       oder steht mit Begruendung in AUSNAHMEN (eigene, nicht geteilte
#       Verbindung).
#   R2  Jeder except-Behandler in ihr, der einen Datenbankfehler faengt
#       (sqlite3.*, Exception, BaseException, nacktes except) und ihn NICHT
#       weiterwirft, ruft selbst rollback() auf — sofern der zugehoerige
#       try-Block SCHREIBT (INSERT/UPDATE/DELETE/REPLACE oder commit()) und
#       nicht selbst den Schreibvorgang enthaelt (dann ist vor dem
#       Verschlucken schon zurueckgerollt). Ein try-Block, der nur liest,
#       hinterlaesst keine Transaktion (implizites BEGIN nur vor DML).
#   R3  (Build 775) Jede innerste Funktion, die DML ausfuehrt (INSERT/UPDATE/
#       DELETE/REPLACE als Zeichenkette), laeuft im Schreibvorgang — AUCH
#       wenn sie selbst kein commit() ruft. Befund der unabhaengigen
#       Durchsicht 14.10.2026: get_sort_index_after verschob Bloecke ohne
#       commit (das kam spaeter aus save_block); dazwischen konnte ein
#       fremdes rollback() die Verschiebung zuruecknehmen. R1 sah die
#       Funktion nicht, weil sie kein commit() enthielt.
#
# WARUM (Befund 13./14.10.2026): Gemessen ohne rollback() waren vor Build 774
# 38 von 40 Schreibfunktionen in db/evidence_db.py und alle 3 in
# db/coordinator_db.py. Ein einziger Pfad ohne rollback() genuegte, um die
# Transaktion der geteilten Verbindung offen zu lassen und coordinator.db zu
# sperren. Der Waechter verhindert, dass ein kuenftiger Pfad das wieder tut.
#
# GELTUNGSBEREICH: die Verzeichnisse des Webserver-Prozesses (BEREICH). Das
# Management hat eigene Schreibwege mit rollback (management/gateway/
# evidence_writer.py, coordinator_writer.py) und ist hier ausgenommen.
#
#   WT01  R1 fuer alle Funktionen im Bereich
#   WT02  R2 fuer alle Funktionen im Bereich
#   WT03  jede Ausnahme existiert noch (keine Leichen in der Liste)
#   WT04  der Waechter faengt, was er fangen soll (Gegenprobe an Beispielcode)
#   WT05  Zahl der geschuetzten Funktionen in evidence_db/coordinator_db
#         (43 + 3, Stand Build 775) — sinkt sie, ist etwas verloren gegangen
#   WT06  R3 fuer alle Funktionen im Bereich (Build 775)
#
# Version: v0.8.774 · Build: 774 · 2026-10-14
# =============================================================================
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

BEREICH = ("core", "db", "forensic_api", "server", "report_render",
           "maintenance", "userinfo", "editor", "main.py")

#: (Datei, Funktion) -> Begruendung. Jede Zeile ist eine bewusste Ausnahme.
AUSNAHMEN = {
    ("db/locking_connection.py", "commit"):
        "Der Wrapper selbst — er IST das commit() der geteilten Verbindung.",
    ("db/locking_connection.py", "__exit__"):
        "Kontextmanager des Wrappers: commit bei Erfolg, rollback bei Fehler.",
    ("core/startup_checks.py", "_check_forensic_db_readonly"):
        "Eigene, nur-lesend (mode=ro) geoeffnete Wegwerf-Verbindung; der "
        "Schreibversuch SOLL scheitern.",
    ("db/review_addendum_db.py", "_setup_schema"):
        "Eigene Verbindung auf die Addendum-Datei (open_addendum, "
        "isolation_level=None, kein impliziter BEGIN).",
    ("db/search_index_db.py", "_oeffnen"):
        "Eigene Verbindung auf search_index.db (Hilfsindex).",
    ("forensic_api/annotate.py", "_write_cross_annotation"):
        "Eigene Verbindung auf die Transportdatei (t_con, sqlite3.connect "
        "auf cross_path), wird im finally geschlossen.",
    ("report_render/sqlite_renderer.py", "render"):
        "Eigene :memory:-Verbindung des Exports.",
    # --- Build 775, nur fuer R3 (DML ohne eigenes commit) ------------------
    ("report_render/sqlite_renderer.py", "_build"):
        "Fuellt die eigene :memory:-Verbindung von render().",
    ("db/review_addendum_db.py", "add_comment"):
        "Eigene Verbindung auf die Addendum-Datei.",
    ("db/review_addendum_db.py", "set_status"):
        "Eigene Verbindung auf die Addendum-Datei.",
    ("db/search_index_db.py", "ersetze_fall"):
        "Eigene Verbindung auf search_index.db, 'with self._con'.",
    ("db/search_index_db.py", "entferne_fall"):
        "Eigene Verbindung auf search_index.db, 'with self._con'.",
    ("db/search_index_db.py", "setze_meta"):
        "Eigene Verbindung auf search_index.db, 'with self._con'.",
    ("db/search_index_db.py", "optimiere"):
        "Eigene Verbindung auf search_index.db, 'with self._con'.",
    ("db/tatzeit_repo.py", "_write"):
        "Rueckruf fuer EvidenceWriter.audited_write: laeuft in "
        "EvidenceWriter.transaction() (Lock fuer die ganze Dauer, BEGIN "
        "IMMEDIATE, ROLLBACK bei jeder Ausnahme).",
}

_DB_FEHLER = ("sqlite3", "Exception", "BaseException", "DatabaseError",
              "OperationalError", "IntegrityError")


def _dateien():
    for b in BEREICH:
        p = WURZEL / b
        if p.is_file():
            yield p
        elif p.is_dir():
            yield from sorted(p.rglob("*.py"))


def _ruft(node, name):
    return any(isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
               and c.func.attr == name for c in ast.walk(node))


def _ist_schreibvorgang(w):
    return isinstance(w, ast.With) and any(
        isinstance(i.context_expr, ast.Call)
        and getattr(i.context_expr.func, "id", "") == "Schreibvorgang"
        for i in w.items)


def _innerste_committer(baum):
    for n in ast.walk(baum):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _ruft(n, "commit"):
            if any(m is not n and isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and _ruft(m, "commit") for m in ast.walk(n)):
                continue
            yield n


def _faengt_db_fehler(h):
    if h.type is None:
        return True
    text = ast.unparse(h.type)
    return any(k in text for k in _DB_FEHLER)


_DML = ("INSERT", "UPDATE", "DELETE", "REPLACE")


def _schreibt(anweisungen):
    """True, wenn die Anweisungen commit() rufen oder DML ausfuehren."""
    for st in anweisungen:
        for c in ast.walk(st):
            if not (isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)):
                continue
            if c.func.attr == "commit":
                return True
            if c.func.attr in ("execute", "executemany") and c.args:
                a = c.args[0]
                text = ""
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    text = a.value
                elif isinstance(a, ast.JoinedStr):
                    text = "".join(v.value for v in a.values
                                   if isinstance(v, ast.Constant))
                else:
                    return True      # nicht feststellbar -> als schreibend werten
                if text.lstrip().upper().startswith(_DML):
                    return True
    return False


def _r2_verstoesse(fn):
    """Behandler, die einen DB-Fehler verschlucken, ohne zurueckzurollen."""
    aus = []
    for t in ast.walk(fn):
        if not isinstance(t, ast.Try):
            continue
        try_geschuetzt = any(_ist_schreibvorgang(w) for st in t.body for w in ast.walk(st))
        if not _schreibt(t.body):
            continue
        for h in t.handlers:
            if not _faengt_db_fehler(h):
                continue
            wirft = any(isinstance(x, ast.Raise) for x in ast.walk(h))
            rollt = _ruft(h, "rollback")
            if not (wirft or rollt or try_geschuetzt):
                aus.append(h.lineno)
    return aus


def _dml_literal(fn):
    """True, wenn fn eine Anweisung ausfuehrt, die als Zeichenkette mit
    INSERT/UPDATE/DELETE/REPLACE beginnt (R3)."""
    for c in ast.walk(fn):
        if not (isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                and c.func.attr in ("execute", "executemany") and c.args):
            continue
        a = c.args[0]
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            text = a.value
        elif isinstance(a, ast.JoinedStr):
            text = "".join(v.value for v in a.values if isinstance(v, ast.Constant))
        else:
            continue
        if text.lstrip().upper().startswith(_DML):
            return True
    return False


def r3_pruefen(quelltext, dateiname="<test>"):
    """-> [(datei, fn, zeile)] DML-Funktionen ausserhalb des Schreibvorgangs."""
    baum = ast.parse(quelltext)
    aus = []
    for fn in ast.walk(baum):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(m is not fn and isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
               and _dml_literal(m) for m in ast.walk(fn)):
            continue                      # nur die innerste Funktion zaehlt
        if not _dml_literal(fn) or (dateiname, fn.name) in AUSNAHMEN:
            continue
        if not any(_ist_schreibvorgang(w) for w in ast.walk(fn)):
            aus.append((dateiname, fn.name, fn.lineno))
    return aus


def pruefen(quelltext, dateiname="<test>"):
    """-> (r1_verstoesse [(datei, fn, zeile)], r2_verstoesse [...], geschuetzt)"""
    baum = ast.parse(quelltext)
    r1, r2, geschuetzt = [], [], []
    for fn in _innerste_committer(baum):
        schluessel = (dateiname, fn.name)
        if schluessel in AUSNAHMEN:
            continue
        hat = any(_ist_schreibvorgang(w) for w in ast.walk(fn))
        if not hat:
            r1.append((dateiname, fn.name, fn.lineno))
        else:
            geschuetzt.append(fn.name)
        for z in _r2_verstoesse(fn):
            r2.append((dateiname, fn.name, z))
    return r1, r2, geschuetzt


def _alles():
    r1, r2, gesch = [], [], {}
    for p in _dateien():
        rel = p.relative_to(WURZEL).as_posix()
        a, b, g = pruefen(p.read_text(encoding="utf-8"), rel)
        r1 += a
        r2 += b
        gesch[rel] = g
    return r1, r2, gesch


class TestWaechter(unittest.TestCase):

    def test_wt01_jede_schreibfunktion_im_schreibvorgang(self):
        r1, _r2, _g = _alles()
        self.assertEqual(r1, [], "Schreibfunktionen ohne 'with Schreibvorgang(...)'"
                         " (db/schreibvorgang.py) — oder mit Begruendung in "
                         "AUSNAHMEN eintragen: %r" % r1)

    def test_wt02_wer_db_fehler_verschluckt_rollt_zurueck(self):
        _r1, r2, _g = _alles()
        self.assertEqual(r2, [], "except-Behandler verschlucken einen DB-Fehler "
                         "ohne rollback(): %r" % r2)

    def test_wt03_ausnahmen_existieren(self):
        vorhanden = set()
        for p in _dateien():
            rel = p.relative_to(WURZEL).as_posix()
            for fn in _innerste_committer(ast.parse(p.read_text(encoding="utf-8"))):
                vorhanden.add((rel, fn.name))
        for p in _dateien():
            rel = p.relative_to(WURZEL).as_posix()
            for fn in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and _dml_literal(fn):
                    vorhanden.add((rel, fn.name))
        leichen = sorted(set(AUSNAHMEN) - vorhanden)
        self.assertEqual(leichen, [], "Ausnahmen ohne Gegenstueck im Code: %r" % leichen)

    def test_wt04_gegenprobe_waechter_faengt(self):
        ohne = (
            "def f(self):\n"
            "    self._con.execute('INSERT INTO t VALUES (1)')\n"
            "    self._con.commit()\n")
        r1, _r2, _g = pruefen(ohne)
        self.assertEqual([x[1] for x in r1], ["f"])
        verschluckt = (
            "def g(self):\n"
            "    with Schreibvorgang(self._con, 'g'):\n"
            "        try:\n"
            "            self._con.execute('INSERT INTO t VALUES (1)')\n"
            "            self._con.commit()\n"
            "        except sqlite3.IntegrityError:\n"
            "            return None\n")
        _r1, r2, _g = pruefen(verschluckt)
        self.assertEqual(len(r2), 1)
        mit_rollback = verschluckt.replace("return None",
                                           "self._con.rollback()\n            return None")
        self.assertEqual(pruefen(mit_rollback)[1], [])
        aussen = (
            "def h(self):\n"
            "    try:\n"
            "        with Schreibvorgang(self._con, 'h'):\n"
            "            self._con.execute('DELETE FROM t')\n"
            "            self._con.commit()\n"
            "    except Exception:\n"
            "        pass\n")
        self.assertEqual(pruefen(aussen)[:2], ([], []))
        # Nur lesender try-Block: kein Verstoss, auch ohne rollback.
        lesend = (
            "def k(self):\n"
            "    with Schreibvorgang(self._con, 'k'):\n"
            "        try:\n"
            "            self._con.execute('SELECT 1')\n"
            "        except Exception:\n"
            "            pass\n"
            "        self._con.commit()\n")
        self.assertEqual(pruefen(lesend)[1], [])
        # Nicht feststellbare Anweisung (Variable) zaehlt als schreibend.
        variabel = lesend.replace("'SELECT 1'", "sql")
        self.assertEqual(len(pruefen(variabel)[1]), 1)

    def test_wt05_anzahl_geschuetzt(self):
        _r1, _r2, g = _alles()
        self.assertEqual(len(g["db/evidence_db.py"]), 43)
        self.assertEqual(len(g["db/coordinator_db.py"]), 3)


    def test_wt06_dml_auch_ohne_commit_im_schreibvorgang(self):
        aus = []
        for p in _dateien():
            rel = p.relative_to(WURZEL).as_posix()
            aus += r3_pruefen(p.read_text(encoding="utf-8"), rel)
        self.assertEqual(aus, [], "DML ausserhalb des Schreibvorgangs: %r" % aus)
        # Gegenprobe am Beispiel: genau das Muster von get_sort_index_after
        # bis Build 774.
        alt = ("def get_sort_index_after(self):\n"
               "    self._con.execute('UPDATE report_block_order SET x = 1')\n"
               "    return 1\n")
        self.assertEqual([x[1] for x in r3_pruefen(alt)], ["get_sort_index_after"])


if __name__ == "__main__":
    unittest.main()
