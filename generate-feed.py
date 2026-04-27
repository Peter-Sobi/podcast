import requests
from xml.etree import ElementTree as ET
from pathlib import Path
import subprocess
import time
import re
import unicodedata
from email.utils import parsedate_to_datetime

RSS_URL = "https://apolut.net/podcast/rss"
HEADERS = {"User-Agent": "Mozilla/5.0"}

MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)

TARGET_SIZE = 50 * 1024 * 1024  # Zielgröße 50 MB
KEEP_EPISODES = 10              # Nur die 10 neuesten Episoden behalten

def slugify(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")

def extract_slug_from_url(url: str) -> str:
    try:
        return url.rstrip("/").split("/")[-1]
    except:
        return ""

def extract_apolut_id(item) -> str:
    possible_tags = ["guid", "id", "dc:identifier"]
    for tag in possible_tags:
        elem = item.find(tag)
        if elem is not None and elem.text:
            text = elem.text.strip()
            if re.fullmatch(r"[0-9a-f]{8,32}", text):
                return text

    link = item.findtext("link", "")
    return re.sub(r"[^0-9a-f]", "", link.lower())[:16]

def fetch_rss(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.text
    except:
        return None

def extract_mp3_from_page(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        html = r.text
    except:
        return None

    m = re.search(r"https://apolut\.net/content/media/[0-9]{4}/[0-9]{2}/[^\"']+\.mp3", html)
    return m.group(0) if m else None

def try_construct_mp3_urls(date: str, title: str, url_slug: str) -> list[str]:
    dt = parsedate_to_datetime(date)
    yyyy = dt.strftime("%Y")
    mm = dt.strftime("%m")
    ymd = dt.strftime("%Y%m%d")

    title_slug = slugify(title)
    title_slug_short = title_slug.split("_von_")[0] if "_von_" in title_slug else title_slug

    base = f"https://apolut.net/content/media/{yyyy}/{mm}"

    return [
        f"{base}/{url_slug}.mp3",
        f"{base}/{url_slug}-{ymd}.mp3",
        f"{base}/{url_slug}-{ymd}-apolut.mp3",
        f"{base}/{url_slug}-tagesdosis.mp3",
        f"{base}/tagesdosis-{url_slug}.mp3",
        f"{base}/{title_slug}.mp3",
        f"{base}/{title_slug_short}.mp3",
        f"{base}/{title_slug}-{ymd}.mp3",
        f"{base}/{title_slug_short}-{ymd}.mp3",
        f"{base}/{title_slug}-{ymd}-apolut.mp3",
        f"{base}/{title_slug_short}-{ymd}-apolut.mp3",
        f"{base}/tagesdosis-{ymd}.mp3",
        f"{base}/tagesdosis-{ymd}-apolut.mp3",
    ]

def check_url_exists(url: str) -> bool:
    try:
        r = requests.head(url, headers=HEADERS, timeout=10)
        return r.status_code == 200
    except:
        return False

def download_file(url: str, filename: Path) -> bool:
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=180, stream=True)
            r.raise_for_status()
            with open(filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
            return True
        except:
            time.sleep(5)
    return False

# ---------------------------------------------------------
# Dynamische Kompression: so lange runter, bis < 50 MB
# ---------------------------------------------------------

def compress_mp3(input_file: Path):
    bitrates = ["48k", "40k", "32k", "24k", "16k", "12k", "8k"]

    for br in bitrates:
        temp = input_file.with_suffix(f".{br}.tmp.mp3")

        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i", str(input_file),
                    "-b:a", br,
                    "-ac", "1",        # MONO
                    str(temp)
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
        except:
            return False

        input_file.unlink()
        temp.rename(input_file)

        if input_file.stat().st_size <= TARGET_SIZE:
            return True

    input_file.unlink()
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

        url_slug = extract_slug_from_url(link)
        apolut_id = extract_apolut_id(item)

        mp3 = enclosure.attrib.get("url", "") if enclosure is not None else None
        if not mp3:
            mp3 = extract_mp3_from_page(link)

        if not mp3:
            for candidate in try_construct_mp3_urls(pubDate, title, url_slug):
                if check_url_exists(candidate):
                    mp3 = candidate
                    break

        if not mp3:
            continue

        items.append({
            "title": title,
            "link": link,
            "date": pubDate,
            "mp3": mp3,
            "id": apolut_id
        })

    # Nur die 10 neuesten Episoden behalten
    items.sort(key=lambda x: parsedate_to_datetime(x["date"]), reverse=True)
    return items[:KEEP_EPISODES]

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

def main():
    xml = fetch_rss(RSS_URL)
    if not xml:
        return

    items = parse_rss(xml)

    # Alte Dateien löschen
    for f in MEDIA_DIR.glob("*.mp3"):
        try:
            f.unlink()
        except:
            pass

    # Neue Dateien erzeugen
    for item in items:
        dt = parsedate_to_datetime(item["date"])
        date_str = dt.strftime("%a_%d_%b_%Y")
        title_slug = slugify(item["title"])
        apolut_id = item["id"]

        base = f"{date_str}_{title_slug}_{apolut_id}"
        mp3_file = MEDIA_DIR / f"{base}.mp3"

        if not download_file(item["mp3"], mp3_file):
            continue

        if not compress_mp3(mp3_file):
            continue

        item["local_mp3"] = mp3_file.name

    rss = build_rss(items)
    Path("feed.xml").write_text(rss, encoding="utf-8")

if __name__ == "__main__":
    main()

