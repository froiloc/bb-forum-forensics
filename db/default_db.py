# =============================================================================
# db/default_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Kapselt alle Lesezugriffe auf die default.db (ATTACH-Alias: ddb).
#   Liefert statische Assets (CSS, Bilder, Smilies, Icons) anhand ihrer URL.
#   Schreibt niemals in ddb — READ-ONLY ist eine harte Invariante.
#
# Schema (ddb):
#   default_assets  — Inhalt der Assets als BLOB (Content-Hash als eindeutiger Key)
#   default_urls    — URL → Asset-Verknüpfung (url, url_hash, asset_id, ...)
#   default_meta    — Schlüssel-Wert-Metadaten
#
# Verwendung:
#   asset_handler.py ruft get_asset(url) auf und liefert das Ergebnis
#   direkt als HTTP-Response aus. Die MIME-Type-Information ist in der
#   DB gespeichert und wird 1:1 weitergereicht.
#
# Forensische Relevanz:
#   Statische Assets sind nutzerneutral — sie gehören zum Forum, nicht
#   zu einem Beschuldigten. Sie sind in default.db getrennt von den
#   forensischen Beweismitteln in forensic_<uid>.db gespeichert.
#
# Abhängigkeiten: sqlite3 — ausschließlich Stdlib
# Version: v0.1.0 · Build: 018 · 2026-04-15
# =============================================================================

from __future__ import annotations

import time
import sqlite3
from dataclasses import dataclass
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)

# Standard-MIME-Type wenn keiner in der DB gespeichert ist
_DEFAULT_MIME_TYPE = "application/octet-stream"


@dataclass(frozen=True)
class AssetRecord:
    """
    Ergebnisobjekt eines Asset-Lookups.

    Felder:
        url       — Die angeforderte URL
        data      — Binärinhalt des Assets (bytes), oder None wenn Abruf fehlschlug
        mime_type — MIME-Type des Assets, z.B. 'text/css', 'image/png'
        file_size — Größe in Bytes laut DB (kann von len(data) abweichen wenn NULL)
    """
    url:       str
    data:      Optional[bytes]
    mime_type: str
    file_size: Optional[int]

    @property
    def available(self) -> bool:
        """True wenn das Asset als Binärdaten vorliegt (data ist nicht None)."""
        return self.data is not None


class DefaultDb:
    """
    Kapselt alle Lesezugriffe auf ddb (default.db).

    Verwendung:
        ddb = DefaultDb(con)
        asset = ddb.get_asset("/forum/style/oxygen/oxygen.css")
        if asset and asset.available:
            return asset.data, asset.mime_type

    Die Instanz hält keine eigene Verbindung — sie arbeitet auf der
    übergebenen Verbindung von connection_manager.py.
    """

    def __init__(
        self,
        con: sqlite3.Connection,
        forum_base_url: Optional[str] = None,
    ) -> None:
        """
        Initialisiert DefaultDb.

        Args:
            con:            Geöffnete sqlite3.Connection mit angebundener ddb.
            forum_base_url: Vollständige Basis-URL des Original-Forums, z.B.
                            'http://alice4n...onion' (ohne abschließenden Slash).
                            Wird beim Asset-Lookup als Präfix vor den URL-Pfad
                            gestellt, falls default_urls ebenfalls vollständige
                            Onion-URLs als Schlüssel speichert.
                            Wenn None, wird der Pfad unverändert gesucht.

        Raises:
            sqlite3.OperationalError: Wenn ddb nicht angebunden ist.
        """
        self._con = con
        self._con.row_factory = sqlite3.Row
        # Abschließenden Slash entfernen für saubere Konkatenation
        self._forum_base_url: Optional[str] = (
            forum_base_url.rstrip("/") if forum_base_url else None
        )
        self._verify_attachment()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _verify_attachment(self) -> None:
        """
        Prüft ob ddb korrekt angebunden ist.

        Raises:
            sqlite3.OperationalError: Wenn ddb nicht erreichbar ist.
        """
        try:
            self._con.execute("SELECT COUNT(*) FROM ddb.default_assets").fetchone()
            logger.debug("ddb (default.db) korrekt angebunden und erreichbar")
        except sqlite3.OperationalError as exc:
            raise sqlite3.OperationalError(
                f"ddb (default.db) nicht erreichbar oder falsch angebunden.\n"
                f"SQLite-Fehler: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Asset-Lookup
    # ------------------------------------------------------------------

    def _retryable_query(self, sql: str, params=(), max_retries: int = 3) -> Optional[sqlite3.Row]:
        delay = 0.1
        for attempt in range(max_retries):
            cursor = None
            try:
                cursor = self._con.cursor()
                cursor.row_factory = sqlite3.Row
                cursor.execute(sql, params)
                row = cursor.fetchone()
                # Prüfe auf leeres Row-Objekt (Länge 0)
                if row is not None and hasattr(row, "__len__") and len(row) == 0:
                    raise IndexError("Leeres Row-Objekt (Länge 0)")
                return row
            except (sqlite3.InterfaceError, sqlite3.OperationalError, IndexError, TypeError) as exc:
                logger.warning(
                    "Query fehlgeschlagen (Versuch %d/%d): %s - %s",
                    attempt + 1, max_retries, sql[:80], exc
                )
                if cursor:
                    try:
                        cursor.close()
                    except Exception:
                        pass
                try:
                    self._con.rollback()
                except Exception:
                    pass
                if attempt == max_retries - 1:
                    logger.error("Query nach %d Versuchen aufgegeben: %s", max_retries, sql[:80])
                    return None
                time.sleep(delay)
                delay *= 2
        return None

    def get_asset(self, url: str) -> Optional[AssetRecord]:
        lookup_url = f"{self._forum_base_url}{url}" if self._forum_base_url else url

        row = self._retryable_query(
            """
            SELECT du.url, da.data, da.mime_type, da.file_size
            FROM ddb.default_urls du
            LEFT JOIN ddb.default_assets da ON da.id = du.asset_id
            WHERE du.url = ? LIMIT 1
            """,
            (lookup_url,)
        )

        if row is None:
            logger.debug("Asset nicht in default.db: '%s'", url)
            return None

        # row ist garantiert ein gültiges sqlite3.Row (Länge >= 4) durch _retryable_query
        try:
            asset_url = str(row[0])
            data = row[1]
            mime_type = str(row[2]) if row[2] else _DEFAULT_MIME_TYPE
            file_size = int(row[3]) if row[3] is not None else None
        except (IndexError, TypeError) as exc:
            logger.error("Unerwarteter Extraktionsfehler für '%s': %s (row: %r)", url, exc, row)
            return None

        return AssetRecord(
            url=asset_url,
            data=data,
            mime_type=mime_type,
            file_size=file_size,
        )
        
    def has_asset(self, url: str) -> bool:
        """
        Prüft ob eine URL in default_urls bekannt ist (ohne Daten zu laden).
        Effizienter als get_asset() wenn nur die Existenz geprüft werden soll.

        Wendet dieselbe URL-Normalisierung an wie get_asset() (Onion-Präfix).

        Args:
            url: URL-Pfad des Assets.

        Returns:
            True wenn die URL in default_urls eingetragen ist.
        """
        lookup_url = (
            f"{self._forum_base_url}{url}"
            if self._forum_base_url
            else url
        )
        try:
            row = self._con.execute(
                "SELECT 1 FROM ddb.default_urls WHERE url = ? LIMIT 1",
                (lookup_url,),
            ).fetchone()
            return row is not None
        except sqlite3.OperationalError:
            return False

    def get_meta(self, key: str) -> Optional[str]:
        """
        Liest einen Wert aus ddb.default_meta.

        Args:
            key: Schlüssel, z.B. 'schema_version', 'created_at'.

        Returns:
            Wert als String, oder None wenn nicht gefunden.
        """
        try:
            row = self._con.execute(
                "SELECT value FROM ddb.default_meta WHERE key = ?",
                (key,),
            ).fetchone()
            return str(row["value"]) if row else None
        except sqlite3.OperationalError as exc:
            logger.error("get_meta('%s') fehlgeschlagen: %s", key, exc)
            return None


    def get_username_by_uid(self, user_id: int) -> str | None:
        """
        Schlaegt einen Forum-Benutzernamen anhand der user_id in known_users nach.
        Wird vom knownusers/resolve-Endpunkt und vom Popup (Bug 2.92) verwendet.

        Returns:
            username-String wenn gefunden, None wenn nicht in known_users.
        Beleg: Projektgespraech 2026-05-12 — Bug 2.92 (BS3).
        """
        try:
            row = self._con.execute(
                "SELECT username FROM ddb.known_users WHERE user_id = ? LIMIT 1",
                (user_id,),
            ).fetchone()
            return str(row["username"]) if row else None
        except Exception as exc:
            logger.warning(
                "get_username_by_uid(%d): Abfrage fehlgeschlagen: %s", user_id, exc
            )
            return None

    def search_known_users(self, query: str, limit: int = 20) -> list[dict]:
        """
        Sucht in known_users und known_aliases nach Benutzern, deren Username
        oder Alias den Suchbegriff enthält (LIKE-Suche, case-insensitive).

        Wird von KnownUsersEndpoint (/_forensic/knownusers?q=...) aufgerufen.

        Architektur-Hinweis:
          - known_users und known_aliases werden vom aiw_sqlite_prepper in
            default.db befüllt (BS0, Bugs 2.82+2.83).
          - Benötigte Tabellen + Indizes (angelegt vom Prepper):
              known_users  (user_id INTEGER PK, username TEXT NOT NULL)
              known_aliases(alias_id INTEGER PK AUTOINCREMENT,
                            user_id  INTEGER REFERENCES known_users(user_id),
                            name     TEXT NOT NULL)  -- Spalte heisst 'name' (Build 183 Fix)
              INDEX known_users_username_idx ON known_users(username COLLATE NOCASE)
              INDEX known_aliases_name_idx   ON known_aliases(name    COLLATE NOCASE)
          - default.db ist READ-ONLY: diese Methode schreibt nie.
          - Suche erst ab 4 Zeichen (Pflicht, wegen 500k+ Einträgen).

        Args:
            query: Suchbegriff (mind. 4 Zeichen, sonst leere Liste).
            limit: Maximale Trefferanzahl (Default: 20).

        Returns:
            Liste von {"user_id": int, "username": str, "matched_alias": str|None}.
            matched_alias ist None wenn der Treffer auf username basiert,
            sonst der gematchte Alias-String.

        Beleg: Projektgespräch 2026-05-12 — Bugs 2.78/2.82/2.83 (BS3/BS0).
        """
        # Sicherheitsnetz: Suche erst ab 4 Zeichen (Performance bei 500k Einträgen)
        if not query or len(query.strip()) < 4:
            return []

        q = query.strip()
        pattern = "%" + q + "%"

        results: list[dict] = []

        try:
            # Treffer direkt auf username
            rows = self._con.execute(
                """
                SELECT user_id, username
                FROM ddb.known_users
                WHERE username LIKE ? COLLATE NOCASE
                LIMIT ?
                """,
                (pattern, limit),
            ).fetchall()
            seen_ids: set[int] = set()
            for row in rows:
                uid = int(row["user_id"])
                seen_ids.add(uid)
                results.append({
                    "user_id":      uid,
                    "username":     str(row["username"]),
                    "matched_alias": None,
                })
        except Exception as exc:
            logger.warning(
                "search_known_users: known_users-Abfrage fehlgeschlagen: %s", exc
            )
            # Tabelle existiert noch nicht (Prepper hat noch nicht befüllt)
            return []

        # Treffer über Aliasse — bis Limit auffüllen
        remaining = limit - len(results)
        if remaining > 0:
            try:
                # Bug 3.9 (Build 183): Spalte heisst 'name', nicht 'alias'.
                # Beleg: Webserver-Log, Fehler 'no such column: ka.alias'.
                alias_rows = self._con.execute(
                    """
                    SELECT ka.user_id, ku.username, ka.name
                    FROM ddb.known_aliases ka
                    JOIN ddb.known_users ku ON ku.user_id = ka.user_id
                    WHERE ka.name LIKE ? COLLATE NOCASE
                    LIMIT ?
                    """,
                    (pattern, remaining * 2),
                ).fetchall()
                for row in alias_rows:
                    uid = int(row["user_id"])
                    if uid in seen_ids:
                        continue
                    seen_ids.add(uid)
                    results.append({
                        "user_id":      uid,
                        "username":     str(row["username"]),
                        "matched_alias": str(row["name"]),
                    })
                    if len(results) >= limit:
                        break
            except Exception as exc:
                logger.warning(
                    "search_known_users: known_aliases-Abfrage fehlgeschlagen: %s", exc
                )
                # Alias-Tabelle fehlt noch — kein Fehler, nur username-Treffer zurückgeben

        return results

    def asset_count(self) -> int:
        """Gibt die Anzahl der gespeicherten Assets zurück. Für Statusanzeigen."""
        try:
            row = self._con.execute(
                "SELECT COUNT(*) FROM ddb.default_assets"
            ).fetchone()
            return int(row[0]) if row else 0
        except sqlite3.OperationalError:
            return 0
