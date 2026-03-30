import feedparser
import requests
from bs4 import BeautifulSoup
import re

FEED_URL = "https://apolut.net/feed/"
OUTPUT_FILE = "apolitisch.xml"


def get_full_article_html(url):
    """Lädt den vollständigen HTML‑Artikel von Apolut."""
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.text


def extract_mp3_from_content(html):
    """Extrahiert die MP3‑URL aus dem vollständigen HTML‑Artikel."""
    soup = BeautifulSoup(html, "lxml")

    # Störende HTML‑Tags entfernen
    for tag in soup(["svg", "path", "script", "style", "div", "figure", "img", "audio"]):
        tag.decompose()

    # 1. Versuch: <audio src="...mp3">
    audio = soup.find("audio", src=True)
    if audio and audio["src"].endswith(".mp3"):
        return audio["src"]

    # 2. Versuch: <a href="...mp3">
    for a in soup.find_all("a", href=True):
        if a["href"].endswith(".mp3"):
            return a["href"]

    # 3. Fallback: Regex direkt auf dem HTML‑String
    match = re.search(r"https://apolut\.net/content/media/[^\s\"']+\.mp3", html)
    if match:
        return match.group(0)

    return None


def generate_feed():
    """Erzeugt die FRITZ!Box‑kompatible RSS‑XML."""
    feed = feedparser.parse(FEED_URL)

    items = []

    for entry in feed.entries[:10]:
        # Vollständigen Artikel laden
        try:
            html = get_full_article_html(entry.link)
        except Exception:
            continue

        mp3 = extract_mp3_from_content(html)
        if not mp3:
            continue

        items.append(f"""
<item>
<title>{entry.title}</title>
<link>{entry.link}</link>
<enclosure url="{mp3}" length="0" type="audio/mpeg"/>
<guid>{entry.id}</guid>
<pubDate>{entry.published}</pubDate>
</item>
""")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Apolut Podcast – Automatischer Feed</title>
<link>https://apolut.net/podcast/</link>
<description>Automatisch generierter Feed für FRITZ!Box</description>
<language>de-de</language>
{"".join(items)}
</channel>
</rss>
"""

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(xml)


if __name__ == "__main__":
    generate_feed()

