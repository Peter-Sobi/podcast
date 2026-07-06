#!/usr/bin/env python3
import os
import re
import sys
import time
import logging
from datetime import datetime
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

RSS_URL = "https://apolut.net/feed/"
MEDIA_DIR = "media"                     # <<< geändert
LOG_DIR = "logs"
FEED_FILE = "feed.xml"                  # <<< geändert
MAX_EPISODES = 20
MAX_RETRIES = 5
CHUNK_SIZE = 1024 * 1024  # 1 MB pro Chunk
BASE_MEDIA_URL = "https://peter-sobi.github.io/podcast/media/"   # <<< geändert

os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%Y-%m-%d %H:%M:%S] [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "apolut.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

log = logging.getLogger("apolut")


def sanitize_title(title: str) -> str:
    title = title.strip()
    title = title.replace(" ", "_")
    title = re.sub(r"[^\w\-_\.]", "_", title)
    return title


def parse_pub_date(text: str) -> datetime:
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return datetime.utcnow()


def format_dd_mm(dt: datetime) -> str:
    return dt.strftime("%d.%m")


def fetch_rss(url: str) -> BeautifulSoup | None:
    log.info("[apolut] Lade RSS-Feed: %s", url)
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "xml")
    except Exception as e:
        log.error("[rss] Fehler beim Laden: %s", e)
        return None


def extract_items(soup: BeautifulSoup):
    items = []
    if soup is None:
        return items

    for item in soup.find_all("item"):
        title_tag = item.find("title")
        enclosure = item.find("enclosure")
        pub_tag = item.find("pubDate")

        if not title_tag or not enclosure or not enclosure.get("url"):
            continue

        title = title_tag.text.strip()
        media_url = enclosure.get("url").strip()
        pub_raw = pub_tag.text.strip() if pub_tag else ""
        pub_dt = parse_pub_date(pub_raw)

        items.append(
            {
                "title": title,
                "media_url": media_url,
                "pub_dt": pub_dt,
            }
        )

    return items


def robust_download(url: str, path: str) -> bool:
    """
    Robuster Apolut-Downloader:
    - prüft Content-Length
    - lädt in großen Blöcken
    - wiederholt bei Fehlern
    - löscht defekte Dateien
    """

    for attempt in range(1, MAX_RETRIES + 1):
        log.info("[download] Versuch %d: %s", attempt, url)

        try:
            with requests.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()

                total_size = int(r.headers.get("Content-Length", 0))
                if total_size == 0:
                    log.warning("[download] Keine Content-Length – Server instabil")

                temp_path = path + ".part"

                with open(temp_path, "wb") as f:
                    downloaded = 0
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                # Prüfen, ob Datei vollständig ist
                if total_size > 0 and downloaded < total_size:
                    log.warning("[download] Datei unvollständig (%d < %d) – neuer Versuch",
                                downloaded, total_size)
                    os.remove(temp_path)
                    time.sleep(2)
                    continue

                # Datei ist vollständig → umbenennen
                os.rename(temp_path, path)
                log.info("[download] Fertig: %s", path)
                return True

        except Exception as e:
            log.error("[download] Fehler: %s", e)
            if os.path.exists(path + ".part"):
                os.remove(path + ".part")
            time.sleep(2)

    log.error("[download] Alle Versuche fehlgeschlagen: %s", url)
    return False


def download_episode(item: dict):
    title = item["title"]
    media_url = item["media_url"]
    pub_dt = item["pub_dt"]

    date_prefix = format_dd_mm(pub_dt)
    safe_title = sanitize_title(title)
    filename = f"{date_prefix}_{safe_title}.mp3"
    path = os.path.join(MEDIA_DIR, filename)

    if os.path.exists(path):
        log.info("[skip] Datei existiert bereits: %s", filename)
        return path, pub_dt

    log.info("[episode] %s", title)

    ok = robust_download(media_url, path)
    if ok:
        return path, pub_dt
    else:
        return None, pub_dt


def build_feed(files: list[tuple[str, datetime]]):
    log.info("[feed] Erzeuge neuen Apolut RSS-Feed (%d Episoden)", len(files))

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "Apolut – Podcast (Inoffiziell)"
    ET.SubElement(channel, "link").text = "https://apolut.net/"
    ET.SubElement(channel, "description").text = "Inoffizieller Apolut-Podcastfeed"
    ET.SubElement(channel, "language").text = "de"

    for path, pub_dt in files:
        fname = os.path.basename(path)
        parts = fname.rsplit(".mp3", 1)[0]

        try:
            date_prefix, title_part = parts.split("_", 1)
        except ValueError:
            date_prefix = ""
            title_part = parts

        title_clean = title_part.replace("_", " ")
        full_title = f"{date_prefix} {title_clean}"

        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = full_title
        ET.SubElement(item, "description").text = full_title
        ET.SubElement(item, "pubDate").text = pub_dt.strftime("%a, %d %b %Y %H:%M:%S +0000")

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
    log.info("[apolut] Starte Apolut-Feed-Generator")

    soup = fetch_rss(RSS_URL)
    items = extract_items(soup)

    if not items:
        log.error("[apolut] RSS leer – Abbruch.")
        return

    # Nur die neuesten 20 Episoden
    items.sort(key=lambda x: x["pub_dt"], reverse=True)
    items = items[:MAX_EPISODES]

    downloaded = []
    for item in items:
        path, pub_dt = download_episode(item)
        if path:
            downloaded.append((path, pub_dt))

    downloaded.sort(key=lambda x: x[1], reverse=True)
    build_feed(downloaded)


if __name__ == "__main__":
    main()

