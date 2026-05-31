#!/usr/bin/env python3
import feedparser
import requests
import subprocess
from pathlib import Path
from datetime import datetime
import re
import json

# ---------------------------------------------------------
# AUF1 FEEDS – ALLE FUNKTIONIERENDEN KANÄLE
# ---------------------------------------------------------
RSS_FEEDS = [
    "https://auf1.tv/feed/podcast/auf1-nachrichten/",
    "https://auf1.tv/feed/podcast/auf1-magazin/",
    "https://auf1.tv/feed/podcast/auf1-interview/",
    "https://auf1.tv/feed/podcast/auf1-spezial/",
    "https://auf1.tv/feed/podcast/auf1-doku/",
    "https://auf1.tv/feed/podcast/auf1-gesund/",
    "https://auf1.tv/feed/podcast/elsa-auf1/",
]

BASE = Path(__file__).resolve().parent
MEDIA = BASE / "media_auf1"
ASSET_LIST = BASE / "auf1_assets.txt"
URL_FILE = BASE / "release_urls.txt"
OUT_FEED = BASE / "feed_auf1.xml"


# ---------------------------------------------------------
# HILFSFUNKTIONEN
# ---------------------------------------------------------
def ensure_dirs():
    MEDIA.mkdir(exist_ok=True)


def sanitize_title(title: str) -> str:
    title = title.strip()
    title = title.replace(" ", "_")
    title = re.sub(r"[^0-9A-Za-zÄÖÜäöüß_]+", "", title)
    title = re.sub(r"_+", "_", title)
    return title.strip("_")


def download(url, path):
    print("Lade:", url)
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)


def convert(src, dst):
    print("Konvertiere:", dst.name)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-b:a", "32k", "-ac", "1", str(dst)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True
    )


# ---------------------------------------------------------
# AUDIO-URL AUS EPISODENSEITE EXTRAHIEREN
# ---------------------------------------------------------
def extract_audio_from_page(url):
    print("Lade Episodenseite:", url)
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    html = r.text

    # JSON-Block finden
    m = re.search(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None

    try:
        data = json.loads(m.group(1))
    except:
        return None

    # mögliche Felder
    for key in ("file", "src", "audio", "url"):
        if key in data and isinstance(data[key], str) and data[key].startswith("http"):
            return data[key]

    return None


# ---------------------------------------------------------
# ALLE EPISODEN SAMMELN
# ---------------------------------------------------------
def collect_all_entries():
    all_entries = []

    for url in RSS_FEEDS:
        print("Lade Feed:", url)
        feed = feedparser.parse(url)

        for entry in feed.entries:
            page_url = entry.link
            audio_url = extract_audio_from_page(page_url)
            if not audio_url:
                print("WARNUNG: Keine Audio-URL gefunden:", entry.title)
                continue

            pub = datetime(*entry.published_parsed[:6])
            all_entries.append((pub, entry, audio_url))

    all_entries.sort(key=lambda x: x[0], reverse=True)
    return all_entries[:20]


# ---------------------------------------------------------
# DOWNLOAD + KONVERTIERUNG
# ---------------------------------------------------------
def process_episodes():
    print("== AUF1: Lade & konvertiere Episoden ==")
    ensure_dirs()

    entries = collect_all_entries()

    with open(ASSET_LIST, "w", encoding="utf-8") as out:
        for pub, entry, audio_url in entries:
            date_str = pub.strftime("%d.%m.%Y")
            title_clean = sanitize_title(entry.title)
            filename = f"{title_clean}_{date_str}.mp3"

            original = MEDIA / ("orig_" + filename)
            converted = MEDIA / filename

            download(audio_url, original)
            convert(original, converted)

            size = converted.stat().st_size
            out.write(f"media_auf1/{converted.name}|{size}\n")

    print("Fertig: auf1_assets.txt erzeugt.")


# ---------------------------------------------------------
# FEED BAUEN
# ---------------------------------------------------------
def build_feed():
    if not URL_FILE.exists():
        print("release_urls.txt fehlt – Feed wird später gebaut.")
        return

    print("== AUF1: Baue finalen Feed ==")

    items = []

    with URL_FILE.open(encoding="utf-8") as f:
        for line in f:
            name, url = line.strip().split("|")

            stem = name[:-4] if name.endswith(".mp3") else name

            try:
                title_part, date_part = stem.rsplit("_", 1)
            except ValueError:
                title_part = stem
                date_part = datetime.utcnow().strftime("%d.%m.%Y")

            title_clean = title_part.replace("_", " ")

            try:
                dt = datetime.strptime(date_part, "%d.%m.%Y")
            except ValueError:
                dt = datetime.utcnow()

            pub_rfc822 = dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
            final_title = f"{title_clean} – {date_part}"

            items.append(f"""
            <item>
                <title>{final_title}</title>
                <enclosure url="{url}" type="audio/mpeg" />
                <pubDate>{pub_rfc822}</pubDate>
            </item>
            """)

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>AUF1 – Alle Formate (32kbps)</title>
    <link>https://auf1.tv</link>
    <description>Automatisch komprimierte AUF1-Version für FRITZ!Box – alle Kanäle kombiniert</description>
    {''.join(items)}
  </channel>
</rss>
"""

    OUT_FEED.write_text(rss, encoding="utf-8")
    print("Feed erzeugt:", OUT_FEED)


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
if __name__ == "__main__":
    process_episodes()
    build_feed()
