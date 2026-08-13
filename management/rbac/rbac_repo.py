# =============================================================================
# management/rbac/rbac_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Auditierte Zugriffsschicht auf die RBAC-Matrix (rbac_grant, person_role) in
#   coordinator.db. JEDER Schreibvorgang laeuft ueber das CoordinatorWriter-
#   Gateway; die geschriebene Zeile traegt per audit_seq die exakte seq ihres
#   audit_log-Belegs (Kopplung wie case_events, Beleg §8.3). Damit existiert kein
#   Grant / keine Rollenzuweisung ohne lueckenlosen Beleg (Grundregel 1).
#
# Entwurfsentscheidungen (Beleg: Bauplan B7 v1.1 §11.1/§11.3/§11.7, Schnitt b;
# mc 2026-07-10):
#   - KATALOG-VALIDIERUNG: role_code muss in catalog.ROLE_CODES, capability_code
#     in catalog.CAPABILITY_CODES liegen; scope in {'alle','eigene',None}. Der
#     Katalog (catalog.py) ist die Wahrheitsquelle im Code; ungueltige Codes
#     werden mit RbacError abgewiesen (kein stiller Fehlgriff).
#   - APPEND-ONLY Soft-Revoke: KEIN DELETE. Ruecknahme setzt revoked_at/by +
#     revoke_audit_seq; die Zeile bleibt als Beleg erhalten. 'aktiv' = revoked_at
#     IS NULL.
#   - LOGISCHE EINDEUTIGKEIT je aktivem Schluessel: ein zweiter AKTIVER Grant fuer
#     dasselbe (role_code, capability_code) bzw. eine zweite AKTIVE Zuweisung fuer
#     dasselbe (person_id, role_code) wird abgewiesen. Scope-Aenderung erfolgt per
#     revoke-then-grant (append-only), nicht per Update.
#   - DEFAULT-DENY: leere Matrix = niemand darf etwas. Die Durchsetzung (Resolver)
#     ist Schnitt (c); dieses Modul stellt nur den Schreibpfad + Leser bereit.
#
# ── BUILD 716 — ZWEITER WAECHTER BEIM GRANT (Vorgang 1b7d55ae) ────────────────
#
#   DER SPALT. Die Katalog-Validierung oben prueft capability_code gegen
#   catalog.CAPABILITY_CODES — also gegen den Katalog im CODE. Ob die
#   Faehigkeit in rbac_capability der DATENBANK steht, prueft sie nicht, und
#   die Fremdschluessel der coordinator.db greifen bei foreign_keys=OFF nicht.
#   Zwischen dem Einspielen einer Lieferung und dem Migrationslauf laufen die
#   beiden Kataloge auseinander; in genau diesem Spalt entsteht ein Grant auf
#   ein Recht, das die Datenbank nicht kennt — klaglos.
#
#   WAS DAS ANRICHTETE: Vorgang 9c4e17b2 (Grant #62 vom 12.08.2026). Der
#   Bestand war danach VERRIEGELT — die Migration, die das Recht anlegen
#   sollte, brach an der Waise ab, und der vorgesehene Rueckweg (Soft-Revoke)
#   half nicht (Herleitung im Kopf von m038_caseoverview_rbac.py). Die
#   Vorbeugung sass seit Build 711 allein im CLI-Werkzeug 'migrate-grants',
#   also an dem einen Weg, auf dem es damals geschah. Jeder andere Weg konnte
#   dieselbe Waise weiter erzeugen.
#
#   DIE PRUEFUNG SITZT JETZT IM REPOSITORY, also an der Stelle, durch die
#   ALLE Schreibwege laufen. Sie steht INNERHALB der Schreibsperre (in _w),
#   nicht in _validate_capability: der statische Validierer hat keine
#   Verbindung, und ausserhalb der Sperre waere die Antwort ein TOCTOU-Befund.
#   Damit steht sie an derselben Stelle wie der Duplikat-Guard und aus
#   demselben Grund.
#
#   ABWEISEN, NICHT WARNEN (Weisung Alex, 13.08.2026). GEMESSEN VORHER, nicht
#   geschaetzt: eine Sonde an genau dieser Stelle hat die volle Testsuite
#   mitgeschrieben — 1958 Grant-Aufrufe, davon 2 mit einer in der Datenbank
#   unbekannten Faehigkeit, 0 ohne die Tabelle rbac_capability. Produktive
#   Aufrufer sind drei: rbac_admin 'grant', rbac_admin 'migrate-grants' (das
#   prueft seit Build 711 selbst, vorgelagert) und demo_seed. Das Management
#   ist nicht betroffen — die Grant-Matrix ist CLI-only (management_app.py
#   Z. 118/484), dort laeuft nur assign_role.
#
#   FEHLENDE TABELLE WARNT NUR UND LAESST DURCH. 'rbac_capability existiert
#   nicht' ist eine andere Lage als 'die Migration steht noch aus': die erste
#   heisst 'nicht pruefbar', die zweite 'nachweislich falsch'. Dieselbe
#   Unterscheidung trifft _nicht_in_db in rbac_admin (None gegen leere Liste).
#   Ein Abbruch auf 'nicht pruefbar' traefe Altbestaende, ueber die wir keinen
#   Befund haben — und der Vorgang 9c4e17b2 entstand nicht so.
#
#   DER NOTAUSGANG 'db_katalog_pruefen=False' ist fuer die zwei gemessenen
#   Faelle da und fuer nichts sonst: SperrriegelTests RB11/RB11b in
#   tests/test_rechtetrennung_falluebersicht.py stellen die Lage vom
#   12.08.2026 nach und MUESSEN die Waise erzeugen koennen, um zu belegen,
#   dass M038 seit Build 711 nicht mehr daran haengenbleibt. Rohes SQL
#   scheidet dafuer aus — RB11 prueft die Beleg-seq des Grants, der Grant muss
#   also ein ordentlich belegter sein. Die Voreinstellung ist streng: wer
#   RbacRepo.grant kuenftig aufruft, ist gedeckt, ohne davon zu wissen.
#
#   UND DER UEBERGANGENE WAECHTER BLEIBT NICHT STILL (Grundregel 1): sowohl
#   der Notausgang als auch die nicht pruefbare Lage schreiben einen Vermerk
#   in die audit_log-Nutzlast des Grants (Schluessel 'db_katalog') und eine
#   Zeile ins Protokoll. Im Regelfall bleibt die Nutzlast unveraendert —
#   der Schluessel entsteht nur in der Ausnahme.
#
# Version: v0.7.344 · Build: 344 · 2026-07-10
#   erweitert v0.8.716 · Build: 716 · 2026-08-13 (Vorgang 1b7d55ae:
#   Grant prueft zusaetzlich den Katalog der DATENBANK)
# =============================================================================

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.gateway.coordinator_writer import CoordinatorWriter
from management.rbac import catalog

logger = logging.getLogger(__name__)

#: Zulaessige Scope-Werte (None = ohne Scope-Unterscheidung).
_VALID_SCOPES = ("alle", "eigene", None)


class RbacError(Exception):
    """Fachlicher RBAC-Fehler (ungueltiger Code, Duplikat, nicht vorhanden)."""


class RbacRepo:
    """Auditierte Lese-/Schreibmethoden auf rbac_grant und person_role."""

    def __init__(self, con: sqlite3.Connection, writer: CoordinatorWriter) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._writer = writer

    # =====================================================================
    #  Grants (rbac_grant): Rolle -> Faehigkeit [+ Scope]
    # =====================================================================
    def grant(
        self, role_code: str, capability_code: str, *,
        scope: Optional[str] = None, actor_id: Optional[int] = None,
        note: Optional[str] = None, meta: Optional[Any] = None,
        db_katalog_pruefen: bool = True,
    ) -> int:
        """
        Vergibt einer Rolle eine Faehigkeit (optional mit Scope). Beleg
        RBAC_GRANTED; die neue rbac_grant-Zeile traegt audit_seq == Beleg-seq.
        Gibt die audit_log-seq zurueck.

        db_katalog_pruefen (Build 716, Vorgang 1b7d55ae): steht die Faehigkeit
        nicht in rbac_capability der DATENBANK, wird der Grant abgewiesen.
        NUR die Nachstellung des Vorgangs 9c4e17b2 (SperrriegelTests RB11/RB11b)
        setzt das auf False; sie braucht die Waise als Ausgangslage. Jede
        andere Verwendung waere die Wiederherstellung genau des Lochs, das
        dieser Waechter schliesst. Der uebergangene Waechter bleibt nicht
        still: er vermerkt sich in der audit_log-Nutzlast.
        """
        self._validate_role(role_code)
        self._validate_capability(capability_code)
        self._validate_scope(scope)
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            # ZWEITER KATALOG (Build 716): kennt die DATENBANK das Recht? Die
            # Pruefung steht hier und nicht in _validate_capability, weil sie
            # eine Verbindung braucht und weil sie - wie der Duplikat-Guard
            # darunter - INNERHALB der Schreibsperre stehen muss (kein TOCTOU).
            vermerk = None
            kennt = self._db_kennt_faehigkeit(con, capability_code)
            if kennt is None:
                # Tabelle fehlt: NICHT PRUEFBAR, nicht 'nachweislich falsch'.
                # Durchlassen, aber benennen (Grundregel 1).
                vermerk = "nicht_pruefbar_tabelle_fehlt"
                logger.warning(
                    "Grant %s -> %s: die Datenbank hat keine Tabelle "
                    "'rbac_capability' (Migration M006 nicht angewandt). Der "
                    "Katalog der Datenbank konnte NICHT geprueft werden; der "
                    "Grant wird geschrieben und traegt einen Vermerk.",
                    role_code, capability_code,
                )
            elif not kennt:
                if db_katalog_pruefen:
                    raise RbacError(
                        "Die Faehigkeit '%s' steht im Katalog des Codes, aber "
                        "NICHT in rbac_capability dieser Datenbank. Die "
                        "zugehoerige Migration ist noch nicht angewandt - "
                        "zuerst 'python -m management.migrate' fahren, dann "
                        "diesen Grant. Es wurde NICHTS geschrieben. Grund: ein "
                        "Grant auf ein der Datenbank unbekanntes Recht "
                        "entsteht klaglos (die Fremdschluessel greifen bei "
                        "foreign_keys=OFF nicht) und behindert danach die "
                        "Migration, die das Recht anlegen soll (Vorgang "
                        "9c4e17b2)." % capability_code
                    )
                vermerk = "unbekannt_uebergangen"
                logger.warning(
                    "Grant %s -> %s: die Faehigkeit steht NICHT in "
                    "rbac_capability dieser Datenbank. Die Pruefung wurde mit "
                    "db_katalog_pruefen=False ausdruecklich uebergangen; der "
                    "Grant entsteht als Waise und traegt einen Vermerk.",
                    role_code, capability_code,
                )

            # Duplikat-Guard INNERHALB der Schreibsperre (kein TOCTOU).
            if con.execute(
                "SELECT 1 FROM rbac_grant WHERE role_code=? AND "
                "capability_code=? AND revoked_at IS NULL",
                (role_code, capability_code),
            ).fetchone() is not None:
                raise RbacError(
                    "Aktiver Grant %s -> %s existiert bereits (fuer Scope-"
                    "Aenderung erst zuruecknehmen)."
                    % (role_code, capability_code)
                )
            nutzlast = {"role_code": role_code,
                        "capability_code": capability_code, "scope": scope}
            # Der Schluessel entsteht NUR in der Ausnahme - im Regelfall
            # bleibt die Nutzlast Zeichen fuer Zeichen die von vorher.
            if vermerk is not None:
                nutzlast["db_katalog"] = vermerk
            return nutzlast

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute(
                "INSERT INTO rbac_grant "
                "(role_code, capability_code, scope, audit_seq, granted_by, "
                " granted_at, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (role_code, capability_code, scope, seq, actor_id, now, note),
            )

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.RBAC_GRANTED,
            actor_id=actor_id, target_type="rbac_grant",
            target_id="%s/%s" % (role_code, capability_code),
            meta=meta, after_audit=_after,
        )

    def revoke_grant(
        self, grant_id: int, *, actor_id: Optional[int] = None,
        note: Optional[str] = None, meta: Optional[Any] = None,
    ) -> int:
        """
        Nimmt einen Grant zurueck (Soft-Revoke, kein DELETE). Beleg
        RBAC_REVOKED; setzt revoked_at/by + revoke_audit_seq == Beleg-seq.
        """
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = con.execute(
                "SELECT role_code, capability_code, revoked_at FROM rbac_grant "
                "WHERE id=?", (grant_id,)
            ).fetchone()
            if row is None:
                raise RbacError("Kein Grant id=%s." % grant_id)
            if row["revoked_at"] is not None:
                raise RbacError("Grant id=%s ist bereits zurueckgenommen."
                                % grant_id)
            return {"grant_id": grant_id, "role_code": row["role_code"],
                    "capability_code": row["capability_code"]}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute(
                "UPDATE rbac_grant SET revoked_at=?, revoked_by=?, "
                "revoke_audit_seq=?, note=COALESCE(?, note) WHERE id=?",
                (now, actor_id, seq, note, grant_id),
            )

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.RBAC_REVOKED,
            actor_id=actor_id, target_type="rbac_grant",
            target_id=str(grant_id), meta=meta, after_audit=_after,
        )

    # =====================================================================
    #  Rollenzuweisungen (person_role): Person -> Rolle
    # =====================================================================
    def assign_role(
        self, person_id: int, role_code: str, *,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
    ) -> int:
        """
        Weist einer Person eine Rolle zu. Beleg ROLE_ASSIGNED; die person_role-
        Zeile traegt audit_seq == Beleg-seq.
        """
        self._validate_role(role_code)
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            if con.execute(
                "SELECT 1 FROM person WHERE id=?", (person_id,)
            ).fetchone() is None:
                raise RbacError("Keine Person id=%s." % person_id)
            if con.execute(
                "SELECT 1 FROM person_role WHERE person_id=? AND role_code=? "
                "AND revoked_at IS NULL", (person_id, role_code),
            ).fetchone() is not None:
                raise RbacError(
                    "Person id=%s hat die Rolle '%s' bereits aktiv."
                    % (person_id, role_code)
                )
            return {"person_id": person_id, "role_code": role_code}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute(
                "INSERT INTO person_role "
                "(person_id, role_code, assigned_by, assigned_at, audit_seq) "
                "VALUES (?, ?, ?, ?, ?)",
                (person_id, role_code, actor_id, now, seq),
            )

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.ROLE_ASSIGNED,
            actor_id=actor_id, target_type="person_role",
            target_id="%s/%s" % (person_id, role_code),
            meta=meta, after_audit=_after,
        )

    def revoke_role(
        self, person_role_id: int, *, actor_id: Optional[int] = None,
        meta: Optional[Any] = None,
    ) -> int:
        """
        Nimmt eine Rollenzuweisung zurueck (Soft-Revoke, kein DELETE). Beleg
        ROLE_REVOKED; setzt revoked_at/by + revoke_audit_seq == Beleg-seq.
        """
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = con.execute(
                "SELECT person_id, role_code, revoked_at FROM person_role "
                "WHERE id=?", (person_role_id,)
            ).fetchone()
            if row is None:
                raise RbacError("Keine Rollenzuweisung id=%s." % person_role_id)
            if row["revoked_at"] is not None:
                raise RbacError(
                    "Rollenzuweisung id=%s ist bereits zurueckgenommen."
                    % person_role_id
                )
            return {"person_role_id": person_role_id,
                    "person_id": row["person_id"], "role_code": row["role_code"]}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute(
                "UPDATE person_role SET revoked_at=?, revoked_by=?, "
                "revoke_audit_seq=? WHERE id=?",
                (now, actor_id, seq, person_role_id),
            )

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.ROLE_REVOKED,
            actor_id=actor_id, target_type="person_role",
            target_id=str(person_role_id), meta=meta, after_audit=_after,
        )

    # =====================================================================
    #  Leser (rein lesend; Durchsetzung/Aufloesung folgt in Schnitt c)
    # =====================================================================
    def list_grants(self, *, active_only: bool = True) -> List[Dict[str, Any]]:
        """Grants auflisten (Standard: nur aktive)."""
        sql = (
            "SELECT id, role_code, capability_code, scope, audit_seq, "
            "       granted_by, granted_at, revoked_at, revoked_by, "
            "       revoke_audit_seq, note FROM rbac_grant"
        )
        if active_only:
            sql += " WHERE revoked_at IS NULL"
        sql += " ORDER BY role_code, capability_code, id"
        return [dict(r) for r in self._con.execute(sql).fetchall()]

    def list_person_roles(
        self, person_id: Optional[int] = None, *, active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Rollenzuweisungen auflisten (optional gefiltert auf eine Person)."""
        clauses = []
        params: List[Any] = []
        if person_id is not None:
            clauses.append("person_id = ?")
            params.append(person_id)
        if active_only:
            clauses.append("revoked_at IS NULL")
        sql = (
            "SELECT id, person_id, role_code, assigned_by, assigned_at, "
            "       revoked_at, revoked_by, audit_seq, revoke_audit_seq "
            "FROM person_role"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY person_id, role_code, id"
        return [dict(r) for r in self._con.execute(sql, params).fetchall()]

    def get_grant(self, grant_id: int) -> Optional[Dict[str, Any]]:
        row = self._con.execute(
            "SELECT * FROM rbac_grant WHERE id=?", (grant_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    # --------------------------------------------------------------- Validierung
    @staticmethod
    def _validate_role(role_code: str) -> None:
        if role_code not in catalog.ROLE_CODES:
            raise RbacError(
                "Unbekannte Rolle '%s' (nicht im Katalog)." % role_code)

    @staticmethod
    def _validate_capability(capability_code: str) -> None:
        if capability_code not in catalog.CAPABILITY_CODES:
            raise RbacError(
                "Unbekannte Faehigkeit '%s' (nicht im Katalog)."
                % capability_code)

    @staticmethod
    def _db_kennt_faehigkeit(
        con: sqlite3.Connection, capability_code: str,
    ) -> Optional[bool]:
        """
        Steht 'capability_code' in rbac_capability DIESER Datenbank?

        -> True  = ja
        -> False = nein (Migration steht aus - nachweislich falsch)
        -> None  = die Tabelle selbst fehlt (M006 nicht angewandt - NICHT
                   pruefbar)

        Die Dreiwertigkeit ist der Zweck der Funktion und kein Zierrat: die
        beiden Nein-Faelle brauchen unterschiedliche Antworten (Abbruch gegen
        Vermerk), weil sie unterschiedliche Befunde sind. Dieselbe
        Unterscheidung trifft _nicht_in_db in rbac_admin fuer den CLI-Weg;
        beide Stellen bleiben bestehen: dort wird VOR dem ersten Schreibvorgang
        eines Uebernahmelaufs geprueft (damit ein Lauf gar nicht erst
        anfaengt), hier bei JEDEM einzelnen Grant, gleich welcher Weg ihn
        anstoesst (Vorgang 1b7d55ae).
        """
        if con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND "
            "name='rbac_capability'"
        ).fetchone() is None:
            return None
        return con.execute(
            "SELECT 1 FROM rbac_capability WHERE code=?", (capability_code,)
        ).fetchone() is not None

    @staticmethod
    def _validate_scope(scope: Optional[str]) -> None:
        if scope not in _VALID_SCOPES:
            raise RbacError(
                "Ungueltiger Scope %r (erlaubt: 'alle', 'eigene', keiner)."
                % scope)
