@echo off
setlocal enabledelayedexpansion

for %%f in (".\data\assets\assets_*.db") do (
    set "filename=%%~nf"
    set "id=!filename:assets_=!"
    start /b "" "..\GoogleChromePortable64\GoogleChromePortable.exe" http://127.0.0.2:8080/
    start /b "" "..\Python\python.exe" main.py --user-id !id!
)
