#!/bin/bash
uuid="$(uuid)"
last_uuid="$(ls -1 "${ROOTDIR}debug/bugs-and-tasks/"last.*.md | head -n 1 | cut -d'.' -f 2)"
echo "Die neue cache-buster UUID ist ${uuid}"
ROOTDIR="/opt/aiw_webserver/"
if ls -1 ${ROOTDIR}debug/bugs-and-tasks/last.*.md 2>/dev/null
then
	git mv "${ROOTDIR}debug/bugs-and-tasks/last.${last_uuid}.md" "${ROOTDIR}debug/bugs-and-tasks/last.${uuid}.md"
	mv "${ROOTDIR}debug/bugs-and-tasks/last.md" "${ROOTDIR}debug/bugs-and-tasks/last.${uuid}.md" 2>/dev/null
	sed -i -E 's#[0-9a-f]{8}-4[0-9a-f]{3}(-[0-9a-f]{4}){3}[0-9a-f]{8}#'${uuid}'#g' "${ROOTDIR}debug/bugs-and-tasks/last.${uuid}.md"
fi
if ls -1 ${ROOTDIR}debug/devtools-console/last.*.log 2>/dev/null
then
	git mv "${ROOTDIR}debug/devtools-console/last.${last_uuid}.log" "${ROOTDIR}debug/devtools-console/last.${uuid}.log"
	mv "${ROOTDIR}debug/devtools-console/last.log" "${ROOTDIR}debug/devtools-console/last.${uuid}.log" 2>/dev/null
fi
if ls -1 ${ROOTDIR}debug/devtools-network/last.*.har 2>/dev/null
then
	git mv "${ROOTDIR}debug/devtools-network/last.${last_uuid}.har" "${ROOTDIR}debug/devtools-network/last.${uuid}.har"
	mv "${ROOTDIR}debug/devtools-network/last..har" "${ROOTDIR}debug/devtools-network/last.${uuid}.har" 2>/dev/null
fi
if ls -1 ${ROOTDIR}debug/dom-dump/last-html.*.html 2>/dev/null
then
	git mv "${ROOTDIR}debug/dom-dump/last-html.${last_uuid}.html" "${ROOTDIR}debug/dom-dump/last-html.${uuid}.html"
	mv "${ROOTDIR}debug/dom-dump/last-html.html" "${ROOTDIR}debug/dom-dump/last-html.${uuid}.html" 2>/dev/null
	if [[ -f "${ROOTDIR}debug/dom-dump/last-html.${uuid}.html" ]]
	then	
		git mv "${ROOTDIR}debug/dom-dump/last-main.${last_uuid}.html" "${ROOTDIR}debug/dom-dump/last-main.${uuid}.html" 2>/dev/null
		python "${ROOTDIR}debug/html_query.py" -i "${ROOTDIR}debug/dom-dump/last-html.${uuid}.html" -o "${ROOTDIR}debug/dom-dump/last-main.${uuid}.html" -c main
		git add -f "${ROOTDIR}debug/dom-dump/last-main.${uuid}.html" 2>/dev/null

		git mv "${ROOTDIR}debug/dom-dump/last-sidebar.${last_uuid}.html" "${ROOTDIR}debug/dom-dump/last-sidebar.${uuid}.html" 2>/dev/null
		python "${ROOTDIR}debug/html_query.py" -i "${ROOTDIR}debug/dom-dump/last-html.${uuid}.html" -o "${ROOTDIR}debug/dom-dump/last-sidebar.${uuid}.html" -c aside
		git add -f "${ROOTDIR}debug/dom-dump/last-sidebar.${uuid}.html" 2>/dev/null

		git mv "${ROOTDIR}debug/dom-dump/last-body.${last_uuid}.html" "${ROOTDIR}debug/dom-dump/last-body.${uuid}.html" 2>/dev/null
		python "${ROOTDIR}debug/html_query.py" -i "${ROOTDIR}debug/dom-dump/last-html.${uuid}.html" -o "${ROOTDIR}debug/dom-dump/last-body.${uuid}.html" -c body
		git add -f "${ROOTDIR}debug/dom-dump/last-body.${uuid}.html" 2>/dev/null

		git mv "${ROOTDIR}debug/dom-dump/last-accordion-1.${last_uuid}.html" "${ROOTDIR}debug/dom-dump/last-accordion-1.${uuid}.html" 2>/dev/null
		python "${ROOTDIR}debug/html_query.py" -i "${ROOTDIR}debug/dom-dump/last-html.${uuid}.html" -o "${ROOTDIR}debug/dom-dump/last-accordion-1.${uuid}.html" -c '#support-sidebar .support-accordion-section:nth-of-type(1)'
		git add -f "${ROOTDIR}debug/dom-dump/last-accordion-1.${uuid}.html" 2>/dev/null

		git mv "${ROOTDIR}debug/dom-dump/last-accordion-2.${last_uuid}.html" "${ROOTDIR}debug/dom-dump/last-accordion-2.${uuid}.html" 2>/dev/null
		python "${ROOTDIR}debug/html_query.py" -i "${ROOTDIR}debug/dom-dump/last-html.${uuid}.html" -o "${ROOTDIR}debug/dom-dump/last-accordion-2.${uuid}.html" -c '#support-sidebar .support-accordion-section:nth-of-type(2)'
		git add -f "${ROOTDIR}debug/dom-dump/last-accordion-2.${uuid}.html" 2>/dev/null

		git mv "${ROOTDIR}debug/dom-dump/last-accordion-3.${last_uuid}.html" "${ROOTDIR}debug/dom-dump/last-accordion-3.${uuid}.html" 2>/dev/null
		python "${ROOTDIR}debug/html_query.py" -i "${ROOTDIR}debug/dom-dump/last-html.${uuid}.html" -o "${ROOTDIR}debug/dom-dump/last-accordion-3.${uuid}.html" -c '#support-sidebar .support-accordion-section:nth-of-type(3)'
		git add -f "${ROOTDIR}debug/dom-dump/last-accordion-3.${uuid}.html" 2>/dev/null

		git mv "${ROOTDIR}debug/dom-dump/last-accordion-4.${last_uuid}.html" "${ROOTDIR}debug/dom-dump/last-accordion-4.${uuid}.html" 2>/dev/null
		python "${ROOTDIR}debug/html_query.py" -i "${ROOTDIR}debug/dom-dump/last-html.${uuid}.html" -o "${ROOTDIR}debug/dom-dump/last-accordion-4.${uuid}.html" -c '#support-sidebar .support-accordion-section:nth-of-type(4)'
		git add -f "${ROOTDIR}debug/dom-dump/last-accordion-4.${uuid}.html" 2>/dev/null

	fi
fi
if ls -1 ${ROOTDIR}debug/webserver-log/last.*.log 2>/dev/null
then
	git mv ${ROOTDIR}debug/webserver-log/last.*.log "${ROOTDIR}debug/webserver-log/last.${uuid}.log"
	mv "${ROOTDIR}debug/webserver-log/last.log" "${ROOTDIR}debug/webserver-log/last.${uuid}.log" 2>/dev/null
fi
git add "${ROOTDIR}debug/screenshots/*"
git commit -a -m "${1:-$(git log -1 | tail -n1 | awk -F. '{print $1 "." $2 "." $3+1}')} - ${uuid}"
git push
git rm "${ROOTDIR}debug/screenshots/*.png" 2>/dev/null
mkdir -p "${ROOTDIR}debug/screenshots/"
xclip -selection clipboard -i <<<"https://raw.githubusercontent.com/froiloc/bb-forum-forensics/refs/heads/master/debug/bugs-and-tasks/last.${uuid}.md"
