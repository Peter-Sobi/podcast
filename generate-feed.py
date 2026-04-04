import requests
from xml.etree import ElementTree as ET
from pathlib import Path

RSS_URL = "https://apolut.net/podcast/rss"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def mp3_reachable(url: str) -> bool:
    try:
        r = requests.head(url, headers=HEADERS, timeout=10, allow_redirects=True)
        return r.status_code == 200
    except Exception:
        return False

def fetch_rss(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception:
        return None

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
        if not mp3 or not mp3_reachable(mp3):
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
<enclosure url="{t['mp3']}" length="0" type="audio/mpeg"/>
<guid>{t['link']}</guid>
<pubDate>{t['date']}</pubDate>
</item>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Apolut Kombinierter Podcast</title>
<link>https://apolut.net</link>
<description>Stabiler, FRITZ!Box-kompatibler Feed basierend auf dem offiziellen Apolut-Podcast</description>
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

    print(f"Gefundene gültige MP3-Folgen: {len(items)}")

    rss = build_rss(items)
    Path("feed.xml").write_text(rss, encoding="utf-8")

    print("feed.xml erfolgreich erzeugt.")

if __name__ == "__main__":
    main()

