#!/bin/bash
# Initial values
current_version="$(git log -1 --pretty=%B|head -n1|tr ' ' '_')"
zip="${PWD##*/}_${current_version,,}.zip"
md5="md5.chksum"

# Clean up previous files
rm -f "${zip}" "${md5}"

# Find files, zip them, and generate checksums
while IFS= read -r file
do
    p="${PWD}"
    cd ..
    zip -u1 "${p##*/}/${zip}" "${p##*/}/${file#*/}" >/dev/null 2>&1
    cd "${p}"
    md5sum "${file}"
done < <(find . -type f -not \( \
        -regex './.\(venv\|git\|pytest_cache\).*' -or \
        -regex '.*__pycache__.*' -or \
        -regex '.*\.\(zip\|log\|base64\|md\|chksum\|org\|pdf\)$' -or \
	-regex './\(logs\|node_modules\|forensik\|data\)/.*' -or \
        -regex '.*.env$' -or \
        -regex '$^' \) \
    ) | sort -k2,2 | tee "${md5}"

# Add the MD5 checksum file to the archive
if [ -f "${md5}" ]
then
    p="${PWD}"
    cd ..
    zip -u1 "${p##*/}/${zip}" "${p##*/}/${md5}" >/dev/null 2>&1
    cd "${p}"
fi

# Create a base64 encoded version of the archive
[ -f "${zip}" ] && base64 < "${zip}" > "${zip%*.zip}.base64"
