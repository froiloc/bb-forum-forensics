aiw_webserver — Setup-Verzeichnis
==================================
Dieses Verzeichnis wird von prepare_deployment.py befuellt.

Struktur nach prepare_deployment.py:
  win64/
    wheels/          Python-Wheels fuer Windows 64-bit
    README.txt
  linux64/
    wheels/          Python-Wheels fuer Linux 64-bit
    README.txt
  deployment_manifest.json   MD5-Checksummen aller Dateien

Baustelle 1 ergaenzt spaeter:
  win64/firefox/    Portabler Firefox ESR fuer Windows
  win64/python/     Portable Python-Laufzeitumgebung
  linux64/firefox/  Portabler Firefox ESR fuer Linux

Verwendung:
  python install.py --target=prod --os=win
  python install.py --target=dev  --os=linux
