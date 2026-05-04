import requests
from xml.etree import ElementTree as ET
from pathlib import Path
import subprocess
import time
from email.utils import parsedate_to_datetime

RSS_URL = "https://auf1.radio/api/feed"
HEADERS = {"User-Agent": "Mozilla/5.0"}

MEDIA_DIR = Path("media_auf1")
MEDIA_DIR.mkdir(exist_ok=True)

TARGET_SIZE = 50 * 1024 * 1024
KEEP_EPISODES = 10

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

def compress_mp3(input_file: Path):
    bitrates = ["48k", "40k", "32k", "24k", "16k", "12k", "8k"]

    for br in bitrates:
        temp = input_file.with_suffix(f".{br}.tmp.mp3")

        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(input_file), "-b:a", br, "-ac", "1", str(temp)],
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
<enclosure url="https://peter-sobi.github.io/podcast/media_auf1/{t['local_mp3']}" length="0" type="audio/mpeg"/>
<pubDate>{t['date']}</pubDate>
</item>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>AUF1 Kombinierter Podcast</title>
<link>https://auf1.radio</link>
<description>Automatisch generierter Feed</description>
<language>de-de</language>
{''.join(xml_items)}
</channel>
</rss>
"""

def main():
    try:
        r = requests.get(RSS_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        xml = r.text
    except:
        return

    items = parse_rss(xml)

    for f in MEDIA_DIR.glob("*.mp3"):
        try:
            f.unlink()
        except:
            pass

    for item in items:
        dt = parsedate_to_datetime(item["date"])
        date_str = dt.strftime("%a_%d_%b_%Y")

        safe_title = item["title"].replace(" ", "_").replace("/", "_")
        mp3_file = MEDIA_DIR / f"{date_str}_{safe_title}.mp3"

        if not download_file(item["mp3"], mp3_file):
            continue

        if not compress_mp3(mp3_file):
            continue

        item["local_mp3"] = mp3_file.name

    rss = build_rss(items)
    Path("feed_auf1.xml").write_text(rss, encoding="utf-8")

if __name__ == "__main__":
    main()

