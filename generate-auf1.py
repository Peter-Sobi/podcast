#!/usr/bin/env python3
import os
import sys
import re
import requests
import datetime
from bs4 import BeautifulSoup

RSS_URL = "https://auf1.tv/feed/podcast/"
MEDIA_DIR = "auf1_media"
FEED_FILE = "auf1_feed.xml"

def log(msg):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")

def sanitize_filename(name):
    bad = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for b in bad:
        name = name.replace(b, "")
    return name.replace(" ", "_")

def extract_date_from_url(url):
    m = re.search(r"(20\d{6})", url)
    if not m:
        return None
    yyyymmdd = m.group(1)
    year = int(yyyymmdd[0:4])
    month = int(yyyymmdd[4:6])
    day = int(yyyymmdd[6:8])
    return f"{day:02d}.{month:02d}"

def date_to_sort_key(date_prefix):
    if not date_prefix:
        return 0
    day, month = date_prefix.split(".")
    return int(f"2026{month}{day}")

def download_file(url, path):
    log(f"[download] Lade Datei: {url}")
    try:
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        log(f"[download] Fertig: {path}")
    except Exception as e:
        log(f"[error] Download fehlgeschlagen: {e}")

def generate_feed(items):
    log("[feed] Erzeuge neuen AUF1 RSS-Feed")

    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        '<channel>',
        '<title>AUF1 Podcast – Vollständiger Feed</title>',
        '<link>https://auf1.tv</link>',
        '<description>Automatisch generierter Feed</description>'
    ]

    for item in items:
        xml.append("<item>")
        xml.append(f"<title>{item['feed_title']}</title>")
        xml.append(f"<link>{item['url']}</link>")
        xml.append(f"<enclosure url=\"{item['url']}\" type=\"audio/mpeg\"/>")
        xml.append("</item>")

    xml.append("</channel>")
    xml.append("</rss>")

    with open(FEED_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(xml))

    log(f"[feed] Feed gespeichert: {FEED_FILE}")

def fallback_from_existing_files():
    log("[fallback] AUF1 RSS leer – Erzeuge Feed aus vorhandenen Dateien")

    items = []
    for filename in os.listdir(MEDIA_DIR):
        if filename.endswith(".mp3"):
            parts = filename.split("_", 1)

            if len(parts) == 2 and "." in parts[0]:
                date_prefix = parts[0]
                title = parts[1].replace(".mp3", "").replace("_", " ")
                feed_title = f"{date_prefix} – {title}"
                sort_key = date_to_sort_key(date_prefix)
            else:
                feed_title = filename.replace(".mp3", "")
                sort_key = 0

            items.append({
                "feed_title": feed_title,
                "url": f"https://raw.githubusercontent.com/Peter-Sobi/podcast/main/{MEDIA_DIR}/{filename}",
                "sort_key": sort_key
            })

    items.sort(key=lambda x: x["sort_key"], reverse=True)
    generate_feed(items)

def main():
    log("[auf1] Starte RSS-basierten Feed-Generator")
    log(f"[rss] Lade RSS: {RSS_URL}")

    try:
        r = requests.get(RSS_URL, timeout=20)
        r.raise_for_status()
    except Exception as e:
        log(f"[error] RSS konnte nicht geladen werden: {e}")
        fallback_from_existing_files()
        return

    soup = BeautifulSoup(r.text, "lxml-xml")
    rss_items = soup.find_all("item")

    os.makedirs(MEDIA_DIR, exist_ok=True)

    if not rss_items:
        log("[auf1] RSS enthält keine Items – Fallback wird verwendet.")
        fallback_from_existing_files()
        return

    downloaded_items = []
    new_files = 0

    for item in rss_items:
        title = item.find("title").text.strip()
        enclosure = item.find("enclosure")

        if enclosure and enclosure.get("type") == "audio/mpeg":
            url = enclosure.get("url")

            date_prefix = extract_date_from_url(url)
            sort_key = date_to_sort_key(date_prefix)

            if date_prefix:
                feed_title = f"{date_prefix} – {title}"
                filename = f"{date_prefix}_{sanitize_filename(title)}.mp3"
            else:
                feed_title = title
                filename = sanitize_filename(title) + ".mp3"

            filepath = os.path.join(MEDIA_DIR, filename)

            log(f"[episode] Gefunden: {feed_title}")

            if os.path.exists(filepath):
                log(f"[skip] Datei existiert bereits: {filename}")
            else:
                new_files += 1
                download_file(url, filepath)

            downloaded_items.append({
                "feed_title": feed_title,
                "url": url,
                "file": filepath,
                "sort_key": sort_key
            })

    downloaded_items.sort(key=lambda x: x["sort_key"], reverse=True)
    generate_feed(downloaded_items)

    log(f"[auf1] Fertig. {new_files} neue Episoden verarbeitet.")

if __name__ == "__main__":
    main()

