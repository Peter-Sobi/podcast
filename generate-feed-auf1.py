#!/usr/bin/env python3
import feedparser
import requests
import re
import os
import html
from datetime import datetime
from urllib.parse import quote

FEED_URL = "https://auf1.radio/api/feed"
MEDIA_DIR = "media_auf1"
OUTPUT_FEED = "feed_auf1.xml"

# GitHub Pages URL (ANPASSEN falls Repo anders heißt)
BASE_URL = "https://peter-sobi.github.io/podcast/media_auf1/"

# Stelle sicher, dass der Ordner existiert
os.makedirs(MEDIA_DIR, exist_ok=True)

def sanitize_filename(name):
    name = name.replace(" ", "_")
    name = re.sub(r"[^A-Za-z0-9_\-äöüÄÖÜß\.]", "", name)
    return name

def extract_audio_url(page_url):
    """Extrahiert die MP3-URL aus der Episodenseite."""
    try:
        r = requests.get(page_url, timeout=10)
        if r.status_code != 200:
            return None

        # JSON-Block mit "audio": "URL"
        match = re.search(r'"audio"\s*:\s*"([^"]+)"', r.text)
        if match:
            return match.group(1)
    except:
        return None

    return None

def download_and_convert(title, audio_url):
    """Lädt MP3 herunter und speichert sie direkt."""
    filename = sanitize_filename(title) + ".mp3"
    filepath = os.path.join(MEDIA_DIR, filename)

    if os.path.exists(filepath):
        print(f"Schon vorhanden: {filename}")
        return filename

    print(f"Lade herunter: {audio_url}")

    try:
        r = requests.get(audio_url, timeout=20)
        if r.status_code != 200:
            print("Download fehlgeschlagen:", audio_url)
            return None

        with open(filepath, "wb") as f:
            f.write(r.content)

        return filename
    except Exception as e:
        print("Fehler beim Download:", e)
        return None

def build_feed(entries):
    """Erzeugt feed_auf1.xml mit GitHub Pages URLs."""
    items_xml = ""

    for title, filename, pubdate in entries:
        url = BASE_URL + quote(filename)

        items_xml += f"""
        <item>
            <title>{html.escape(title)}</title>
            <link>{url}</link>
            <enclosure url="{url}" type="audio/mpeg" />
            <pubDate>{pubdate}</pubDate>
        </item>
        """

    feed_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
    <title>AUF1 Radio (32kbps)</title>
    <link>https://peter-sobi.github.io/podcast/</link>
    <description>Automatisch generierter AUF1 Radio Feed</description>
    {items_xml}
</channel>
</rss>
"""

    with open(OUTPUT_FEED, "w", encoding="utf-8") as f:
        f.write(feed_xml)

    print("Feed erzeugt:", OUTPUT_FEED)

def main():
    print("Lade RSS-Feed…")
    feed = feedparser.parse(FEED_URL)

    processed = []

    for entry in feed.entries:
        title = entry.title
        page_url = entry.link
        pubdate = entry.published

        print("Verarbeite:", title)

        audio_url = extract_audio_url(page_url)
        if not audio_url:
            print("Keine Audio-URL gefunden!")
            continue

        filename = download_and_convert(title, audio_url)
        if filename:
            processed.append((title, filename, pubdate))

        # Nur die neuesten 20 behalten
        if len(processed) >= 20:
            break

    build_feed(processed)

if __name__ == "__main__":
    main()
