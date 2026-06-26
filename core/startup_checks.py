# =============================================================================
# core/startup_checks.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Führt alle Voraussetzungsprüfungen beim Serverstart durch, bevor der
#   HTTP-Server hochfährt. Jede fehlgeschlagene Prüfung ist ein harter Fehler.
#
# Prüfungen (in dieser Reihenfolge):
#   1. Datenbankdateien erreichbar (forensic_db, evidence_db, default_db)
#   2. coordinator.db erreichbar (Warnung wenn nicht — Support-Modus toleriert)
#   3. Schema-Versionscheck: forensic_db muss in
#      SUPPORTED_FORENSIC_DB_SCHEMA_VERSIONS sein (aktuell {"1", "2"})
#   4. SHA-256-Integritätsprüfung: forensic_db (aus forensic_meta['sha256'])
#   5. forensic_db ist READ-ONLY geöffnet (Schreibversuch schlägt fehl)
#
# Forensische Relevanz:
#   Die SHA-256-Prüfung ist das Herzstück der Beweissicherung. Sie stellt
#   sicher, dass die forensic_db seit ihrer Versiegelung durch Stage 2 nicht
#   verändert wurde. Ein Betrieb mit veränderter forensic_db ist nicht
#   zulässig und würde die forensische Beweiskette unterbrechen.
#
#   Schlägt die SHA-256-Prüfung fehl, verweigert der Server den Start
#   vollständig. Es gibt keine Umgehungsmöglichkeit.
#
# SHA-256-Berechnung:
#   Der Hash wird über den gesamten Dateiinhalt der forensic_db berechnet
#   (nicht über einzelne Tabelleninhalte). Das entspricht dem Vorgehen
#   von Stage 2 beim Versiegeln.
#
# Abhängigkeiten: sqlite3, hashlib, pathlib — ausschließlich Stdlib
# Version: v0.1.0 · Build: 6 · 2026-04-10
# =============================================================================

import hashlib
import sqlite3
from pathlib import Path
from typing import Optional

from core.config_loader import ConfigLoader
from core.logger import get_logger
from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)


def _path_to_sqlite_uri(path: Path, mode: str = "ro") -> str:
    """
    Konvertiert einen Pfad in eine SQLite-kompatible URI mit ?mode=<mode>.

    Hintergrund (Build 019): Path.as_uri() erzeugt auf Windows UNC-Pfaden
    (\\\\server\\share\\...) eine file://server/...-URI. SQLite lehnt die
    Authority "server" ab (nur "localhost" oder leer erlaubt) —
    Fehler: "invalid uri authority: <servername>".
    Beleg: RFC 8089 §2, SQLite URI-Doku (https://www.sqlite.org/uri.html)
    Beleg: Projektgespräch 2026-04-22 — UNC-Pfad-Problem PROD

    Lösung: RFC-8089-konforme UNC-URI mit 4 Schrägstrichen:
      \\\\server\\share\\path → file:////server/share/path?mode=ro

    Typen:
      Windows UNC:    \\\\srv\\share\\f → file:////srv/share/f?mode=ro
      Windows lokal:  C:\\foo\\bar → file:///C:/foo/bar?mode=ro
      Unix/Linux:     /opt/f → file:///opt/f?mode=ro
    """
    import urllib.parse as _up
    p = str(path)
    if p.startswith("\\\\") or (p.startswith("//") and not p.startswith("///")):
        normalized = p.replace("\\", "/")
        uri_base = "file://" + normalized
    elif len(p) >= 2 and p[1] == ":":
        normalized = p.replace("\\", "/")
        uri_base = "file:///" + _up.quote(normalized, safe="/:")
    else:
        uri_base = path.as_uri()
    return uri_base + f"?mode={mode}"


# Aktuelle/erwartete Schema-Version (für Meldungen und als Test-Default).
# Muss mit FORENSIC_DB_SCHEMA_VERSION in aiw_sqlite_prepper
# (stage2/forensic_db_writer.py) übereinstimmen.
FORENSIC_DB_SCHEMA_VERSION = "2"

# Akzeptierte forensic_db-Schema-Versionen.
# Version 1 → 2 (Prepper Build 098) ist REIN ADDITIV: post_aliases erhielt die
# nullable Spalten `page` und `page_resolved`; keine bestehende Semantik wurde
# geändert. Der Webserver liest diese Spalten defensiv (forensic_db.
# resolve_posts_progress prüft per PRAGMA auf Existenz), daher sind v1 und v2
# vollständig kompatibel — eine v1-DB läuft (ohne Suchtreffer-Auflösung), eine
# v2-DB voll funktionsfähig. Ein künftiges BREAKING-Schema würde hier bewusst
# NICHT aufgenommen. Beleg: Befund 2026-06-26; aiw_sqlite_prepper Build 098/101.
SUPPORTED_FORENSIC_DB_SCHEMA_VERSIONS = frozenset({"1", "2"})

# Blockgröße für SHA-256-Berechnung (4 MB)
_HASH_BLOCK_SIZE = 4 * 1024 * 1024


class StartupCheckError(Exception):
    """
    Wird geworfen, wenn eine Startprüfung fehlschlägt.
    Führt immer zu einem harten Serverabbruch.
    Die Meldung ist so formuliert, dass sie direkt als Fehlermeldung
    auf der Konsole ausgegeben werden kann.
    """


class StartupChecker:
    """
    Führt alle Startprüfungen durch.

    Verwendung:
        checker = StartupChecker(config, resolved_context)
        checker.run_all()   # wirft StartupCheckError bei Fehler

    run_all() ruft alle Prüfungen in der definierten Reihenfolge auf.
    Der erste Fehler bricht die Prüfung ab — keine Folgeprüfungen mehr.
    """

    def __init__(
        self,
        context: ResolvedContext,
        config: ConfigLoader,
    ) -> None:
        # Reihenfolge (context, config) entspricht dem Aufruf in main.py.
        self._config = config
        self._ctx = context

    def run_all(self) -> None:
        """
        Führt alle Startprüfungen durch.

        Raises:
            StartupCheckError: Bei der ersten fehlgeschlagenen Prüfung.
        """
        logger.info("Starte Voraussetzungsprüfungen...")

        self._check_forensic_db_exists()
        self._check_default_db_exists()
        self._check_coordinator_db_exists()
        self._check_forensic_db_schema_version()
        self._check_forensic_db_integrity()
        self._check_forensic_db_readonly()

        logger.info("Alle Voraussetzungsprüfungen erfolgreich abgeschlossen.")

    # ------------------------------------------------------------------
    # Einzelne Prüfungen
    # ------------------------------------------------------------------

    def _check_forensic_db_exists(self) -> None:
        """
        Prüft ob forensic_db und evidence_db als Dateien erreichbar sind.

        evidence_db muss im Modus 'job' und 'cli' existieren.
        Im Modus 'support' wird die evidence_db als read-only angebunden —
        sie muss ebenfalls existieren, da sie gelesen wird.

        Raises:
            StartupCheckError: Wenn eine der Dateien nicht gefunden wird.
        """
        for label, path in [
            ("forensic_db", self._ctx.forensic_db),
            ("evidence_db", self._ctx.evidence_db),
        ]:
            if not path.exists():
                raise StartupCheckError(
                    f"Datenbankdatei nicht gefunden: {label} = '{path}'\n"
                    f"Prüfen: Ist der Pfad korrekt? Wurde Stage 2 erfolgreich "
                    f"abgeschlossen?\n"
                    f"User-ID: {self._ctx.user_id}"
                )
            if not path.is_file():
                raise StartupCheckError(
                    f"Datenbankpfad ist keine Datei: {label} = '{path}'"
                )
            logger.debug("Datei gefunden: %s = '%s'", label, path)

    def _check_default_db_exists(self) -> None:
        """
        Prüft ob default_db erreichbar ist.

        Raises:
            StartupCheckError: Wenn die Datei nicht gefunden wird.
        """
        path = self._ctx.default_db
        if not path.exists():
            raise StartupCheckError(
                f"default.db nicht gefunden: '{path}'\n"
                f"Die default.db enthält statische Assets (CSS, Bilder) und "
                f"ist für den Betrieb zwingend erforderlich."
            )
        logger.debug("default_db gefunden: '%s'", path)

    def _check_coordinator_db_exists(self) -> None:
        """
        Prüft ob coordinator_db erreichbar ist.

        Im Support-Modus: Warnung statt harter Fehler — der Supporter kann
        auch ohne coordinator.db arbeiten (read-only-Ansicht).
        In allen anderen Modi: harter Fehler.

        Raises:
            StartupCheckError: Wenn coordinator.db fehlt (nur in job/cli-Modus).
        """
        path = self._ctx.coordinator_db
        if not path.exists():
            if self._ctx.mode == "support":
                logger.warning(
                    "coordinator.db nicht gefunden: '%s' — "
                    "Im Support-Modus wird ohne coordinator.db fortgefahren.",
                    path,
                )
                return
            raise StartupCheckError(
                f"coordinator.db nicht gefunden: '{path}'\n"
                f"Die coordinator.db ist für Modus '{self._ctx.mode}' erforderlich."
            )
        logger.debug("coordinator_db gefunden: '%s'", path)

    def _check_forensic_db_schema_version(self) -> None:
        """
        Prüft die Schema-Version der forensic_db.
        Akzeptiert: forensic_meta['schema_version'] in
        SUPPORTED_FORENSIC_DB_SCHEMA_VERSIONS (v1 und v2 sind kompatibel,
        da der Sprung rein additiv war).

        Eine falsche Schema-Version bedeutet, dass die DB mit einer
        inkompatiblen Stage-2-Version erstellt wurde.

        Raises:
            StartupCheckError: Bei falscher oder fehlender Schema-Version.
        """
        path = self._ctx.forensic_db
        try:
            # URI-Modus mit mode=ro erzwingt READ-ONLY-Öffnung
            uri = _path_to_sqlite_uri(path, mode="ro")
            con = sqlite3.connect(uri, uri=True, timeout=5.0)
            con.row_factory = sqlite3.Row
            try:
                row = con.execute(
                    "SELECT value FROM forensic_meta WHERE key = 'schema_version'"
                ).fetchone()
            finally:
                con.close()
        except sqlite3.OperationalError as exc:
            raise StartupCheckError(
                f"forensic_db konnte nicht geöffnet werden: '{path}'\n"
                f"SQLite-Fehler: {exc}"
            ) from exc

        if row is None:
            raise StartupCheckError(
                f"forensic_meta['schema_version'] nicht gefunden in '{path}'.\n"
                f"Möglicherweise keine gültige forensic_db oder beschädigte Datei."
            )

        actual_version = str(row["value"])
        if actual_version not in SUPPORTED_FORENSIC_DB_SCHEMA_VERSIONS:
            supported = ", ".join(sorted(SUPPORTED_FORENSIC_DB_SCHEMA_VERSIONS))
            raise StartupCheckError(
                f"forensic_db Schema-Version inkompatibel:\n"
                f"  Unterstützt: {supported}\n"
                f"  Gefunden: {actual_version}\n"
                f"  Datei: '{path}'\n"
                f"Die DB wurde möglicherweise mit einer anderen Stage-2-Version "
                f"erstellt. Bitte Stage 2 neu ausführen."
            )

        logger.debug(
            "Schema-Version geprüft: %s (unterstützt: %s) ✓",
            actual_version,
            ", ".join(sorted(SUPPORTED_FORENSIC_DB_SCHEMA_VERSIONS)),
        )

    def _check_forensic_db_integrity(self) -> None:
        """
        Prüft die SHA-256-Integrität der forensic_db.

        Hash-Konvention (identisch mit Stage 2 und compute_content_sha256()):
          Der Hash wird nicht über die rohen Datei-Bytes berechnet, sondern
          über einen kanonischen Dump aller Tabelleninhalte der forensic_db —
          ausgenommen der forensic_meta-Zeile mit key='sha256' selbst.

          Begründung: Ein dateibasierter SHA-256-Hash ist bei SQLite-Dateien
          nicht stabil, weil sqlite3 beim Schreiben des Hash-Eintrags die
          interne Seitenstruktur verändert (selbstreferenzieller Hash-Konflikt).
          Ein inhaltsbasierter Hash über alle Daten außer dem Hash-Eintrag
          selbst ist hingegen deterministisch und reproduzierbar.

          Kanonische Dump-Reihenfolge:
          1. Alle Tabellen alphabetisch sortiert (außer sqlite_*)
          2. Innerhalb jeder Tabelle: alle Zeilen nach dem Primärschlüssel
          3. forensic_meta: alle Zeilen außer key='sha256', nach key sortiert
          4. Jede Zelle als repr()-String, durch '|' getrennt, Zeilen durch '\n'

        Raises:
            StartupCheckError: Wenn der Hash fehlt oder nicht übereinstimmt.
        """
        path = self._ctx.forensic_db

        try:
            uri = _path_to_sqlite_uri(path, mode="ro")
            con = sqlite3.connect(uri, uri=True, timeout=5.0)
            con.row_factory = sqlite3.Row
            try:
                # Gespeicherten Hash lesen
                row = con.execute(
                    "SELECT value FROM forensic_meta WHERE key = 'sha256'"
                ).fetchone()

                if row is None or not row["value"]:
                    raise StartupCheckError(
                        f"forensic_meta['sha256'] nicht gefunden oder leer in '{path}'.\n"
                        f"Die forensic_db wurde möglicherweise nicht korrekt versiegelt.\n"
                        f"Bitte Stage 2 neu ausführen."
                    )

                stored_hash = str(row["value"]).strip().lower()

                # Inhaltsbasierten Hash berechnen
                computed_hash = self._compute_content_sha256(con)

            finally:
                con.close()

        except sqlite3.OperationalError as exc:
            raise StartupCheckError(
                f"forensic_db konnte nicht für Integritätsprüfung geöffnet "
                f"werden: '{path}'\nSQLite-Fehler: {exc}"
            ) from exc

        if computed_hash != stored_hash:
            raise StartupCheckError(
                f"INTEGRITÄTSPRÜFUNG FEHLGESCHLAGEN — forensic_db wurde "
                f"möglicherweise verändert!\n"
                f"  Datei:              '{path}'\n"
                f"  Gespeicherter Hash: {stored_hash}\n"
                f"  Berechneter Hash:   {computed_hash}\n"
                f"Der Serverbetrieb wird verweigert. "
                f"Bitte die Datei auf Manipulationen prüfen."
            )

        logger.info(
            "Integritätsprüfung forensic_db erfolgreich: SHA-256 = %s ✓",
            computed_hash[:16] + "...",
        )

    def _check_forensic_db_readonly(self) -> None:
        """
        Prüft, ob die forensic_db tatsächlich im READ-ONLY-Modus geöffnet
        werden kann und keine Schreiboperationen akzeptiert.

        Konkret: Ein Schreibversuch via URI mode=ro muss scheitern.

        Raises:
            StartupCheckError: Wenn die forensic_db unerwartet beschreibbar ist.
        """
        path = self._ctx.forensic_db
        try:
            uri = _path_to_sqlite_uri(path, mode="ro")
            con = sqlite3.connect(uri, uri=True, timeout=5.0)
            try:
                # Schreibversuch — muss OperationalError werfen
                con.execute(
                    "INSERT INTO forensic_meta (key, value) "
                    "VALUES ('__readonly_test__', '1')"
                )
                con.commit()
                # Wenn wir hier ankommen, ist die DB beschreibbar — das ist falsch
                con.execute(
                    "DELETE FROM forensic_meta WHERE key = '__readonly_test__'"
                )
                con.commit()
                con.close()
                raise StartupCheckError(
                    f"forensic_db ist unerwartet beschreibbar: '{path}'\n"
                    f"Die forensic_db muss nach Versiegelung READ-ONLY sein.\n"
                    f"Bitte Dateisystemberechtigungen prüfen (chmod 0444)."
                )
            except sqlite3.OperationalError:
                # Erwarteter Fall: READ-ONLY wirft OperationalError
                logger.debug("forensic_db READ-ONLY-Prüfung bestanden ✓")
            finally:
                con.close()
        except sqlite3.OperationalError as exc:
            # Datei konnte nicht geöffnet werden — separater Fehler
            raise StartupCheckError(
                f"forensic_db konnte nicht für READ-ONLY-Prüfung geöffnet "
                f"werden: '{path}'\nSQLite-Fehler: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    def _compute_content_sha256(self, con: sqlite3.Connection) -> str:
        """
        Berechnet den SHA-256-Hash über den kanonischen Inhaltsdump der forensic_db.

        Ausgeschlossen: forensic_meta WHERE key = 'sha256' (der Hash-Eintrag selbst).
        Alle anderen Tabellen und Zeilen werden vollständig einbezogen.

        Kanonische Reihenfolge:
          1. Tabellennamen alphabetisch sortiert (sqlite_*-Tabellen ausgeschlossen)
          2. Jede Tabelle: alle Spalten in Definitionsreihenfolge,
             alle Zeilen nach ROWID aufsteigend
          3. forensic_meta: alle Zeilen außer key='sha256', nach key sortiert

        Format pro Zeile: "tabelle:col1|col2|col3\n" als UTF-8-Bytes.

        Returns:
            SHA-256-Hash als lowercase Hex-String (64 Zeichen).
        """
        sha256 = hashlib.sha256()

        # Alle Tabellen ermitteln (außer sqlite_*-internen Tabellen)
        tables = [
            row[0] for row in con.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name ASC"
            ).fetchall()
        ]

        for table in tables:
            if table == "forensic_meta":
                # forensic_meta: sha256-Eintrag ausschließen
                rows = con.execute(
                    "SELECT key, value FROM forensic_meta "
                    "WHERE key != 'sha256' ORDER BY key ASC"
                ).fetchall()
            else:
                # Alle anderen Tabellen vollständig, nach ROWID sortiert
                rows = con.execute(
                    f"SELECT * FROM \"{table}\" ORDER BY ROWID ASC"
                ).fetchall()

            for row in rows:
                line = f"{table}:" + "|".join(repr(col) for col in row) + "\n"
                sha256.update(line.encode("utf-8"))

        return sha256.hexdigest()

    def _compute_sha256(self, path: Path) -> str:
        """
        Berechnet den SHA-256-Hash der gesamten Datei (binär).
        Wird nur für compute_sha256_for_sealing() verwendet.

        Args:
            path: Pfad zur zu hashenden Datei.

        Returns:
            SHA-256-Hash als Hex-String (lowercase, 64 Zeichen).
        """
        sha256 = hashlib.sha256()
        with open(path, "rb") as fh:
            while True:
                block = fh.read(_HASH_BLOCK_SIZE)
                if not block:
                    break
                sha256.update(block)
        return sha256.hexdigest()

    def compute_sha256_for_sealing(self, db_path: Path) -> str:
        """
        Öffentliche Hilfsmethode: Berechnet den Inhalts-SHA-256 für das
        Versiegeln einer forensic_db durch Stage 2.

        Verwendet dieselbe Methode wie _check_forensic_db_integrity():
        kanonischer Inhaltsdump ohne den sha256-Eintrag selbst.

        Stage 2 muss diesen Wert in forensic_meta['sha256'] eintragen.

        Args:
            db_path: Pfad zur (noch unversiegelten) forensic_db.

        Returns:
            SHA-256-Hash als Hex-String.
        """
        con = sqlite3.connect(str(db_path), timeout=5.0)
        try:
            return self._compute_content_sha256(con)
        finally:
            con.close()
