import feedparser
import requests
import re
from bs4 import BeautifulSoup

FEED_URL = "https://apolut.net/feed/"
OUTPUT_FILE = "apolitisch.xml"


def get_mp3_from_api(article_url):
    """Extrahiert die MP3‑URL über die WordPress‑API anhand des Artikel‑Slugs."""
    # Slug aus der URL extrahieren
    slug = article_url.rstrip("/").split("/")[-1]

    api_url = f"https://apolut.net/wp-json/wp/v2/posts?slug={slug}"

    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data:
            return None

        post = data[0]

        # MP3 in ACF-Feldern suchen
        acf = post.get("acf", {})

        if "audio_file" in acf and acf["audio_file"]:
            return acf["audio_file"]

        if "podcast_file" in acf and acf["podcast_file"]:
            return acf["podcast_file"]

    except Exception:
        return None

    return None


def generate_feed():
    feed = feedparser.parse(FEED_URL)
    items = []

    for entry in feed.entries[:10]:
        mp3 = get_mp3_from_api(entry.link)
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

