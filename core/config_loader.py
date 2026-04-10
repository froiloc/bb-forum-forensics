# =============================================================================
# core/config_loader.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Lädt die zentrale Konfigurationsdatei (config.yaml) und stellt alle
#   Konfigurationsparameter als typisiertes, unveränderliches Objekt bereit.
#
# Eskalationskette (gilt projektübergreifend ohne Ausnahme):
#   CLI-Argument  >  config.yaml  >  Coded Default
#
#   Für den Pfad zur config.yaml selbst:
#   --config <pfad> (CLI)  >  ./config.yaml (relatives Default neben dem Skript)
#
# Forensische Relevanz:
#   Die geladene Konfiguration bestimmt, welche Datenbanken geöffnet werden
#   und auf welchen Pfaden die Beweismittel liegen. Fehlerhafte oder nicht
#   auffindbare Konfiguration führt zu einem harten Abbruch — kein stiller
#   Betrieb mit unbekannten Defaults ist zulässig (Grundregel 1).
#
# Abhängigkeiten: yaml (PyYAML), os, pathlib — ausschließlich Stdlib + PyYAML
# Version: v0.1.0 · Build: 001 · 2026-04-10
# =============================================================================

import os
import copy
from pathlib import Path
from typing import Any, Optional

import yaml


# ---------------------------------------------------------------------------
# Coded Defaults
# Jeder Default ist hier dokumentiert. Ein Wert, der weder per CLI noch per
# config.yaml gesetzt wird, fällt auf diesen Wert zurück.
# ---------------------------------------------------------------------------
_DEFAULTS: dict[str, Any] = {
    "server": {
        "host": "127.0.0.2",
        "port": 80,
        "mode": "job",          # job | cli | support
    },
    "paths": {
        "coordinator_db":   "./data/coordinator.db",
        "forensic_db_dir":  "./data/forensic/",
        "default_db":       "./data/default.db",
        "evidence_db_dir":  "./data/evidence/",
    },
    "hosts_management": {
        "enabled":        False,
        "forum_hostname": "",
        "target_ip":      "127.0.0.2",
    },
    "logging": {
        "level":        "info",             # info | debug
        "logfile":      "./logs/forensic_server.log",
        "max_bytes":    10 * 1024 * 1024,   # 10 MB
        "backup_count": 5,
    },
    "support": {
        "temp_db": "memory",    # memory | file
    },
    "url_patterns": {
        "asset_prefixes": [
            "/forum/style/",
            "/forum/img/",
            "/forum/extensions/",
        ],
        "alias_patterns": {
            "post_id_param": "pid",
            "notify_param":  "notify",
            "fragment_post": "p",
        },
    },
}


class ConfigLoader:
    """
    Lädt config.yaml und stellt alle Konfigurationsparameter bereit.

    Verwendung:
        cfg = ConfigLoader(config_path="/pfad/zu/config.yaml")
        host = cfg.get("server.host")           # "127.0.0.2"
        port = cfg.get("server.port")           # 80
        mode = cfg.get("server.mode")           # "job"

    Die Eskalationskette wird in dieser Klasse für alle Werte eingehalten.
    CLI-Overrides werden nach dem Laden per apply_cli_overrides() aufgebracht.
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        """
        Initialisiert den ConfigLoader.

        Args:
            config_path: Pfad zur config.yaml. Wenn None, wird ./config.yaml
                         relativ zum aufrufenden Skript gesucht.

        Raises:
            FileNotFoundError: Wenn die config.yaml nicht gefunden wurde.
            yaml.YAMLError:    Wenn die config.yaml nicht geparst werden kann.
            ValueError:        Wenn ein Pflichtfeld fehlt oder einen ungültigen
                               Wert enthält.
        """
        # Tiefen-Kopie der Defaults als Ausgangsbasis — niemals die Defaults
        # direkt mutieren, damit Tests unabhängig voneinander laufen können.
        self._config: dict[str, Any] = copy.deepcopy(_DEFAULTS)

        # Pfad zur config.yaml auflösen
        self._config_path: Path = self._resolve_config_path(config_path)

        # config.yaml laden und über Defaults mergen
        self._load_yaml()

        # Validierung der geladenen Konfiguration
        self._validate()

    # ------------------------------------------------------------------
    # Öffentliche Schnittstelle
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """
        Gibt einen Konfigurationswert anhand eines Punkt-separierten Schlüssels
        zurück.

        Beispiele:
            cfg.get("server.host")                    → "127.0.0.2"
            cfg.get("url_patterns.asset_prefixes")    → ["/forum/style/", ...]
            cfg.get("logging.level")                  → "info"

        Args:
            key:     Punkt-separierter Pfad zum Wert, z.B. "server.host"
            default: Rückgabewert, wenn der Schlüssel nicht existiert.
                     Normalerweise nicht nötig, da alle bekannten Schlüssel
                     durch Coded Defaults abgedeckt sind.

        Returns:
            Den Konfigurationswert oder default.
        """
        parts = key.split(".")
        node: Any = self._config
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def apply_cli_overrides(self, overrides: dict[str, Any]) -> None:
        """
        Wendet CLI-Argumente als Overrides auf die geladene Konfiguration an.
        CLI-Argumente haben höchste Priorität (Eskalationskette: CLI > yaml > Default).

        Erwartet ein flaches Dict mit Punkt-separierten Schlüsseln:

            overrides = {
                "server.mode":        "cli",
                "paths.forensic_db_dir": "/mnt/nrw/forensic/",
                "logging.level":      "debug",
            }

        Unbekannte Schlüssel werden ignoriert — Grundregel: kein stiller Fehler
        bei bekannten Schlüsseln, aber fremde Schlüssel werfen keine Exception,
        da zukünftige CLI-Argumente rückwärtskompatibel sein müssen.

        Args:
            overrides: Dict mit Punkt-Schlüsseln und Überschreibwerten.
                       None-Werte werden ignoriert (CLI-Argument nicht gesetzt).
        """
        for dotted_key, value in overrides.items():
            if value is None:
                # CLI-Argument wurde nicht angegeben — überspringen
                continue
            self._set(dotted_key, value)

    @property
    def config_path(self) -> Path:
        """Gibt den tatsächlich geladenen config.yaml-Pfad zurück."""
        return self._config_path

    def as_dict(self) -> dict[str, Any]:
        """
        Gibt eine Tiefen-Kopie der vollständigen Konfiguration zurück.
        Für Logging und Diagnosezwecke.
        """
        return copy.deepcopy(self._config)

    # ------------------------------------------------------------------
    # Interne Hilfsmethoden
    # ------------------------------------------------------------------

    def _resolve_config_path(self, config_path: Optional[str]) -> Path:
        """
        Löst den Pfad zur config.yaml auf.

        Priorität:
        1. Explizit übergebener config_path (entspricht --config CLI-Argument)
        2. ./config.yaml relativ zum aktuellen Arbeitsverzeichnis

        Raises:
            FileNotFoundError: Wenn die Datei am aufgelösten Pfad nicht existiert.
        """
        if config_path is not None:
            path = Path(config_path)
        else:
            # Coded Default: config.yaml neben dem Skript / im CWD
            path = Path("config.yaml")

        if not path.exists():
            raise FileNotFoundError(
                f"config.yaml nicht gefunden: '{path.resolve()}'\n"
                f"Bitte --config <pfad> angeben oder config.yaml im "
                f"Arbeitsverzeichnis ablegen."
            )

        return path.resolve()

    def _load_yaml(self) -> None:
        """
        Liest die config.yaml ein und mergt sie über die Coded Defaults.
        Felder, die in config.yaml fehlen, behalten ihren Default-Wert.

        Raises:
            yaml.YAMLError: Wenn die Datei nicht geparst werden kann.
            ValueError:     Wenn die YAML-Wurzel kein Dict ist.
        """
        with open(self._config_path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        if raw is None:
            # Leere config.yaml ist erlaubt — alle Defaults greifen
            return

        if not isinstance(raw, dict):
            raise ValueError(
                f"config.yaml muss ein YAML-Mapping (Dict) auf oberster Ebene "
                f"sein. Gefunden: {type(raw).__name__}"
            )

        # Rekursives tiefes Merge: YAML-Werte überschreiben Defaults,
        # aber fehlende YAML-Schlüssel behalten ihren Default.
        self._deep_merge(self._config, raw)

    def _deep_merge(self, base: dict, override: dict) -> None:
        """
        Mergt 'override' rekursiv in 'base'. Modifiziert 'base' in-place.
        Nur Dict-Werte werden rekursiv gemergt; alle anderen Typen werden
        direkt überschrieben.
        """
        for key, value in override.items():
            if (
                key in base
                and isinstance(base[key], dict)
                and isinstance(value, dict)
            ):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _set(self, dotted_key: str, value: Any) -> None:
        """
        Setzt einen Wert anhand eines Punkt-separierten Schlüssels in-place.
        Zwischenknoten werden als leere Dicts angelegt, falls sie fehlen.
        """
        parts = dotted_key.split(".")
        node = self._config
        for part in parts[:-1]:
            if part not in node or not isinstance(node[part], dict):
                node[part] = {}
            node = node[part]
        node[parts[-1]] = value

    def _validate(self) -> None:
        """
        Prüft die Konfiguration auf Gültigkeit.

        Geprüfte Invarianten:
        - server.mode muss einer der drei zulässigen Werte sein
        - server.port muss eine positive Ganzzahl sein
        - logging.level muss 'info' oder 'debug' sein
        - support.temp_db muss 'memory' oder 'file' sein
        - paths.forensic_db_dir und paths.evidence_db_dir müssen Strings sein
          (Existenz der Verzeichnisse wird erst in startup_checks.py geprüft,
           da sie beim Laden der Config noch nicht zwingend existieren müssen)

        Raises:
            ValueError: Bei ungültigem Konfigurationswert.
        """
        valid_modes = {"job", "cli", "support"}
        mode = self.get("server.mode")
        if mode not in valid_modes:
            raise ValueError(
                f"server.mode='{mode}' ist ungültig. "
                f"Zulässige Werte: {sorted(valid_modes)}"
            )

        port = self.get("server.port")
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise ValueError(
                f"server.port='{port}' ist ungültig. "
                f"Muss eine Ganzzahl zwischen 1 und 65535 sein."
            )

        valid_log_levels = {"info", "debug"}
        level = self.get("logging.level")
        if level not in valid_log_levels:
            raise ValueError(
                f"logging.level='{level}' ist ungültig. "
                f"Zulässige Werte: {sorted(valid_log_levels)}"
            )

        valid_temp_db = {"memory", "file"}
        temp_db = self.get("support.temp_db")
        if temp_db not in valid_temp_db:
            raise ValueError(
                f"support.temp_db='{temp_db}' ist ungültig. "
                f"Zulässige Werte: {sorted(valid_temp_db)}"
            )

        for path_key in ("paths.forensic_db_dir", "paths.evidence_db_dir",
                         "paths.coordinator_db", "paths.default_db"):
            val = self.get(path_key)
            if not isinstance(val, str) or not val.strip():
                raise ValueError(
                    f"'{path_key}' muss ein nicht-leerer String sein. "
                    f"Gefunden: {val!r}"
                )
