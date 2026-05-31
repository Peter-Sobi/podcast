#!/usr/bin/env python3
import feedparser
import requests
import subprocess
from pathlib import Path
from datetime import datetime
import os
import re

# ---------------------------------------------------------
# KONFIGURATION
# ---------------------------------------------------------
# Hier den AUF1-Apple-Podcast-RSS eintragen (direkte RSS-URL, nicht die HTML-Seite)
RSS_URL = "HIER_DEIN_APPLE_RSS_LINK"

BASE = Path(__file__).resolve().parent
MEDIA = BASE / "media_auf1"
ASSET_LIST = BASE / "auf1_assets.txt"
RELEASE_URLS = BASE / "release_urls.txt"
OUT_FEED = BASE / "feed_auf1.xml"


# ---------------------------------------------------------
# HILFSFUNKTIONEN
# ---------------------------------------------------------
def ensure_dirs():
    MEDIA.mkdir(exist_ok=True)


def download_file(url: str, path: Path):
    print("Lade:", url)
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)


def convert_to_32kbps(src: Path, dst: Path):
    print("Konvertiere:", dst.name)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-b:a",
            "32k",
            "-ac",
            "1",
            str(dst),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def sanitize_title_for_filename(title: str) -> str:
    # Leerzeichen zu Unterstrichen, Sonderzeichen raus
    title = title.strip()
    title = title.replace(" ", "_")
    title = re.sub(r"[^0-9A-Za-zÄÖÜäöüß_]+", "", title)
    title = re.sub(r"_+", "_", title)
    return title.strip("_")


# ---------------------------------------------------------
# SCHRITT 1: RSS LADEN, 20 NEUESTE MP3 LADEN, KONVERTIEREN
# ---------------------------------------------------------
def process_episodes():
    ensure_dirs()
    print("Lade RSS:", RSS_URL)
    feed = feedparser.parse(RSS_URL)

    entries = feed.entries[:20]  # immer die 20 neuesten Streams

    with open(ASSET_LIST, "w", encoding="utf-8") as out:
        for entry in entries:
            # Datum aus dem RSS
            pub = datetime(*entry.published_parsed[:6])
            date_str = pub.strftime("%d.%m.%Y")

            # Titel aus dem RSS
            title_raw = entry.title
            base_title = sanitize_title_for_filename(title_raw)

            # Dateiname im gewünschten Format:
            # Nachrichten_AUF1_31.05.2026.mp3
            filename = f"{base_title}_{date_str}.mp3"
            original = MEDIA / ("orig_" + filename)
            converted = MEDIA / filename

            audio_url = entry.enclosures[0].href

            download_file(audio_url, original)
            convert_to_32kbps(original, converted)

            size = converted.stat().st_size
            out.write(f"media_auf1/{converted.name}|{size}\n")

    print("Asset-Liste erzeugt:", ASSET_LIST)


# ---------------------------------------------------------
# SCHRITT 2: FINALEN FEED AUS RELEASE-URLS BAUEN
# ---------------------------------------------------------
def build_feed():
    items = []

    with open(RELEASE_URLS, encoding="utf-8") as f:
        for line in f:
            name, url = line.strip().split("|")

            # name z.B.: Nachrichten_AUF1_31.05.2026.mp3
            if name.lower().endswith(".mp3"):
                stem = name[:-4]
            else:
                stem = name

            # Titel und Datum aus dem Dateinamen holen
            # Nachrichten_AUF1_31.05.2026
            try:
                title_part, date_part = stem.rsplit("_", 1)
            except ValueError:
                # Fallback, falls Format unerwartet ist
                title_part = stem
                date_part = datetime.utcnow().strftime("%d.%m.%Y")

            title_clean = title_part.replace("_", " ").strip()

            # pubDate aus dem Datum im Dateinamen
            try:
                dt = datetime.strptime(date_part, "%d.%m.%Y")
            except ValueError:
                dt = datetime.utcnow()

            pub_rfc822 = dt.strftime("%a, %d %b %Y %H:%M:%S GMT")

            # Titel im Feed: Thema vorne, Datum hinten
            final_title = f"{title_clean} – {date_part}"

            item = f"""
            <item>
                <title>{final_title}</title>
                <enclosure url="{url}" type="audio/mpeg" />
                <pubDate>{pub_rfc822}</pubDate>
            </item>
            """
            items.append(item)

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>AUF1 Podcast – 32kbps Version</title>
        <link>https://auf1.tv</link>
        <description>Automatisch komprimierte AUF1-Version für FRITZ!Box (20 neueste Streams)</description>
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
    # 1) MP3s holen + konvertieren + auf1_assets.txt schreiben
    process_episodes()
    # 2) Nach dem GitHub-Release-Schritt: release_urls.txt einlesen und Feed bauen
    build_feed()

