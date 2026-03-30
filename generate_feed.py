import feedparser
import requests
from bs4 import BeautifulSoup
import re

FEED_URL = "https://apolut.net/feed/"
OUTPUT_FILE = "apolitisch.xml"

def extract_mp3_from_content(html):
    soup = BeautifulSoup(html, "html.parser")
    # Suche nach .mp3 in allen Links
    for a in soup.find_all("a", href=True):
        if a["href"].endswith(".mp3"):
            return a["href"]

    # Falls nicht gefunden: Regex als Fallback
    match = re.search(r"https://apolut\.net/content/media/[\w/\-]+\.mp3", html)
    if match:
        return match.group(0)

    return None

def generate_feed():
    feed = feedparser.parse(FEED_URL)

    items = []
    for entry in feed.entries[:10]:
        mp3 = extract_mp3_from_content(entry.summary)
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
