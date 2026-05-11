#!/usr/bin/env python3
import os
import re
from pathlib import Path
from email.utils import format_datetime
from datetime import datetime

BASE = Path(__file__).resolve().parent

# Dateien aus dem Workflow
URL_FILE = BASE / "release_urls.txt"
ASSET_FILE = BASE / "auf1_assets.txt"

# Ausgabe
OUT_FEED = BASE / "feed_auf1.xml"

# Regex zum Datum aus Dateinamen extrahieren
DATE_RE = re.compile(
    r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)_(\d{2})_(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)_(\d{4})"
)

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
    "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
}

def parse_date_from_filename(name: str) -> datetime:
    """
    Extrahiert Datum aus AUF1-Dateinamen.
    Beispiel:
    Fri_08_May_2026_Bauern_am_Limit.mp3
    """
    m = DATE_RE.search(name)
    if not m:
        # Fallback: aktuelles Datum
        return datetime.utcnow()

    _, day, month, year = m.groups()
    return datetime(int(year), MONTHS[month], int(day))

def load_urls():
    urls = {}
    with URL_FILE.open() as f:
        for line in f:
            name, url = line.strip().split("|")
            urls[name] = url
    return urls

def load_sizes():
    sizes = {}
    with ASSET_FILE.open() as f:
        for line in f:
            file, size = line.strip().split("|")
            sizes[os.path.basename(file)] = size
    return sizes

def main():
    urls = load_urls()
    sizes = load_sizes()

    items = []

    for filename, url in urls.items():
        base = os.path.basename(filename)

        if base not in sizes:
            # Datei existiert nicht → nicht in den Feed aufnehmen
            continue

        pubdate = parse_date_from_filename(base)
        pubdate_rfc = format_datetime(pubdate)

        items.append((pubdate, f"""
<item>
<title>{base}</title>
<link>https://auf1.radio</link>
<description><![CDATA[{base}]]></description>
<enclosure url="{url}" length="{sizes[base]}" type="audio/mpeg"/>
<guid isPermaLink="false">{url}</guid>
<pubDate>{pubdate_rfc}</pubDate>
</item>
"""))

    # Sortieren: neueste zuerst
    items.sort(key=lambda x: x[0], reverse=True)

    rss_items = "".join(item for _, item in items)

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>AUF1 Kombinierter Podcast</title>
<link>https://auf1.radio</link>
<description>Automatisch generierter Feed</description>
<language>de-de</language>
{rss_items}
</channel>
</rss>
"""

    OUT_FEED.write_text(rss, encoding="utf-8")
    print("Feed erfolgreich erzeugt:", OUT_FEED)

if __name__ == "__main__":
    main()

