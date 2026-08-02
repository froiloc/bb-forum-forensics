#!/bin/bash
# merge any new tickets to data/issues.json
python merge.py eintraege_claude_Build*.json --auto-resolve source && rm eintraege_claude_Build*.json
