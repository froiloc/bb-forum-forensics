# =============================================================================
# management/maintenance/default_db_merger.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management/Wartung
# =============================================================================
# Zweck:
#   Konsolidiert mehrere versehentlich pro Beschuldigtem angelegte
#   default.db-Dateien VERLUSTFREI in eine einzige zentrale default.db.
#
# Hintergrund (Beleg: Projektgespräch 2026-07-01, mc):
#   Der frühere Prepper-Workflow legte das Output-Verzeichnis vor jeder
#   User-Extraktion komplett neu an. Dadurch entstand pro Beschuldigtem
#   eine eigene default.db — jede nur ein Teil-Snapshot der forum-weiten,
#   nutzerneutralen Assets. Korrekt ist: EINE default.db für alle Ermittler,
#   nur assets_<uid>.db ist beschuldigten-spezifisch.
#
#   default.db ist zur Laufzeit read-only (db/default_db.py). Es existiert
#   also KEIN Ermittler-Wissen in default.db, das verloren gehen könnte —
#   alle Tabellen werden ausschließlich vom Prepper befüllt. Der Merge ist
#   damit eine reine Vereinigung der Prepper-Ausgaben.
#
# Forensische Grundregeln, die dieses Modul umsetzt:
#   1. Kein Beleg wird still übersprungen. Jede Quellzeile landet entweder
#      im Ziel (eingefügt / als identisch dedupliziert) ODER wird als
#      Konflikt/Anomalie protokolliert. Am Ende prüft eine Invariante je
#      Tabelle:  rows_read == inserted + deduped + conflicts (+ anomalies).
#      Schlägt sie fehl -> Abbruch (es wäre still etwas verschwunden).
#   "measure, don't compute": Es werden reale Zeilen gezählt, nicht geschätzt.
#
# Merge-Strategien je Tabelle (Beleg: Merge-Klassifikation 2026-07-01):
#   default_assets   content_hash-Dedup, neue AUTOINCREMENT-id, alt->neu-Map
#   default_urls     url-Dedup, asset_id über die Map remappen (FK-Erhalt!)
#   known_aliases    Dedup über (user_id, name), alias_id neu vergeben
#   default_meta     stabile Keys (protocol/domainname) müssen übereinstimmen;
#                    Lauf-Keys (last_run_*) -> neueste Quelle gewinnt
#   alle übrigen     natürlicher PK; identisch -> dedup, abweichend -> Konflikt
#                    (neueste Quelle gewinnt, protokolliert)
#
#   Konfliktauflösung "neueste Quelle gewinnt": Quellen werden nach
#   default_meta.last_run_ts aufsteigend verarbeitet; bei Abweichung
#   überschreibt die spätere (=neuere) Quelle die frühere (REPLACE) —
#   IMMER mit Protokolleintrag, nie still.
#
# Immutabilität der Quellen:
#   Quell-DBs werden ausschließlich read-only geöffnet (URI mode=ro).
#   Der gesamte Merge läuft in EINER Transaktion auf dem Ziel; bei Fehler
#   Rollback -> kein halbfertiges Ziel.
#
# Aufruf: über management/consolidate_default_db.py (CLI). Diese Klasse ist
#   der wiederverwendbare, testbare Kern.
#
# Abhängigkeiten: sqlite3, hashlib, json — ausschließlich Stdlib.
# Version: v0.7.309 · Build: 309 · 2026-07-01
# =============================================================================

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)


# -----------------------------------------------------------------------------
# Kanonisches Schema der zentralen default.db (10 Tabellen inkl. host_aliases).
# Beleg: default_db_schema.sql (maßgeblich, mc 2026-07-01) sowie die
# Laufzeit-DDL in aiw_sqlite_prepper/stage3/default_db_writer.py.
# Eingebettet, weil in der Produktivumgebung keine .sql-Datei beiliegt.
# -----------------------------------------------------------------------------
_CANONICAL_DDL = """
CREATE TABLE IF NOT EXISTS default_groups (
    g_id                INTEGER PRIMARY KEY,
    g_title             TEXT    NOT NULL,
    g_user_title        TEXT,
    g_moderator         INTEGER NOT NULL DEFAULT 0,
    g_global_moderator  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS default_badges (
    id      INTEGER PRIMARY KEY,
    name    TEXT    NOT NULL,
    info    TEXT    NOT NULL,
    status  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS default_forums (
    id          INTEGER PRIMARY KEY,
    forum_name  TEXT    NOT NULL,
    forum_desc  TEXT,
    parent_id   INTEGER
);

CREATE TABLE IF NOT EXISTS known_users (
    user_id   INTEGER PRIMARY KEY,
    username  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS known_aliases (
    alias_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL,
    name      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS identified_users (
    user_id  INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS default_assets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash  TEXT    NOT NULL UNIQUE,
    data          BLOB,
    mime_type     TEXT,
    file_size     INTEGER,
    source_note   TEXT    NOT NULL,
    fetched_at    INTEGER
);

CREATE TABLE IF NOT EXISTS default_urls (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url          TEXT    NOT NULL UNIQUE,
    url_hash     TEXT    NOT NULL,
    asset_id     INTEGER REFERENCES default_assets(id),
    url_context  TEXT    NOT NULL,
    http_status  INTEGER,
    added_at     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS default_meta (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS host_aliases (
    hostname  TEXT PRIMARY KEY,
    role      TEXT NOT NULL,
    note      TEXT
);

CREATE INDEX IF NOT EXISTS known_users_username_idx  ON known_users (username);
CREATE INDEX IF NOT EXISTS known_aliases_user_id_idx ON known_aliases (user_id);
CREATE INDEX IF NOT EXISTS default_urls_url_idx      ON default_urls (url);
CREATE INDEX IF NOT EXISTS default_assets_hash_idx   ON default_assets (content_hash);
"""

# Verarbeitungsreihenfolge je Quelle. assets VOR urls (FK-Remap!).
# Beleg: Merge-Klassifikation 2026-07-01.
_MERGE_ORDER = [
    "default_assets",   # Sonderfall: content_hash-Dedup, baut id-Map
    "default_urls",     # Sonderfall: asset_id remappen
    "default_groups",
    "default_badges",
    "default_forums",
    "known_users",
    "identified_users",
    "host_aliases",
    "known_aliases",    # Sonderfall: composite (user_id, name)
    "default_meta",     # Sonderfall: Konfliktpolicy
]

# Natürlicher-PK-Tabellen: identisch -> dedup, abweichend -> Konflikt.
# Wert = Liste der Schlüsselspalten.
_NATURAL_PK = {
    "default_groups":   ["g_id"],
    "default_badges":   ["id"],
    "default_forums":   ["id"],
    "known_users":      ["user_id"],
    "identified_users": ["user_id"],
    "host_aliases":     ["hostname"],
}

# default_meta-Keys, die forum-weit stabil sein MÜSSEN. Abweichung deutet auf
# das Vermischen von DBs verschiedener Foren hin -> harter Integritätsfehler.
_META_STABLE_KEYS = ("protocol", "domainname")


# -----------------------------------------------------------------------------
# Ergebnis-/Protokoll-Wertobjekte (reine Datencontainer, kein Verhalten).
# -----------------------------------------------------------------------------
@dataclass
class TableStat:
    """Zählwerk pro Tabelle über alle Quellen hinweg."""
    rows_read: int = 0
    inserted: int = 0
    deduped: int = 0
    conflicts: int = 0
    anomalies: int = 0

    @property
    def accounted(self) -> int:
        return self.inserted + self.deduped + self.conflicts + self.anomalies

    @property
    def balanced(self) -> bool:
        """Invariante: jede gelesene Zeile ist verbucht (kein stilles Verwerfen)."""
        return self.rows_read == self.accounted


@dataclass(frozen=True)
class ConflictRecord:
    """Ein aufgelöster Konflikt (immer protokolliert, nie still)."""
    table: str
    key: str
    old_value: str
    new_value: str
    source: str
    resolution: str  # z.B. 'newest_wins'


@dataclass(frozen=True)
class SourceInfo:
    """Metadaten einer Quell-DB (für recency-Sortierung + Bericht)."""
    path: str
    last_run_ts: int  # 0 wenn nicht ermittelbar


@dataclass
class MergeReport:
    """Gesamtbericht des Merge-Laufs."""
    target: str = ""
    sources: list[SourceInfo] = field(default_factory=list)
    tables: dict = field(default_factory=dict)  # name -> TableStat
    conflicts: list[ConflictRecord] = field(default_factory=list)
    started_at: int = 0
    finished_at: int = 0
    fk_check_ok: bool = False

    def as_text(self) -> str:
        """Menschenlesbarer Abgleichbericht (für Log-Datei + Konsole)."""
        lines: list[str] = []
        lines.append("=" * 72)
        lines.append("default.db-Konsolidierung — Abgleichbericht")
        lines.append("=" * 72)
        lines.append(f"Ziel:     {self.target}")
        lines.append(f"Start:    {_iso(self.started_at)}")
        lines.append(f"Ende:     {_iso(self.finished_at)}")
        lines.append(f"Quellen:  {len(self.sources)} "
                     "(verarbeitet nach last_run_ts aufsteigend)")
        for s in self.sources:
            lines.append(f"    - last_run_ts={s.last_run_ts} ({_iso(s.last_run_ts)})  {s.path}")
        lines.append("-" * 72)
        header = f"{'Tabelle':<18}{'gelesen':>9}{'eingefügt':>11}{'dedup':>8}{'konflikt':>10}{'anom.':>7}{'ok':>5}"
        lines.append(header)
        for name in _MERGE_ORDER:
            st = self.tables.get(name)
            if st is None:
                continue
            ok = "ja" if st.balanced else "NEIN"
            lines.append(
                f"{name:<18}{st.rows_read:>9}{st.inserted:>11}"
                f"{st.deduped:>8}{st.conflicts:>10}{st.anomalies:>7}{ok:>5}"
            )
        lines.append("-" * 72)
        lines.append(f"Fremdschlüsselprüfung (Ziel): {'sauber' if self.fk_check_ok else 'FEHLER'}")
        if self.conflicts:
            lines.append("-" * 72)
            lines.append(f"Aufgelöste Konflikte ({len(self.conflicts)}) — Auszug (max 50):")
            for c in self.conflicts[:50]:
                lines.append(
                    f"  [{c.table}] key={c.key} :: '{c.old_value}' -> '{c.new_value}' "
                    f"({c.resolution}, Quelle {c.source})"
                )
            if len(self.conflicts) > 50:
                lines.append(f"  ... {len(self.conflicts) - 50} weitere im JSON-Protokoll.")
        lines.append("=" * 72)
        return "\n".join(lines)

    def as_provenance_json(self) -> str:
        """Kompakte Herkunftsdokumentation für default_meta.merge_provenance."""
        return json.dumps({
            "merged_at": self.finished_at,
            "sources": [{"path": s.path, "last_run_ts": s.last_run_ts}
                        for s in self.sources],
            "tables": {n: {
                "rows_read": st.rows_read, "inserted": st.inserted,
                "deduped": st.deduped, "conflicts": st.conflicts,
                "anomalies": st.anomalies,
            } for n, st in self.tables.items()},
            "conflict_count": len(self.conflicts),
            "fk_check_ok": self.fk_check_ok,
        }, ensure_ascii=False)


def _iso(ts: int) -> str:
    """Unix-Timestamp -> lesbare UTC-Zeit; 0/leere sauber behandeln."""
    if not ts:
        return "—"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime(ts))
    except (ValueError, OSError):
        return str(ts)


class MergeError(RuntimeError):
    """Harter Integritäts- oder Konfigurationsfehler beim Merge (Abbruch)."""


class DefaultDbMerger:
    """
    Konsolidiert mehrere default.db-Quellen in eine zentrale Ziel-default.db.

    Verwendung:
        merger = DefaultDbMerger(
            target_path=Path("data/default.db"),
            source_paths=[Path(p) for p in glob(...)],
            overwrite=False,
            allow_host_mismatch=False,
        )
        report = merger.run()          # wirft MergeError bei hartem Fehler
        print(report.as_text())

    Die Instanz ist einmalig verwendbar (run() genau einmal aufrufen).
    """

    def __init__(
        self,
        target_path: Path,
        source_paths: list[Path],
        overwrite: bool = False,
        allow_host_mismatch: bool = False,
    ) -> None:
        self._target_path = Path(target_path)
        self._source_paths = [Path(p) for p in source_paths]
        self._overwrite = overwrite
        self._allow_host_mismatch = allow_host_mismatch

        self._target: Optional[sqlite3.Connection] = None
        self._report = MergeReport(target=str(self._target_path))
        # TableStat je Tabelle vorinitialisieren (auch 0-Zeilen erscheinen im Bericht)
        for name in _MERGE_ORDER:
            self._report.tables[name] = TableStat()

    # ------------------------------------------------------------------ public
    def run(self) -> MergeReport:
        """Führt den kompletten Merge in EINER Transaktion aus."""
        self._report.started_at = int(time.time())
        self._validate_inputs()

        sources = self._probe_sources()  # read-only Metadaten + recency-Sortierung
        self._report.sources = sources

        self._open_target()
        assert self._target is not None
        try:
            # PRAGMA foreign_keys AUS während des Merges — wir remappen FKs
            # selbst und prüfen am Ende explizit per foreign_key_check.
            self._target.execute("PRAGMA foreign_keys=OFF")
            self._target.execute("BEGIN")

            for src in sources:
                self._merge_one_source(src)

            self._write_provenance()
            self._verify_invariants()      # kein stilles Verwerfen
            self._verify_foreign_keys()    # asset_id-Remap korrekt?

            self._target.execute("COMMIT")
        except Exception:
            try:
                self._target.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            self._target.close()
            self._target = None

        self._report.finished_at = int(time.time())
        logger.info("Konsolidierung abgeschlossen: %s", self._target_path)
        return self._report

    # --------------------------------------------------------------- validation
    def _validate_inputs(self) -> None:
        if not self._source_paths:
            raise MergeError("Keine Quell-DB angegeben.")
        seen: set[str] = set()
        for p in self._source_paths:
            rp = str(p.resolve())
            if not p.exists():
                raise MergeError(f"Quell-DB nicht gefunden: {p}")
            if rp in seen:
                raise MergeError(f"Quell-DB doppelt angegeben: {p}")
            seen.add(rp)
        # Ziel darf keine der Quellen sein (Quellen bleiben unangetastet).
        tgt_rp = str(self._target_path.resolve())
        if tgt_rp in seen:
            raise MergeError(
                f"Ziel darf keine der Quellen sein (Immutabilität): {self._target_path}"
            )
        if self._target_path.exists() and not self._overwrite:
            raise MergeError(
                f"Ziel existiert bereits: {self._target_path} "
                "(--overwrite verwenden, um es neu aufzubauen)."
            )

    def _probe_sources(self) -> list[SourceInfo]:
        """
        Öffnet jede Quelle read-only, liest last_run_ts (recency) und prüft,
        dass keine unbekannte Tabelle/Spalte vorhanden ist (fail loud).
        Sortiert aufsteigend nach recency -> spätere (neuere) Quelle gewinnt.
        """
        infos: list[SourceInfo] = []
        canonical_tables = set(_MERGE_ORDER)
        canonical_cols = self._canonical_columns()

        for p in self._source_paths:
            con = self._connect_ro(p)
            try:
                # Unbekannte Tabellen? -> Abbruch, niemals still ignorieren.
                src_tables = {
                    r[0] for r in con.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                }
                unknown_tables = src_tables - canonical_tables
                if unknown_tables:
                    raise MergeError(
                        f"Quelle {p} enthält unbekannte Tabelle(n): "
                        f"{sorted(unknown_tables)} — nicht im kanonischen Schema. "
                        "Abbruch statt stillem Datenverlust."
                    )
                # Unbekannte Spalten je Tabelle? -> Abbruch.
                for t in src_tables:
                    src_cols = {ci[1] for ci in con.execute(
                        f"PRAGMA table_info({t})").fetchall()}
                    unknown_cols = src_cols - canonical_cols[t]
                    if unknown_cols:
                        raise MergeError(
                            f"Quelle {p}, Tabelle {t}: unbekannte Spalte(n) "
                            f"{sorted(unknown_cols)}. Abbruch statt Datenverlust."
                        )
                last_run_ts = self._read_meta_int(con, "last_run_ts")
                infos.append(SourceInfo(path=str(p), last_run_ts=last_run_ts))
            finally:
                con.close()

        # aufsteigend nach recency; Tie-Break: Pfad (deterministisch)
        infos.sort(key=lambda s: (s.last_run_ts, s.path))
        return infos

    # ------------------------------------------------------------------- target
    def _open_target(self) -> None:
        if self._target_path.exists() and self._overwrite:
            self._target_path.unlink()
            logger.info("Bestehendes Ziel entfernt (--overwrite): %s", self._target_path)
        self._target_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self._target_path)
        con.row_factory = sqlite3.Row
        con.executescript(_CANONICAL_DDL)
        con.commit()
        self._target = con
        logger.info("Ziel-default.db angelegt: %s", self._target_path)

    # -------------------------------------------------------------- merge steps
    def _merge_one_source(self, src: SourceInfo) -> None:
        logger.info("Verarbeite Quelle (last_run_ts=%d): %s", src.last_run_ts, src.path)
        con = self._connect_ro(Path(src.path))
        try:
            id_map = self._merge_assets(con, src.path)
            self._merge_urls(con, src.path, id_map)
            for table, key_cols in _NATURAL_PK.items():
                self._merge_natural_pk(con, src.path, table, key_cols)
            self._merge_known_aliases(con, src.path)
            self._merge_meta(con, src.path)
        finally:
            con.close()

    def _merge_assets(self, con: sqlite3.Connection, source: str) -> dict:
        """
        default_assets: content_hash-Dedup. Gibt id_map {quelle_id: ziel_id}
        zurück (für den anschließenden default_urls-Remap).
        content_hash ist inhaltsadressiert -> gleicher Hash == gleiche Bytes,
        daher kein Konfliktbegriff, nur Dedup.
        """
        assert self._target is not None
        st = self._report.tables["default_assets"]
        if not self._has_table(con, "default_assets"):
            return {}
        carried = [c for c in self._columns(con, "default_assets") if c != "id"]
        if "content_hash" not in carried:
            raise MergeError(f"Quelle {source}: default_assets ohne content_hash.")
        col_list = ", ".join(carried)
        placeholders = ", ".join("?" * len(carried))

        id_map: dict = {}
        rows = con.execute(f"SELECT id, {col_list} FROM default_assets").fetchall()
        for row in rows:
            st.rows_read += 1
            ch = row["content_hash"]
            existing = self._target.execute(
                "SELECT id FROM default_assets WHERE content_hash = ?", (ch,)
            ).fetchone()
            if existing:
                id_map[row["id"]] = existing["id"]
                st.deduped += 1
                continue
            values = [row[c] for c in carried]
            cur = self._target.execute(
                f"INSERT INTO default_assets ({col_list}) VALUES ({placeholders})",
                values,
            )
            id_map[row["id"]] = cur.lastrowid
            st.inserted += 1
        return id_map

    def _merge_urls(self, con: sqlite3.Connection, source: str, id_map: dict) -> None:
        """
        default_urls: url-Dedup. asset_id wird über id_map remappt (FK-Erhalt).
        Zeigt dieselbe URL im Ziel bereits auf ein ANDERES Asset (Forum-Asset
        zwischen Scrapes geändert), ist das ein forensisch relevanter Konflikt
        -> neueste Quelle gewinnt, protokolliert.
        """
        assert self._target is not None
        st = self._report.tables["default_urls"]
        if not self._has_table(con, "default_urls"):
            return
        carried = [c for c in self._columns(con, "default_urls") if c != "id"]
        rows = con.execute(
            f"SELECT {', '.join(carried)} FROM default_urls"
        ).fetchall()
        for row in rows:
            st.rows_read += 1
            url = row["url"]
            src_asset_id = row["asset_id"] if "asset_id" in carried else None
            # asset_id remappen
            if src_asset_id is None:
                mapped_asset = None
            elif src_asset_id in id_map:
                mapped_asset = id_map[src_asset_id]
            else:
                # asset_id ohne passendes Asset in derselben Quelle -> Anomalie.
                # Niemals still: protokollieren, url mit asset_id=NULL aufnehmen.
                logger.warning(
                    "Quelle %s: default_urls.url=%s verweist auf asset_id=%s "
                    "ohne Asset in derselben Quelle (dangling FK).",
                    source, url, src_asset_id,
                )
                st.anomalies += 1
                mapped_asset = None

            values = {c: row[c] for c in carried}
            if "asset_id" in values:
                values["asset_id"] = mapped_asset

            existing = self._target.execute(
                "SELECT * FROM default_urls WHERE url = ?", (url,)
            ).fetchone()
            if existing is None:
                cols = list(values.keys())
                self._target.execute(
                    f"INSERT INTO default_urls ({', '.join(cols)}) "
                    f"VALUES ({', '.join('?' * len(cols))})",
                    [values[c] for c in cols],
                )
                if mapped_asset is None and src_asset_id is not None:
                    pass  # bereits als Anomalie gezählt
                else:
                    st.inserted += 1
                continue

            # URL existiert schon -> vergleichen
            if self._url_row_equal(existing, values):
                if not (mapped_asset is None and src_asset_id is not None):
                    st.deduped += 1
                continue
            # Abweichung -> neueste Quelle gewinnt (Quellen aufsteigend verarbeitet)
            set_cols = [c for c in values.keys() if c != "url"]
            self._target.execute(
                f"UPDATE default_urls SET {', '.join(c + ' = ?' for c in set_cols)} "
                "WHERE url = ?",
                [values[c] for c in set_cols] + [url],
            )
            self._report.conflicts.append(ConflictRecord(
                table="default_urls", key=str(url),
                old_value=f"asset_id={existing['asset_id']}",
                new_value=f"asset_id={values.get('asset_id')}",
                source=source, resolution="newest_wins",
            ))
            if not (mapped_asset is None and src_asset_id is not None):
                st.conflicts += 1

    def _merge_natural_pk(
        self, con: sqlite3.Connection, source: str, table: str, key_cols: list
    ) -> None:
        """Tabellen mit natürlichem PK: identisch -> dedup, abweichend -> Konflikt."""
        assert self._target is not None
        st = self._report.tables[table]
        if not self._has_table(con, table):
            return
        carried = self._columns(con, table)
        where = " AND ".join(f"{k} = ?" for k in key_cols)
        rows = con.execute(f"SELECT {', '.join(carried)} FROM {table}").fetchall()
        for row in rows:
            st.rows_read += 1
            keyvals = [row[k] for k in key_cols]
            existing = self._target.execute(
                f"SELECT {', '.join(carried)} FROM {table} WHERE {where}", keyvals
            ).fetchone()
            if existing is None:
                self._target.execute(
                    f"INSERT INTO {table} ({', '.join(carried)}) "
                    f"VALUES ({', '.join('?' * len(carried))})",
                    [row[c] for c in carried],
                )
                st.inserted += 1
                continue
            if all(existing[c] == row[c] for c in carried):
                st.deduped += 1
                continue
            # Abweichung -> neueste Quelle gewinnt
            payload = [c for c in carried if c not in key_cols]
            self._target.execute(
                f"UPDATE {table} SET {', '.join(c + ' = ?' for c in payload)} "
                f"WHERE {where}",
                [row[c] for c in payload] + keyvals,
            )
            self._report.conflicts.append(ConflictRecord(
                table=table, key=repr(tuple(keyvals)),
                old_value=repr(tuple(existing[c] for c in payload)),
                new_value=repr(tuple(row[c] for c in payload)),
                source=source, resolution="newest_wins",
            ))
            st.conflicts += 1

    def _merge_known_aliases(self, con: sqlite3.Connection, source: str) -> None:
        """
        known_aliases: composite-Dedup über (user_id, name). alias_id wird im
        Ziel neu vergeben (AUTOINCREMENT). Kein Konfliktbegriff — name ist Teil
        des Schlüssels; entweder (user_id,name) existiert (dedup) oder nicht.
        """
        assert self._target is not None
        st = self._report.tables["known_aliases"]
        if not self._has_table(con, "known_aliases"):
            return
        rows = con.execute(
            "SELECT user_id, name FROM known_aliases"
        ).fetchall()
        for row in rows:
            st.rows_read += 1
            existing = self._target.execute(
                "SELECT 1 FROM known_aliases WHERE user_id = ? AND name = ?",
                (row["user_id"], row["name"]),
            ).fetchone()
            if existing:
                st.deduped += 1
                continue
            self._target.execute(
                "INSERT INTO known_aliases (user_id, name) VALUES (?, ?)",
                (row["user_id"], row["name"]),
            )
            st.inserted += 1

    def _merge_meta(self, con: sqlite3.Connection, source: str) -> None:
        """
        default_meta: stabile Keys (protocol/domainname) MÜSSEN übereinstimmen
        (sonst Verdacht: DBs verschiedener Foren -> Abbruch, außer explizit
        erlaubt). Alle übrigen Keys: neueste Quelle gewinnt (Quellen aufsteigend
        verarbeitet), Abweichungen werden protokolliert.
        """
        assert self._target is not None
        st = self._report.tables["default_meta"]
        if not self._has_table(con, "default_meta"):
            return
        rows = con.execute("SELECT key, value FROM default_meta").fetchall()
        for row in rows:
            st.rows_read += 1
            key, value = row["key"], row["value"]
            existing = self._target.execute(
                "SELECT value FROM default_meta WHERE key = ?", (key,)
            ).fetchone()
            if existing is None:
                self._target.execute(
                    "INSERT INTO default_meta (key, value) VALUES (?, ?)",
                    (key, value),
                )
                st.inserted += 1
                continue
            if existing["value"] == value:
                st.deduped += 1
                continue
            # Abweichung
            if key in _META_STABLE_KEYS and not self._allow_host_mismatch:
                raise MergeError(
                    f"Stabiler Meta-Key '{key}' divergiert zwischen Quellen: "
                    f"'{existing['value']}' vs '{value}' (Quelle {source}). "
                    "Verdacht: DBs verschiedener Foren. Abbruch. "
                    "Mit --allow-host-mismatch bewusst überstimmbar."
                )
            self._target.execute(
                "UPDATE default_meta SET value = ? WHERE key = ?", (value, key)
            )
            self._report.conflicts.append(ConflictRecord(
                table="default_meta", key=str(key),
                old_value=str(existing["value"]), new_value=str(value),
                source=source, resolution="newest_wins",
            ))
            st.conflicts += 1

    # ----------------------------------------------------------- finalize/verify
    def _write_provenance(self) -> None:
        """Herkunftsdokumentation in default_meta.merge_provenance (idempotent)."""
        assert self._target is not None
        self._report.finished_at = int(time.time())
        self._target.execute(
            "INSERT OR REPLACE INTO default_meta (key, value) VALUES (?, ?)",
            ("merge_provenance", self._report.as_provenance_json()),
        )
        # merge_provenance selbst nicht als Meta-Zeile mitzählen (Werkzeug-Metadatum)

    def _verify_invariants(self) -> None:
        """Kein stilles Verwerfen: jede gelesene Zeile muss verbucht sein."""
        broken = [n for n, st in self._report.tables.items() if not st.balanced]
        if broken:
            details = "; ".join(
                f"{n}: gelesen={self._report.tables[n].rows_read} "
                f"verbucht={self._report.tables[n].accounted}" for n in broken
            )
            raise MergeError(
                "Invariante verletzt (stilles Verwerfen möglich) — " + details
            )

    def _verify_foreign_keys(self) -> None:
        """foreign_key_check auf dem Ziel — validiert den asset_id-Remap."""
        assert self._target is not None
        violations = self._target.execute("PRAGMA foreign_key_check").fetchall()
        self._report.fk_check_ok = not violations
        if violations:
            raise MergeError(
                f"Fremdschlüsselprüfung fehlgeschlagen ({len(violations)} "
                "Verletzung(en)) — asset_id-Remap fehlerhaft."
            )

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _connect_ro(path: Path) -> sqlite3.Connection:
        """Öffnet eine Quelle strikt read-only (Immutabilität der Quellen)."""
        uri = f"file:{path.resolve().as_posix()}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def _has_table(con: sqlite3.Connection, table: str) -> bool:
        row = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (table,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _columns(con: sqlite3.Connection, table: str) -> list:
        return [ci[1] for ci in con.execute(f"PRAGMA table_info({table})").fetchall()]

    def _canonical_columns(self) -> dict:
        """Spaltenmengen des kanonischen Schemas (für die fail-loud-Prüfung)."""
        tmp = sqlite3.connect(":memory:")
        try:
            tmp.executescript(_CANONICAL_DDL)
            out: dict = {}
            for name in _MERGE_ORDER:
                out[name] = {
                    ci[1] for ci in tmp.execute(f"PRAGMA table_info({name})").fetchall()
                }
            return out
        finally:
            tmp.close()

    @staticmethod
    def _read_meta_int(con: sqlite3.Connection, key: str) -> int:
        try:
            row = con.execute(
                "SELECT value FROM default_meta WHERE key = ?", (key,)
            ).fetchone()
            return int(row["value"]) if row and row["value"] is not None else 0
        except (sqlite3.Error, ValueError, TypeError):
            return 0

    @staticmethod
    def _url_row_equal(existing: sqlite3.Row, values: dict) -> bool:
        """Vergleicht eine bestehende default_urls-Zeile mit den (remappten) Werten."""
        for c, v in values.items():
            if c == "url":
                continue
            if existing[c] != v:
                return False
        return True
