#!/usr/bin/env python3
# AUF1 – lädt nur neue Episoden, stoppt bei erster bekannter Datei
# Begrenzung: Ordner und Feed IMMER auf 20 Dateien
# Titel: echte Titel aus dem Feed, nicht aus Dateinamen

import feedparser
import requests
import os
import html
import json
from datetime import datetime, timezone
from email.utils import format_datetime

FEED_URL = "https://auf1.radio/api/feed"
MEDIA_DIR = "media_auf1"
TITLE_DB = "auf1_titles.json"
OUTPUT_FEED = "feed_auf1.xml"
BASE_URL = "https://peter-sobi.github.io/podcast/media_auf1/"

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

    for fn in delete:
        os.remove(os.path.join(MEDIA_DIR, fn))
        TITLE_MAP.pop(fn, None)

    save_titles()
    return keep

def build_feed(files):
    xml = ""
    for fn in files:
        title = TITLE_MAP.get(fn, fn)  # Fallback falls Titel fehlt
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
<title>AUF1 Radio</title>
<link>https://peter-sobi.github.io/podcast/</link>
<description>Automatisch generierter AUF1 Radio Feed</description>
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
        title = entry.title
        url = entry.enclosures[0].href
        filename = url.split("/")[-1]
        filepath = os.path.join(MEDIA_DIR, filename)

        if os.path.exists(filepath):
            print("STOP: Found existing file →", filename)
            break

        print("Downloading NEW:", filename)
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

