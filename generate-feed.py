#!/usr/bin/env python3
import os
import sys
import re
import requests
import subprocess
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

def download_hls_to_mp3(m3u8_url, out_mp3):
    log(f"[hls] Lade Playlist: {m3u8_url}")

    try:
        # ffmpeg lädt HLS und encodiert direkt zu MP3 64 kbps
        cmd = [
            "ffmpeg",
            "-y",
            "-i", m3u8_url,
            "-vn",
            "-acodec", "libmp3lame",
            "-b:a", "64k",
            out_mp3
        ]
        subprocess.run(cmd, check=True)
        log(f"[hls] MP3 erzeugt: {out_mp3}")
        return True

    except Exception as e:
        log(f"[error] ffmpeg Fehler: {e}")
        return False

def generate_feed(items):
    log("[feed] Erzeuge neuen RSS-Feed")

    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        '<channel>',
        '<title>Apolut Podcast – MP3 Feed</title>',
        '<link>https://apolut.net</link>',
        '<description>Automatisch generierter MP3-Feed (HLS → MP3)</description>'
    ]

    for item in items:
        xml.append("<item>")
        xml.append(f"<title>{item['feed_title']}</title>")
        xml.append(f"<link>{item['mp3_url']}</link>")
        xml.append(f"<enclosure url=\"{item['mp3_url']}\" type=\"audio/mpeg\"/>")
        xml.append("</item>")

    xml.append("</channel>")
    xml.append("</rss>")

    with open(FEED_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(xml))

    log(f"[feed] Feed gespeichert: {FEED_FILE}")

def main():
    log("[apolut] Starte HLS→MP3 Feed-Generator")
    log(f"[rss] Lade RSS: {RSS_URL}")

    try:
        r = requests.get(RSS_URL, timeout=20)
        r.raise_for_status()
    except Exception as e:
        log(f"[error] RSS konnte nicht geladen werden: {e}")
        sys.exit(1)

    soup = BeautifulSoup(r.text, "lxml-xml")
    rss_items = soup.find_all("item")

    if not rss_items:
        log("[apolut] FEHLER: RSS enthält keine Items – Abbruch.")
        sys.exit(0)

    os.makedirs(MEDIA_DIR, exist_ok=True)

    downloaded_items = []
    new_files = 0

    for item in rss_items:
        title = item.find("title").text.strip()
        enclosure = item.find("enclosure")

        if not enclosure:
            continue

        url = enclosure.get("url")

        # Nur HLS-Streams akzeptieren
        if not url.endswith(".m3u8"):
            log(f"[skip] Keine HLS-Playlist: {url}")
            continue

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
            ok = download_hls_to_mp3(url, filepath)
            if not ok:
                log(f"[error] Konnte Episode nicht konvertieren: {title}")
                continue

        downloaded_items.append({
            "title": title,
            "feed_title": feed_title,
            "mp3_url": f"https://peter-sobi.github.io/podcast/media/{filename}",
            "file": filepath,
            "sort_key": sort_key
        })

    if not downloaded_items:
        log("[apolut] WARNUNG: Keine MP3-Episoden erzeugt – Abbruch.")
        sys.exit(0)

    downloaded_items.sort(key=lambda x: x["sort_key"], reverse=True)

    generate_feed(downloaded_items)

    log(f"[apolut] Fertig. {new_files} neue Episoden verarbeitet.")

if __name__ == "__main__":
    main()

