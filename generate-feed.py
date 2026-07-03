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

TAG_URL = "https://apolut.net/tag/tagesdosis/"
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
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
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

# ------------------------------------------------------------
# Artikel-Links von der Tag-Seite holen
# ------------------------------------------------------------

def get_article_links_from_tag(html):
    soup = BeautifulSoup(html, "html.parser")
    links = []

    # Apolut nutzt meist Artikel-Teaser mit <a> auf den Beitrag
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # einfache Filterung: nur Apolut-Artikel, keine Tags/Kategorien
        if href.startswith("https://apolut.net/") and "/tag/" not in href and "/kategorie/" not in href:
            links.append(href)

    # Duplikate entfernen, Reihenfolge beibehalten
    seen = set()
    unique = []
    for l in links:
        if l not in seen:
            seen.add(l)
            unique.append(l)

    log(f"[tag] Gefundene Artikel-Links: {len(unique)}")
    return unique

# ------------------------------------------------------------
# MP3-Erkennung in einem Artikel
# ------------------------------------------------------------

def extract_mp3_links_from_article(html):
    soup = BeautifulSoup(html, "html.parser")
    links = set()

    # 1) klassische Links
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
# Stabile IDs / Dateinamen
# ------------------------------------------------------------

def stable_id(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def build_title_from_article(soup, fallback="Tagesdosis"):
    # Versuche <title> oder og:title
    title_tag = soup.find("title")
    if title_tag and title_tag.text.strip():
        return title_tag.text.strip()

    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()

    return fallback

# ------------------------------------------------------------
# Feed schreiben
# ------------------------------------------------------------

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

# ------------------------------------------------------------
# Hauptlogik
# ------------------------------------------------------------

def main():
    log("[apolut] Starte Tagesdosis-Feed-Generator")

    os.makedirs(MEDIA_DIR, exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    tag_html = fetch_page(TAG_URL)
    if not tag_html:
        log("[apolut] WARNUNG: Tag-Seite nicht erreichbar – alter Feed bleibt bestehen.")
        return

    article_links = get_article_links_from_tag(tag_html)
    if not article_links:
        log("[apolut] WARNUNG: Keine Artikel-Links gefunden – alter Feed bleibt bestehen.")
        return

    items = []
    for article_url in article_links:
        if len(items) >= MAX_EPISODES:
            break

        article_html = fetch_page(article_url)
        if not article_html:
            log(f"[article] Konnte Artikel nicht laden: {article_url}")
            continue

        soup = BeautifulSoup(article_html, "html.parser")
        title = build_title_from_article(soup)

        mp3s = extract_mp3_links_from_article(article_html)
        if not mp3s:
            log(f"[article] Keine MP3 in Artikel gefunden: {article_url}")
            continue

        # Pro Artikel nur die erste MP3
        mp3_url = mp3s[0]
        id_ = stable_id(article_url + mp3_url)

        items.append({
            "title": title,
            "article_url": article_url,
            "mp3_url": mp3_url,
            "id": id_,
        })

    if not items:
        log("[apolut] WARNUNG: Keine Episoden gefunden – alter Feed bleibt bestehen.")
        return

    write_feed(items)
    log("[apolut] Feed erfolgreich aktualisiert.")

# ------------------------------------------------------------
# Start
# ------------------------------------------------------------

if __name__ == "__main__":
    main()

