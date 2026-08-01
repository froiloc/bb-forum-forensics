#!/usr/bin/env python3
"""
Anonymize HTML text by replacing content of elements matched by XPath(s)
with blind text of the same length.
"""

import argparse
import sys
import os
from lxml import html, etree

def anonymize_text(text):
    """Replace each non-space character with 'X', keep spaces and line breaks."""
    if not text:
        return text
    # Replace any character that is not space/tab/newline with 'X'
    return ''.join(ch if ch.isspace() else 'X' for ch in text)

def process_element(elem, xpath_expr, verbose, dry_run, file_obj_for_verbose):
    """Replace text of element if it matches any xpath (already filtered by caller)."""
    original = elem.text
    if original and original.strip():
        blinded = anonymize_text(original)
        if verbose and not dry_run:
            print(f"[VERBOSE] XPath: {xpath_expr}", file=file_obj_for_verbose)
            print(f"  Original: {repr(original[:80])}", file=file_obj_for_verbose)
            print(f"  Blinded:  {repr(blinded[:80])}", file=file_obj_for_verbose)
        elif dry_run:
            print(f"[DRY RUN] Would replace text in element matching: {xpath_expr}", file=file_obj_for_verbose)
            print(f"  Original: {repr(original[:80])}", file=file_obj_for_verbose)
            print(f"  Blinded:  {repr(blinded[:80])}", file=file_obj_for_verbose)
        if not dry_run:
            elem.text = blinded
        return True
    return False

def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("html_file", help="Path of the HTML file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show what is replaced")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Show what would be executed")
    parser.add_argument("-o", "--output", help="Output file path (default: <original>.new.<extension>)")
    parser.add_argument("-f", "--xpath-file", help="Text file with one XPath per line")
    parser.add_argument("-x", "--xpath", help="Single XPath expression")
    parser.add_argument("-h", "--help", action="help", help="Show this help message")
    
    args = parser.parse_args()
    
    # Validate XPath sources
    if not args.xpath_file and not args.xpath:
        print("ERROR: Either --xpath-file or --xpath must be provided.", file=sys.stderr)
        sys.exit(1)
    
    if args.xpath_file and args.xpath:
        print("ERROR: Provide only one of --xpath-file or --xpath, not both.", file=sys.stderr)
        sys.exit(1)
    
    # Read XPath expressions
    xpaths = []
    if args.xpath_file:
        try:
            with open(args.xpath_file, 'r') as f:
                xpaths = [line.strip() for line in f if line.strip()]
        except Exception as e:
            print(f"ERROR: Cannot read xpath file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        xpaths = [args.xpath]
    
    # Check if input HTML exists
    if not os.path.isfile(args.html_file):
        print(f"ERROR: HTML file not found: {args.html_file}", file=sys.stderr)
        sys.exit(1)
    
    # Determine output path
    if args.output:
        output_path = args.output
    else:
        base, ext = os.path.splitext(args.html_file)
        output_path = f"{base}.new{ext}"
    
    # Parse HTML
    try:
        with open(args.html_file, 'rb') as f:
            content = f.read()
        tree = html.fromstring(content)
    except Exception as e:
        print(f"ERROR: Failed to parse HTML: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Collect all matching elements (avoid modifying while iterating if overlapping)
    matched_elements = set()
    for xp in xpaths:
        try:
            elements = tree.xpath(xp)
            for elem in elements:
                if isinstance(elem, html.HtmlElement):
                    matched_elements.add((elem, xp))
        except etree.XPathError as e:
            print(f"ERROR: Invalid XPath '{xp}': {e}", file=sys.stderr)
            sys.exit(1)
    
    if not matched_elements:
        print("No elements matched the given XPath(s).", file=sys.stderr)
        if not args.dry_run and not args.verbose:
            sys.exit(0)
    
    # Process replacements
    changes_made = 0
    verbose_out = sys.stderr if args.dry_run else sys.stdout
    
    for elem, xp in matched_elements:
        if process_element(elem, xp, args.verbose, args.dry_run, verbose_out):
            changes_made += 1
    
    # Write output (unless dry run)
    if not args.dry_run:
        try:
            with open(output_path, 'wb') as f:
                f.write(html.tostring(tree, encoding='utf-8', method='html'))
            print(f"Written anonymized HTML to: {output_path}", file=sys.stderr)
        except Exception as e:
            print(f"ERROR: Failed to write output: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"[DRY RUN] No file written. Would write to: {output_path}", file=sys.stderr)
    
    if args.verbose or args.dry_run:
        print(f"Processed {changes_made} text nodes.", file=sys.stderr)

if __name__ == "__main__":
    main()