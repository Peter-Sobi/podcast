import feedparser
import requests
import os
import logging
from datetime import datetime

logging.basicConfig(
    filename="logs/auf1.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)

FEED_URL = "https://auf1.radio/feed"
MEDIA_DIR = "media_auf1"

os.makedirs(MEDIA_DIR, exist_ok=True)

logging.info("Loading feed…")
feed = feedparser.parse(FEED_URL)

stop_loading = False
new_items = []

for entry in feed.entries:
    title = entry.title
    url = entry.enclosures[0].href
    filename = os.path.join(MEDIA_DIR, url.split("/")[-1])

    if os.path.exists(filename):
        logging.info(f"Stop: Found existing file → {filename}")
        stop_loading = True
        break

    logging.info(f"Downloading NEW: {filename}")
    new_items.append((url, filename))

# Download only the NEW items
for url, filename in new_items:
    r = requests.get(url, stream=True)
    with open(filename, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)

logging.info("Done.")
