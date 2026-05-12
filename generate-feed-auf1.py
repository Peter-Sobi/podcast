#!/usr/bin/env python3
import os
import re
import feedparser
from pathlib import Path
from datetime import datetime
from gtts import gTTS
from bs4 import BeautifulSoup
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.text_rank import TextRankSummarizer

BASE = Path(__file__).resolve().parent
MEDIA = BASE / "media_auf1"
ASSET_LIST = BASE / "auf1_assets.txt"

AUF1_RSS = "https://auf1.tv/feed/"

def ensure_dirs():
    MEDIA.mkdir(exist_ok=True)

def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return name[:200]

def generate_summary(title: str, link: str):
    text = f"""
    Dies ist eine automatisch generierte Zusammenfassung des AUF1-Artikels:
    Titel: {title}
    Link: {link}

    Der Artikel behandelt ein aktuelles Thema aus Politik, Gesellschaft oder Gesundheit.
    Die Inhalte wurden von AUF1 veröffentlicht und sind über den obigen Link abrufbar.
    """

    parser = PlaintextParser.from_string(text, Tokenizer("german"))
    summarizer = TextRankSummarizer()
    summary_sentences = summarizer(parser.document, 3)

    summary = " ".join(str(s) for s in summary_sentences)
    return summary

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

    summary = generate_summary(entry.title, entry.link)
    text_to_mp3(summary, filepath)

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

