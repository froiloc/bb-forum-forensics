# =============================================================================
# management/export/staging.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem (AP-2B)
# =============================================================================
# Zweck (Idee 4 — StA-Ausschleus-/Uebergabe-Verzeichnis):
#   Ein definierter Sammel- und Uebergabepunkt Richtung Staatsanwaltschaft. In
#   das Ausschleus-Verzeichnis werden GEPRUEFTE Exporte (Bericht-PDF,
#   Fallstatus-Excel, Sichten-HTML) mit
#     * je Artefakt einer SHA-256-Pruefsumme (unabhaengig nachrechenbar),
#     * einem verpflichtenden UNBEDENKLICHKEITSVERMERK (Fallregel 3: Inhalte
#       nur nach Pruefung auf Unverfaenglichkeit teilen) und
#     * einem Manifest (manifest.json) samt Manifest-Digest
#   abgelegt. Ohne ausdruecklichen Unbedenklichkeits-Nachweis wird ein Artefakt
#   NICHT aufgenommen (default-deny -> UnbedenklichkeitError); nichts wird still
#   uebersprungen (GR1).
#
#   coordinator.db wird — wenn ueberhaupt — nur LESEND fuer die Ketten-Spitze im
#   Erzeugungsvermerk herangezogen (via context_builder, in der CLI). Dieses
#   Modul selbst ist DB-frei und arbeitet ausschliesslich auf dem Dateisystem;
#   Zeitstempel werden injiziert -> testbar/deterministisch.
#
#   VERIFIKATION: verify() rechnet jede Datei im Verzeichnis gegen ihre im
#   Manifest hinterlegte Pruefsumme nach — erkennt nachtraegliche Aenderung,
#   Fehlen oder Ergaenzung. So ist das ausgeschleuste Paket selbst-pruefbar.
#
# Version: v0.7.443 · Build: 443 · 2026-07-19
# =============================================================================

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import List, Optional

from management.export.checksum import content_sha256_bytes, json_payload_sha256
from management.export.export_envelope import ExportContext, ExportEnvelope

MANIFEST_NAME = "manifest.json"
OVERVIEW_NAME = "UEBERGABE.txt"
SCHEMA_VERSION = 1

# Dateien, die zur Ausschleus-Mechanik gehoeren und NICHT als Artefakt zaehlen.
_RESERVED = {MANIFEST_NAME, OVERVIEW_NAME}


class StagingError(Exception):
    """Allgemeiner Fehler im Ausschleus-Verzeichnis."""


class UnbedenklichkeitError(StagingError):
    """Aufnahme ohne bestaetigte Unbedenklichkeit (Fallregel 3) — abgewiesen."""


class StagingArea:
    """
    Verwaltet ein Ausschleus-Verzeichnis (Sammeln -> Finalisieren -> Verifizieren).
    Der Zustand liegt im manifest.json und ueberlebt CLI-Aufrufe (inkrementell).
    """

    def __init__(self, target_dir: str) -> None:
        self._dir = Path(target_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def manifest_path(self) -> Path:
        return self._dir / MANIFEST_NAME

    # -- Manifest laden/speichern -------------------------------------------

    def load(self) -> dict:
        """Manifest lesen; frisches Grundgeruest, falls noch keines existiert."""
        if self.manifest_path.exists():
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return {
            "schema_version": SCHEMA_VERSION,
            "klassifikation": None,
            "behoerde": None,
            "aktenzeichen": None,
            "erstellt_am": None,
            "erzeugungsvermerk": [],
            "artifacts": [],
            "manifest_sha256": json_payload_sha256([]),
        }

    def _save(self, manifest: dict) -> None:
        # Manifest-Digest deckt AUSSCHLIESSLICH die Artefaktliste (stabil,
        # unabhaengig von Kopfdaten/Zeit) -> vom Empfaenger nachrechenbar.
        manifest["manifest_sha256"] = json_payload_sha256(manifest["artifacts"])
        self.manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8")

    # -- Aufnahme eines Artefakts -------------------------------------------

    def add_artifact(self, src_path: str, *, kind: str, source_ref: str,
                     unbedenklich: bool, cleared_by: str, added_at: str,
                     note: str = "") -> dict:
        """
        Nimmt eine gepruefte Datei in das Ausschleus-Verzeichnis auf.

        unbedenklich MUSS True sein und cleared_by nicht leer — sonst
        UnbedenklichkeitError (default-deny, Fallregel 3). Bei Namenskollision
        StagingError (kein stilles Ueberschreiben, GR1).
        """
        if not unbedenklich:
            raise UnbedenklichkeitError(
                "Aufnahme verweigert: Unbedenklichkeit nicht bestaetigt "
                "(Fallregel 3). Artefakt '%s' NICHT ausgeschleust." % src_path)
        if not cleared_by or not cleared_by.strip():
            raise UnbedenklichkeitError(
                "Aufnahme verweigert: kein Pruefer (cleared_by) angegeben.")

        src = Path(src_path)
        if not src.is_file():
            raise StagingError("Quelldatei nicht gefunden: %s" % src_path)

        filename = src.name
        if filename in _RESERVED:
            raise StagingError(
                "Dateiname '%s' ist reserviert." % filename)
        dest = self._dir / filename
        if dest.exists():
            raise StagingError(
                "Artefakt '%s' existiert bereits im Ausschleus-Verzeichnis "
                "(kein Ueberschreiben)." % filename)

        data = src.read_bytes()
        digest = content_sha256_bytes(data)
        shutil.copy2(str(src), str(dest))

        entry = {
            "filename": filename,
            "kind": kind,
            "source_ref": source_ref,
            "sha256": digest,
            "size": len(data),
            "unbedenklich": True,
            "cleared_by": cleared_by,
            "note": note,
            "added_at": added_at,
        }
        manifest = self.load()
        manifest["artifacts"].append(entry)
        self._save(manifest)
        return entry

    # -- Finalisierung (Kopfdaten + menschenlesbare Uebergabe) --------------

    def finalize(self, context: ExportContext) -> None:
        """
        Stempelt Kopfdaten (Behoerde/Aktenzeichen/Klassifikation/
        Erzeugungsvermerk inkl. Ketten-Spitze) in das Manifest und schreibt
        eine menschenlesbare UEBERGABE.txt (Aktenkopf + Erzeugungsvermerk +
        Artefaktliste mit Pruefsummen).
        """
        env = ExportEnvelope(context)
        manifest = self.load()
        manifest["klassifikation"] = context.klassifikation
        manifest["behoerde"] = context.behoerde
        manifest["aktenzeichen"] = context.aktenzeichen
        manifest["erstellt_am"] = context.generated_at
        manifest["erzeugungsvermerk"] = env.erzeugungsvermerk_lines()
        self._save(manifest)

        lines = [env.header_text("StA-Ausschleus — Uebergabepaket")]
        lines.append("Artefakte (%d):" % len(manifest["artifacts"]))
        for a in manifest["artifacts"]:
            lines.append(
                "  - %s [%s] Quelle=%s unbedenklich_durch=%s\n"
                "      SHA-256=%s  (%d Bytes)%s"
                % (a["filename"], a["kind"], a["source_ref"], a["cleared_by"],
                   a["sha256"], a["size"],
                   ("  Notiz: " + a["note"]) if a["note"] else ""))
        lines.append("")
        lines.append(env.footer_text(manifest["manifest_sha256"]))
        (self._dir / OVERVIEW_NAME).write_text(
            "\n".join(lines) + "\n", encoding="utf-8")

    # -- Selbstpruefung ------------------------------------------------------

    def verify(self) -> dict:
        """
        Rechnet jede im Manifest gefuehrte Datei nach und meldet Abweichungen.

        Liefert {'ok': bool, 'kein_manifest': bool, 'mismatched': [...],
                 'missing': [...], 'extra': [...]}.
        'extra' = Dateien im Verzeichnis, die NICHT im Manifest stehen (ausser
        den reservierten) — auch das ist ein Befund (GR1: nichts uebersehen).

        =====================================================================
        BUILD 647 (Vorgang d30b3d95): 'kein_manifest' IST NEU, UND ES IST DER
        KERN DES VORGANGS.
        =====================================================================
        Bis Build 646 lief hier 'self.load()', das bei FEHLENDEM Manifest ein
        frisches Grundgeruest mit LEERER Artefaktliste zurueckgibt. Danach
        waren 'mismatched', 'missing' und 'extra' saemtlich leer, und 'ok'
        wurde True. GEMESSEN: 'verify --dir /tmp/leer' auf ein frisch
        angelegtes, leeres Verzeichnis meldete "OK — alle Artefakte stimmen
        mit dem Manifest ueberein" und den Rueckgabewert 0.

        AUS "ES GIBT NICHTS ZU PRUEFEN" WURDE "ALLES GEPRUEFT UND IN ORDNUNG".
        Die Ausschleusung ist der Weg, auf dem Material das Haus verlaesst;
        wer 'verify' auf ein Verzeichnis anwendet, in dem das Paket in
        Wahrheit nie erzeugt wurde, bekam eine Bestaetigung fuer etwas, das
        nicht existiert.

        DREI LAGEN, NICHT ZWEI - und die dritte ist von der ersten sauber zu
        trennen:
          * Manifest da, alles stimmt          -> ok=True,  kein_manifest=False
          * Manifest da, Abweichung            -> ok=False, kein_manifest=False
          * KEIN Manifest                      -> ok=False, kein_manifest=True

        EIN LEERES PAKET MIT MANIFEST BLEIBT GUELTIG. Das ist ungewoehnlich,
        aber es ist eine Aussage: jemand hat ein Paket erzeugt, das keine
        Artefakte enthaelt. Es unterscheidet sich von "hier wurde nie etwas
        erzeugt", und genau diese Unterscheidung war verlorengegangen.
        """
        kein_manifest = not self.manifest_path.exists()
        manifest = self.load()
        mismatched: List[str] = []
        missing: List[str] = []
        listed = set()
        for a in manifest["artifacts"]:
            listed.add(a["filename"])
            p = self._dir / a["filename"]
            if not p.is_file():
                missing.append(a["filename"])
                continue
            if content_sha256_bytes(p.read_bytes()) != a["sha256"]:
                mismatched.append(a["filename"])
        extra = [
            f.name for f in self._dir.iterdir()
            if f.is_file() and f.name not in _RESERVED and f.name not in listed
        ]
        # Ohne Manifest ist 'ok' NIE True - auch dann nicht, wenn die drei
        # Listen leer sind. Sie sind es dann naemlich nur, weil nichts da war,
        # woran man haette messen koennen.
        ok = (not kein_manifest) and not (mismatched or missing or extra)
        return {"ok": ok, "kein_manifest": kein_manifest,
                "mismatched": sorted(mismatched),
                "missing": sorted(missing), "extra": sorted(extra)}
