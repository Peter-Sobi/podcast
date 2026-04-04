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

DEFAULT_IMAGE = "default.jpg"   # Muss im media/ Ordner liegen!

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
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"RSS-Fehler: {e}")
        return None

def download_file(url: str, filename: Path) -> bool:
    """Download beliebige Datei (MP3 oder Bild) mit Retry."""
    if not url:
        print("WARNUNG: Keine URL vorhanden.")
        return False

    for attempt in range(3):
        try:
            print(f"Download Versuch {attempt+1}: {url}")
            r = requests.get(url, headers=HEADERS, timeout=180, stream=True)
            r.raise_for_status()

            with open(filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
            return True

        except Exception as e:
            print(f"WARNUNG: Download fehlgeschlagen ({e})")
            time.sleep(5)

    print(f"FEHLER: Datei konnte nicht geladen werden: {url}")
    return False

def convert_to_jpg_150(input_file: Path, output_file: Path) -> bool:
    """Konvertiert jedes Bild zu 150x150 JPG."""
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", str(input_file),
                "-vf", "scale=150:150:force_original_aspect_ratio=decrease,pad=150:150:(ow-iw)/2:(oh-ih)/2",
                "-q:v", "3",
                str(output_file)
            ],
            check=True
        )
        return True
    except Exception as e:
        print(f"Bildkonvertierung fehlgeschlagen: {e}")
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

        # Cover extrahieren
        image_tag = item.find("{http://www.itunes.com/dtds/podcast-1.0.dtd}image")
        cover_url = None

        if image_tag is not None:
            href = image_tag.attrib.get("href", "")
            if href:
                cover_url = href

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
        if f.name != DEFAULT_IMAGE:
            try:
                f.unlink()
            except Exception as e:
                print(f"Konnte alte Datei nicht löschen: {e}")

    # Neue Dateien herunterladen
    for i, item in enumerate(items):
        try:
            dt = parsedate_to_datetime(item["date"])
        except:
            print(f"WARNUNG: Ungültiges Datum, überspringe Episode: {item['title']}")
            continue

        date_str = dt.strftime("%Y-%m-%d")
        title_slug = slugify(item["title"])

        base = f"{date_str}_{title_slug}"

        mp3_file = MEDIA_DIR / f"{base}.mp3"

        print(f"Lade MP3 {mp3_file.name}…")
        ok = download_file(item["mp3"], mp3_file)
        if not ok:
            print(f"WARNUNG: MP3 konnte nicht geladen werden, überspringe Episode.")
            continue

        print(f"Komprimiere {mp3_file.name}…")
        ok = compress_mp3(mp3_file)
        if not ok:
            print(f"WARNUNG: MP3 konnte nicht komprimiert werden, überspringe Episode.")
            continue

        # Cover herunterladen
        cover_url = item["cover"]

        if cover_url:
            temp_file = MEDIA_DIR / f"{base}_orig"
            jpg_file = MEDIA_DIR / f"{base}.jpg"

            print(f"Lade Cover…")
            ok = download_file(cover_url, temp_file)

            if ok:
                print("Konvertiere Cover zu 150x150 JPG…")
                ok2 = convert_to_jpg_150(temp_file, jpg_file)
                temp_file.unlink(missing_ok=True)

                if ok2:
                    item["local_img"] = jpg_file.name
                else:
                    print("WARNUNG: Konvertierung fehlgeschlagen, verwende default.jpg")
                    item["local_img"] = DEFAULT_IMAGE
            else:
                print("WARNUNG: Cover-Download fehlgeschlagen, verwende default.jpg")
                item["local_img"] = DEFAULT_IMAGE
        else:
            print("WARNUNG: Kein Cover im RSS gefunden, verwende default.jpg")
            item["local_img"] = DEFAULT_IMAGE

        item["local_mp3"] = mp3_file.name

    rss = build_rss(items)
    Path("feed.xml").write_text(rss, encoding="utf-8")

    print("feed.xml erfolgreich erzeugt.")

if __name__ == "__main__":
    main()
