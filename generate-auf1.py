#!/usr/bin/env python3
import os
import re
import sys
import logging
from datetime import datetime
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

RSS_URL_PRIMARY = "https://auf1.radio/api/feed"
RSS_URL_FALLBACK = "https://auf1.tv/feed/podcast/"
MEDIA_DIR = "auf1_media"
LOG_DIR = "logs"
FEED_FILE = "auf1_feed.xml"
BASE_MEDIA_URL = "https://peter-sobi.github.io/podcast/auf1_media/"

os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%Y-%m-%d %H:%M:%S] [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "auf1.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

log = logging.getLogger("auf1")


def sanitize_title(title: str) -> str:
    title = title.strip()
    title = title.replace(" ", "_")
    title = re.sub(r"[^\w\-_\.]", "_", title)
    return title


def format_dd_mm(dt: datetime) -> str:
    return dt.strftime("%d.%m")


def parse_pub_date(text: str) -> datetime:
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return datetime.utcnow()


def fetch_rss(url: str) -> BeautifulSoup | None:
    log.info("[auf1] Lade RSS-Feed: %s", url)
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "xml")
    except Exception as e:
        log.error("[rss] Fehler beim Laden von %s: %s", url, e)
        return None


def extract_items(soup: BeautifulSoup):
    items = []
    if soup is None:
        return items
    for item in soup.find_all("item"):
        title_tag = item.find("title")
        enclosure = item.find("enclosure")
        pub_tag = item.find("pubDate") or item.find("published") or item.find("dc:date")

        if not title_tag or not enclosure or not enclosure.get("url"):
            continue

        title = title_tag.text.strip()
        media_url = enclosure.get("url").strip()
        pub_raw = pub_tag.text.strip() if pub_tag else ""
        pub_dt = parse_pub_date(pub_raw) if pub_raw else datetime.utcnow()

        items.append(
            {
                "title": title,
                "media_url": media_url,
                "pub_dt": pub_dt,
            }
        )
    return items


def download_episode(item: dict):
    title = item["title"]
    media_url = item["media_url"]
    pub_dt = item["pub_dt"]

    date_prefix = format_dd_mm(pub_dt)
    safe_title = sanitize_title(title)
    filename = f"{date_prefix}_{safe_title}.mp3"
    path = os.path.join(MEDIA_DIR, filename)

    if os.path.exists(path):
        log.info("[download] Überspringe (bereits vorhanden): %s", path)
        return path, pub_dt

    log.info("[episode] Gefunden: %s", title)
    log.info("[download] Lade Datei: %s", media_url)

    try:
        with requests.get(media_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        log.info("[download] Fertig: %s", path)
        return path, pub_dt
    except Exception as e:
        log.error("[download] Fehler bei %s: %s", media_url, e)
        return None, pub_dt


def build_feed_from_files(files: list[tuple[str, datetime]]):
    log.info("[feed] Erzeuge neuen AUF1 RSS-Feed aus %d Dateien", len(files))

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "AUF1 – Radio (Inoffiziell)"
    ET.SubElement(channel, "link").text = "https://auf1.radio/"
    ET.SubElement(channel, "description").text = (
        "Inoffizieller AUF1-Radiofeed, generiert für persönliche Nutzung."
    )
    ET.SubElement(channel, "language").text = "de"

    for path, pub_dt in files:
        fname = os.path.basename(path)
        # Date prefix already in filename, but we also ensure title has dd.mm
        # Extract original title part after prefix
        parts = fname.rsplit(".mp3", 1)[0]
        # parts like "dd.mm_Sanitized_Title"
        try:
            _, title_part = parts.split("_", 1)
        except ValueError:
            title_part = parts
        title_clean = title_part.replace("_", " ")
        date_prefix = format_dd_mm(pub_dt)
        full_title = f"{date_prefix} {title_clean}"

        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = full_title
        ET.SubElement(item, "description").text = full_title
        ET.SubElement(item, "pubDate").text = pub_dt.strftime(
            "%a, %d %b %Y %H:%M:%S +0000"
        )

        media_url = BASE_MEDIA_URL + fname
        enclosure = ET.SubElement(item, "enclosure")
        enclosure.set("url", media_url)
        enclosure.set("type", "audio/mpeg")

        guid = ET.SubElement(item, "guid")
        guid.text = media_url
        guid.set("isPermaLink", "true")

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ", level=0)
    tree.write(FEED_FILE, encoding="utf-8", xml_declaration=True)
    log.info("[feed] Feed gespeichert: %s", FEED_FILE)


def main():
    log.info("[auf1] Starte AUF1-Feed-Generator")

    # 1. Versuche Primary-RSS (Radio-API)
    soup = fetch_rss(RSS_URL_PRIMARY)
    items = extract_items(soup)

    # 2. Wenn leer, versuche alten RSS
    if not items:
        log.info("[auf1] Primary-RSS leer – versuche Fallback-RSS: %s", RSS_URL_FALLBACK)
        soup_fb = fetch_rss(RSS_URL_FALLBACK)
        items = extract_items(soup_fb)

    # 3. Wenn immer noch leer: reiner Dateifallback
    if not items:
        log.warning(
            "[auf1] RSS enthält keine Items – Fallback wird verwendet (nur lokale Dateien)."
        )
        files = []
        for fname in sorted(os.listdir(MEDIA_DIR)):
            if not fname.lower().endswith(".mp3"):
                continue
            path = os.path.join(MEDIA_DIR, fname)
            mtime = datetime.utcfromtimestamp(os.path.getmtime(path))
            files.append((path, mtime))
        files.sort(key=lambda x: x[1], reverse=True)
        if not files:
            log.error("[fallback] Keine lokalen Dateien gefunden – Feed kann nicht erzeugt werden.")
            return
        build_feed_from_files(files)
        return

    # 4. Wir haben RSS-Items: herunterladen + Feed aus diesen Dateien bauen
    downloaded: list[tuple[str, datetime]] = []
    for item in items:
        path, pub_dt = download_episode(item)
        if path:
            downloaded.append((path, pub_dt))

    if not downloaded:
        log.error("[auf1] Keine Dateien heruntergeladen – verwende vorhandene Dateien im Fallback.")
        files = []
        for fname in sorted(os.listdir(MEDIA_DIR)):
            if not fname.lower().endswith(".mp3"):
                continue
            path = os.path.join(MEDIA_DIR, fname)
            mtime = datetime.utcfromtimestamp(os.path.getmtime(path))
            files.append((path, mtime))
        files.sort(key=lambda x: x[1], reverse=True)
        if not files:
            log.error("[fallback] Keine lokalen Dateien gefunden – Feed kann nicht erzeugt werden.")
            return
        build_feed_from_files(files)
        return

    # 5. Feed aus frisch heruntergeladenen Dateien
    downloaded.sort(key=lambda x: x[1], reverse=True)
    build_feed_from_files(downloaded)


if __name__ == "__main__":
    main()

