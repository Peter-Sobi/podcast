import requests
from xml.etree import ElementTree as ET
from pathlib import Path
import os

RSS_URL = "https://apolut.net/podcast/rss"
HEADERS = {"User-Agent": "Mozilla/5.0"}

MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)

def fetch_rss(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception:
        return None

def download_mp3(url: str, filename: str) -> bool:
    try:
        r = requests.get(url, headers=HEADERS, timeout=60, stream=True)
        r.raise_for_status()

        with open(MEDIA_DIR / filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
        return True
    except Exception:
        return False

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

        items.append({
            "title": title,
            "link": link,
            "date": pubDate,
            "mp3": mp3
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
<enclosure url="https://peter-sobi.github.io/podcast/media/{t['local']}" length="0" type="audio/mpeg"/>
<guid>{t['link']}</guid>
<pubDate>{t['date']}</pubDate>
</item>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Apolut Kombinierter Podcast (Proxy)</title>
<link>https://apolut.net</link>
<description>Stabiler Proxy-Feed mit lokalen MP3-Dateien</description>
<language>de-de</language>
{''.join(xml_items)}
</channel>
</rss>
"""

def main():
    print("Lade offiziellen RSS-Feed…")
    xml = fetch_rss(RSS_URL)
    if not xml:
        print("FEHLER: Konnte RSS nicht laden.")
        return

    print("Parse Feed…")
    items = parse_rss(xml)

    # Nur die letzten 10 Folgen
    items = items[:10]

    # Alte MP3s löschen
    for f in MEDIA_DIR.glob("*.mp3"):
        f.unlink()

    # Neue MP3s herunterladen
    for i, item in enumerate(items):
        filename = f"folge_{i+1}.mp3"
        print(f"Lade {filename}…")
        ok = download_mp3(item["mp3"], filename)
        if not ok:
            print(f"FEHLER beim Laden: {item['mp3']}")
            continue
        item["local"] = filename

    # Feed erzeugen
    rss = build_rss(items)
    Path("feed.xml").write_text(rss, encoding="utf-8")

    print("feed.xml erfolgreich erzeugt.")

if __name__ == "__main__":
    main()

