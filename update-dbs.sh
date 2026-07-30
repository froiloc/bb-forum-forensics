#!/bin/bash
while
	read -r id
do
	python tools/migrate-dbs.py --subject-id $id --apply --changed-by h0a2898
done < <(ls -1 data/forensic/*.db | cut -d'_' -f2 | cut -d'.' -f1) \
	| tee -a "logs/migrate-evidence-$(date +"%Y%m%d-%H%I%S").log"

