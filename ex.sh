#!/bin/bash
path="${1}"
[[ "${path}" == *.base64 ]] && bn="${path%%.base64}" || \
[[ "${path}" == *.zip ]] && bn="${path%%.zip}" || \
( echo "Weder Base64 noch Zip-Archiv angegeben." && exit 1 )
wd="$(basename $PWD)"
[[ -f "${bn}.base64" ]] && base64 -d < "${bn}.base64" > ${bn}.zip
[[ -f "${bn}.zip" ]] && unzip -o -qq ${bn}.zip "${wd}/*" -d "${PWD}"
cd "${wd}" && \
cp -rf * .. && \
cd .. && \
rm -rf "${wd}"
