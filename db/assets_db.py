# =============================================================================
# db/assets_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Kapselt alle Lesezugriffe auf die assets_<uid>.db (ATTACH-Alias: adb).
#   Liefert nutzerspezifische Binär-Assets (Avatare, Post-Bilder,
#   Signatur-Grafiken) anhand ihrer URL.
#   Schreibt niemals in adb — READ-ONLY ist eine harte Invariante.
#
# Schema (adb):
#   assets      — Inhalt der Assets als BLOB (content_hash als eindeutiger Key)
#   asset_urls  — URL → Asset-Verknüpfung (url, url_hash, asset_id,
#                  url_context, page_id)
#   assets_meta — Schlüssel-Wert-Metadaten
#
# Unterschied zu default_db.py:
#   - Tabellennamen: assets / asset_urls / assets_meta
#     (nicht: default_assets / default_urls / default_meta)
#   - Kein fetched_at-Feld in assets
#   - ATTACH-Alias: adb (nicht ddb)
#   - Fehlende Datei ist KEIN harter Fehler — assets_<uid>.db entsteht
#     erst nach dem asset_importer-Lauf. AssetsDb akzeptiert con=None
#     und gibt bei allen Lookups None / False zurück.
#
# Verwendung (durch asset_handler.py):
#   asset = bundle.assets.get_asset("/forum/img/avatars/18.jpg")
#   if asset and asset.available:
#       return asset.data, asset.mime_type
#
# Forensische Relevanz:
#   Avatare und Post-Bilder sind nutzerspezifisch und können einen
#   identifikatorischen Wert haben (z.B. wiedererkennbare Profilbilder).
#   Sie werden daher getrennt von den nutzerneutralen Forumsassets in
#   default.db gespeichert.
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
    Ergebnisobjekt eines Asset-Lookups aus assets_<uid>.db.

    Identisch zu DefaultDb.AssetRecord — gleicher Vertrag, damit
    asset_handler.py beide Quellen transparent kaskadieren kann.

    Felder:
        url       — Die angeforderte URL
        data      — Binärinhalt des Assets (bytes), oder None wenn Abruf fehlschlug
        mime_type — MIME-Type des Assets, z.B. 'image/jpeg', 'image/png'
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


class AssetsDb:
    """
    Kapselt alle Lesezugriffe auf adb (assets_<uid>.db).

    Fehlende Datenbank:
        Wenn con=None übergeben wird (assets_<uid>.db nicht vorhanden),
        geben alle Methoden None / False zurück — kein Absturz, da die
        Datei erst nach dem asset_importer-Lauf existiert.

    Verwendung:
        adb = AssetsDb(con)          # con ist Haupt-Connection mit ATTACH adb
        asset = adb.get_asset("/forum/img/avatars/18.jpg")
        if asset and asset.available:
            return asset.data, asset.mime_type

    Die Instanz hält keine eigene Verbindung — sie arbeitet auf der
    übergebenen Verbindung von connection_manager.py.
    """

    def __init__(
        self,
        con: Optional[sqlite3.Connection],
        forum_base_url: Optional[str] = None,
    ) -> None:
        """
        Initialisiert AssetsDb.

        Args:
            con:            Geöffnete sqlite3.Connection mit angebundener adb,
                            oder None wenn assets_<uid>.db nicht existiert.
            forum_base_url: Vollständige Basis-URL des Original-Forums, z.B.
                            'http://alice4n...onion' (ohne abschließenden Slash).
                            Wird beim Asset-Lookup als Präfix vor den URL-Pfad
                            gestellt, da asset_urls die vollständige Onion-URL
                            als Schlüssel speichert.
                            Wenn None, wird der Pfad unverändert gesucht (Fallback,
                            z.B. wenn forensic_meta noch nicht befüllt ist).

        Raises:
            sqlite3.OperationalError: Wenn con gesetzt ist, aber adb nicht
                                      korrekt angebunden ist.
        """
        self._con = con
        # Abschließenden Slash entfernen für saubere Konkatenation
        self._forum_base_url: Optional[str] = (
            forum_base_url.rstrip("/") if forum_base_url else None
        )
        self._available = False

        if con is not None:
            self._con.row_factory = sqlite3.Row
            self._verify_attachment()
        else:
            logger.debug(
                "AssetsDb: con=None — assets_<uid>.db nicht verfügbar. "
                "Alle Lookups geben None / False zurück."
            )

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _verify_attachment(self) -> None:
        """
        Prüft ob adb korrekt angebunden ist.

        Setzt self._available = True wenn erfolgreich.

        Raises:
            sqlite3.OperationalError: Wenn adb nicht erreichbar ist.
        """
        try:
            self._con.execute("SELECT COUNT(*) FROM adb.assets").fetchone()
            self._available = True
            logger.debug("adb (assets_<uid>.db) korrekt angebunden und erreichbar")
        except sqlite3.OperationalError as exc:
            raise sqlite3.OperationalError(
                f"adb (assets_<uid>.db) nicht erreichbar oder falsch angebunden.\n"
                f"SQLite-Fehler: {exc}"
            ) from exc

    @property
    def is_available(self) -> bool:
        """True wenn assets_<uid>.db angebunden und erreichbar ist."""
        return self._available

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
        if not self._available:
            return None
        lookup_url = f"{self._forum_base_url}{url}" if self._forum_base_url else url

        row = self._retryable_query(
            """
            SELECT au.url, a.data, a.mime_type, a.file_size
            FROM adb.asset_urls au
            LEFT JOIN adb.assets a ON a.id = au.asset_id
            WHERE au.url = ? LIMIT 1
            """,
            (lookup_url,)
        )

        if row is None:
            logger.debug("Asset nicht in assets_<uid>.db: '%s'", url)
            return None

        # row ist garantiert ein gültiges sqlite3.Row (Länge >= 4)
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
        Prüft ob eine URL in asset_urls bekannt ist (ohne Daten zu laden).
        Effizienter als get_asset() wenn nur die Existenz geprüft werden soll.

        Wendet dieselbe URL-Normalisierung an wie get_asset() (Onion-Präfix).

        Args:
            url: URL-Pfad des Assets.

        Returns:
            True wenn die URL in asset_urls eingetragen ist.
        """
        if not self._available:
            return False

        lookup_url = (
            f"{self._forum_base_url}{url}"
            if self._forum_base_url
            else url
        )

        try:
            row = self._con.execute(
                "SELECT 1 FROM adb.asset_urls WHERE url = ? LIMIT 1",
                (lookup_url,),
            ).fetchone()
            return row is not None
        except sqlite3.OperationalError:
            return False

    def get_meta(self, key: str) -> Optional[str]:
        """
        Liest einen Wert aus adb.assets_meta.

        Args:
            key: Schlüssel, z.B. 'schema_version', 'created_at'.

        Returns:
            Wert als String, oder None wenn nicht gefunden oder DB nicht verfügbar.
        """
        if not self._available:
            return None

        try:
            row = self._con.execute(
                "SELECT value FROM adb.assets_meta WHERE key = ?",
                (key,),
            ).fetchone()
            return str(row["value"]) if row else None
        except sqlite3.OperationalError as exc:
            logger.error("get_meta('%s') fehlgeschlagen: %s", key, exc)
            return None

    def asset_count(self) -> int:
        """Gibt die Anzahl der gespeicherten Assets zurück. Für Statusanzeigen."""
        if not self._available:
            return 0

        try:
            row = self._con.execute(
                "SELECT COUNT(*) FROM adb.assets"
            ).fetchone()
            return int(row[0]) if row else 0
        except sqlite3.OperationalError:
            return 0
