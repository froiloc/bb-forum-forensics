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

BUILD 774 — TRANSAKTIONS-BESITZER UND SICHERHEITSNETZ (Befund 13./14.10.2026):
    Eine gescheiterte Schreibanweisung ohne rollback() liess die Transaktion der
    geteilten Verbindung offen; jede folgende Lesung auf coordinator.db (cdb)
    hielt darin eine SHARED-Sperre, und der Bildschleier-Schreiber einer anderen
    Verbindung bekam nach 5 s 'database is locked'.
    Abhilfe 1 (db/schreibvorgang.py): jede Schreibfunktion rollt bei Fehlern
    selbst zurueck. Abhilfe 2 (hier): der Wrapper merkt sich, WELCHER Thread die
    laufende Transaktion eroeffnet hat (transaktions_besitzer). Am Ende jedes
    HTTP-Requests ruft der Server sicherheitsnetz() auf. Zurueckgerollt wird NUR,
    wenn dieser Thread der Besitzer ist — die halbfertige Transaktion eines
    gleichzeitig laufenden anderen Requests bleibt unberuehrt (Festlegung Alex,
    14.10.2026: "Rollback nur im Thread, der die Transaktion eroeffnet hat").
    Eine Zaehlung laufender Requests haette nicht gereicht: die SSE-Verbindung
    des Berichtseditors ist dauerhaft offen und zaehlt immer mit.
"""

from __future__ import annotations

import sqlite3
import threading
from typing import Any, Callable, Iterator, List, Optional, Sequence

from core.logger import get_logger

logger = get_logger(__name__)


class _LockedCursor:
    """
    Ergebnis-/Cursor-Wrapper. Materialisiert das Query-Ergebnis unter dem Lock und bedient
    danach fetch*/Iteration aus dem Speicher. Deckt beide realen Zugriffsmuster ab:
      (a) con.execute(sql, params).fetchone()/.fetchall()/Iteration/.lastrowid/.rowcount
      (b) cur = con.cursor(); cur.row_factory = Row; cur.execute(...); cur.fetchone()
          (Belege: db/assets_db.py:192, db/default_db.py:137)
    """

    # Interne Attribute, die NICHT an den realen Cursor weitergereicht werden.
    _INTERNAL = ("_real", "_lock", "_rows", "_idx", "_waechter", "_real_con")

    def __init__(self, real_con: sqlite3.Connection, lock: "threading.RLock",
                 waechter: Optional[Callable[[bool], None]] = None) -> None:
        object.__setattr__(self, "_lock", lock)
        object.__setattr__(self, "_real", real_con.cursor())
        object.__setattr__(self, "_rows", [])   # materialisierte Zeilen
        object.__setattr__(self, "_idx", 0)      # Leseposition
        # Build 774: Rueckruf an die LockingConnection nach jeder Ausfuehrung,
        # damit sie den Transaktions-Besitzer fuehren kann. Bekommt den
        # Zustand in_transaction VOR der Anweisung.
        object.__setattr__(self, "_waechter", waechter)
        object.__setattr__(self, "_real_con", real_con)

    def _vorher_offen(self) -> bool:
        # getattr mit Vorgabe: auch Verbindungs-Attrappen ohne in_transaction
        # (tests/test_locking_connection.py, _FakeConnection) muessen gehen.
        try:
            return bool(getattr(self._real_con, "in_transaction", False))
        except sqlite3.Error:
            return False

    # --- Ausfuehrung (unter Lock, mit Materialisierung) ---------------------
    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> "_LockedCursor":
        with self._lock:
            vorher = self._vorher_offen()
            try:
                self._real.execute(sql, parameters)
                object.__setattr__(self, "_rows", self._real.fetchall())
                object.__setattr__(self, "_idx", 0)
            finally:
                # AUCH nach einem Fehler: genau dann bleibt die Transaktion
                # offen (implizites BEGIN gelungen, Anweisung gescheitert).
                if self._waechter is not None:
                    self._waechter(vorher)
        return self

    def executemany(self, sql: str, seq_of_parameters: Any) -> "_LockedCursor":
        with self._lock:
            vorher = self._vorher_offen()
            try:
                self._real.executemany(sql, seq_of_parameters)
                object.__setattr__(self, "_rows", [])
                object.__setattr__(self, "_idx", 0)
            finally:
                if self._waechter is not None:
                    self._waechter(vorher)
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

    _INTERNAL = ("_con", "lock", "_besitzer", "_unbekannt_gemeldet")

    def __init__(self, con: sqlite3.Connection) -> None:
        object.__setattr__(self, "_con", con)
        object.__setattr__(self, "lock", threading.RLock())
        # Build 774: Thread-Kennung (threading.get_ident) des Threads, dessen
        # Anweisung die laufende Transaktion eroeffnet hat; None = keine offen
        # bzw. unbekannt.
        object.__setattr__(self, "_besitzer", None)
        object.__setattr__(self, "_unbekannt_gemeldet", False)

    # --- Build 774: Transaktions-Besitzer -----------------------------------
    def _transaktion_beobachten(self, vorher_offen: bool) -> None:
        """Nach jeder Anweisung (unter dem Lock): Besitzer fortschreiben."""
        try:
            offen = bool(getattr(self._con, "in_transaction", False))
        except sqlite3.Error:
            return
        if offen and not vorher_offen:
            object.__setattr__(self, "_besitzer", threading.get_ident())
        elif not offen:
            object.__setattr__(self, "_besitzer", None)
            object.__setattr__(self, "_unbekannt_gemeldet", False)

    @property
    def transaktions_besitzer(self) -> Optional[int]:
        """Thread-Kennung des Eroeffners der offenen Transaktion, sonst None."""
        return self._besitzer

    def sicherheitsnetz(self, kontext: str) -> Optional[str]:
        """
        Am Ende eines HTTP-Requests im Request-Thread aufzurufen.

        Ist eine Transaktion offen und hat DIESER Thread sie eroeffnet, wurde
        eine Schreibstelle ohne Transaktionsschutz verlassen: rollback() und
        Meldung der Stufe ERROR mit dem Kontext (Methode und Pfad).
        Rueckgabe: 'zurueckgerollt', 'rollback_gescheitert', 'unbekannt'
        (offen, Eroeffner unbekannt — nur gemeldet, einmal je Transaktion)
        oder None (nichts zu tun, auch: fremder Besitzer -> unberuehrt).
        """
        with self.lock:
            try:
                offen = bool(getattr(self._con, "in_transaction", False))
            except sqlite3.Error:
                return None              # z. B. geschlossene Verbindung
            if not offen:
                object.__setattr__(self, "_besitzer", None)
                object.__setattr__(self, "_unbekannt_gemeldet", False)
                return None
            ich = threading.get_ident()
            if self._besitzer == ich:
                try:
                    self._con.rollback()
                except sqlite3.Error as exc:
                    logger.error(
                        "Sicherheitsnetz: offene Transaktion am Ende von %s "
                        "gefunden, rollback() gescheitert: %s: %s",
                        kontext, type(exc).__name__, exc)
                    return "rollback_gescheitert"
                object.__setattr__(self, "_besitzer", None)
                logger.error(
                    "Sicherheitsnetz: offene Transaktion am Ende von %s "
                    "zurueckgerollt (Thread %s). Ursache ist eine Schreibstelle "
                    "ohne Transaktionsschutz (db/schreibvorgang.py) — bitte "
                    "dieses Protokoll melden.", kontext, ich)
                return "zurueckgerollt"
            if self._besitzer is None and not self._unbekannt_gemeldet:
                object.__setattr__(self, "_unbekannt_gemeldet", True)
                logger.warning(
                    "Sicherheitsnetz: am Ende von %s ist eine Transaktion "
                    "offen, deren Eroeffner unbekannt ist. Sie bleibt "
                    "unberuehrt.", kontext)
                return "unbekannt"
            return None

    # --- Kern: serialisierte Ausfuehrung mit Materialisierung ---------------
    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> _LockedCursor:
        cur = _LockedCursor(self._con, self.lock, self._transaktion_beobachten)
        return cur.execute(sql, parameters)

    def executemany(self, sql: str, seq_of_parameters: Any) -> _LockedCursor:
        cur = _LockedCursor(self._con, self.lock, self._transaktion_beobachten)
        return cur.executemany(sql, seq_of_parameters)

    def executescript(self, script: str) -> Any:
        # Zur Laufzeit auf dem geteilten con ungenutzt (Beleg: Muster-grep leer);
        # defensiv unter Lock durchgereicht, damit kuenftige Nutzung sicher bleibt.
        with self.lock:
            try:
                vorher = bool(getattr(self._con, "in_transaction", False))
            except sqlite3.Error:
                vorher = False
            try:
                return self._con.executescript(script)
            finally:
                self._transaktion_beobachten(vorher)

    def cursor(self) -> _LockedCursor:
        # Frischer, noch nicht ausgefuehrter Cursor (Muster assets_db/default_db).
        return _LockedCursor(self._con, self.lock, self._transaktion_beobachten)

    def commit(self) -> None:
        with self.lock:
            try:
                self._con.commit()
            finally:
                self._transaktion_beobachten(True)

    def rollback(self) -> None:
        with self.lock:
            try:
                self._con.rollback()
            finally:
                self._transaktion_beobachten(True)

    def close(self) -> None:
        with self.lock:
            self._con.close()

    # --- Kontextmanager (zur Laufzeit ungenutzt; spiegelt sqlite3-Semantik) --
    def __enter__(self) -> "LockingConnection":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        with self.lock:
            try:
                if exc_type is None:
                    self._con.commit()
                else:
                    self._con.rollback()
            finally:
                self._transaktion_beobachten(True)
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
