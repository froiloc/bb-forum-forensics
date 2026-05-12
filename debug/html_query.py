#!/usr/bin/env python3
"""
HTML Query Tool - Extrahiert OuterHTML von Elementen mittels XPath oder CSS-Selector.
Unterstützt moderne CSS-Selektoren wie :nth-of-type().

Verwendung:
    python html_query.py -i input.html -o output.txt -x "//div[@class='content']"
    python html_query.py -i input.html -o output.txt -c "div p:nth-of-type(2)"
"""

import sys
import argparse
from bs4 import BeautifulSoup
from lxml import html, etree
import cssselect


def query_html_css(content, css_selector):
    """
    Führt eine CSS-Selector-Abfrage mit BeautifulSoup4 aus 
    (unterstützt moderne CSS-Selektoren).
    """
    soup = BeautifulSoup(content, 'html.parser')
    elements = soup.select(css_selector)
    
    results = []
    for element in elements:
        # BeautifulSoup liefert standardmäßig kein echtes OuterHTML,
        # aber wir können es so bekommen
        results.append(str(element))
    
    return results


def query_html_xpath(content, xpath):
    """
    Führt eine XPath-Abfrage mit lxml aus.
    """
    tree = html.fromstring(content)
    
    try:
        elements = tree.xpath(xpath)
    except etree.XPathEvalError as e:
        raise ValueError(f"Ungültiger XPath-Ausdruck: {e}")
    
    results = []
    for element in elements:
        if isinstance(element, str):
            results.append(element)
        else:
            outer_html = etree.tostring(element, encoding='unicode', method='html')
            results.append(outer_html.strip())
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description='Extrahiert OuterHTML von Elementen aus HTML-Dateien mittels XPath oder CSS-Selector.'
    )
    parser.add_argument('-i', '--input', help='Eingabe-HTML-Datei (falls nicht angegeben, wird stdin verwendet)')
    parser.add_argument('-o', '--output', help='Ausgabe-Datei (falls nicht angegeben, wird stdout verwendet)')
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-x', '--xpath', help='XPath-Ausdruck')
    group.add_argument('-c', '--css', help='CSS-Selector (unterstützt moderne CSS4-Selektoren)')
    
    args = parser.parse_args()
    
    try:
        # HTML-Inhalt lesen
        if args.input:
            with open(args.input, 'r', encoding='utf-8') as f:
                html_content = f.read()
        else:
            html_content = sys.stdin.read()
        
        # Abfrage ausführen
        if args.css:
            results = query_html_css(html_content, args.css)
        else:
            results = query_html_xpath(html_content, args.xpath)
        
        # Ergebnis formatieren
        output = '\n'.join(results)
        
        # Ausgabe schreiben
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
                if results:
                    f.write('\n')
            print(f"Ergebnisse in {args.output} geschrieben ({len(results)} Treffer)", file=sys.stderr)
        else:
            print(output)
    
    except FileNotFoundError as e:
        print(f"Fehler: Datei nicht gefunden - {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Fehler: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unerwarteter Fehler: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
