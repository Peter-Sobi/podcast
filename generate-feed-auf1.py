#!/usr/bin/env python3
import os
import re
import requests
import feedparser
from pathlib import Path
from datetime import datetime
import subprocess

BASE = Path(__file__).resolve().parent
MEDIA = BASE / "media_auf1"
ASSET_LIST = BASE / "auf1_assets.txt"

# Alle AUF1 Rumble RSS Feeds
RUMBLE_FEEDS = [
    "https://rumble.com/rss.php?channel=AUF1TV",
    "https://rumble.com/rss.php?channel=ElsaAUF1",
    "https://rumble.com/rss.php?channel=GesundAUF1",
    "https://rumble.com/rss.php?channel=AUF1Spezial",
    "https://rumble.com/rss.php?channel=AUF1Doku"
]

def ensure_dirs():
    MEDIA.mkdir(exist_ok=True)

def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return name[:200]

def download_and_convert(entry):
    title = sanitize_filename(entry.title)
    pub = datetime(*entry.published_parsed[:6])
    date_str = pub.strftime("%a_%d_%b_%Y")

    filename = f"{date_str}_{title}.mp3"
    filepath = MEDIA / filename

    # MP4-URL direkt aus dem RSS
    if "enclosures" not in entry or not entry.enclosures:
        print("Keine MP4-URL im RSS gefunden:", entry.title)
        return None

    mp4_url = entry.enclosures[0].get("url")
    if not mp4_url:
        print("Keine MP4-URL im RSS gefunden:", entry.title)
        return None

    mp4_path = MEDIA / (filename + ".mp4")

    print("Lade Video:", mp4_url)
    r = requests.get(mp4_url, stream=True)
    if r.status_code != 200:
        print("Fehler beim Download:", mp4_url)
        return None

    with open(mp4_path, "wb") as f:
        for chunk in r.iter_content(1024 * 1024):
            f.write(chunk)

    print("Konvertiere nach MP3:", filename)
    subprocess.run([
        "ffmpeg", "-i", str(mp4_path),
        "-vn", "-acodec", "libmp3lame", "-b:a", "128k",
        str(filepath)
    ], check=True)

    mp4_path.unlink()
    return filepath

def build_asset_list():
    with open(ASSET_LIST, "w") as out:
        for file in MEDIA.iterdir():
            if file.suffix.lower() == ".mp3":
                size = file.stat().st_size
                out.write(f"media_auf1/{file.name}|{size}\n")

def main():
    ensure_dirs()

    print("Lade alle Rumble RSS Feeds…")

    entries = []

    # Alle Feeds laden
    for url in RUMBLE_FEEDS:
        print("Lade Feed:", url)
        feed = feedparser.parse(url)
        entries.extend(feed.entries)

    # Nach Datum sortieren (neueste zuerst)
    entries.sort(key=lambda e: e.published_parsed, reverse=True)

    # Nur die neuesten 20 Episoden
    for entry in entries[:20]:
        mp3 = download_and_convert(entry)
        if mp3:
            print("Gespeichert:", mp3)

    build_asset_list()
    print("Asset-Liste erzeugt:", ASSET_LIST)

if __name__ == "__main__":
    main()

