import feedparser
import re

FEED_URL = "https://apolut.net/feed/"
OUTPUT_FILE = "apolitisch.xml"

# Regex sucht MP3-URL in JSON-Blöcken im RSS-Feed
MP3_REGEX = re.compile(r"https://apolut\.net/content/media/[^\s\"']+\.mp3")


def extract_mp3_from_feed_content(entry):
    """Extrahiert die MP3-URL direkt aus dem RSS-Feed-Content."""
    html = ""

    # Vollständigen Content bevorzugen
    if hasattr(entry, "content") and entry.content:
        html = entry.content[0].value
    else:
        html = entry.summary

    match = MP3_REGEX.search(html)
    if match:
        return match.group(0)

    return None


def generate_feed():
    feed = feedparser.parse(FEED_URL)
    items = []

    for entry in feed.entries[:10]:
        mp3 = extract_mp3_from_feed_content(entry)
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

