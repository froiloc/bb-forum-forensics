#!/bin/bash
base64="${1}"
bn="${base64%%.base64}"
wd="$(basename $PWD)"
base64 -d < "${bn}.base64" > ${bn}.zip && \
unzip -o -qq ${bn}.zip "${wd}/*" -d "${PWD}"
cd "${wd}" && \
cp -rf * .. && \
cd .. && \
rm -rf "${wd}"
