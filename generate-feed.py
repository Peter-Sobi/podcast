import requests
from xml.etree import ElementTree as ET
from pathlib import Path
import subprocess
import os
import time
import re
import unicodedata
from email.utils import parsedate_to_datetime

RSS_URL = "https://apolut.net/podcast/rss"
HEADERS = {"User-Agent": "Mozilla/5.0"}

MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------

def slugify(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")

def fetch_rss(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"RSS-Fehler: {e}")
        return None

def download_file(url: str, filename: Path) -> bool:
    """Download beliebige Datei (MP3 oder Bild) mit Retry."""
    if not url:
        return False

    for attempt in range(3):
        try:
            print(f"Download Versuch {attempt+1}: {url}")
            r = requests.get(url, headers=HEADERS, timeout=60, stream=True)
            r.raise_for_status()

            with open(filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
            return True
        except Exception as e:
            print(f"Fehler beim Download: {e}")
            time.sleep(3)
    return False

def compress_mp3(input_file: Path):
    temp = input_file.with_suffix(".tmp.mp3")

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", str(input_file),
                "-b:a", "48k",
                "-ac", "2",
                str(temp)
            ],
            check=True
        )
    except Exception as e:
        print(f"Komprimierung fehlgeschlagen: {e}")
        return False

    input_file.unlink()
    temp.rename(input_file)

    if input_file.stat().st_size > 50 * 1024 * 1024:
        print(f"Datei {input_file.name} ist nach Kompression noch zu groß!")
        input_file.unlink()
        return False

    return True

def parse_rss(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    items = []

    for item in channel.findall("item"):
        title = item.findtext("title", default="Ohne Titel")
        link = item.findtext("link", default="")
        pubDate = item.findtext("pubDate", default="")
        enclosure = item.find("enclosure")

        if enclosure is None:
            continue

        mp3 = enclosure.attrib.get("url", "")
        if not mp3:
            continue

        # Thumbnail-Cover extrahieren
        image_tag = item.find("{http://www.itunes.com/dtds/podcast-1.0.dtd}image")
        cover_url = None

        if image_tag is not None:
            href = image_tag.attrib.get("href", "")
            if href:
                # Thumbnail erzwingen
                if "-150x150" in href:
                    cover_url = href
                else:
                    cover_url = href.replace(".jpg", "-150x150.jpg").replace(".png", "-150x150.png")

        items.append({
            "title": title,
            "link": link,
            "date": pubDate,
            "mp3": mp3,
            "cover": cover_url
        })

    return items

def build_rss(items: list[dict]) -> str:
    xml_items = []
    for t in items:
        xml_items.append(
f"""
<item>
<title>{t['title']}</title>
<link>{t['link']}</link>
<description><![CDATA[{t['title']}]]></description>
<enclosure url="https://peter-sobi.github.io/podcast/media/{t['local_mp3']}" length="0" type="audio/mpeg"/>
<itunes:image href="https://peter-sobi.github.io/podcast/media/{t['local_img']}" />
<guid>{t['link']}</guid>
<pubDate>{t['date']}</pubDate>
</item>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel>
<title>Apolut Kombinierter Podcast (Proxy, 48kbit)</title>
<link>https://apolut.net</link>
<description>Stabiler Proxy-Feed mit komprimierten MP3-Dateien und Episoden-Covern</description>
<language>de-de</language>
{''.join(xml_items)}
</channel>
</rss>
"""

# ---------------------------------------------------------
# Hauptlogik
# ---------------------------------------------------------

def main():
    print("Lade offiziellen RSS-Feed…")
    xml = fetch_rss(RSS_URL)
    if not xml:
        print("FEHLER: Konnte RSS nicht laden.")
        return

    print("Parse Feed…")
    items = parse_rss(xml)

    items = items[:10]

    # Alte Dateien löschen
    for f in MEDIA_DIR.glob("*.*"):
        try:
            f.unlink()
        except Exception as e:
            print(f"Konnte alte Datei nicht löschen: {e}")

    # Neue Dateien herunterladen
    for i, item in enumerate(items):
        dt = parsedate_to_datetime(item["date"])
        date_str = dt.strftime("%Y-%m-%d")
        title_slug = slugify(item["title"])

        base = f"{date_str}_{title_slug}"

        mp3_file = MEDIA_DIR / f"{base}.mp3"

        print(f"Lade MP3 {mp3_file.name}…")
        ok = download_file(item["mp3"], mp3_file)
        if not ok:
            print(f"FEHLER beim Laden: {item['mp3']}")
            continue

        print(f"Komprimiere {mp3_file.name}…")
        ok = compress_mp3(mp3_file)
        if not ok:
            print(f"FEHLER: {mp3_file.name} konnte nicht komprimiert werden.")
            continue

        # Cover herunterladen
        if item["cover"]:
            img_ext = item["cover"].split(".")[-1]
            img_file = MEDIA_DIR / f"{base}.{img_ext}"

            print(f"Lade Cover {img_file.name}…")
            ok = download_file(item["cover"], img_file)
            if not ok:
                print(f"FEHLER beim Laden des Covers: {item['cover']}")
                item["local_img"] = "default.jpg"
            else:
                item["local_img"] = img_file.name
        else:
            print(f"Kein Cover für {item['title']} – verwende default.jpg")
            item["local_img"] = "default.jpg"

        item["local_mp3"] = mp3_file.name

    rss = build_rss(items)
    Path("feed.xml").write_text(rss, encoding="utf-8")

    print("feed.xml erfolgreich erzeugt.")

if __name__ == "__main__":
    main()
