#!/bin/bash
find . -type f -not \( -regex './.\(venv\|git\).*' -or -regex '.*__pycache__.*' -or -regex '.*\.zip' \) -exec md5sum "{}" \; | sort -k2,2
