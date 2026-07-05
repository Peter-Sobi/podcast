#!/usr/bin/env python3
import os
import sys
import re
import json
import requests
import datetime
from bs4 import BeautifulSoup

MEDIA_DIR = "auf1_media"
FEED_FILE = "auf1_feed.xml"
BASE_URL = "https://auf1.tv"

def log(msg):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")

def sanitize_filename(name):
    bad = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for b in bad:
        name = name.replace(b, "")
    return name.replace(" ", "_")

def extract_date(date_str):
    m = re.search(r"(20\d{2})[-]?(0\d|1[0-2])[-]?(0\d|[12]\d|3[01])", date_str)
    if not m:
        return None
    year, month, day = m.group(1), m.group(2), m.group(3)
    return f"{day}.{month}"

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
    log("[feed] Erzeuge neuen AUF1 Video-RSS-Feed")

    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        '<channel>',
        '<title>AUF1 Video Podcast – Vollständiger Feed</title>',
        '<link>https://auf1.tv</link>',
        '<description>Automatisch generierter Video-Feed</description>'
    ]

    for item in items:
        xml.append("<item>")
        xml.append(f"<title>{item['feed_title']}</title>")
        xml.append(f"<link>{item['url']}</link>")
        xml.append(f"<enclosure url=\"{item['url']}\" type=\"video/mp4\"/>")
        xml.append("</item>")

    xml.append("</channel>")
    xml.append("</rss>")

    with open(FEED_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(xml))

    log(f"[feed] Feed gespeichert: {FEED_FILE}")

def fallback_from_existing_files():
    log("[fallback] Erzeuge Feed aus vorhandenen Dateien")

    items = []
    for filename in os.listdir(MEDIA_DIR):
        if filename.endswith(".mp4"):
            parts = filename.split("_", 1)

            if len(parts) == 2 and "." in parts[0]:
                date_prefix = parts[0]
                title = parts[1].replace(".mp4", "").replace("_", " ")
                feed_title = f"{date_prefix} – {title}"
                sort_key = date_to_sort_key(date_prefix)
            else:
                feed_title = filename.replace(".mp4", "")
                sort_key = 0

            items.append({
                "feed_title": feed_title,
                "url": f"https://raw.githubusercontent.com/Peter-Sobi/podcast/main/{MEDIA_DIR}/{filename}",
                "sort_key": sort_key
            })

    items.sort(key=lambda x: x["sort_key"], reverse=True)
    generate_feed(items)

def scrape_auf1_videos():
    log("[html] Lade AUF1 Startseite")
    try:
        r = requests.get(BASE_URL, timeout=20)
        r.raise_for_status()
    except Exception as e:
        log(f"[error] AUF1 HTML konnte nicht geladen werden: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    script = soup.find("script", string=lambda s: s and "window.__NUXT__" in s)
    if not script:
        log("[error] Kein window.__NUXT__ gefunden – Fallback wird verwendet.")
        return None

    try:
        json_text = script.string.split("window.__NUXT__=")[1].strip()
        if json_text.endswith(";"):
            json_text = json_text[:-1]
        data = json.loads(json_text)
    except Exception as e:
        log(f"[error] Konnte NUXT JSON nicht parsen: {e}")
        return None

    try:
        posts = data["state"]["posts"]["items"]
    except:
        log("[error] Konnte Video-Items nicht finden – Fallback wird verwendet.")
        return None

    items = []

    for post in posts:
        title = post.get("title", "Unbekannt")
        date_raw = post.get("date", "")
        date_prefix = extract_date(date_raw)
        sort_key = date_to_sort_key(date_prefix)

        # Video-URL suchen
        video_url = None

        if "videoUrl" in post:
            video_url = post["videoUrl"]

        if not video_url and "video" in post and "url" in post["video"]:
            video_url = post["video"]["url"]

        if not video_url:
            continue

        if date_prefix:
            filename = f"{date_prefix}_{sanitize_filename(title)}.mp4"
            feed_title = f"{date_prefix} – {title}"
        else:
            filename = sanitize_filename(title) + ".mp4"
            feed_title = title

        filepath = os.path.join(MEDIA_DIR, filename)

        if not os.path.exists(filepath):
            download_file(video_url, filepath)
        else:
            log(f"[skip] Datei existiert bereits: {filename}")

        items.append({
            "feed_title": feed_title,
            "url": video_url,
            "file": filepath,
            "sort_key": sort_key
        })

    return items

def main():
    log("[auf1] Starte Video-Scraper")
    os.makedirs(MEDIA_DIR, exist_ok=True)

    items = scrape_auf1_videos()

    if not items:
        log("[auf1] Video-Scraper liefert keine Items – Fallback wird verwendet.")
        fallback_from_existing_files()
        return

    items.sort(key=lambda x: x["sort_key"], reverse=True)
    generate_feed(items)

    log(f"[auf1] Fertig. {len(items)} Videos verarbeitet.")

if __name__ == "__main__":
    main()

