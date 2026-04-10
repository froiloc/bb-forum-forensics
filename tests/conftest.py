"""
tests/conftest.py — Pytest/Unittest Path-Konfiguration
=======================================================
Stellt sicher, dass das Projektroot im sys.path liegt,
unabhängig davon aus welchem Verzeichnis die Tests aufgerufen werden.

Build: 003 · 2026-04-07
"""
import sys
from pathlib import Path

# Projektroot = Elternverzeichnis von tests/
_project_root = Path(__file__).parent.parent.resolve()
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
