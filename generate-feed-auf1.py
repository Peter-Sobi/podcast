
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

AUF1_RSS = "https://auf1.tv/feed/"

def ensure_dirs():
    MEDIA.mkdir(exist_ok=True)

def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return name[:200]

def extract_rumble_embed(html: str):
    """
    Sucht Rumble-Embed-URL in AUF1-Seite.
    Beispiel:
    https://rumble.com/embed/vabcdef/?pub=xyz123
    """
    match = re.search(r'https://rumble\.com/embed/[^"]+', html)
    return match.group(0) if match else None

def extract_pub_id(embed_url: str):
    """
    Extrahiert pub=XXXX aus der Embed-URL.
    """
    match = re.search(r'pub=([A-Za-z0-9]+)', embed_url)
    return match.group(1) if match else None

def extract_video_id(embed_url: str):
    """
    Extrahiert die Video-ID aus der Embed-URL.
    Beispiel:
    https://rumble.com/embed/vabcdef/?pub=xyz123
    → vabcdef
    """
    match = re.search(r'/embed/([^/?]+)', embed_url)
    return match.group(1) if match else None

def get_mp4_from_rumble(video_id: str):
    """
    Holt die MP4-URL direkt aus der Rumble-Video-Seite.
    """
    url = f"https://rumble.com/{video_id}.html"
    print("Lade Rumble-Seite:", url)

    r = requests.get(url)
    if r.status_code != 200:
        print("Fehler beim Laden der Rumble-Seite:", url)
        return None

    match = re.search(r'https://[^"]+\.mp4', r.text)
    return match.group(0) if match else None

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

    embed = extract_rumble_embed(page.text)
    if not embed:
        print("Keine Rumble-Embed gefunden:", entry.link)
        return None

    video_id = extract_video_id(embed)
    if not video_id:
        print("Keine Video-ID gefunden:", embed)
        return None

    mp4_url = get_mp4_from_rumble(video_id)
    if not mp4_url:
        print("Keine MP4-URL gefunden:", video_id)
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
    feed = feedparser.parse(AUF1_RSS)

    # Nur die neuesten 20 Einträge
    for entry in feed.entries[:20]:
        mp3 = download_and_convert(entry)
        if mp3:
            print("Gespeichert:", mp3)

    build_asset_list()
    print("Asset-Liste erzeugt:", ASSET_LIST)

if __name__ == "__main__":
    main()
