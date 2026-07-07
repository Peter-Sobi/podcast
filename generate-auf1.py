#!/usr/bin/env python3
import os
import re
import sys
import logging
import subprocess
from datetime import datetime
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

RSS_URL = "https://auf1.radio/api/feed"
MEDIA_DIR = "auf1_media"
LOG_DIR = "logs"
FEED_FILE = "auf1_feed.xml"
MAX_EPISODES = 20
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


def parse_pub_date(text: str) -> datetime:
    for fmt in ("%a, %d %b %Y %H:%M:%S %z",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return datetime.utcnow()


def format_dd_mm(dt: datetime) -> str:
    return dt.strftime("%d.%m")


def fetch_rss(url: str) -> BeautifulSoup | None:
    log.info("[auf1] Lade RSS-Feed: %s", url)
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

        items.append({
            "title": title,
            "media_url": media_url,
            "pub_dt": pub_dt,
        })

    return items


def download_original(url, temp_path):
    log.info("[download] Lade Original-MP3: %s", url)
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(temp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        log.info("[download] Fertig: %s", temp_path)
        return True
    except Exception as e:
        log.error("[download] Fehler: %s", e)
        return False


def reencode_32kbps(src, dst):
    log.info("[ffmpeg] Reencode auf 32kbps: %s", dst)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", src,
                "-ac", "1",
                "-b:a", "32k",
                "-codec:a", "libmp3lame",
                dst,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        log.error("[ffmpeg] Fehler: %s", e)
        return False


def auto_delete_old_files():
    log.info("[cleanup] Lösche alte AUF1-Dateien…")

    files = sorted(
        [os.path.join(MEDIA_DIR, f) for f in os.listdir(MEDIA_DIR) if f.endswith(".mp3")],
        key=lambda p: os.path.getmtime(p),
        reverse=True
    )

    if len(files) <= MAX_EPISODES:
        log.info("[cleanup] Keine alten Dateien zu löschen.")
        return

    to_delete = files[MAX_EPISODES:]
    for f in to_delete:
        try:
            os.remove(f)
            log.info("[cleanup] Entfernt: %s", os.path.basename(f))
        except Exception as e:
            log.error("[cleanup] Fehler beim Löschen: %s", e)


def build_feed(files: list[tuple[str, datetime]]):
    log.info("[feed] Erzeuge neuen AUF1 RSS-Feed (%d Episoden)", len(files))

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "AUF1 – Radio (32kbps)"
    ET.SubElement(channel, "link").text = "https://auf1.radio/"
    ET.SubElement(channel, "description").text = "Inoffizieller AUF1-Radiofeed (32kbps)"
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
    log.info("[auf1] Starte AUF1-Feed-Generator (32kbps + Auto-Delete)")

    soup = fetch_rss(RSS_URL)
    items = extract_items(soup)

    if not items:
        log.error("[auf1] RSS leer – Abbruch.")
        return

    items.sort(key=lambda x: x["pub_dt"], reverse=True)
    items = items[:MAX_EPISODES]

    downloaded = []
    for item in items:
        title = item["title"]
        media_url = item["media_url"]
        pub_dt = item["pub_dt"]

        date_prefix = format_dd_mm(pub_dt)
        safe_title = sanitize_title(title)
        filename = f"{date_prefix}_{safe_title}.mp3"

        final_path = os.path.join(MEDIA_DIR, filename)
        temp_path = final_path + ".orig"

        log.info("[episode] %s", title)

        if os.path.exists(final_path):
            log.info("[skip] Datei existiert bereits: %s", filename)
            downloaded.append((final_path, pub_dt))
            continue

        if download_original(media_url, temp_path):
            if reencode_32kbps(temp_path, final_path):
                downloaded.append((final_path, pub_dt))
            os.remove(temp_path)

    downloaded.sort(key=lambda x: x[1], reverse=True)
    build_feed(downloaded)

    auto_delete_old_files()


if __name__ == "__main__":
    main()

