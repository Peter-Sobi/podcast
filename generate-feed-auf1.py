#!/usr/bin/env python3
import os
import re
import json
import requests
import feedparser
from pathlib import Path
from datetime import datetime
import subprocess
from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent
MEDIA = BASE / "media_auf1"
ASSET_LIST = BASE / "auf1_assets.txt"

RSS_URL = "https://auf1.tv/feed/"

def ensure_dirs():
    MEDIA.mkdir(exist_ok=True)

def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return name[:200]

def get_mp4_url_with_playwright(url: str):
    """
    Lädt die AUF1-Seite wie ein echter Browser und extrahiert die MP4-URL.
    """
    print("Playwright lädt Seite:", url)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto(url, timeout=60000)
            page.wait_for_load_state("networkidle")

            # Auf <video> oder <source> warten
            video = page.query_selector("video source, video, source")
            if not video:
                print("Kein Video-Element gefunden:", url)
                browser.close()
                return None

            src = video.get_attribute("src")
            browser.close()

            if src and src.endswith(".mp4"):
                return src

            print("Gefundenes Video hat keine MP4-URL:", src)
            return None

        except Exception as e:
            print("Playwright Fehler:", e)
            browser.close()
            return None

def download_and_convert(entry):
    title = sanitize_filename(entry.title)
    pub = datetime(*entry.published_parsed[:6])
    date_str = pub.strftime("%a_%d_%b_%Y")

    filename = f"{date_str}_{title}.mp3"
    filepath = MEDIA / filename

    # MP4-URL über Playwright extrahieren
    video_url = get_mp4_url_with_playwright(entry.link)
    if not video_url:
        print("Keine MP4-URL gefunden:", entry.link)
        return None

    mp4_path = MEDIA / (filename + ".mp4")

    print("Lade Video:", video_url)
    r = requests.get(video_url, stream=True)
    if r.status_code != 200:
        print("Fehler beim Download:", video_url)
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

