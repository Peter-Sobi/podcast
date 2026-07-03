#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import hashlib
import datetime
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

RSS_URL = "https://apolut.net/podcast/rss"
FEED_FILE = "feed.xml"
LOG_FILE = "logs/apolut.log"
MAX_EPISODES = 10
TIMEOUT = 12

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except:
        pass

def fetch_rss(url):
    log(f"[rss] Lade RSS: {url}")
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception as e:
        log(f"[rss] Fehler: {e}")
        return None

def stable_id(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def write_feed(items):
    log("[feed] Schreibe feed.xml")

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<rss version="2.0">\n<channel>\n'
    xml += '<title>Apolut Tagesdosis</title>\n'
    xml += '<link>https://apolut.net/tag/tagesdosis/</link>\n'
    xml += '<description>Automatisch generierter Tagesdosis-Feed</description>\n'

    for item in items:
        xml += "<item>\n"
        xml += f"<title>{item['title']}</title>\n"
        xml += f"<guid>{item['id']}</guid>\n"
        xml += f"<link>{item['article_url']}</link>\n"
        xml += f"<enclosure url=\"{item['mp3_url']}\" type=\"audio/mpeg\" />\n"
        xml += "</item>\n"

    xml += "</channel>\n</rss>\n"

    with open(FEED_FILE, "w", encoding="utf-8") as f:
        f.write(xml)

def main():
    log("[apolut] Starte RSS-basierten Tagesdosis-Feed-Generator")

    rss = fetch_rss(RSS_URL)
    if not rss:
        log("[apolut] WARNUNG: RSS nicht erreichbar – alter Feed bleibt bestehen.")
        return

    root = ET.fromstring(rss)
    channel = root.find("channel")
    items_raw = channel.findall("item")

    items = []

    for item in items_raw:
        title = item.find("title").text.strip()
        link = item.find("link").text.strip()

        enclosure = item.find("enclosure")
        if enclosure is None:
            continue

        mp3_url = enclosure.attrib.get("url")
        if not mp3_url:
            continue

        # Nur Tagesdosis filtern
        if "Tagesdosis" not in title:
            continue

        id_ = stable_id(title + mp3_url)

        items.append({
            "title": title,
            "article_url": link,
            "mp3_url": mp3_url,
            "id": id_,
        })

        if len(items) >= MAX_EPISODES:
            break

    if not items:
        log("[apolut] WARNUNG: Keine Tagesdosis-Episoden gefunden – alter Feed bleibt bestehen.")
        return

    write_feed(items)
    log("[apolut] Feed erfolgreich aktualisiert.")

if __name__ == "__main__":
    main()

