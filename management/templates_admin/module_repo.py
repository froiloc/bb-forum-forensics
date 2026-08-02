# =============================================================================
# management/templates_admin/module_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — W1 (Build 426): Lese-/Schreib-Repo der Baustein-Module
# =============================================================================
# Zweck:
#   Liest report_modules (fuer die Liste in der Autoren-Maske) und schreibt sie
#   AUSSCHLIESSLICH ueber den auditierten TemplatesWriter (Build 421). Ein Upsert
#   (create ODER update, nach der stabilen module_key) laeuft mit seinem
#   Audit-Eintrag (target_type='module') in EINER Transaktion.
#
#   Die Validierung (module_validator) erfolgt VOR dem Aufruf von upsert() im
#   Endpunkt — das Repo schreibt nur bereits gepruefte Module.
#
# Version: v0.7.426 · Build: 426 · 2026-07-15
# =============================================================================

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.gateway.templates_writer import TemplatesWriter


class ModuleKeyAssignError(Exception):
    """
    Build 564: Ein module_key laesst sich nicht (so) nachtragen. Traegt das
    schuldige Feld mit, damit die Maske es markieren kann - dasselbe Muster
    wie CapacityError seit Build 560.
    """

    def __init__(self, message: str, feld: str = None) -> None:
        super().__init__(message)
        self.feld = feld


class ModuleAuthorRepo:
    """Lese-/Schreibzugriff auf templates.db.report_modules."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row

    # ------------------------------------------------------------------
    def list(self) -> List[Dict[str, Any]]:
        rows = self._con.execute(
            "SELECT id, module_key, title, description, role, topic, body, "
            "sort_order, is_active, created_by, created_at, updated_at, "
            "block_type, block_data "
            "FROM report_modules ORDER BY role, sort_order, module_key"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_by_key(self, key: str) -> Optional[Dict[str, Any]]:
        row = self._con.execute(
            "SELECT id, module_key, title, description, role, topic, body, "
            "sort_order, is_active, created_by, created_at, updated_at, "
            "block_type, block_data "
            "FROM report_modules WHERE module_key = ?", (key,)).fetchone()
        return dict(row) if row is not None else None

    def get_by_id(self, row_id: int) -> Optional[Dict[str, Any]]:
        """
        Build 564: Zugriff ueber die Zeilen-id. Noetig fuer den EINZIGEN Fall,
        in dem der module_key als Adresse nicht taugt - naemlich wenn er noch
        gar nicht vergeben ist (Altbestand vor der Schluessel-Migration).
        """
        row = self._con.execute(
            "SELECT id, module_key, title, description, role, topic, body, "
            "sort_order, is_active, created_by, created_at, updated_at, "
            "block_type, block_data "
            "FROM report_modules WHERE id = ?", (row_id,)).fetchone()
        return dict(row) if row is not None else None

    # ------------------------------------------------------------------
    def upsert(self, m: Dict[str, Any], changed_by: str,
               *, ts: Optional[int] = None) -> Dict[str, Any]:
        """
        Legt einen Baustein an ODER aktualisiert ihn (nach module_key). Auditiert
        ueber den TemplatesWriter (target_type='module'). Gibt {target_id,
        created(bool)} zurueck.
        """
        key = str(m["module_key"]).strip()

        # ------------------------------------------------------------------
        # BUILD 564 - SCHLUESSEL NACHTRAGEN.
        # Bis hierher adressierte der Upsert AUSSCHLIESSLICH ueber module_key.
        # Fuer Altzeilen ohne Schluessel war das eine Sackgasse: sie liessen
        # sich nicht ansprechen, und ein neu getippter Schluessel haette nichts
        # gefunden - der Upsert haette eine ZWEITE Zeile angelegt und die alte
        # unerreichbar daneben stehen lassen. Aus einem gesperrten Baustein
        # waeren zwei geworden.
        #
        # Deshalb der Sonderweg ueber die Zeilen-id, und NUR fuer diesen einen
        # Fall: ist eine id angegeben und traegt die Zeile noch KEINEN
        # Schluessel, wird sie per id aktualisiert und bekommt ihn zugewiesen.
        #
        # DER SCHLUESSEL IST DANACH ENDGUELTIG (mc 2026-07-29). Er ist eine
        # STABILE Kennung (Build 341): Berichtsvorlagen verweisen ueber ihn auf
        # den Baustein. Wanderte er, braeche jede referenzierende Vorlage - und
        # zwar still, denn ein nicht gefundener Baustein faellt erst beim
        # Erzeugen des Berichts auf. Ein Umtragen wird deshalb ABGEWIESEN.
        # ------------------------------------------------------------------
        nachtrag_id = m.get("id")
        nachtrag = False
        if nachtrag_id is not None and str(nachtrag_id) != "":
            ziel = self.get_by_id(int(nachtrag_id))
            if ziel is None:
                raise ModuleKeyAssignError(
                    "Unbekanntes Baustein-Modul (id=%s)." % nachtrag_id, "id")
            if ziel.get("module_key"):
                raise ModuleKeyAssignError(
                    "Das Modul traegt bereits den Schluessel '%s'. Ein "
                    "module_key ist eine stabile Kennung, auf die "
                    "Berichtsvorlagen verweisen - er wird nicht umgetragen."
                    % ziel["module_key"], "module_key")
            kollision = self.get_by_key(key)
            if kollision is not None:
                # VOR dem Schreiben pruefen: der partielle Unique-Index wuerde
                # sonst einen IntegrityError werfen, und der sagt dem
                # Ausfuellenden nichts.
                raise ModuleKeyAssignError(
                    "Der Schluessel '%s' ist bereits vergeben (Modul id=%s, "
                    "'%s')." % (key, kollision["id"], kollision["title"]),
                    "module_key")
            nachtrag = True
            existing = ziel
            created = False
        else:
            existing = self.get_by_key(key)
            created = existing is None
        now = int(ts if ts is not None else time.time())

        title = str(m["title"]).strip()
        desc = m.get("description")
        desc = None if desc is None else str(desc)
        role = m["role"]
        topic = str(m["topic"]).strip()
        body = str(m["body"])
        sort_order = int(m.get("sort_order") or 0)

        # ------------------------------------------------------------------
        # BUILD 655 (Ticket 5d81a0c7) - BLOCKTYP UND BLOCKDATEN.
        #
        # DIE WICHTIGSTE ZEILE DIESES BUILDS STEHT HIER: FEHLT EIN FELD IM
        # PAYLOAD, BLEIBT DER BESTANDSWERT STEHEN. Es wird NICHT auf den
        # Vorgabewert zurueckgesetzt.
        #
        # Warum das kein Feinschliff ist, sondern der Unterschied zwischen
        # Migration und Datenverlust: Die Maske aus Build 654 sendet diese
        # beiden Felder noch gar nicht - die Eingabe dafuer kommt erst mit
        # Build 656. Wuerde ein fehlendes Feld als "leer" gedeutet, dann
        # loeschte JEDES Speichern aus der alten Maske die Blockdaten eines
        # Bausteins, der sie schon hat. Ein Redakteur, der nur den Titel
        # korrigiert, verlöre den Tabelleninhalt - und zwar still.
        #
        # Deshalb die Unterscheidung zwischen "Feld nicht dabei" (Bestand
        # behalten) und "Feld dabei, aber leer" (ausdrueckliches Loeschen).
        # 'in m' ist hier bedeutungstragend und darf nicht zu m.get()
        # vereinfacht werden.
        # ------------------------------------------------------------------
        if "block_type" in m and m["block_type"]:
            block_type = str(m["block_type"])
        elif existing is not None:
            block_type = str(existing.get("block_type") or "paragraph")
        else:
            block_type = "paragraph"

        if "block_data" in m:
            bd = m["block_data"]
            # Der Speicherwert ist TEXT (JSON). Ein dict aus der API wird
            # hier serialisiert - nicht in der API, damit es genau eine
            # Stelle gibt, die ueber die Speicherform entscheidet.
            if bd is None or bd == "":
                block_data = None
            elif isinstance(bd, (dict, list)):
                block_data = json.dumps(bd, ensure_ascii=False)
            else:
                block_data = str(bd)
        elif existing is not None:
            block_data = existing.get("block_data")
        else:
            block_data = None

        # Kanonische Vorher/Nachher-Werte fuer den Audit (nur Fakten, kompakt;
        # der volle body-Text wird NICHT in den Audit kopiert — er kann sehr
        # lang sein; die Laenge genuegt als Beleg der Aenderung).
        neu_dict = {"title": title, "role": role, "topic": topic,
                    "body_len": len(body),
                    # Build 655: der Blocktyp gehoert in den Audit - er
                    # aendert, WIE der Baustein im Bericht erscheint. Die
                    # Blockdaten selbst nicht (sie koennen sehr lang sein);
                    # ihre Laenge genuegt als Beleg der Aenderung, wie beim
                    # body auch.
                    "block_type": block_type,
                    "block_data_len": len(block_data or "")}
        alt_dict = None
        if existing is not None:
            alt_dict = {"title": existing.get("title"),
                        "role": existing.get("role"),
                        "topic": existing.get("topic"),
                        "body_len": len(str(existing.get("body") or "")),
                        "block_type": existing.get("block_type") or "paragraph",
                        "block_data_len": len(
                            str(existing.get("block_data") or ""))}
        if nachtrag:
            # DIE ZUWEISUNG IST EINE EIGENE TATSACHE und gehoert benannt.
            # Ohne sie stuende in der Akte nur "geaendert", und wer wann
            # welchen Schluessel vergeben hat, waere nicht mehr feststellbar.
            alt_dict["module_key"] = None
            neu_dict["module_key"] = key
        new_value = json.dumps(neu_dict, ensure_ascii=False)
        old_value = (None if alt_dict is None
                     else json.dumps(alt_dict, ensure_ascii=False))

        def _do_write(con: sqlite3.Connection) -> Dict[str, Any]:
            if created:
                con.execute(
                    "INSERT INTO report_modules "
                    "(title, description, role, topic, body, sort_order, "
                    " is_active, created_by, created_at, updated_at, "
                    " module_key, block_type, block_data) "
                    "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)",
                    (title, desc, role, topic, body, sort_order,
                     changed_by, now, now, key, block_type, block_data))
            elif nachtrag:
                # UEBER DIE id, nicht ueber den Schluessel: den gibt es an
                # dieser Zeile ja noch nicht.
                con.execute(
                    "UPDATE report_modules SET module_key=?, title=?, "
                    "description=?, role=?, topic=?, body=?, sort_order=?, "
                    "block_type=?, block_data=?, "
                    "updated_at=? WHERE id=? AND module_key IS NULL",
                    (key, title, desc, role, topic, body, sort_order,
                     block_type, block_data, now, int(nachtrag_id)))
            else:
                con.execute(
                    "UPDATE report_modules SET title=?, description=?, role=?, "
                    "topic=?, body=?, sort_order=?, block_type=?, "
                    "block_data=?, updated_at=? "
                    "WHERE module_key=?",
                    (title, desc, role, topic, body, sort_order, block_type,
                     block_data, now, key))
            return {"target_id": key, "old_value": old_value,
                    "new_value": new_value}

        writer = TemplatesWriter(self._con)
        writer.audited_write(
            do_write=_do_write,
            action=("create" if created else "update"),
            target_type="module", changed_by=changed_by, ts=now)
        return {"target_id": key, "created": created,
                "nachtrag": nachtrag}
