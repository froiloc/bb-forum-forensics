#!/bin/bash
filename="${1:-"$(mktemp --suffix=log)"}"
start_line_current_session=$(grep -n 'Logging initialisiert ' logs/forensic_server.log | tail -n1 | cut -d':' -f1)
tail -n +${start_line_current_session} logs/forensic_server.log > "${filename}"
if [[ -z "$1" ]]
then
	if [[ -x /bin/xclip ]]
	then
		xclip -selection clipboard < "${filename}"
		rm "${filename}"
	else
		echo "xclip ist nicht installiert. Kann nicht in Zwischenablage speichern." >&2
		exit 1
	fi
fi
