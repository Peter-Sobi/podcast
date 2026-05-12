#!/usr/bin/env python3
import os
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

def extract_article_text(url: str):
    print("Lade Artikel:", url)
    r = requests.get(url)
    if r.status_code != 200:
        print("Fehler beim Laden:", url)
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    # AUF1-Artikeltext steckt in <div class="content">
    content = soup.find("div", class_="content")
    if not content:
        print("Kein Artikeltext gefunden:", url)
        return None

    text = content.get_text(separator="\n", strip=True)
    return text

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

    article_text = extract_article_text(entry.link)
    if not article_text:
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

    # Nur die neuesten 20 Artikel
    for entry in feed.entries[:20]:
        mp3 = download_and_convert(entry)
        if mp3:
            print("Gespeichert:", mp3)

    build_asset_list()
    print("Asset-Liste erzeugt:", ASSET_LIST)

if __name__ == "__main__":
    main()

