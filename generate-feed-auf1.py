#!/usr/bin/env python3
# generate-feed-auf1.py
# Ziel: AUF1 -> API get/<slug> -> audiofile -> download -> media_auf1 -> feed_auf1.xml

import feedparser
import requests
import re
import os
import html
from datetime import datetime
from urllib.parse import quote, urlparse
import sys
import time

FEED_URL = "https://auf1.radio/api/feed"
MEDIA_DIR = "media_auf1"
OUTPUT_FEED = "feed_auf1.xml"
BASE_URL = "https://peter-sobi.github.io/podcast/media_auf1/"
API_GET = "https://auf1.radio/api/get/"

# Einstellungen
REQUEST_TIMEOUT = 12
MAX_ITEMS = 20
USER_AGENT = "github-actions/auf1-feed-generator (+https://github.com/peter-sobi/podcast)"

os.makedirs(MEDIA_DIR, exist_ok=True)

def sanitize_filename(name):
    name = name.strip()
    name = name.replace(" ", "_")
    name = re.sub(r"[^A-Za-z0-9_\-äöüÄÖÜß\.]", "", name)
    # Kürze auf 120 Zeichen
    return name[:120]

def slug_from_link(link):
    try:
        p = urlparse(link)
        path = p.path.rstrip("/")
        if not path:
            return None
        slug = path.split("/")[-1]
        return slug
    except Exception:
        return None

def get_audio_url_from_api(slug):
    if not slug:
        return None
    api_url = API_GET + slug
    headers = {"User-Agent": USER_AGENT}
    try:
        r = requests.get(api_url, timeout=REQUEST_TIMEOUT, headers=headers)
        if r.status_code != 200:
            print(f"API {api_url} returned {r.status_code}")
            return None
        data = r.json()
        # Manche Antworten können das Feld anders nennen; wir prüfen robust
        audiofile = data.get("audiofile") or data.get("audio") or data.get("file")
        if not audiofile:
            print("Kein 'audiofile' in API-Antwort:", api_url)
            return None
        # Falls audiofile bereits eine vollständige URL ist, nutze sie
        if audiofile.startswith("http://") or audiofile.startswith("https://"):
            return audiofile
        return f"https://auf1.radio/storage/{audiofile}"
    except Exception as e:
        print("Fehler beim API-Abruf:", e)
        return None

def download_file(url, title):
    filename = sanitize_filename(title) + ".mp3"
    filepath = os.path.join(MEDIA_DIR, filename)

    # Wenn Datei existiert, überschreiben wir nicht automatisch.
    # Workflow/YAML löscht vorher den Ordner (Refresh). Falls du kein Refresh hast,
    # kannst du hier das Verhalten anpassen (z.B. prüfen Größe/Alter).
    try:
        print("Lade herunter:", url)
        headers = {"User-Agent": USER_AGENT}
        r = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers, stream=True)
        if r.status_code != 200:
            print("Download fehlgeschlagen:", r.status_code, url)
            return None
        # Schreibe in temporäre Datei, dann umbenennen
        tmp = filepath + ".part"
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        os.replace(tmp, filepath)
        print("Gespeichert als:", filename)
        return filename
    except Exception as e:
        print("Fehler beim Herunterladen:", e)
        return None

def build_feed(entries):
    items_xml = ""
    for title, filename, pubdate in entries:
        url = BASE_URL + quote(filename)
        # pubdate: falls None, setze jetzt
        pd = pubdate or datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        items_xml += f"""
        <item>
            <title>{html.escape(title)}</title>
            <link>{url}</link>
            <enclosure url="{url}" type="audio/mpeg" />
            <pubDate>{pd}</pubDate>
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
    print("Lade RSS-Feed…", FEED_URL)
    headers = {"User-Agent": USER_AGENT}
    try:
        feed = feedparser.parse(FEED_URL)
    except Exception as e:
        print("Feedparser Fehler:", e)
        sys.exit(1)

    if not hasattr(feed, "entries") or len(feed.entries) == 0:
        print("Feed enthält keine Einträge.")
        sys.exit(1)

    processed = []
    for entry in feed.entries:
        title = getattr(entry, "title", "AUF1 Beitrag")
        link = getattr(entry, "link", None)
        pubdate = getattr(entry, "published", None) or getattr(entry, "updated", None)

        print("Verarbeite:", title)
        slug = slug_from_link(link)
        if not slug:
            print("Keine slug aus Link extrahierbar:", link)
            continue

        audio_url = get_audio_url_from_api(slug)
        if not audio_url:
            print("Keine Audio-URL gefunden für slug:", slug)
            continue

        filename = download_file(audio_url, title)
        if filename:
            processed.append((title, filename, pubdate))

        # Begrenze auf MAX_ITEMS
        if len(processed) >= MAX_ITEMS:
            break

        # kleine Pause, um API nicht zu überlasten
        time.sleep(0.5)

    if not processed:
        print("Keine Dateien heruntergeladen. Feed wird nicht erzeugt.")
        sys.exit(2)

    build_feed(processed)

if __name__ == "__main__":
    main()
