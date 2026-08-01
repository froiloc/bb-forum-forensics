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
# Änderungen gegenüber Build 001 (Build 013):
#   - ConfigLoaderError: Neue benannte Exception für alle Fehler beim Laden.
#     main.py importiert und fängt diese Exception. Zuvor wurden
#     FileNotFoundError und ValueError geworfen — beide sind jetzt Subklassen
#     von ConfigLoaderError, damit bestehende except-Zweige weiterhin greifen.
#   - ConfigLoader.__init__: Neuer optionaler Parameter cli_overrides (dict).
#     Entspricht dem bisherigen apply_cli_overrides()-Aufruf, aber inline im
#     Konstruktor, wie main.py es erwartet. apply_cli_overrides() bleibt
#     zusätzlich erhalten (rückwärtskompatibel).
#   - _validate() und _resolve_config_path() werfen nun ConfigLoaderError
#     statt ValueError / FileNotFoundError.
#
# Änderungen Build 638 (Ticket 15429c75 — Vorrangregel):
#   - Der ROHE Inhalt der YAML-Datei wird zusätzlich aufbewahrt (self._raw),
#     und stammt_aus_datei() beantwortet die Frage, ob ein Schlüssel in der
#     Datei TATSÄCHLICH EINGETRAGEN ist.
#     WARUM DAS NÖTIG IST: get() kann diese Frage nicht beantworten. Es
#     liefert auch dann einen Wert, wenn nur _DEFAULTS ihn hergibt. Ein
#     Werkzeug, das die Herkunft seiner Werte belegen soll (Grundregel 1),
#     würde damit 'aus config.yaml' melden, wo in Wahrheit ein fest
#     verdrahteter Vorgabewert gegriffen hat — eine falsche Herkunftsangabe
#     ist schlimmer als gar keine.
#     Der geladene Konfigurationsinhalt selbst ist UNVERÄNDERT; get() und
#     as_dict() verhalten sich exakt wie zuvor.
#
# Abhängigkeiten: yaml (PyYAML), os, pathlib — ausschließlich Stdlib + PyYAML
# Version: v0.8.638 · Build: 638 · 2026-08-01
# =============================================================================

import os
import copy
from pathlib import Path
from typing import Any, Optional

import yaml


# ---------------------------------------------------------------------------
# Benannte Exception (NEU Build 013)
# ---------------------------------------------------------------------------

class ConfigLoaderError(Exception):
    """
    Wird geworfen bei allen Fehlern beim Laden oder Validieren der
    Konfiguration. Subklassen für spezifische Fehlerfälle:
      ConfigFileNotFoundError — config.yaml nicht vorhanden
      ConfigValueError        — ungültiger Konfigurationswert
    main.py fängt ConfigLoaderError als einzige Klasse ab.
    """


class ConfigFileNotFoundError(ConfigLoaderError, FileNotFoundError):
    """config.yaml nicht gefunden (ist gleichzeitig FileNotFoundError)."""


class ConfigValueError(ConfigLoaderError, ValueError):
    """Ungültiger Konfigurationswert (ist gleichzeitig ValueError)."""


# ---------------------------------------------------------------------------
# Coded Defaults
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
        "assets_db_dir":    "./data/assets/",    # NEU Build 017
        "templates_db":     "./data/templates.db",  # NEU Build 117 — Bug 3.3
        "translations_db":  "./data/translations.db",  # NEU Build 329 — read-only ATTACH
        # Zentrale Siegel-DB freigegebener Berichte (Build 377). Nur der
        # auditierte Freigabepfad schreibt hier; Lesen (verify) ist frei.
        "approved_reports_db": "./data/approved_reports.db",
    },
    # Backup (Welle 0, Build 352 ff.). Ziel + Rahmenbedingungen fuer die
    # DB-Sicherung per 'VACUUM INTO'. Siehe kommentierte config.yaml.
    "backup": {
        "dest_dir":            "./backups/",
        "retention_count":     7,      # Generationen je DB
        "min_free_factor":     1.3,    # frei >= Faktor * Gesamt-Quellgroesse
        "checkpoint":          "passive",  # passive | none (nie truncate)
        "include_shared_dbs":  True,   # default/templates/translations mitsichern
    },
    "hosts_management": {
        "enabled":        False,
        "forum_hostname": "",
        "target_ip":      "127.0.0.2",
    },
    "logging": {
        "level":        "info",
        "logfile":      "./logs/forensic_server.log",
        "max_bytes":    10 * 1024 * 1024,
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

    Verwendung (Build 013 — cli_overrides im Konstruktor):
        cfg = ConfigLoader(
            config_path="./config.yaml",
            cli_overrides={"server.mode": "cli", "server.port": 8080},
        )
        host = cfg.get("server.host")   # "127.0.0.2"

    Rückwärtskompatibilität:
        cfg = ConfigLoader(config_path="./config.yaml")
        cfg.apply_cli_overrides({"server.mode": "cli"})

    Raises:
        ConfigLoaderError (oder Subklassen) bei Fehler.
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        cli_overrides: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Initialisiert den ConfigLoader.

        Args:
            config_path:   Pfad zur config.yaml. None → ./config.yaml.
            cli_overrides: Dict mit CLI-Overrides (Punkt-separierte Schlüssel).
                           Wird nach dem Laden der YAML-Datei angewendet.
                           None-Werte im Dict werden ignoriert.

        Raises:
            ConfigFileNotFoundError: Wenn die config.yaml nicht gefunden wurde.
            ConfigValueError:        Wenn ein Wert ungültig ist.
        """
        self._config: dict[str, Any] = copy.deepcopy(_DEFAULTS)
        # Build 638: der ROHE Dateiinhalt, unvermischt mit _DEFAULTS. Nur er
        # belegt, was in der Datei WIRKLICH steht (siehe stammt_aus_datei).
        self._raw: dict[str, Any] = {}
        self._config_path: Path = self._resolve_config_path(config_path)
        self._load_yaml()

        if cli_overrides:
            self.apply_cli_overrides(cli_overrides)

        self._validate()

    # ------------------------------------------------------------------
    # Öffentliche Schnittstelle
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """
        Gibt einen Konfigurationswert anhand eines Punkt-separierten Schlüssels
        zurück.

        Beispiele:
            cfg.get("server.host")
            cfg.get("url_patterns.asset_prefixes")
        """
        parts = key.split(".")
        node: Any = self._config
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def stammt_aus_datei(self, key: str) -> bool:
        """
        Beantwortet: Steht dieser Punkt-separierte Schlüssel TATSÄCHLICH in der
        geladenen config.yaml? (NEU Build 638)

        Abgrenzung zu get(): get() liefert auch Werte, die ausschließlich aus
        den Coded Defaults dieses Moduls stammen. Für eine Herkunftsangabe ist
        das nicht brauchbar — 'aus config.yaml' wäre dann eine unbelegte
        Behauptung. Diese Methode sieht ausschließlich in den rohen
        Dateiinhalt.

        Achtung, bewusste Festlegung: Ein Schlüssel, der in der Datei steht,
        aber leer ist ('' oder null), gilt hier als VORHANDEN. Ob ein leerer
        Wert brauchbar ist, entscheidet der Aufrufer — nicht dieses Modul.
        CLI-Overrides ändern das Ergebnis NICHT; sie stehen nicht in der Datei.

        Beispiel:
            cfg.stammt_aus_datei("paths.coordinator_db")   -> True/False
        """
        node: Any = self._raw
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return False
            node = node[part]
        return True

    def apply_cli_overrides(self, overrides: dict[str, Any]) -> None:
        """
        Wendet CLI-Argumente als Overrides auf die geladene Konfiguration an.
        CLI hat höchste Priorität (CLI > yaml > Default).
        None-Werte werden ignoriert (Argument nicht gesetzt).
        """
        for dotted_key, value in overrides.items():
            if value is None:
                continue
            self._set(dotted_key, value)

    @property
    def config_path(self) -> Path:
        """Gibt den tatsächlich geladenen config.yaml-Pfad zurück."""
        return self._config_path

    def as_dict(self) -> dict[str, Any]:
        """Gibt eine Tiefen-Kopie der vollständigen Konfiguration zurück."""
        return copy.deepcopy(self._config)

    # ------------------------------------------------------------------
    # Interne Hilfsmethoden
    # ------------------------------------------------------------------

    def _resolve_config_path(self, config_path: Optional[str]) -> Path:
        """
        Löst den Pfad zur config.yaml auf.

        Raises:
            ConfigFileNotFoundError: Wenn die Datei nicht existiert.
        """
        path = Path(config_path) if config_path is not None else Path("config.yaml")

        if not path.exists():
            raise ConfigFileNotFoundError(
                f"config.yaml nicht gefunden: '{path.resolve()}'\n"
                f"Bitte --config <pfad> angeben oder config.yaml im "
                f"Arbeitsverzeichnis ablegen."
            )

        return path.resolve()

    def _load_yaml(self) -> None:
        """
        Liest die config.yaml ein und mergt sie über die Coded Defaults.

        Raises:
            ConfigValueError: Wenn die YAML-Wurzel kein Dict ist.
            ConfigLoaderError: Wenn die YAML-Datei nicht geparst werden kann.
        """
        try:
            with open(self._config_path, encoding="utf-8") as fh:
                raw = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ConfigLoaderError(
                f"config.yaml konnte nicht geparst werden: {exc}"
            ) from exc

        if raw is None:
            self._raw = {}
            return  # Leere config.yaml — alle Defaults greifen

        if not isinstance(raw, dict):
            raise ConfigValueError(
                f"config.yaml muss ein YAML-Mapping (Dict) auf oberster Ebene "
                f"sein. Gefunden: {type(raw).__name__}"
            )

        # Build 638: Der rohe Inhalt wird VOR dem Merge weggelegt. Eine Kopie,
        # damit ein späteres _deep_merge/_set die Beleglage nicht verändert.
        self._raw = copy.deepcopy(raw)
        self._deep_merge(self._config, raw)

    def _deep_merge(self, base: dict, override: dict) -> None:
        """
        Mergt 'override' rekursiv in 'base'. Modifiziert 'base' in-place.
        Dict-Werte werden rekursiv gemergt; alle anderen Typen direkt überschrieben.
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
        """Setzt einen Wert anhand eines Punkt-separierten Schlüssels in-place."""
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

        Raises:
            ConfigValueError: Bei ungültigem Konfigurationswert.
        """
        valid_modes = {"job", "cli", "support"}
        mode = self.get("server.mode")
        if mode not in valid_modes:
            raise ConfigValueError(
                f"server.mode='{mode}' ist ungültig. "
                f"Zulässige Werte: {sorted(valid_modes)}"
            )

        port = self.get("server.port")
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise ConfigValueError(
                f"server.port='{port}' ist ungültig. "
                f"Muss eine Ganzzahl zwischen 1 und 65535 sein."
            )

        valid_log_levels = {"info", "debug"}
        level = self.get("logging.level")
        if level not in valid_log_levels:
            raise ConfigValueError(
                f"logging.level='{level}' ist ungültig. "
                f"Zulässige Werte: {sorted(valid_log_levels)}"
            )

        valid_temp_db = {"memory", "file"}
        temp_db = self.get("support.temp_db")
        if temp_db not in valid_temp_db:
            raise ConfigValueError(
                f"support.temp_db='{temp_db}' ist ungültig. "
                f"Zulässige Werte: {sorted(valid_temp_db)}"
            )

        for path_key in (
            "paths.forensic_db_dir", "paths.evidence_db_dir",
            "paths.coordinator_db",  "paths.default_db",
            "paths.assets_db_dir",   # NEU Build 017
        ):
            val = self.get(path_key)
            if not isinstance(val, str) or not val.strip():
                raise ConfigValueError(
                    f"'{path_key}' muss ein nicht-leerer String sein. "
                    f"Gefunden: {val!r}"
                )
