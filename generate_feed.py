import feedparser
import requests
import re
import urllib.parse

FEED_URL = "https://apolut.net/feed/"
OUTPUT_FILE = "apolitisch.xml"

PROXY = "https://thingproxy.freeboard.io/fetch/"


def proxied(url):
    return PROXY + url


def get_post_id_from_slug(slug):
    api_url = f"https://apolut.net/wp-json/wp/v2/posts?slug={slug}"
    proxied_url = proxied(api_url)

    try:
        response = requests.get(proxied_url, timeout=15)
        response.raise_for_status()
        data = response.json()

        if not data:
            return None

        return data[0]["id"]

    except Exception:
        return None


def get_mp3_from_player_data(post_id):
    url = f"https://apolut.net/wp-content/plugins/podcast-player/js/player-data.php?post={post_id}"
    proxied_url = proxied(url)

    try:
        response = requests.get(proxied_url, timeout=15)
        response.raise_for_status()
        data = response.json()

        if "audio" in data and data["audio"].endswith(".mp3"):
            return data["audio"]

    except Exception:
        return None

    return None


def generate_feed():
    feed = feedparser.parse(FEED_URL)
    items = []

    for entry in feed.entries[:10]:
        slug = entry.link.rstrip("/").split("/")[-1]

        post_id = get_post_id_from_slug(slug)
        if not post_id:
            continue

        mp3 = get_mp3_from_player_data(post_id)
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

