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

    def asset_count(self) -> int:
        """Gibt die Anzahl der gespeicherten Assets zurück. Für Statusanzeigen."""
        try:
            row = self._con.execute(
                "SELECT COUNT(*) FROM ddb.default_assets"
            ).fetchone()
            return int(row[0]) if row else 0
        except sqlite3.OperationalError:
            return 0
