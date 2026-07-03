#!/usr/bin/env python3
import os
import sys
import requests
import datetime
from bs4 import BeautifulSoup

RSS_URL = "https://apolut.net/podcast/rss"
MEDIA_DIR = "media"
FEED_FILE = "feed.xml"

def log(msg):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")

def sanitize_filename(name):
    bad = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for b in bad:
        name = name.replace(b, "")
    return name.replace(" ", "_")

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
    log("[feed] Erzeuge neuen RSS-Feed")

    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        '<channel>',
        '<title>Apolut Podcast – Vollständiger Feed</title>',
        '<link>https://apolut.net</link>',
        '<description>Automatisch generierter Feed</description>'
    ]

    for item in items:
        xml.append("<item>")
        xml.append(f"<title>{item['title']}</title>")
        xml.append(f"<link>{item['url']}</link>")
        xml.append(f"<enclosure url=\"{item['url']}\" type=\"audio/mpeg\"/>")
        xml.append("</item>")

    xml.append("</channel>")
    xml.append("</rss>")

    with open(FEED_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(xml))

    log(f"[feed] Feed gespeichert: {FEED_FILE}")

def main():
    log("[apolut] Starte RSS-basierten Feed-Generator")
    log(f"[rss] Lade RSS: {RSS_URL}")

    try:
        r = requests.get(RSS_URL, timeout=20)
        r.raise_for_status()
    except Exception as e:
        log(f"[error] RSS konnte nicht geladen werden: {e}")
        sys.exit(1)

    # WICHTIG: GitHub Actions benötigt lxml-xml
    soup = BeautifulSoup(r.text, "lxml-xml")

    rss_items = soup.find_all("item")

    if not rss_items:
        log("[apolut] FEHLER: RSS enthält keine Items – Abbruch.")
        sys.exit(0)

    os.makedirs(MEDIA_DIR, exist_ok=True)

    downloaded_items = []

    for item in rss_items:
        title = item.find("title").text.strip()
        enclosure = item.find("enclosure")

        if enclosure and enclosure.get("type") == "audio/mpeg":
            url = enclosure.get("url")
            filename = sanitize_filename(title) + ".mp3"
            filepath = os.path.join(MEDIA_DIR, filename)

            log(f"[episode] Gefunden: {title}")

            download_file(url, filepath)

            downloaded_items.append({
                "title": title,
                "url": url,
                "file": filepath
            })

    if not downloaded_items:
        log("[apolut] WARNUNG: Keine MP3-Episoden gefunden – alter Feed bleibt bestehen.")
        sys.exit(0)

    generate_feed(downloaded_items)

    log(f"[apolut] Fertig. {len(downloaded_items)} Episoden verarbeitet.")

if __name__ == "__main__":
    main()

