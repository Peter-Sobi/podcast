import feedparser
import requests
import os
import html
from datetime import datetime, timezone
from email.utils import format_datetime

FEED_URL = "https://auf1.radio/feed"
MEDIA_DIR = "media_auf1"
OUTPUT_FEED = "feed_auf1.xml"
BASE_URL = "https://peter-sobi.github.io/podcast/media_auf1/"

# Browser-User-Agent setzen (AUF1 blockiert sonst!)
feedparser.USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs("logs", exist_ok=True)

def download(url, path):
    try:
        r = requests.get(url, stream=True, timeout=20, headers={
            "User-Agent": "Mozilla/5.0"
        })
        if r.status_code != 200:
            return False
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
        return True
    except:
        return False

def build_feed(items):
    xml = ""
    for title, fn in items:
        url = BASE_URL + fn
        length = os.path.getsize(os.path.join(MEDIA_DIR, fn))
        pub = format_datetime(datetime.now(timezone.utc))

        xml += f"""
        <item>
            <title>{html.escape(title)}</title>
            <link>{url}</link>
            <enclosure url="{url}" length="{length}" type="audio/mpeg" />
            <guid isPermaLink="false">{html.escape(url)}</guid>
            <pubDate>{pub}</pubDate>
        </item>
        """

    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>AUF1 Radio</title>
<link>https://peter-sobi.github.io/podcast/</link>
<description>Automatisch generierter AUF1 Radio Feed</description>
{xml}
</channel></rss>"""

    with open(OUTPUT_FEED, "w", encoding="utf-8") as f:
        f.write(feed)

def main():
    print("Loading feed…")
    feed = feedparser.parse(FEED_URL)

    if not feed.entries:
        print("ERROR: No entries (AUF1 blocked request)")
        return 1

    new_items = []

    for entry in feed.entries:
        title = entry.title
        url = entry.enclosures[0].href
        filename = url.split("/")[-1]
        filepath = os.path.join(MEDIA_DIR, filename)

        if os.path.exists(filepath):
            print("STOP: Found existing file →", filename)
            break

        print("Downloading NEW:", filename)
        if download(url, filepath):
            new_items.append((title, filename))
        else:
            print("Download failed:", url)

    if not new_items:
        print("No new items → nothing to update")
        return 0

    print("Building feed…")
    build_feed(new_items)
    print("Done.")
    return 0

if __name__ == "__main__":
    main()
