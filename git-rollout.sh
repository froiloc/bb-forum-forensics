#!/bin/bash
uuid="$(uuid)"
last_uuid="$(ls -1 "${ROOTDIR}debug/bugs-and-tasks/"last.*.md | head -n 1 | cut -d'.' -f 2)"
echo "Die neue cache-buster UUID ist ${uuid}"
ROOTDIR="/opt/aiw_webserver/"
if [[ -f "${ROOTDIR}debug/bugs-and-tasks/last.${last_uuid}.md" ]]
then
	git mv "${ROOTDIR}debug/bugs-and-tasks/last.${last_uuid}.md" "${ROOTDIR}debug/bugs-and-tasks/last.${uuid}.md"
	mv "${ROOTDIR}debug/bugs-and-tasks/last.md" "${ROOTDIR}debug/bugs-and-tasks/last.${uuid}.md" 2>/dev/null
	sed -i -E 's#[0-9a-f]{8}-4[0-9a-f]{3}(-[0-9a-f]{4}){3}[0-9a-f]{8}#'${uuid}'#g' "${ROOTDIR}debug/bugs-and-tasks/last.${uuid}.md"
fi
if [[ -f "${ROOTDIR}debug/devtools-console/last.${last_uuid}.log" ]]
then
	git mv "${ROOTDIR}debug/devtools-console/last.${last_uuid}.log" "${ROOTDIR}debug/devtools-console/last.${uuid}.log"
	mv "${ROOTDIR}debug/devtools-console/last.log" "${ROOTDIR}debug/devtools-console/last.${uuid}.log" 2>/dev/null
fi
if [[ -f "${ROOTDIR}debug/devtools-network/last.${last_uuid}.har" ]]
then
	git mv "${ROOTDIR}debug/devtools-network/last.${last_uuid}.har" "${ROOTDIR}debug/devtools-network/last.${uuid}.har"
	mv "${ROOTDIR}debug/devtools-network/last..har" "${ROOTDIR}debug/devtools-network/last.${uuid}.har" 2>/dev/null
fi
if [[ -f "${ROOTDIR}debug/dom-dump/last.${last_uuid}.html" ]]
then
	git mv "${ROOTDIR}debug/dom-dump/last.${last_uuid}.html" "${ROOTDIR}debug/dom-dump/last.${uuid}.html"
	mv "${ROOTDIR}debug/dom-dump/last.html" "${ROOTDIR}debug/dom-dump/last.${uuid}.html" 2>/dev/null
fi
if [[ -f "${ROOTDIR}debug/webserver-log/last.${last_uuid}.log" ]]
then
	git mv "${ROOTDIR}debug/webserver-log/last.${last_uuid}.log" "${ROOTDIR}debug/webserver-log/last.${uuid}.log"
	mv "${ROOTDIR}debug/webserver-log/last.log" "${ROOTDIR}debug/webserver-log/last.${uuid}.log" 2>/dev/null
fi
git add "${ROOTDIR}debug/screenshots/*"
git commit -a -m "${1:-$(git log -1 | tail -n1 | echo "Version 0.6.134" | awk -F. '{print $1 "." $2 "." $3+1}')} - ${uuid}"
git push
git rm "${ROOTDIR}debug/screenshots/*.png"
mkdir -p "${ROOTDIR}debug/screenshots/"
