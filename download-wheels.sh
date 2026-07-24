#/bin/bash
# download python libraries for offline installation
python -m pip download -d ./setup/win64/wheels/ --python-version 3.14 --platform win_amd64 --no-deps -r requirements.txt 
