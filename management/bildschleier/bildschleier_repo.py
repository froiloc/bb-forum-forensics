# =============================================================================
# management/bildschleier/bildschleier_repo.py
# IT-Forensisches Ermittlungswerkzeug — Bildschleier (Build 771)
# =============================================================================
# Zweck:
#   Ermittelt den Bildschleier-Zustand einer Person und schreibt ihre Wahl
#   (Tabelle person_image_veil, M040). Lesen ohne Schreiber, Schreiben
#   ausschliesslich ueber CoordinatorWriter mit audit_log-Beleg
#   (Muster ViewPrefRepo, Build 545).
#
# ── DIE ENTSCHEIDUNGSFOLGE (Bauplan §4.1) ───────────────────────────────────
#
#   1. Keine Person aufloesbar              -> no_investigator  (gesperrt)
#   2. RBAC nicht lesbar (sqlite3.Error)    -> rbac_unavailable (gesperrt)
#   3. Rolle 'researcher' aktiv             -> required_by_role (gesperrt)
#   4. Recht 'imageveil.lift' fehlt         -> no_capability    (gesperrt)
#   5. Wahl nicht lesbar (sqlite3.Error)    -> store_unavailable (gesperrt)
#   6. Zeile vorhanden                      -> chosen  (veiled = Zeile)
#   7. keine Zeile                          -> default (veiled = False)
#
#   Schritt 3 VOR Schritt 4, und das ist der Kern: die Rolle 'researcher'
#   setzt sich gegen jedes Recht durch, auch wenn eine zweite Rolle der
#   Person 'imageveil.lift' mitbringt. Begruendung im Katalog
#   (management/rbac/catalog.py, Rolle 'researcher').
#
# ── NUR sqlite3.Error WIRD ABGEFANGEN ───────────────────────────────────────
#
#   Lehre aus Build 769: ein 'except Exception' verschluckte dort einen
#   Programmierfehler (falscher Feldname) und lieferte stillschweigend ein
#   leeres Ergebnis. Hier werden deshalb NUR Datenbankfehler zu einem Grund.
#   Alles andere fliegt weiter; der Webserver faengt es an EINER Stelle ab,
#   protokolliert es mit Traceback und meldet 'internal_error' — gesperrt und
#   verschleiert, aber nicht als Betriebsstoerung getarnt.
#
# ── EINE PERSON SCHREIBT NUR IHRE EIGENE WAHL ───────────────────────────────
#
#   Kein Scope, keine Vertretung (Muster ViewPrefRepo). Wer fuer eine andere
#   Person den Schleier abschalten koennte, koennte ihr ungefragt Bilder
#   zeigen — genau das soll niemand koennen.
#
# Version: v0.8.771 · Build: 771 · 2026-10-09
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Optional

from management.audit.event_types import EventType
from management.bildschleier.bildschleier_zustand import (
    GRUND_GEWAEHLT, GRUND_KEINE_PERSON, GRUND_RBAC_FEHLT, GRUND_RECHT_FEHLT,
    GRUND_ROLLE, GRUND_SPEICHER_FEHLT, GRUND_VORGABE, BildschleierZustand,
)
from management.gateway.coordinator_writer import CoordinatorWriter
from management.rbac.rbac_resolver import RbacResolver

logger = logging.getLogger(__name__)

#: Das Recht, den Schleier selbst zu schalten (Seed in M040).
RECHT = "imageveil.lift"
#: Die Rolle, fuer die der Schleier verpflichtend ist (Seed in M040).
ROLLE_PFLICHT = "researcher"


class BildschleierFehler(Exception):
    """Ein Schreibwunsch ist unzulaessig (fehlendes Recht, fremde Person,
    falscher Wert). Die Meldung ist fuer das Protokoll und die Antwort des
    Endpunkts bestimmt."""


class BildschleierRepo:
    """Zustand lesen und Wahl auditiert schreiben."""

    def __init__(self, con: sqlite3.Connection,
                 writer: Optional[CoordinatorWriter] = None) -> None:
        self._con = con
        self._writer = writer

    # ------------------------------------------------------------- Lesen ---
    def zustand(self, person_id: Optional[int]) -> BildschleierZustand:
        """Der Zustand nach der Entscheidungsfolge im Modulkopf."""
        if person_id is None:
            logger.info("Bildschleier: keine Person aufloesbar -> %s",
                        GRUND_KEINE_PERSON)
            return BildschleierZustand.gesperrt(GRUND_KEINE_PERSON)

        try:
            policy = RbacResolver(self._con).resolve(int(person_id))
        except sqlite3.Error as exc:
            logger.error("Bildschleier: RBAC fuer Person %s nicht lesbar: %s",
                         person_id, exc)
            return BildschleierZustand.gesperrt(GRUND_RBAC_FEHLT)

        if ROLLE_PFLICHT in policy.roles:
            if policy.can(RECHT):
                # Kein Fehler, aber ein Befund: jemand hat der Person eine
                # zweite Rolle mit dem Recht gegeben. Die Rolle setzt sich
                # durch — gesagt wird es trotzdem (Grundregel 1).
                logger.warning(
                    "Bildschleier: Person %s traegt '%s' UND das Recht '%s' "
                    "(Rollen: %s). Die Rolle hat Vorrang; der Schleier bleibt.",
                    person_id, ROLLE_PFLICHT, RECHT,
                    ", ".join(sorted(policy.roles)))
            return BildschleierZustand.gesperrt(GRUND_ROLLE)

        if not policy.can(RECHT):
            return BildschleierZustand.gesperrt(GRUND_RECHT_FEHLT)

        try:
            row = self._con.execute(
                "SELECT veiled FROM person_image_veil WHERE person_id = ?",
                (int(person_id),)).fetchone()
        except sqlite3.Error as exc:
            logger.error(
                "Bildschleier: gespeicherte Wahl von Person %s nicht lesbar "
                "(M040 angewandt?): %s", person_id, exc)
            return BildschleierZustand.gesperrt(GRUND_SPEICHER_FEHLT)

        if row is None:
            return BildschleierZustand(veiled=False, locked=False,
                                       reason=GRUND_VORGABE)
        return BildschleierZustand(veiled=bool(row[0]), locked=False,
                                   reason=GRUND_GEWAEHLT)

    # ---------------------------------------------------------- Schreiben ---
    def setzen(self, *, person_id: int, veiled: bool,
               actor_id: Optional[int]) -> int:
        """
        Speichert die Wahl und schreibt EINEN audit_log-Beleg.
        Gibt die seq des Belegs zurueck.

        Prueft das Recht SELBST, nicht erst der Endpunkt: der Schreibweg ist
        die Stelle, an der eine Regel halten muss, gleich wer ihn aufruft.
        """
        if self._writer is None:
            raise BildschleierFehler(
                "Kein Schreibweg: BildschleierRepo wurde ohne "
                "CoordinatorWriter erzeugt.")
        if actor_id is None:
            raise BildschleierFehler(
                "Eine Aenderung ohne handelnde Person ist kein Beleg "
                "(actor_id fehlt).")
        if int(actor_id) != int(person_id):
            raise BildschleierFehler(
                "Den Bildschleier kann nur die betroffene Person selbst "
                "schalten (actor_id %d != person_id %d)."
                % (int(actor_id), int(person_id)))
        if not isinstance(veiled, bool):
            raise BildschleierFehler(
                "'veiled' muss true oder false sein, erhalten: %r" % (veiled,))

        vorher = self.zustand(int(person_id))
        if vorher.locked:
            raise BildschleierFehler(
                "Umschalten nicht zulaessig: %s (Grund '%s')."
                % (vorher.tooltip, vorher.reason))

        now = int(time.time())
        pid = int(person_id)

        def _w(con: sqlite3.Connection):
            # audit_seq zunaechst 0, im after_audit-Hook auf die echte seq
            # gesetzt — dieselbe Transaktion, atomar (Muster ViewPrefRepo).
            con.execute(
                "INSERT INTO person_image_veil (person_id, veiled, "
                "changed_at, audit_seq) VALUES (?, ?, ?, 0) "
                "ON CONFLICT(person_id) DO UPDATE SET "
                "veiled = excluded.veiled, changed_at = excluded.changed_at, "
                "audit_seq = 0",
                (pid, 1 if veiled else 0, now))
            # Payload: der VOLLSTAENDIGE Zustand nach der Aenderung.
            return {"veiled": bool(veiled)}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute(
                "UPDATE person_image_veil SET audit_seq = ? "
                "WHERE person_id = ?", (seq, pid))

        seq = self._writer.audited_write(
            do_write=_w, event_type=EventType.IMAGE_VEIL_SET,
            actor_id=int(actor_id), target_type="person_image_veil",
            target_id=str(pid), after_audit=_after)
        logger.info("Bildschleier: Person %d -> %s (audit seq=%d)",
                    pid, "verschleiert" if veiled else "klar", seq)
        return seq
