"""
tests/test_locking_connection.py — Build 325

Zwei Testgruppen:

1) CONTRACT (gegen echte sqlite3-:memory:-Verbindung): Der Wrapper bildet alle realen
   Zugriffsmuster deckungsgleich ab — execute().fetchone()/.fetchall()/Iteration,
   lastrowid (INSERT), rowcount (UPDATE), cursor()+row_factory (Muster assets_db/default_db),
   commit/rollback, .lock-Reentranz.

2) SERIALISIERUNG (deterministischer Nachweis via Overlap-Detektor, OHNE echte DB): Beweist,
   dass LockingConnection gleichzeitigen Zugriff wirklich serialisiert — unabhaengig vom
   SQLite-Threading-Modus der jeweiligen Umgebung (kein Verlass auf zufaellige native
   Korruption, daher nicht flaky). Kein 'gruen-aber-tot': ein Gegen-Test weist nach, dass
   der Detektor bei UNSERIALISIERTEM Zugriff tatsaechlich Verletzungen meldet.

Beleg der Notwendigkeit: Live-Diagnose 2026-07-06 (aiw-Serverlog) — identische get_page('/')
scheiterten unter Nebenlaeufigkeit mit 'sqlite3.InterfaceError: bad parameter or other API
misuse'; Ursache: geteilte sqlite3.Connection unter socketserver.ThreadingMixIn.
"""

import sqlite3
import threading
import time

import pytest

from db.locking_connection import LockingConnection


# ============================================================================
# 1) CONTRACT — gegen echte sqlite3-Verbindung
# ============================================================================

def _make_real_db():
    raw = sqlite3.connect(":memory:", check_same_thread=False)
    raw.row_factory = sqlite3.Row
    raw.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    raw.executemany("INSERT INTO t (val) VALUES (?)", [(f"v{i}",) for i in range(200)])
    raw.commit()
    return raw


class TestContract:
    def setup_method(self):
        self.con = LockingConnection(_make_real_db())

    def test_execute_fetchone(self):
        row = self.con.execute("SELECT val FROM t WHERE id=?", (1,)).fetchone()
        assert row["val"] == "v0"

    def test_execute_fetchall(self):
        rows = self.con.execute("SELECT val FROM t ORDER BY id").fetchall()
        assert len(rows) == 200
        assert rows[0]["val"] == "v0" and rows[-1]["val"] == "v199"

    def test_iteration(self):
        vals = [r["val"] for r in self.con.execute("SELECT val FROM t ORDER BY id")]
        assert len(vals) == 200

    def test_fetchmany(self):
        cur = self.con.execute("SELECT val FROM t ORDER BY id")
        first = cur.fetchmany(10)
        assert len(first) == 10
        rest = cur.fetchall()
        assert len(rest) == 190

    def test_lastrowid(self):
        cur = self.con.execute("INSERT INTO t (val) VALUES (?)", ("neu",))
        assert cur.lastrowid == 201

    def test_rowcount(self):
        cur = self.con.execute("UPDATE t SET val=? WHERE id<=?", ("x", 5))
        assert cur.rowcount == 5

    def test_cursor_pattern(self):
        # Muster aus assets_db.py:192 / default_db.py:137
        cur = self.con.cursor()
        cur.row_factory = sqlite3.Row
        cur.execute("SELECT val FROM t WHERE id=?", (2,))
        assert cur.fetchone()["val"] == "v1"

    def test_row_factory_forwarding(self):
        # Zuweisung am Wrapper muss an die reale Verbindung durchgereicht werden.
        self.con.row_factory = None
        r = self.con.execute("SELECT val FROM t WHERE id=1").fetchone()
        assert isinstance(r, tuple)  # ohne Row-Factory -> Tupel

    def test_commit_rollback(self):
        self.con.execute("INSERT INTO t (val) VALUES ('c')")
        self.con.commit()
        self.con.execute("INSERT INTO t (val) VALUES ('r')")
        self.con.rollback()
        n = self.con.execute(
            "SELECT COUNT(*) FROM t WHERE val IN ('c','r')"
        ).fetchone()[0]
        assert n == 1

    def test_lock_is_reentrant(self):
        with self.con.lock:
            with self.con.lock:  # RLock: darf nicht blockieren
                assert self.con.execute("SELECT 1").fetchone()[0] == 1

    def test_attribute_proxy(self):
        # Nicht ueberschriebene Attribute werden an die reale Verbindung gereicht.
        assert callable(self.con.set_authorizer)


# ============================================================================
# 2) SERIALISIERUNG — deterministischer Overlap-Detektor (ohne echte DB)
# ============================================================================

class _FakeCursor:
    """Meldet gleichzeitigen Zugriff. time.sleep() oeffnet ein sicheres Overlap-Fenster."""
    def __init__(self, owner):
        object.__setattr__(self, "_owner", owner)
        object.__setattr__(self, "_rows", [])
        object.__setattr__(self, "lastrowid", 0)
        object.__setattr__(self, "rowcount", -1)
        object.__setattr__(self, "description", None)
        object.__setattr__(self, "arraysize", 1)

    def execute(self, sql, parameters=()):
        o = self._owner
        with o.guard:
            o.active += 1
            if o.active > 1:
                o.violations.append(sql)
        time.sleep(0.003)                      # Fenster: hier wuerde Overlap sichtbar
        with o.guard:
            o.active -= 1
        object.__setattr__(self, "_rows", [(1,), (2,), (3,)])
        return self

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchmany(self, size=1):
        return self._rows[:size]

    def close(self):
        pass


class _FakeConnection:
    """Minimaler sqlite3.Connection-Ersatz fuer den Serialisierungsnachweis."""
    def __init__(self):
        self.active = 0
        self.violations = []
        self.guard = threading.Lock()

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        pass

    def rollback(self):
        pass


def _run_threads(target, n_threads=12, n_ops=15):
    """
    Startet n_threads Threads mit je n_ops Aufrufen und gibt die Zahl der
    ERFOLGREICHEN Aufrufe sowie die aufgetretenen Ausnahmen zurueck.

    Build 774: Vorher gingen Ausnahmen in den Threads verloren (ein Thread,
    der wirft, endet nur — der Test merkt davon nichts). So blieb
    test_wrapper_prevents_overlap gruen, obwohl JEDER Aufruf scheiterte
    (gemessen 14.10.2026 an einer Zwischenfassung von Build 774, die auf der
    Attrappe nach 'in_transaction' fragte): keine Ausfuehrung, also auch keine
    Ueberlappung. Jetzt zaehlt der Aufrufer die Erfolge mit.
    """
    barrier = threading.Barrier(n_threads)
    erfolge = []
    fehler = []
    schutz = threading.Lock()

    def worker():
        barrier.wait()                          # alle gleichzeitig starten
        for _ in range(n_ops):
            try:
                target()
            except Exception as exc:            # noqa: BLE001 — wird gezaehlt
                with schutz:
                    fehler.append(exc)
            else:
                with schutz:
                    erfolge.append(1)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return len(erfolge), fehler


class TestSerialization:
    def test_wrapper_prevents_overlap(self):
        """Der Wrapper serialisiert: der Detektor sieht NIE gleichzeitigen Zugriff."""
        fake = _FakeConnection()
        con = LockingConnection(fake)

        def op():
            con.execute("SELECT 1").fetchall()

        erfolge, fehler = _run_threads(op)
        # Build 774: ohne diese beiden Zeilen ist der Test bei lauter
        # scheiternden Aufrufen 'gruen aber tot'.
        assert fehler == [], f"{len(fehler)} Aufrufe scheiterten: {fehler[:1]!r}"
        assert erfolge == 12 * 15
        assert fake.violations == [], (
            "LockingConnection muss gleichzeitigen Zugriff verhindern, "
            f"sah aber {len(fake.violations)} Overlaps"
        )

    def test_unserialized_access_is_detected(self):
        """Gegen-Test (kein 'gruen-aber-tot'): OHNE Wrapper meldet der Detektor Overlaps."""
        fake = _FakeConnection()

        def op():
            cur = fake.cursor()                 # direkter, unserialisierter Zugriff
            cur.execute("SELECT 1")
            cur.fetchall()

        _run_threads(op)
        assert fake.violations, (
            "Der Overlap-Detektor muss unserialisierten Zugriff erkennen — "
            "sonst waere der Wrapper-Test wirkungslos."
        )
