#!/usr/bin/env python3
import feedparser
import requests
import subprocess
from pathlib import Path
import os
from datetime import datetime

# ---------------------------------------------------------
# KONFIGURATION
# ---------------------------------------------------------
RSS_URL = "HIER_DEIN_APPLE_RSS_LINK"
BASE = Path(__file__).resolve().parent
MEDIA = BASE / "media_apple"
ASSET_LIST = BASE / "apple_assets.txt"
RELEASE_URLS = BASE / "release_urls.txt"
OUT_FEED = BASE / "feed_apple.xml"

# ---------------------------------------------------------
# HILFSFUNKTIONEN
# ---------------------------------------------------------
def ensure_dirs():
    MEDIA.mkdir(exist_ok=True)

def download_file(url, path):
    print("Lade:", url)
    r = requests.get(url, timeout=60)
    with open(path, "wb") as f:
        f.write(r.content)

def convert_to_32kbps(src, dst):
    print("Konvertiere:", dst.name)
    subprocess.run([
        "ffmpeg", "-y", "-i", str(src),
        "-b:a", "32k", "-ac", "1",
        str(dst)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ---------------------------------------------------------
# SCHRITT 1: RSS LADEN, MP3 LADEN, KONVERTIEREN
# ---------------------------------------------------------
def process_episodes():
    ensure_dirs()
    feed = feedparser.parse(RSS_URL)

    with open(ASSET_LIST, "w") as out:
        for entry in feed.entries[:20]:
            audio_url = entry.enclosures[0].href
            filename = os.path.basename(audio_url)
            original = MEDIA / filename
            converted = MEDIA / (Path(filename).stem + "_32kbps.mp3")

            download_file(audio_url, original)
            convert_to_32kbps(original, converted)

            size = converted.stat().st_size
            out.write(f"media_apple/{converted.name}|{size}\n")

    print("Asset-Liste erzeugt:", ASSET_LIST)

# ---------------------------------------------------------
# SCHRITT 2: FINALEN FEED BAUEN
# ---------------------------------------------------------
def build_feed():
    items = []

    with open(RELEASE_URLS) as f:
        for line in f:
            name, url = line.strip().split("|")
            pub = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

            item = f"""
            <item>
                <title>{name}</title>
                <enclosure url="{url}" type="audio/mpeg"/>
                <pubDate>{pub}</pubDate>
            </item>
            """
            items.append(item)

    rss = f"""
    <rss version="2.0">
      <channel>
        <title>Apple Podcast – 32kbps Version</title>
        <link>https://github.com</link>
        <description>Automatisch komprimierte Version</description>
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

