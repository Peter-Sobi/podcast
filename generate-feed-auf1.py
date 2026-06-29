#!/usr/bin/env python3
# AUF2 – perfekte Version
# - echte Titel aus dem Feed
# - Dateinamen aus Titel (keine UUID-Hieroglyphen mehr)
# - UUID-Erkennung bleibt erhalten
# - Mini-Titel-Datenbank (max. 20 Einträge)
# - Ordner und Feed IMMER auf 20 Dateien

import feedparser
import requests
import os
import html
import json
import re
from datetime import datetime, timezone
from email.utils import format_datetime

FEED_URL = "https://auf1.radio/api/feed2"
MEDIA_DIR = "media_auf2"
TITLE_DB = "auf2_titles.json"
OUTPUT_FEED = "feed_auf2.xml"
BASE_URL = "https://peter-sobi.github.io/podcast/media_auf2/"

feedparser.USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

REQUEST_HEADERS = {
    "User-Agent": feedparser.USER_AGENT,
    "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9",
    "Referer": "https://auf1.radio/",
}

os.makedirs(MEDIA_DIR, exist_ok=True)

# Titel-Datenbank laden
if os.path.exists(TITLE_DB):
    with open(TITLE_DB, "r", encoding="utf-8") as f:
        TITLE_MAP = json.load(f)
else:
    TITLE_MAP = {}

def save_titles():
    with open(TITLE_DB, "w", encoding="utf-8") as f:
        json.dump(TITLE_MAP, f, ensure_ascii=False, indent=2)

def download(url, path):
    try:
        r = requests.get(url, stream=True, timeout=20, headers=REQUEST_HEADERS)
        if r.status_code != 200:
            return False
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
        return True
    except:
        return False

def limit_to_20_files():
    files = sorted(
        os.listdir(MEDIA_DIR),
        key=lambda x: os.path.getmtime(os.path.join(MEDIA_DIR, x)),
        reverse=True
    )

    keep = files[:20]
    delete = files[20:]

    # Alte Dateien + alte Titel löschen
    for fn in delete:
        os.remove(os.path.join(MEDIA_DIR, fn))
        TITLE_MAP.pop(fn, None)

    save_titles()
    return keep

def build_feed(files):
    xml = ""
    for fn in files:
        title = TITLE_MAP.get(fn, fn)
        url = BASE_URL + fn
        length = os.path.getsize(os.path.join(MEDIA_DIR, fn))
        pub = format_datetime(datetime.now(timezone.utc))

        xml += f"""
        <item>
            <title>{html.escape(title)}</title>
            <link>{url}</link>
            <enclosure url="{url}" length="{length}" type="audio/mpeg" />
            <guid isPermaLink="false">{html.escape(url)}</guid>
            <pubDate>{pub}</pubDate>
        </item>
        """

    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>AUF1 Radio – Feed 2</title>
<link>https://peter-sobi.github.io/podcast/</link>
<description>Automatisch generierter AUF1 Radio Feed 2</description>
{xml}
</channel></rss>"""

    with open(OUTPUT_FEED, "w", encoding="utf-8") as f:
        f.write(feed)

def main():
    print("Loading feed…")

    feed = feedparser.parse(FEED_URL, request_headers=REQUEST_HEADERS)

    if not feed.entries:
        print("ERROR: No entries")
        return 1

    for entry in feed.entries:
        # AUF1 liefert Titel oft in summary
        title = entry.get("summary", entry.title)
        url = entry.enclosures[0].href

        # UUID aus URL extrahieren
        uuid_name = url.split("/")[-1]

        # Prüfen, ob UUID bereits existiert → STOP
        if any(uuid_name in fn for fn in os.listdir(MEDIA_DIR)):
            print("STOP: Found existing file →", uuid_name)
            break

        # Klarname erzeugen
        safe_title = re.sub(r'[^a-zA-Z0-9_-]+', '_', title).strip('_')
        filename = safe_title + ".mp3"
        filepath = os.path.join(MEDIA_DIR, filename)

        print("Downloading NEW:", filename)

        # Datei speichern
        if download(url, filepath):
            TITLE_MAP[filename] = title
            save_titles()

    print("Limiting to 20 files…")
    newest_20 = limit_to_20_files()

    print("Building feed…")
    build_feed(newest_20)

    print("Done.")
    return 0

if __name__ == "__main__":
    main()

