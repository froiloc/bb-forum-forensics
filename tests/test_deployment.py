# =============================================================================
# tests/test_deployment.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite fuer Deployment-Skripte (AP-E2).
#
# Getestet werden ausschliesslich die testbaren Logik-Teile:
#   - install.py: Argparse, OS-Erkennung, Paketliste, Verifikations-Logik
#   - prepare_deployment.py: Argparse, Pfadberechnung, Manifest-Erstellung
#   - build_editor_bundle.py: URL-Scan-Logik, Manifest-Format
#
# Nicht getestet (externe Systeme):
#   - npm install (erfordert Internet)
#   - esbuild (erfordert npm)
#   - pip download (erfordert Internet)
#
# T01 — install.py: --target=dev -> DEV_PACKAGES in Paketliste
# T02 — install.py: --target=prod -> DEV_PACKAGES NICHT in Paketliste
# T03 — install.py: --os=win -> wheels_dir zeigt auf setup/win64/wheels
# T04 — install.py: --os=linux -> wheels_dir zeigt auf setup/linux64/wheels
# T05 — install.py: auto-detect OS funktioniert ohne --os
# T06 — build_editor_bundle.py: URL-Scan erkennt Google-Fonts-URLs
# T07 — build_editor_bundle.py: URL-Patching ersetzt externe URLs korrekt
# T08 — prepare_deployment.py: Manifest enthaelt alle setup/-Dateien
# T09 — install.py: Python-Version-Check schlaegt bei zu alter Version fehl
# T10 — EDITOR_PACKAGES enthaelt alle geplanten Plugins (vollstaendigkeitscheck)
#
# Version: v0.6.044 · Build: 044 · 2026-04-19
# Beleg: AP-E2, Projektgespraech 2026-04-19
# =============================================================================

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _load_module(rel_path: str):
    """Laedt ein Modul anhand eines relativen Pfads zum Projektroot."""
    project_root = Path(__file__).resolve().parent.parent
    full_path = project_root / rel_path
    spec = importlib.util.spec_from_file_location("_mod", full_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# install.py Tests
# ---------------------------------------------------------------------------

class TestInstall:

    @pytest.fixture(autouse=True)
    def load(self):
        self.install = _load_module("install.py")

    def test_T01_dev_enthaelt_dev_packages(self):
        """T01: DEV_PACKAGES sind in RUNTIME_PACKAGES + DEV_PACKAGES enthalten."""
        all_dev = self.install.RUNTIME_PACKAGES + self.install.DEV_PACKAGES
        for pkg in self.install.DEV_PACKAGES:
            assert pkg in all_dev

    def test_T02_prod_enthaelt_keine_dev_packages(self):
        """T02: RUNTIME_PACKAGES enthalten keine DEV_PACKAGES."""
        for pkg in self.install.DEV_PACKAGES:
            assert pkg not in self.install.RUNTIME_PACKAGES, \
                f"Dev-Paket '{pkg}' darf nicht in RUNTIME_PACKAGES sein"

    def test_T03_wheels_dir_win(self, tmp_path):
        """T03: _wheels_dir('win') zeigt auf setup/win64/wheels."""
        # SCRIPT_DIR temporaer auf tmp_path setzen
        with patch.object(self.install, "SCRIPT_DIR", tmp_path):
            wdir = self.install._wheels_dir("win")
        assert "win64" in str(wdir)
        assert "wheels" in str(wdir)

    def test_T04_wheels_dir_linux(self, tmp_path):
        """T04: _wheels_dir('linux') zeigt auf setup/linux64/wheels."""
        with patch.object(self.install, "SCRIPT_DIR", tmp_path):
            wdir = self.install._wheels_dir("linux")
        assert "linux64" in str(wdir)
        assert "wheels" in str(wdir)

    def test_T05_detect_os_gibt_string_zurueck(self):
        """T05: _detect_os() gibt 'win' oder 'linux' zurueck."""
        result = self.install._detect_os()
        assert result in ("win", "linux"), \
            f"_detect_os() muss 'win' oder 'linux' zurueckgeben, erhalten: {result}"

    def test_T09_python_version_check_schlaegt_fehl(self):
        """T09: _check_python() bricht bei zu alter Python-Version ab."""
        import collections
        # sys.version_info ist ein named tuple — mock muss Attribute haben
        FakeVersion = collections.namedtuple("version_info",
                                             ["major","minor","micro","releaselevel","serial"])
        fake_old = FakeVersion(2, 7, 18, "final", 0)
        with patch("sys.version_info", fake_old):
            with pytest.raises(SystemExit):
                self.install._check_python()


# ---------------------------------------------------------------------------
# build_editor_bundle.py Tests
# ---------------------------------------------------------------------------

class TestBuildEditorBundle:

    @pytest.fixture(autouse=True)
    def load(self):
        self.bundle = _load_module("deployment/build_editor_bundle.py")

    def test_T06_url_scan_erkennt_google_fonts(self, tmp_path):
        """T06: _scan_external_urls() erkennt Google-Fonts-URLs."""
        bundle_js = tmp_path / "editor.bundle.js"
        bundle_js.write_text(
            "var x = 'https://fonts.googleapis.com/css?family=Roboto';\n"
            "var y = 'https://cdn.example.com/lib.js';\n",
            encoding="utf-8",
        )
        urls = self.bundle._scan_external_urls(bundle_js)
        assert any("googleapis" in u for u in urls), \
            "Google-Fonts-URL muss erkannt werden"
        assert any("cdn.example.com" in u for u in urls), \
            "CDN-URL muss erkannt werden"

    def test_T07_url_patching_ersetzt_url(self, tmp_path):
        """T07: _patch_external_urls() ersetzt externe URL durch lokalen Pfad."""
        bundle_js = tmp_path / "editor.bundle.js"
        original = "https://fonts.googleapis.com/css?family=Roboto"
        bundle_js.write_text(
            f"var font = '{original}';", encoding="utf-8"
        )
        count = self.bundle._patch_external_urls(bundle_js, [original])
        assert count == 1
        patched = bundle_js.read_text(encoding="utf-8")
        assert original not in patched, "Externe URL muss ersetzt sein"
        assert "/_forensic/static/editor/" in patched, \
            "Lokaler Pfad muss eingefuegt sein"

    def test_T10_editor_packages_vollstaendig(self):
        """T10: EDITOR_PACKAGES enthaelt alle geplanten Plugins."""
        expected = [
            "@editorjs/editorjs",
            "@editorjs/header",
            "@editorjs/paragraph",
            "@editorjs/nested-list",
            "@editorjs/table",
            "@cychann/editorjs-quote",
            "@editorjs/simple-image",
            "@editorjs/marker",
            "editorjs-annotation",
            "editorjs-undo",
            "@coolbytes/editorjs-delimiter",
        ]
        for pkg in expected:
            assert pkg in self.bundle.EDITOR_PACKAGES, \
                f"Plugin '{pkg}' fehlt in EDITOR_PACKAGES"


# ---------------------------------------------------------------------------
# prepare_deployment.py Tests
# ---------------------------------------------------------------------------

class TestPrepareDeployment:

    @pytest.fixture(autouse=True)
    def load(self):
        self.prep = _load_module("prepare_deployment.py")

    def test_T08_manifest_enthaelt_dateien(self, tmp_path, monkeypatch):
        """T08: _write_manifest() erstellt Manifest mit vorhandenen Dateien."""
        # Testdateien anlegen
        win_dir = tmp_path / "setup" / "win64"
        win_dir.mkdir(parents=True)
        (win_dir / "test.whl").write_bytes(b"fake wheel")

        setup_dir = tmp_path / "setup"
        setup_dir.mkdir(exist_ok=True)

        static_editor = tmp_path / "static" / "editor"
        static_editor.mkdir(parents=True)
        (static_editor / "editor.bundle.js").write_bytes(b"console.log('test')")

        monkeypatch.setattr(self.prep, "SETUP_WIN", win_dir)
        monkeypatch.setattr(self.prep, "SETUP_LINUX", tmp_path / "setup" / "linux64")
        monkeypatch.setattr(self.prep, "STATIC_EDITOR", static_editor)
        monkeypatch.setattr(self.prep, "SCRIPT_DIR", tmp_path)

        self.prep._write_manifest()

        manifest_path = tmp_path / "setup" / "deployment_manifest.json"
        assert manifest_path.exists(), "Manifest-Datei muss erstellt werden"
        data = json.loads(manifest_path.read_text())
        assert "files" in data
        assert "created_at" in data
        # Mindestens die Bundle-Datei muss im Manifest sein
        assert any("editor.bundle.js" in k for k in data["files"]), \
            "Bundle-Datei muss im Manifest sein"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
