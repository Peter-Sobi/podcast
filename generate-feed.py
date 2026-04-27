import requests
from pathlib import Path
from xml.etree import ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import subprocess
import time

# ---------------------------------------------------------
# Einstellungen
# ---------------------------------------------------------

WORKER = "https://broad-sound-0f3e.sobisiakp.workers.dev/"

def proxy(url: str) -> str:
    return WORKER + "?url=" + url

RSS_URL = "https://apolut.net/podcast/rss"

MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)

KEEP_EPISODES = 10

# ---------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------

def fetch(url: str) -> str | None:
    """Lädt eine URL über den Worker."""
    for _ in range(3):
        try:
            r = requests.get(proxy(url), timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            return r.text
        except:
            time.sleep(2)
    return None

def hash_id(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]

def download_file(url: str, filename: Path) -> bool:
    for _ in range(3):
        try:
            r = requests.get(url, stream=True, timeout=180)
            r.raise_for_status()
            with open(filename, "wb") as f:
                for chunk in r.iter_content(1024 * 256):
                    if chunk:
                        f.write(chunk)
            return True
        except:
            time.sleep(3)
    return False

def compress_12k_mono(path: Path):
    tmp = path.with_suffix(".tmp.mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(path), "-b:a", "12k", "-ac", "1", str(tmp)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True
    )
    path.unlink()
    tmp.rename(path)

# ---------------------------------------------------------
# RSS verarbeiten (Tagesdosis + alle anderen)
# ---------------------------------------------------------

def process_rss():
    xml = fetch(RSS_URL)
    if not xml:
        return []

    root = ET.fromstring(xml)
    channel = root.find("channel")
    items = []

    for item in channel.findall("item"):
        title = item.findtext("title", "")
        link = item.findtext("link", "")
        pub = item.findtext("pubDate", "")
        enclosure = item.find("enclosure")

        if not enclosure:
            continue

        mp3 = enclosure.attrib.get("url", "")
        if not mp3:
            continue

        guid = hash_id(title)

        try:
            dt = parsedate_to_datetime(pub).astimezone(timezone.utc)
        except:
            dt = datetime.now(timezone.utc)

        date_str = dt.strftime("%Y-%m-%d")
        filename = MEDIA_DIR / f"{date_str}_{guid}.mp3"

        if download_file(mp3, filename):
            compress_12k_mono(filename)
            items.append({
                "title": title,
                "link": link,
                "date": dt,
                "local_mp3": filename.name,
                "id": guid
            })

        if len(items) >= KEEP_EPISODES:
            break

    return items

# ---------------------------------------------------------
# RSS bauen
# ---------------------------------------------------------

def build_rss(items):
    xml_items = []
    for t in items:
        pubdate = t["date"].strftime("%a, %d %b %Y %H:%M:%S +0000")
        xml_items.append(f"""
<item>
<title>{t['title']}</title>
<link>{t['link']}</link>
<description><![CDATA[{t['title']}]]></description>
<enclosure url="https://peter-sobi.github.io/podcast/media/{t['local_mp3']}" length="0" type="audio/mpeg"/>
<guid>{t['id']}</guid>
<pubDate>{pubdate}</pubDate>
</item>
""")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Kombinierter Podcast</title>
<link>https://apolut.net</link>
<description>Automatisch generierter Podcastfeed</description>
<language>de-de</language>
{''.join(xml_items)}
</channel>
</rss>
"""

# ---------------------------------------------------------
# Medienlimit durchsetzen
# ---------------------------------------------------------

def enforce_media_limit():
    files = sorted(
        MEDIA_DIR.glob("*.mp3"),
        key=lambda f: f.stat().st_mtime
    )

    if len(files) > KEEP_EPISODES:
        to_delete = files[:-KEEP_EPISODES]
        for f in to_delete:
            f.unlink()
            print(f"Gelöscht: {f.name}")

# ---------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------

def main():
    rss_items = process_rss()

    if not rss_items:
        print("Nichts gefunden – alter Feed bleibt erhalten.")
        return

    rss_items.sort(key=lambda x: x["date"], reverse=True)

    rss = build_rss(rss_items[:KEEP_EPISODES])
    Path("feed.xml").write_text(rss, encoding="utf-8")

    enforce_media_limit()

    print("Feed erfolgreich aktualisiert.")

if __name__ == "__main__":
    main()

