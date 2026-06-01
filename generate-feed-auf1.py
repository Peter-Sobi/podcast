#!/usr/bin/env python3
# generate-feed-auf1.py
# AUF1 -> API get/<slug> -> audiofile -> download -> reencode 32k mono -> media_auf1 -> feed_auf1.xml
# Features: retries, backoff, size checks, logging, max items

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import re
import os
import html
from datetime import datetime
from urllib.parse import quote, urlparse
import sys
import time
import subprocess
import logging

# -------------------------
# Configuration
# -------------------------
FEED_URL = "https://auf1.radio/api/feed"
MEDIA_DIR = "media_auf1"
OUTPUT_FEED = "feed_auf1.xml"
BASE_URL = "https://peter-sobi.github.io/podcast/media_auf1/"
API_GET = "https://auf1.radio/api/get/"

USER_AGENT = "github-actions/auf1-feed-generator (+https://github.com/peter-sobi/podcast)"
REQUEST_TIMEOUT = 12
MAX_ITEMS = 20
MIN_SIZE_BYTES = 30 * 1024           # 30 KB minimal
MAX_SIZE_BYTES = 6 * 1024 * 1024     # 6 MB acceptable before reencode
REENCODE_BITRATE = "32k"
LOG_FILE = "logs/auf1.log"
RETRY_TOTAL = 3
RETRY_BACKOFF = 0.5

# Ensure directories
os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# -------------------------
# Logging
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("auf1")

# -------------------------
# HTTP session with retries
# -------------------------
def requests_session_with_retries(retries=RETRY_TOTAL, backoff=RETRY_BACKOFF, status_forcelist=(500,502,503,504)):
    s = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": USER_AGENT})
    return s

session = requests_session_with_retries()

# -------------------------
# Helpers
# -------------------------
def sanitize_filename(name):
    name = name.strip()
    name = name.replace(" ", "_")
    name = re.sub(r"[^A-Za-z0-9_\-äöüÄÖÜß\.]", "", name)
    return name[:120]

def slug_from_link(link):
    try:
        p = urlparse(link)
        path = p.path.rstrip("/")
        if not path:
            return None
        slug = path.split("/")[-1]
        return slug
    except Exception:
        return None

def reencode_to_32k(src_path, dst_path):
    cmd = [
        "ffmpeg", "-y", "-i", src_path,
        "-ac", "1", "-b:a", REENCODE_BITRATE,
        "-af", "loudnorm",
        dst_path
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        logger.warning("ffmpeg Fehler: %s", e)
        return False

def get_audio_url_from_api(slug):
    if not slug:
        return None
    api_url = API_GET + slug
    try:
        logger.info("API Anfrage: %s", api_url)
        r = session.get(api_url, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            logger.warning("API %s returned %s", api_url, r.status_code)
            return None
        data = r.json()
        audiofile = data.get("audiofile") or data.get("audio") or data.get("file")
        if not audiofile:
            logger.warning("Kein 'audiofile' in API-Antwort: %s", api_url)
            return None
        if audiofile.startswith("http://") or audiofile.startswith("https://"):
            return audiofile
        return f"https://auf1.radio/storage/{audiofile}"
    except Exception as e:
        logger.warning("Fehler beim API-Abruf %s: %s", api_url, e)
        return None

def download_stream(url, tmp_path):
    try:
        logger.info("Lade herunter: %s", url)
        with session.get(url, timeout=REQUEST_TIMEOUT, stream=True) as r:
            if r.status_code != 200:
                logger.warning("Download fehlgeschlagen: %s %s", r.status_code, url)
                return False
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return True
    except Exception as e:
        logger.warning("Fehler beim Herunterladen %s: %s", url, e)
        return False

def download_file(url, title):
    filename = sanitize_filename(title) + ".mp3"
    filepath = os.path.join(MEDIA_DIR, filename)
    tmp = filepath + ".part"

    # Download
    ok = download_stream(url, tmp)
    if not ok:
        if os.path.exists(tmp):
            os.remove(tmp)
        return None

    # Size check
    try:
        size = os.path.getsize(tmp)
    except Exception as e:
        logger.warning("Fehler beim Lesen der Dateigröße: %s", e)
        if os.path.exists(tmp):
            os.remove(tmp)
        return None

    if size < MIN_SIZE_BYTES:
        logger.warning("Datei zu klein (%d bytes), verwerfe: %s", size, filename)
        os.remove(tmp)
        return None

    # If too large, reencode; otherwise reencode anyway to guarantee bitrate/mono
    reencoded = filepath + ".re.mp3"
    need_reencode = size > MAX_SIZE_BYTES or True  # always reencode to ensure consistent bitrate
    if need_reencode:
        logger.info("Reencode auf %s: %s (Größe %d)", REENCODE_BITRATE, filename, size)
        ok = reencode_to_32k(tmp, reencoded)
        os.remove(tmp)
        if not ok:
            logger.warning("Reencode fehlgeschlagen, verwerfe: %s", filename)
            if os.path.exists(reencoded):
                os.remove(reencoded)
            return None
        os.replace(reencoded, filepath)
    else:
        os.replace(tmp, filepath)

    final_size = os.path.getsize(filepath)
    logger.info("Gespeichert: %s (Größe: %d bytes)", filename, final_size)
    return filename

# -------------------------
# Feed builder
# -------------------------
def build_feed(entries):
    items_xml = ""
    for title, filename, pubdate in entries:
        url = BASE_URL + quote(filename)
        pd = pubdate or datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        items_xml += f"""
        <item>
            <title>{html.escape(title)}</title>
            <link>{url}</link>
            <enclosure url="{url}" type="audio/mpeg" />
            <pubDate>{pd}</pubDate>
        </item>
        """

    feed_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
    <title>AUF1 Radio (32kbps)</title>
    <link>https://peter-sobi.github.io/podcast/</link>
    <description>Automatisch generierter AUF1 Radio Feed</description>
    {items_xml}
</channel>
</rss>
"""
    with open(OUTPUT_FEED, "w", encoding="utf-8") as f:
        f.write(feed_xml)
    logger.info("Feed erzeugt: %s", OUTPUT_FEED)

# -------------------------
# Main
# -------------------------
def main():
    logger.info("Lade RSS-Feed… %s", FEED_URL)
    try:
        feed = feedparser.parse(FEED_URL)
    except Exception as e:
        logger.error("Feedparser Fehler: %s", e)
        sys.exit(1)

    if not hasattr(feed, "entries") or len(feed.entries) == 0:
        logger.error("Feed enthält keine Einträge.")
        sys.exit(1)

    processed = []
    for entry in feed.entries:
        title = getattr(entry, "title", "AUF1 Beitrag")
        link = getattr(entry, "link", None)
        pubdate = getattr(entry, "published", None) or getattr(entry, "updated", None)

        logger.info("Verarbeite: %s", title)
        slug = slug_from_link(link)
        if not slug:
            logger.warning("Keine slug aus Link extrahierbar: %s", link)
            continue

        audio_url = get_audio_url_from_api(slug)
        if not audio_url:
            logger.warning("Keine Audio-URL gefunden für slug: %s", slug)
            continue

        # Try download with a few attempts (session already has retries)
        filename = download_file(audio_url, title)
        if filename:
            processed.append((title, filename, pubdate))
        else:
            logger.warning("Download/Reencode fehlgeschlagen für: %s", title)

        if len(processed) >= MAX_ITEMS:
            break

        time.sleep(0.5)

    if not processed:
        logger.error("Keine Dateien heruntergeladen. Feed wird nicht erzeugt.")
        sys.exit(2)

    build_feed(processed)
    logger.info("Fertig. %d Dateien verarbeitet.", len(processed))

if __name__ == "__main__":
    main()
