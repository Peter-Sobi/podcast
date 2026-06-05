#!/usr/bin/env python3
# AUF1 – lädt nur neue Episoden, stoppt sobald alte gefunden werden

import feedparser
import requests
import os
import logging

FEED_URL = "https://auf1.radio/feed"
MEDIA_DIR = "media_auf1"
LOG_DIR = "logs"

# Ordner sicherstellen
os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# Logging initialisieren
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "auf1.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)

logging.info("Loading feed…")

feed = feedparser.parse(FEED_URL)
entries = feed.entries

if not entries:
    logging.error("No entries in feed")
    exit(1)

new_items = []
stop = False

# Durch den Feed gehen – von oben nach unten
for entry in entries:
    try:
        title = entry.title
        enclosure = entry.enclosures[0]
        url = enclosure.href
    except Exception as e:
        logging.warning(f"Skipping entry due to missing data: {e}")
        continue

    filename = url.split("/")[-1]
    filepath = os.path.join(MEDIA_DIR, filename)

    # Wenn Datei existiert → STOP
    if os.path.exists(filepath):
        logging.info(f"STOP: Found existing file → {filename}")
        stop = True
        break

    logging.info(f"Downloading NEW: {filename}")
    new_items.append((url, filepath))

# Neue Dateien herunterladen
for url, filepath in new_items:
    try:
        r = requests.get(url, stream=True, timeout=20)
        if r.status_code != 200:
            logging.warning(f"Download failed ({r.status_code}): {url}")
            continue

        with open(filepath, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)

        logging.info(f"Saved: {filepath}")

    except Exception as e:
        logging.error(f"Error downloading {url}: {e}")

logging.info("Done.")
