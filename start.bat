@echo off
setlocal enabledelayedexpansion

REM ============================================================================
REM start.bat — IT-Forensisches Ermittlungswerkzeug (aiw_webserver)
REM ----------------------------------------------------------------------------
REM Startet fuer jede vorhandene data\assets\assets_<id>.db genau einen
REM Server-Prozess. Der Server waehlt automatisch den naechsten freien Port
REM ab 8080 (--auto-port) und oeffnet anschliessend SELBST den Browser
REM (--open-browser). Damit ist die Reihenfolge garantiert: Server zuerst,
REM dann Browser auf der tatsaechlich gebundenen Adresse.
REM
REM Python-Interpreter: bevorzugt portable Laufzeit ..\Python\python.exe,
REM                     sonst 'python' aus dem PATH.
REM Browser: ueber config.yaml (browser.path) oder automatische Erkennung.
REM
REM Beleg: Projektgespraech 2026-06-24 (Light-Version / Auto-Port / Browser)
REM ============================================================================

REM --- Python-Interpreter bestimmen -----------------------------------------
set "PYTHON=python"
if exist "..\Python\python.exe" set "PYTHON=..\Python\python.exe"

REM --- Pro Fall (assets_<id>.db) einen Server starten -----------------------
set "FOUND="
for %%f in (".\data\assets\assets_*.db") do (
    set "filename=%%~nf"
    set "id=!filename:assets_=!"
    set "FOUND=1"
    echo Starte Fall user-id=!id! ...
    start "" "!PYTHON!" main.py --mode cli --user-id !id! --auto-port --open-browser
)

if not defined FOUND (
    echo.
    echo [FEHLER] Keine data\assets\assets_*.db gefunden.
    echo Bitte die fallspezifische Datenbank nach data\assets\ ablegen.
    echo.
    pause
)

endlocal
