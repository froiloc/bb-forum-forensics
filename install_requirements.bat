@echo off
setlocal enabledelayedexpansion
REM --- Pyhton-Interpreter bestimmen --------------------------------------
set "PYTHON=python"
if exist "..\Python\python.exe" set "PYTHON=..\Python\python.exe"

!PYTHON! -m pip install -r requirements.txt --find-links setup\win64\wheels --no-index --no-cache-dir
pause