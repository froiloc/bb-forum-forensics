# db/locking_connection.py
"""
LockingConnection — thread-sichere Serialisierung der geteilten SQLite-Verbindung.

HINTERGRUND (Beleg: Live-Diagnose 2026-07-06, aiw-Serverlog):
    Der Webserver laeuft mit socketserver.ThreadingMixIn (server/http_server.py:242),
    d. h. jeder HTTP-Request UND der langlebige SSE-Stream laufen in eigenen Threads.
    Alle Fach-DBs (forensic/coordinator/evidence/default/assets/templates) teilen sich
    EINE sqlite3.Connection (db/connection_manager.py). Ein sqlite3.Connection/Cursor ist
    NICHT fuer gleichzeitige Nutzung aus mehreren Threads geeignet: ueberlappende
    execute()/fetch()-Aufrufe korrumpieren den Verbindungszustand und werfen
    'sqlite3.InterfaceError: bad parameter or other API misuse' bzw. 'no more rows
    available'. Belegt durch identische get_page('/')-Aufrufe, die 22:43:13 gelangen und
    22:43:40 fehlschlugen (gleiche Eingabe, anderes Ergebnis => Zustandskorruption).
    Zusaetzlicher Code-Beleg: connection_manager.py:262-273 (Build 021) dokumentiert bereits,
    dass 'SSE-Thread und Request-Threads gleichzeitig die Connection nutzen'.

LOESUNG:
    Dieser Wrapper kapselt die EINE geteilte Verbindung. Ein einziger REENTRANTER Lock
    serialisiert JEDEN execute+fetch-Abschnitt. Weil ALLE Zugriffe zwangslaeufig durch
    dieses eine Objekt laufen, kann keine Zugriffsstelle 'vergessen' werden — es gibt genau
    ein Serialisierungs-Tor (statt >150 Einzelstellen).

MATERIALISIERUNG (warum execute sofort fetch't):
    Der Lock muss execute UND fetch umspannen — sonst koennte ein zweiter Thread zwischen
    execute() und fetchone() denselben realen Cursor uebernehmen. Deshalb holt execute()
    das Ergebnis unter dem Lock sofort vollstaendig in den Speicher (fetchall) und gibt einen
    Ergebnis-Cursor zurueck, der fetchone/fetchmany/fetchall/Iteration aus dem Speicher
    bedient. Fuer die Laufzeit-SELECTs (1 bzw. begrenzte Zeilen, z. B. get_page: 1 Zeile) ist
    das deckungsgleich mit dem bisherigen .fetchone()/.fetchall() — es gibt zur Laufzeit kein
    Lazy-Socket-Streaming vom geteilten con (BLOBs werden ohnehin per fetchone geladen).

ESKALATION:
    Der oeffentliche .lock (derselbe RLock) erlaubt kuenftig explizite Mehr-Statement-/
    Streaming-Abschnitte via 'with con.lock: ...'.

NICHT im Scope:
    Eigene, separate Verbindungen (support_presence.py, evidence_db.get_lock, Export/
    Cross-Annotation) besitzen jeweils EIGENE Connection-Objekte und teilen den geteilten
    con nicht — sie koennen dessen Cursor nicht korrumpieren (Datei-Ebene regelt WAL).

Build 325 — 2026-07-06.
"""

from __future__ import annotations

import sqlite3
import threading
from typing import Any, Iterator, List, Optional, Sequence


class _LockedCursor:
    """
    Ergebnis-/Cursor-Wrapper. Materialisiert das Query-Ergebnis unter dem Lock und bedient
    danach fetch*/Iteration aus dem Speicher. Deckt beide realen Zugriffsmuster ab:
      (a) con.execute(sql, params).fetchone()/.fetchall()/Iteration/.lastrowid/.rowcount
      (b) cur = con.cursor(); cur.row_factory = Row; cur.execute(...); cur.fetchone()
          (Belege: db/assets_db.py:192, db/default_db.py:137)
    """

    # Interne Attribute, die NICHT an den realen Cursor weitergereicht werden.
    _INTERNAL = ("_real", "_lock", "_rows", "_idx")

    def __init__(self, real_con: sqlite3.Connection, lock: "threading.RLock") -> None:
        object.__setattr__(self, "_lock", lock)
        object.__setattr__(self, "_real", real_con.cursor())
        object.__setattr__(self, "_rows", [])   # materialisierte Zeilen
        object.__setattr__(self, "_idx", 0)      # Leseposition

    # --- Ausfuehrung (unter Lock, mit Materialisierung) ---------------------
    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> "_LockedCursor":
        with self._lock:
            self._real.execute(sql, parameters)
            object.__setattr__(self, "_rows", self._real.fetchall())
            object.__setattr__(self, "_idx", 0)
        return self

    def executemany(self, sql: str, seq_of_parameters: Any) -> "_LockedCursor":
        with self._lock:
            self._real.executemany(sql, seq_of_parameters)
            object.__setattr__(self, "_rows", [])
            object.__setattr__(self, "_idx", 0)
        return self

    # --- Lesen aus dem materialisierten Puffer ------------------------------
    def fetchone(self) -> Any:
        if self._idx >= len(self._rows):
            return None
        row = self._rows[self._idx]
        object.__setattr__(self, "_idx", self._idx + 1)
        return row

    def fetchmany(self, size: Optional[int] = None) -> List[Any]:
        if size is None:
            size = self._real.arraysize
        end = min(self._idx + size, len(self._rows))
        chunk = self._rows[self._idx:end]
        object.__setattr__(self, "_idx", end)
        return chunk

    def fetchall(self) -> List[Any]:
        rest = self._rows[self._idx:]
        object.__setattr__(self, "_idx", len(self._rows))
        return rest

    def __iter__(self) -> Iterator[Any]:
        while self._idx < len(self._rows):
            row = self._rows[self._idx]
            object.__setattr__(self, "_idx", self._idx + 1)
            yield row

    def close(self) -> None:
        with self._lock:
            self._real.close()

    # --- Attribut-Proxy: lastrowid/rowcount/description/arraysize/row_factory
    def __getattr__(self, name: str) -> Any:
        # Nur aufgerufen, wenn Attribut nicht regulaer gefunden wurde.
        return getattr(object.__getattribute__(self, "_real"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _LockedCursor._INTERNAL:
            object.__setattr__(self, name, value)
        else:
            # z. B. cursor.row_factory = sqlite3.Row -> auf realen Cursor setzen
            setattr(object.__getattribute__(self, "_real"), name, value)


class LockingConnection:
    """
    Thread-sicherer Wrapper um die EINE geteilte sqlite3.Connection. Serialisiert alle
    execute/cursor/commit/rollback-Zugriffe ueber einen reentranten Lock. Nicht
    ueberschriebene Attribute/Methoden werden an die reale Verbindung weitergereicht
    (row_factory, set_authorizer, create_function, text_factory, backup, ...).
    """

    _INTERNAL = ("_con", "lock")

    def __init__(self, con: sqlite3.Connection) -> None:
        object.__setattr__(self, "_con", con)
        object.__setattr__(self, "lock", threading.RLock())

    # --- Kern: serialisierte Ausfuehrung mit Materialisierung ---------------
    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> _LockedCursor:
        cur = _LockedCursor(self._con, self.lock)
        return cur.execute(sql, parameters)

    def executemany(self, sql: str, seq_of_parameters: Any) -> _LockedCursor:
        cur = _LockedCursor(self._con, self.lock)
        return cur.executemany(sql, seq_of_parameters)

    def executescript(self, script: str) -> Any:
        # Zur Laufzeit auf dem geteilten con ungenutzt (Beleg: Muster-grep leer);
        # defensiv unter Lock durchgereicht, damit kuenftige Nutzung sicher bleibt.
        with self.lock:
            return self._con.executescript(script)

    def cursor(self) -> _LockedCursor:
        # Frischer, noch nicht ausgefuehrter Cursor (Muster assets_db/default_db).
        return _LockedCursor(self._con, self.lock)

    def commit(self) -> None:
        with self.lock:
            self._con.commit()

    def rollback(self) -> None:
        with self.lock:
            self._con.rollback()

    def close(self) -> None:
        with self.lock:
            self._con.close()

    # --- Kontextmanager (zur Laufzeit ungenutzt; spiegelt sqlite3-Semantik) --
    def __enter__(self) -> "LockingConnection":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        with self.lock:
            if exc_type is None:
                self._con.commit()
            else:
                self._con.rollback()
        return False  # Exceptions nicht unterdruecken

    # --- Attribut-Proxy fuer alles Uebrige ----------------------------------
    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_con"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in LockingConnection._INTERNAL:
            object.__setattr__(self, name, value)
        else:
            # z. B. con.row_factory = sqlite3.Row -> an reale Verbindung
            setattr(object.__getattribute__(self, "_con"), name, value)
