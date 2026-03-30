import feedparser
import requests
from bs4 import BeautifulSoup
import re

FEED_URL = "https://apolut.net/feed/"
OUTPUT_FILE = "apolitisch.xml"


def extract_mp3_from_content(html):
    # HTML robust parsen
    soup = BeautifulSoup(html, "lxml")

    # Problematische Tags entfernen (verhindert XML-Fehler)
    for tag in soup(["svg", "path", "script", "style"]):
        tag.decompose()

    # 1. Versuch: MP3-Link direkt in <a>-Tags finden
    for a in soup.find_all("a", href=True):
        if a["href"].endswith(".mp3"):
            return a["href"]

    # 2. Versuch: Regex-Fallback für Apolut-Pfade
    match = re.search(r"https://apolut\.net/content/media/.+?\.mp3", html)
    if match:
        return match.group(0)

    return None


def generate_feed():
    feed = feedparser.parse(FEED_URL)

    items = []
    for entry in feed.entries[:10]:
        # Vollständigen Artikelinhalt verwenden, nicht summary
        if hasattr(entry, "content") and entry.content:
            html = entry.content[0].value
        else:
            html = entry.summary

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
{''.join(items)}
  </channel>
</rss>
"""

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(xml)


if __name__ == "__main__":
    generate_feed()
