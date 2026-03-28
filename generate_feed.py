import feedparser
import requests
from bs4 import BeautifulSoup

FEED_URL = "https://apolut.net/feed/"
OUTPUT_FILE = "apolitisch.xml"

def extract_mp3(article_url):
    r = requests.get(article_url, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")
    audio = soup.find("a", href=lambda x: x and x.endswith(".mp3"))
    return audio["href"] if audio else None

def generate_feed():
    feed = feedparser.parse(FEED_URL)

    items = []
    for entry in feed.entries[:10]:
        mp3 = extract_mp3(entry.link)
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
