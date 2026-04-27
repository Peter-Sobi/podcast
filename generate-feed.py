import requests
from xml.etree import ElementTree as ET
from pathlib import Path
import subprocess
import time
import re
import unicodedata
import hashlib
from email.utils import parsedate_to_datetime
from datetime import datetime

RSS_URL = "https://apolut.net/podcast/rss"
APOLUT_HOME = "https://apolut.net/"
HEADERS = {"User-Agent": "Mozilla/5.0"}

MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)

TARGET_SIZE = 50 * 1024 * 1024
KEEP_EPISODES = 10

# ---------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------

def slugify(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")

def hash_id(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]

def fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.text
    except:
        return None

# ---------------------------------------------------------
# Tagesdosis von der Startseite holen
# ---------------------------------------------------------

def find_latest_tagesdosis_url():
    html = fetch(APOLUT_HOME)
    if not html:
        return None

    # Suche nach Links wie: https://apolut.net/tagesdosis-...
    m = re.search(r'https://apolut\.net/tagesdosis-[^"\' ]+/', html)
    return m.group(0) if m else None

def extract_mp3_from_page(url: str) -> str | None:
    html = fetch(url)
    if not html:
        return None

    m = re.search(r"https://apolut\.net/content/media/[0-9]{4}/[0-9]{2}/[^\"']+\.mp3", html)
    return m.group(0) if m else None

def download_file(url: str, filename: Path) -> bool:
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=180, stream=True)
            r.raise_for_status()
            with open(filename, "wb") as f:
                for chunk in r.iter_content(1024 * 256):
                    if chunk:
                        f.write(chunk)
            return True
        except:
            time.sleep(5)
    return False

def compress_12k_mono(input_file: Path):
    temp = input_file.with_suffix(".tmp.mp3")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", str(input_file),
            "-b:a", "12k",
            "-ac", "1",
            str(temp)
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True
    )
    input_file.unlink()
    temp.rename(input_file)

# ---------------------------------------------------------
# RSS verarbeiten (für die restlichen 9 Episoden)
# ---------------------------------------------------------

def parse_rss(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    items = []

    for item in channel.findall("item"):
        title = item.findtext("title", default="")
        link = item.findtext("link", default="")
        pubDate = item.findtext("pubDate", default="")
        enclosure = item.find("enclosure")

        if not enclosure:
            continue

        mp3 = enclosure.attrib.get("url", "")
        if not mp3:
            continue

        items.append({
            "title": title,
            "link": link,
            "date": pubDate,
            "mp3": mp3,
            "id": hash_id(title)
        })

    items.sort(key=lambda x: parsedate_to_datetime(x["date"]), reverse=True)
    return items[:KEEP_EPISODES - 1]  # Platz für Tagesdosis

# ---------------------------------------------------------
# RSS bauen
# ---------------------------------------------------------

def build_rss(items: list[dict]) -> str:
    xml_items = []
    for t in items:
        if "local_mp3" not in t:
            continue

        xml_items.append(
f"""
<item>
<title>{t['title']}</title>
<link>{t['link']}</link>
<description><![CDATA[{t['title']}]]></description>
<enclosure url="https://peter-sobi.github.io/podcast/media/{t['local_mp3']}" length="0" type="audio/mpeg"/>
<guid>{t['id']}</guid>
<pubDate>{t['date']}</pubDate>
</item>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Apolut Kombinierter Podcast</title>
<link>https://apolut.net</link>
<description>Automatisch generierter Feed</description>
<language>de-de</language>
{''.join(xml_items)}
</channel>
</rss>
"""

# ---------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------

def main():
    # Alte Dateien löschen
    for f in MEDIA_DIR.glob("*.mp3"):
        try:
            f.unlink()
        except:
            pass

    # 1) Tagesdosis holen
    td_url = find_latest_tagesdosis_url()
    if td_url:
        mp3_url = extract_mp3_from_page(td_url)
    else:
        mp3_url = None

    items = []

    if mp3_url:
        # Titel extrahieren
        title_html = fetch(td_url)
        m = re.search(r"<title>([^<]+)</title>", title_html or "")
        original_title = m.group(1).replace(" – apolut.net", "") if m else "Tagesdosis"

        final_title = f"Tagesdosis – {original_title}"
        today = datetime.now().strftime("%d.%m.%Y")
        file_id = hash_id(final_title)

        filename = MEDIA_DIR / f"{today}_tagesdosis_{file_id}.mp3"

        if download_file(mp3_url, filename):
            compress_12k_mono(filename)

            items.append({
                "title": final_title,
                "link": td_url,
                "date": datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000"),
                "mp3": mp3_url,
                "id": file_id,
                "local_mp3": filename.name
            })

    # 2) Restliche Episoden aus RSS
    xml = fetch(RSS_URL)
    if xml:
        rss_items = parse_rss(xml)

        for item in rss_items:
            dt = parsedate_to_datetime(item["date"])
            date_str = dt.strftime("%a_%d_%b_%Y")
            title_slug = slugify(item["title"])
            file_id = item["id"]

            filename = MEDIA_DIR / f"{date_str}_{title_slug}_{file_id}.mp3"

            if download_file(item["mp3"], filename):
                compress_12k_mono(filename)
                item["local_mp3"] = filename.name
                items.append(item)

    # 3) RSS schreiben
    rss = build_rss(items)
    Path("feed.xml").write_text(rss, encoding="utf-8")

if __name__ == "__main__":
    main()

