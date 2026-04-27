import requests
from pathlib import Path
from xml.etree import ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import re
import subprocess
import time

WORKER = "https://broad-sound-0f3e.sobisiakp.workers.dev/"

def proxy(url: str) -> str:
    return WORKER + "?url=" + url

RSS_URL = "https://apolut.net/podcast/rss"
HTML_BASE = "https://apolut.net/"

MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)

KEEP_EPISODES = 10

def fetch(url: str) -> str | None:
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

def extract_mp3_links(html: str) -> list[str]:
    patterns = [
        r"https://apolut\.net/content/media/[0-9]{4}/[0-9]{2}/[^\"']+\.mp3",
        r"https://apolut\.net/wp-content/uploads/[0-9]{4}/[0-9]{2}/[^\"']+\.mp3",
        r"https://apolut\.net/wp-content/uploads/[^\"']+\.mp3",
        r"<audio[^>]+src=\"(https://[^\"]+\.mp3)\"",
        r"<source[^>]+src=\"(https://[^\"]+\.mp3)\"",
        r"property=\"og:audio\" content=\"(https://[^\"]+\.mp3)\""
    ]

    links = []
    for p in patterns:
        for m in re.findall(p, html):
            links.append(m if isinstance(m, str) else m[0])

    return list(dict.fromkeys(links))

def extract_date_from_mp3(mp3_url: str) -> str:
    m = re.search(r"tagesdosis-(\d{8})", mp3_url)
    if not m:
        return datetime.now().strftime("%d.%m.%Y")
    d = datetime.strptime(m.group(1), "%Y%m%d")
    return d.strftime("%d.%m.%Y")

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

def find_latest_tagesdosis():
    html = fetch(HTML_BASE)
    if not html:
        return None

    links = re.findall(r"https://apolut\.net/[^\"]+/", html)
    td_links = [l for l in links if "tagesdosis" in l]

    if not td_links:
        return None

    return sorted(set(td_links))[-1]

def process_tagesdosis():
    url = find_latest_tagesdosis()
    if not url:
        return None

    html = fetch(url)
    if not html:
        return None

    mp3s = extract_mp3_links(html)
    if not mp3s:
        return None

    mp3 = mp3s[0]

    m = re.search(r"<title>([^<]+)</title>", html)
    title = m.group(1).replace(" – apolut.net", "") if m else "Tagesdosis"
    title = f"Tagesdosis – {title}"

    date_str = extract_date_from_mp3(mp3)
    guid = hash_id(title)
    filename = MEDIA_DIR / f"{date_str}_tagesdosis_{guid}.mp3"

    if download_file(mp3, filename):
        compress_12k_mono(filename)
        pubdate = datetime.strptime(date_str, "%d.%m.%Y").replace(tzinfo=timezone.utc)
        return {
            "title": title,
            "link": url,
            "date": pubdate,
            "local_mp3": filename.name,
            "id": guid
        }

    return None

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

        date_str = dt.strftime("%a_%d_%b_%Y")
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

        if len(items) >= KEEP_EPISODES - 1:
            break

    return items

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

def main():
    td = process_tagesdosis()
    rss_items = process_rss()

    if not td and not rss_items:
        print("Nichts gefunden – alter Feed bleibt erhalten.")
        return

    items = []
    if td:
        items.append(td)
    items.extend(rss_items)

    items.sort(key=lambda x: x["date"], reverse=True)

    rss = build_rss(items[:KEEP_EPISODES])
    Path("feed.xml").write_text(rss, encoding="utf-8")

    enforce_media_limit()

    print("Feed erfolgreich aktualisiert.")

if __name__ == "__main__":
    main()

