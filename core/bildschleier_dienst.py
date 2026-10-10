# =============================================================================
# core/bildschleier_dienst.py
# IT-Forensisches Ermittlungswerkzeug — Bildschleier (Build 772)
# =============================================================================
# Zweck:
#   Die EINE Stelle im Webserver, die den Bildschleier-Zustand der
#   angemeldeten Person kennt. Shell, Seitenumschlag, Endpunkt und (ab Build
#   773) Asset-Auslieferung fragen hier und nicht jeweils selbst in
#   coordinator.db.
#
# ── EIN WEBSERVER, EINE PERSON ──────────────────────────────────────────────
#
#   Der Webserver laeuft je Windows-Sitzung, fuer genau einen Systembenutzer
#   (core/user_resolver.py). context.investigator_id ist die person.id dieses
#   Benutzers (core/mode_resolver.py). Der Zustand gehoert also zu genau
#   einer Person; ein prozessweiter Zwischenspeicher ist richtig.
#
# ── WANN NEU GELESEN WIRD ───────────────────────────────────────────────────
#
#   * bei jeder Shell (erster Aufruf, Neuladen)
#   * bei jedem Seitenumschlag (Navigation in der Shell)
#   * nach jedem Umschalten
#   * sonst (Bildanfragen, ab Build 773) aus dem Zwischenspeicher, hoechstens
#     MAX_ALTER_SEK alt.
#   Eine Rechteaenderung in der Verwaltung wirkt damit spaetestens beim
#   naechsten Seitenwechsel.
#
# ── DER EINZIGE PAUSCHALE FEHLERABFANG — UND WARUM ER HIER STEHT ────────────
#
#   BildschleierRepo faengt nur sqlite3.Error (Lehre Build 769). Was sonst
#   fliegt, ist ein Programmierfehler — und landet HIER, an genau einer
#   Stelle: mit Traceback im Protokoll und als Grund 'internal_error'
#   (verschleiert, gesperrt, eigener Kurzhinweis). Ein Programmierfehler darf
#   den Schleier nicht abschalten (dann saehe die Forschung Bilder) und nicht
#   als Betriebsstoerung erscheinen (dann sucht man an der falschen Stelle).
#
# Version: v0.8.772 · Build: 772 · 2026-10-09
# =============================================================================

from __future__ import annotations

import sqlite3
import threading
import time
from typing import TYPE_CHECKING, Optional

from core.bildschleier_css import BildschleierCss
from core.bildschleier_regel import BildschleierRegel
from core.bildschleier_seitenausnahmen import BildschleierSeitenausnahmen
from core.logger import get_logger
from management.bildschleier.bildschleier_repo import (
    BildschleierFehler, BildschleierRepo,
)
from management.bildschleier.bildschleier_zustand import (
    GRUND_INTERN, GRUND_RBAC_FEHLT, BildschleierZustand,
)

if TYPE_CHECKING:
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

#: Hoechstalter des Zwischenspeichers fuer Abfragen ohne eigenes Neulesen.
MAX_ALTER_SEK = 30.0


class BildschleierDienst:
    """Zustand, Regel und Stylesheets des Bildschleiers fuer den Webserver."""

    def __init__(self, config: "ConfigLoader",
                 context: "ResolvedContext") -> None:
        self._config = config
        self._context = context
        self._lock = threading.Lock()
        self._zustand: Optional[BildschleierZustand] = None
        self._gelesen_um = 0.0
        # Regel und Grundregel werden beim Start gebaut. Ein Fehler in der
        # Konfiguration bricht hier LAUT ab (ValueError), statt spaeter
        # still eine falsche Regel anzuwenden.
        self.regel = BildschleierRegel.aus_konfiguration(config)
        self.grundregel = BildschleierCss.aus_konfiguration(config)
        self.seitenausnahmen = BildschleierSeitenausnahmen(self.regel)

    # ------------------------------------------------------------ intern ---
    def _person_id(self) -> Optional[int]:
        pid = getattr(self._context, "investigator_id", None)
        return int(pid) if pid is not None else None

    def _coordinator_pfad(self) -> Optional[str]:
        pfad = getattr(self._context, "coordinator_db", None) \
            or self._config.get("paths.coordinator_db")
        return str(pfad) if pfad else None

    def _lesend(self, pfad: str) -> sqlite3.Connection:
        uri = "file:" + pfad.replace("?", "%3f") + "?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=5.0)
        con.row_factory = sqlite3.Row
        return con

    def _lies(self) -> BildschleierZustand:
        pfad = self._coordinator_pfad()
        if not pfad:
            logger.error("Bildschleier: kein coordinator.db-Pfad bekannt.")
            return BildschleierZustand.gesperrt(GRUND_RBAC_FEHLT)
        try:
            con = self._lesend(pfad)
        except sqlite3.Error as exc:
            logger.error("Bildschleier: coordinator.db nicht lesbar (%s): %s",
                         pfad, exc)
            return BildschleierZustand.gesperrt(GRUND_RBAC_FEHLT)
        try:
            return BildschleierRepo(con).zustand(self._person_id())
        finally:
            con.close()

    # ----------------------------------------------------------- Abfrage ---
    def aktualisieren(self) -> BildschleierZustand:
        """Liest den Zustand NEU und legt ihn im Zwischenspeicher ab."""
        try:
            zustand = self._lies()
        except Exception:                                  # noqa: BLE001
            # Siehe Modulkopf: der einzige pauschale Abfang, mit Traceback.
            logger.exception("Bildschleier: interner Fehler beim Lesen des "
                             "Zustands — verschleiert und gesperrt.")
            zustand = BildschleierZustand.gesperrt(GRUND_INTERN)
        with self._lock:
            self._zustand = zustand
            self._gelesen_um = time.monotonic()
        return zustand

    def zustand(self) -> BildschleierZustand:
        """Der Zustand aus dem Zwischenspeicher, notfalls neu gelesen."""
        with self._lock:
            z, alter = self._zustand, time.monotonic() - self._gelesen_um
        if z is None or alter > MAX_ALTER_SEK:
            return self.aktualisieren()
        return z

    # ---------------------------------------------------------- Schreiben ---
    def setzen(self, veiled: bool) -> BildschleierZustand:
        """
        Speichert die Wahl der angemeldeten Person (mit Beleg) und gibt den
        neuen Zustand zurueck. Wirft BildschleierFehler, wenn das Umschalten
        nicht zulaessig ist.
        """
        from management.audit.audit_log import AuditLog
        from management.gateway.coordinator_writer import CoordinatorWriter
        from db.journal_policy import apply_journal_mode

        pid = self._person_id()
        if pid is None:
            raise BildschleierFehler(
                "Keine angemeldete Person aufloesbar — Umschalten nicht "
                "moeglich.")
        pfad = self._coordinator_pfad()
        if not pfad:
            raise BildschleierFehler("Kein coordinator.db-Pfad bekannt.")
        con = sqlite3.connect(pfad, timeout=5.0, isolation_level=None)
        con.row_factory = sqlite3.Row
        try:
            apply_journal_mode(con, pfad, log=logger)
            con.execute("PRAGMA busy_timeout=5000")
            writer = CoordinatorWriter(con, AuditLog(con))
            BildschleierRepo(con, writer).setzen(
                person_id=pid, veiled=bool(veiled), actor_id=pid)
        finally:
            con.close()
        return self.aktualisieren()


# ---------------------------------------------------------------------------
# Prozessweite Instanz (siehe Modulkopf: ein Webserver, eine Person)
# ---------------------------------------------------------------------------
_INSTANZ: Optional[BildschleierDienst] = None
_INSTANZ_LOCK = threading.Lock()


def dienst(config: "ConfigLoader", context: "ResolvedContext") -> BildschleierDienst:
    """Die prozessweite Instanz; beim ersten Aufruf angelegt."""
    global _INSTANZ
    with _INSTANZ_LOCK:
        if _INSTANZ is None:
            _INSTANZ = BildschleierDienst(config, context)
        return _INSTANZ


def zuruecksetzen_fuer_tests() -> None:
    """Nur fuer Tests: die prozessweite Instanz verwerfen."""
    global _INSTANZ
    with _INSTANZ_LOCK:
        _INSTANZ = None


def zustand_html_attribute(z: BildschleierZustand) -> str:
    """
    Die Attribute fuer das <html>-Element der Shell (HTML-escaped).
    Die Klasse steht nur bei veiled; die data-Attribute immer, damit
    toolbar/bildschleier.js die Schaltflaeche ohne eigene Abfrage zeichnen
    kann.
    """
    import html as _html
    teile = []
    if z.veiled:
        from core.bildschleier_css import HTML_KLASSE
        teile.append('class="%s"' % HTML_KLASSE)
    teile.append('data-image-veil-veiled="%s"' % ("1" if z.veiled else "0"))
    teile.append('data-image-veil-locked="%s"' % ("1" if z.locked else "0"))
    teile.append('data-image-veil-reason="%s"' % _html.escape(z.reason, quote=True))
    teile.append('data-image-veil-tooltip="%s"' % _html.escape(z.tooltip, quote=True))
    return " ".join(teile)
