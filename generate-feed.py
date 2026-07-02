#!/usr/bin/env python3
# APOLUT – MULTI-KATEGORIE WEB-SCRAPER
# - scrapt mehrere Kategorien direkt von der Webseite
# - extrahiert MP3, Titel, Datum
# - Klarnamen + Datum voranstellen
# - lädt ALLE neuen Episoden (continue-Fix)
# - 20-Dateien-Limit
# - Log-Datei für GitHub Actions

import requests
import os
import re
import json
import html
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from email.utils import format_datetime

CATEGORIES = {
    "Tagesdosis": "https://apolut.net/category/tagesdosis/",
    "Interviews": "https://apolut.net/category/interviews/",
    "Nachrichten": "https://apolut.net/category/nachrichten/",
    "Standpunkte": "https://apolut.net/category/standpunkte/",
}

MEDIA_DIR = "media_apolut_all"
TITLE_DB = "apolut_all_titles.json"
OUTPUT_FEED = "feed_apolut_all.xml"
LOGFILE = "logs/apolut_all.log"
BASE_URL = "https://peter-sobi.github.io/podcast/media_apolut_all/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9",
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
        r = requests.get(url, stream=True, timeout=20, headers=HEADERS)
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
<title>Apolut – Alle Kategorien</title>
<link>https://peter-sobi.github.io/podcast/</link>
<description>Automatisch generierter Apolut Gesamtfeed (Tagesdosis, Interviews, Nachrichten, Standpunkte)</description>
{xml}
</channel></rss>"""

    with open(OUTPUT_FEED, "w", encoding="utf-8") as f:
        f.write(feed)

def scrape_category(name, url):
    log(f"Scraping Kategorie: {name} → {url}")

    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
    except Exception as e:
        log(f"ERROR: {name} unreachable → {e}")
        return

    if r.status_code != 200:
        log(f"ERROR: {name} HTTP {r.status_code}")
        return

    soup = BeautifulSoup(r.text, "html.parser")

    posts = soup.find_all("article")
    if not posts:
        log(f"WARNING: Keine Artikel in {name} gefunden!")
        return

    log(f"{name}: Gefundene Artikel: {len(posts)}")

    for post in posts:
        # Titel
        h2 = post.find("h2")
        if not h2:
            continue
        title = h2.get_text(strip=True)

        # Kategorie im Titel kenntlich machen
        full_title = f"[{name}] {title}"

        # Datum
        date_tag = post.find("time")
        if date_tag and date_tag.has_attr("datetime"):
            try:
                dt = datetime.fromisoformat(date_tag["datetime"])
                date_str = f"{dt.day:02d}.{dt.month:02d}"
            except Exception:
                date_str = "00.00"
        else:
            date_str = "00.00"

        # MP3-Link suchen
        mp3 = None
        for a in post.find_all("a"):
            href = a.get("href", "")
            if href.endswith(".mp3"):
                mp3 = href
                break

        if not mp3:
            log(f"SKIP ({name}): Keine MP3 gefunden → {title}")
            continue

        uuid_name = mp3.split("/")[-1]

        # UUID-Erkennung → nur überspringen
        if any(uuid_name in fn for fn in os.listdir(MEDIA_DIR)):
            log(f"SKIP ({name}): Already have → {uuid_name}")
            continue

        # Dateiname erzeugen
        safe_title = re.sub(r"[^a-zA-Z0-9_-]+", "_", full_title).strip("_")
        filename = f"{date_str}_{safe_title}.mp3"
        filepath = os.path.join(MEDIA_DIR, filename)

        log(f"Downloading NEW ({name}): {filename}")

        if download(mp3, filepath):
            TITLE_MAP[filename] = full_title
            save_titles()

def main():
    log("Scraping Apolut – alle Kategorien…")

    for name, url in CATEGORIES.items():
        scrape_category(name, url)

    log("Limiting to 20 files…")
    newest_20 = limit_to_20_files()

    log("Building feed…")
    build_feed(newest_20)

    log("Done.")
    return 0

if __name__ == "__main__":
    main()

