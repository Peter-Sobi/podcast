#!/usr/bin/env python3
import re
import requests
import feedparser
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
from gtts import gTTS

BASE = Path(__file__).resolve().parent
MEDIA = BASE / "media_auf1"
ASSET_LIST = BASE / "auf1_assets.txt"

AUF1_RSS = "https://auf1.tv/feed/"

def ensure_dirs():
    MEDIA.mkdir(exist_ok=True)

def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return name[:200]

def extract_slug(url: str):
    slug = url.rstrip("/").split("/")[-1]
    return slug if slug else None

def fetch_post_json(slug: str):
    api_url = f"https://auf1.tv/wp-json/wp/v2/posts?slug={slug}"
    print("Suche JSON:", api_url)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Referer": "https://auf1.tv/"
    }

    r = requests.get(api_url, headers=headers)
    if r.status_code != 200:
        print(f"Fehler beim JSON-Request ({r.status_code}):", api_url)
        return None

    data = r.json()
    return data[0] if data else None

def extract_text_from_json(json_data):
    if not json_data or "content" not in json_data:
        return None
    html = json_data["content"]["rendered"]
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)
    return text if text else None

def text_to_mp3(text: str, filepath: Path):
    print("Erzeuge MP3:", filepath.name)
    tts = gTTS(text=text, lang="de")
    tts.save(str(filepath))

def download_and_convert(entry):
    title = sanitize_filename(entry.title)
    pub = datetime(*entry.published_parsed[:6])
    date_str = pub.strftime("%a_%d_%b_%Y")

    filename = f"{date_str}_{title}.mp3"
    filepath = MEDIA / filename

    slug = extract_slug(entry.link)
    if not slug:
        print("Kein Slug gefunden:", entry.link)
        return None

    json_data = fetch_post_json(slug)
    article_text = extract_text_from_json(json_data)

    if not article_text:
        print("Kein Text im JSON gefunden:", entry.link)
        return None

    text_to_mp3(article_text, filepath)
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

    for entry in feed.entries[:20]:
        mp3 = download_and_convert(entry)
        if mp3:
            print("Gespeichert:", mp3)

    build_asset_list()
    print("Asset-Liste erzeugt:", ASSET_LIST)

if __name__ == "__main__":
    main()

