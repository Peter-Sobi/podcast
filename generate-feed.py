#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import hashlib
import datetime
import requests
from bs4 import BeautifulSoup

# ------------------------------------------------------------
# Konfiguration
# ------------------------------------------------------------

SOURCE_URLS = [
    "https://apolut.net/kategorie/video/",
    "https://apolut.net/video/",
    "https://apolut.net/videos/",
    "https://apolut.net/category/video/",  # alte URL, falls wieder aktiv
]

FEED_FILE = "feed.xml"
MEDIA_DIR = "media"
LOG_FILE = "logs/apolut.log"

MAX_EPISODES = 10
TIMEOUT = 12

# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except:
        pass

# ------------------------------------------------------------
# HTTP Fetch mit Fehlerbehandlung
# ------------------------------------------------------------

def fetch_page(url):
    log(f"[fetch] Lade URL: {url}")
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code == 404:
            log(f"[fetch] 404 Not Found: {url}")
            return None
        r.raise_for_status()
        return r.text
    except Exception as e:
        log(f"[fetch] Fehler: {e}")
        return None

def fetch_first_available():
    for url in SOURCE_URLS:
        html = fetch_page(url)
        if html:
            log(f"[fetch] Erfolgreiche Quelle: {url}")
            return html
    log("[fetch] Keine gültige Apolut-Video-URL gefunden.")
    return None

# ------------------------------------------------------------
# MP3-Erkennung
# ------------------------------------------------------------

def extract_mp3_links(html):
    soup = BeautifulSoup(html, "html.parser")
    links = set()

    # 1) klassische Apolut-Pfade
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.endswith(".mp3"):
            links.add(href)

    # 2) audio-Tags
    for audio in soup.find_all("audio"):
        src = audio.get("src")
        if src and src.endswith(".mp3"):
            links.add(src)

    # 3) meta og:audio
    for meta in soup.find_all("meta"):
        if meta.get("property") == "og:audio":
            content = meta.get("content")
            if content and content.endswith(".mp3"):
                links.add(content)

    return list(links)

# ------------------------------------------------------------
# Dateiname + Hash
# ------------------------------------------------------------

def stable_id(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def build_filename(title, url):
    today = datetime.datetime.now().strftime("%d.%m.%Y")
    h = stable_id(title + url)
    return f"{today}_tagesdosis_{h}.mp3"

# ------------------------------------------------------------
# Feed schreiben
# ------------------------------------------------------------

def write_feed(items):
    log("[feed] Schreibe feed.xml")

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<rss version="2.0">\n<channel>\n'
    xml += '<title>Apolut Gesamtfeed</title>\n'
    xml += '<link>https://apolut.net</link>\n'
    xml += '<description>Automatisch generierter Feed</description>\n'

    for item in items:
        xml += "<item>\n"
        xml += f"<title>{item['title']}</title>\n"
        xml += f"<guid>{item['id']}</guid>\n"
        xml += f"<enclosure url=\"{item['url']}\" type=\"audio/mpeg\" />\n"
        xml += "</item>\n"

    xml += "</channel>\n</rss>\n"

    with open(FEED_FILE, "w", encoding="utf-8") as f:
        f.write(xml)

# ------------------------------------------------------------
# Hauptlogik
# ------------------------------------------------------------

def main():
    log("[apolut] Starte robusten Feed-Generator")

    # Ordner anlegen
    os.makedirs(MEDIA_DIR, exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    # HTML laden
    html = fetch_first_available()
    if not html:
        log("[apolut] WARNUNG: Keine Quelle erreichbar – alter Feed bleibt bestehen.")
        return  # FEED NICHT LÖSCHEN

    # MP3s extrahieren
    mp3s = extract_mp3_links(html)
    if not mp3s:
        log("[apolut] WARNUNG: Keine MP3-Dateien gefunden – alter Feed bleibt bestehen.")
        return

    # Episoden begrenzen
    mp3s = mp3s[:MAX_EPISODES]

    items = []
    for url in mp3s:
        title = "Apolut Episode"
        id_ = stable_id(url)
        items.append({"title": title, "url": url, "id": id_})

    write_feed(items)
    log("[apolut] Feed erfolgreich aktualisiert.")

# ------------------------------------------------------------
# Start
# ------------------------------------------------------------

if __name__ == "__main__":
    main()

