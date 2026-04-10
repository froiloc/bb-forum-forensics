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
# Version: v0.1.0 · Build: 007 · 2026-04-10
# =============================================================================

from __future__ import annotations

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

    def __init__(self, con: sqlite3.Connection) -> None:
        """
        Initialisiert DefaultDb.

        Args:
            con: Geöffnete sqlite3.Connection mit angebundener ddb.

        Raises:
            sqlite3.OperationalError: Wenn ddb nicht angebunden ist.
        """
        self._con = con
        self._con.row_factory = sqlite3.Row
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

    def get_asset(self, url: str) -> Optional[AssetRecord]:
        """
        Sucht ein Asset anhand seiner URL.

        Lookup-Pfad:
          ddb.default_urls (url) → ddb.default_assets (data, mime_type)

        Args:
            url: URL des Assets, z.B. '/forum/style/oxygen/main.css'

        Returns:
            AssetRecord wenn die URL bekannt ist (auch wenn data=None),
            None wenn die URL nicht in default_urls eingetragen ist.
        """
        try:
            row = self._con.execute(
                """
                SELECT
                    du.url,
                    da.data,
                    da.mime_type,
                    da.file_size
                FROM ddb.default_urls du
                LEFT JOIN ddb.default_assets da ON da.id = du.asset_id
                WHERE du.url = ?
                LIMIT 1
                """,
                (url,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            logger.error("Asset-Lookup fehlgeschlagen für '%s': %s", url, exc)
            return None

        if row is None:
            logger.debug("Asset nicht in default.db: '%s'", url)
            return None

        mime_type = str(row["mime_type"]) if row["mime_type"] else _DEFAULT_MIME_TYPE
        record = AssetRecord(
            url=str(row["url"]),
            data=row["data"],   # bytes oder None
            mime_type=mime_type,
            file_size=int(row["file_size"]) if row["file_size"] is not None else None,
        )
        logger.debug(
            "Asset gefunden: '%s' → %s, %s bytes, available=%s",
            url, mime_type,
            record.file_size if record.file_size is not None else "?",
            record.available,
        )
        return record

    def has_asset(self, url: str) -> bool:
        """
        Prüft ob eine URL in default_urls bekannt ist (ohne Daten zu laden).
        Effizienter als get_asset() wenn nur die Existenz geprüft werden soll.

        Args:
            url: URL des Assets.

        Returns:
            True wenn die URL in default_urls eingetragen ist.
        """
        try:
            row = self._con.execute(
                "SELECT 1 FROM ddb.default_urls WHERE url = ? LIMIT 1",
                (url,),
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
