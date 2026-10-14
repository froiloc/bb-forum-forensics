#!/bin/bash
version="$(git log -1 | grep -Pio "Version\s+[0-9\.]+" | head -n1 | awk '{print $2}' | tr '.' '_')"
version="${version:-"$(jq -r ".version" <build.json)"}"
archivename="aiw_webserver_${version}.7z"
7z a "${archivename}" @${1:-".packlist"}
target="${2:-"/media/paul/KODAK"}"
if [ -d "${target}" ]
then
	cp "${archivename}" "${target}"
fi
