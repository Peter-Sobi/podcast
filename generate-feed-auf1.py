#!/usr/bin/env python3
# AUF1 – ROBUSTE VERSION MIT DATUM
# - arbeitet auch bei "No entries"
# - löscht trotzdem alte Dateien
# - baut trotzdem Feed
# - commitet trotzdem
# - Klarnamen + UUID-Erkennung
# - Datum voranstellen: dd.mm_
# - 20-Dateien-Limit IMMER garantiert
# - Log-Datei für GitHub Actions

import feedparser
import requests
import os
import html
import json
import re
from datetime import datetime, timezone
from email.utils import format_datetime

FEED_URL = "https://auf1.radio/api/feed"
MEDIA_DIR = "media_auf1"
TITLE_DB = "auf1_titles.json"
OUTPUT_FEED = "feed_auf1.xml"
LOGFILE = "logs/auf1.log"
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
os.makedirs("logs", exist_ok=True)

# Titel-Datenbank laden
if os.path.exists(TITLE_DB):
    with open(TITLE_DB, "r", encoding="utf-8") as f:
        TITLE_MAP = json.load(f)
else:
    TITLE_MAP = {}

def log(msg):
    print(msg)
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def save_titles():
    with open(TITLE_DB, "w", encoding="utf-8") as f:
        json.dump(TITLE_MAP, f, ensure_ascii=False, indent=2)

def download(url, path):
    try:
        r = requests.get(url, stream=True, timeout=20, headers=REQUEST_HEADERS)
        if r.status_code != 200:
            log(f"Download failed: HTTP {r.status_code}")
            return False
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        log(f"Download error: {e}")
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
        log(f"Deleted old file: {fn}")

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
<title>AUF1 Radio</title>
<link>https://peter-sobi.github.io/podcast/</link>
<description>Automatisch generierter AUF1 Radio Feed</description>
{xml}
</channel></rss>"""

    with open(OUTPUT_FEED, "w", encoding="utf-8") as f:
        f.write(feed)

def main():
    log("Loading feed…")

    feed = feedparser.parse(FEED_URL, request_headers=REQUEST_HEADERS)

    if not feed.entries:
        log("WARNING: AUF1 liefert keine Einträge!")
        log("→ Trotzdem weiterarbeiten (robuste Version).")
    else:
        log(f"AUF1 liefert {len(feed.entries)} Einträge.")

    # Nur neue Dateien laden, wenn Einträge vorhanden sind
    if feed.entries:
        for entry in feed.entries:
            title = entry.get("summary", entry.title)
            url = entry.enclosures[0].href

            uuid_name = url.split("/")[-1]

            # UUID-Erkennung
            if any(uuid_name in fn for fn in os.listdir(MEDIA_DIR)):
                log(f"STOP: Found existing file → {uuid_name}")
                break

            # Datum extrahieren
            dt = entry.get("published_parsed")
            if dt:
                date_str = f"{dt.tm_mday:02d}.{dt.tm_mon:02d}"
            else:
                date_str = "00.00"

            # Klarname erzeugen
            safe_title = re.sub(r'[^a-zA-Z0-9_-]+', '_', title).strip('_')

            # Dateiname mit Datum
            filename = f"{date_str}_{safe_title}.mp3"
            filepath = os.path.join(MEDIA_DIR, filename)

            log(f"Downloading NEW: {filename}")

            if download(url, filepath):
                TITLE_MAP[filename] = title
                save_titles()

    log("Limiting to 20 files…")
    newest_20 = limit_to_20_files()

    log("Building feed…")
    build_feed(newest_20)

    log("Done.")
    return 0

if __name__ == "__main__":
    main()

