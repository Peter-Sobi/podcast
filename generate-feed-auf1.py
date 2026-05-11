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

RSS_URL = "https://auf1.tv/feed/"

def ensure_dirs():
    MEDIA.mkdir(exist_ok=True)

def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return name[:200]

def extract_rumble_url(html: str):
    """
    Sucht die eingebettete Rumble-URL in der AUF1-Seite.
    """
    match = re.search(r'https://rumble\.com/embed/[^\"]+', html)
    if match:
        return match.group(0)
    return None

def extract_mp4_from_rumble(html: str):
    """
    Extrahiert die echte MP4-URL aus der Rumble-Seite.
    """
    match = re.search(r'https://[^"]+\.mp4', html)
    if match:
        return match.group(0)
    return None

def download_and_convert(entry):
    title = sanitize_filename(entry.title)
    pub = datetime(*entry.published_parsed[:6])
    date_str = pub.strftime("%a_%d_%b_%Y")

    filename = f"{date_str}_{title}.mp3"
    filepath = MEDIA / filename

    print("Lade AUF1-Seite:", entry.link)
    page = requests.get(entry.link)
    if page.status_code != 200:
        print("Fehler beim Laden der Seite:", entry.link)
        return None

    rumble_url = extract_rumble_url(page.text)
    if not rumble_url:
        print("Keine Rumble-URL gefunden:", entry.link)
        return None

    print("Lade Rumble-Seite:", rumble_url)
    rumble_page = requests.get(rumble_url)
    if rumble_page.status_code != 200:
        print("Fehler beim Laden der Rumble-Seite:", rumble_url)
        return None

    mp4_url = extract_mp4_from_rumble(rumble_page.text)
    if not mp4_url:
        print("Keine MP4-URL gefunden:", rumble_url)
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

    print("Lade AUF1 RSS…")
    feed = feedparser.parse(RSS_URL)

    for entry in feed.entries[:10]:
        mp3 = download_and_convert(entry)
        if mp3:
            print("Gespeichert:", mp3)

    build_asset_list()
    print("Asset-Liste erzeugt:", ASSET_LIST)

if __name__ == "__main__":
    main()

