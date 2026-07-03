import os
import requests
from bs4 import BeautifulSoup
import datetime
import hashlib
import xml.etree.ElementTree as ET

SOURCE_URL = "https://apolut.net/category/video/"
MEDIA_DIR = "media"
FEED_OUTPUT = "feed.xml"
MAX_ITEMS = 20

def log(msg):
    print(f"[apolut] {msg}")

def ensure_directories():
    if not os.path.exists(MEDIA_DIR):
        os.makedirs(MEDIA_DIR)
        log(f"Ordner erstellt: {MEDIA_DIR}")

def fetch_page(url):
    log(f"Lade Seite: {url}")
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.text

def extract_articles(html):
    soup = BeautifulSoup(html, "html.parser")
    posts = soup.find_all("article")

    episodes = []
    for p in posts:
        title_tag = p.find("h2")
        link_tag = p.find("a")

        if not title_tag or not link_tag:
            continue

        title = title_tag.get_text(strip=True)
        url = link_tag.get("href")

        episodes.append({
            "title": title,
            "url": url
        })

    return episodes[:MAX_ITEMS]

def download_audio(url, title):
    html = fetch_page(url)
    soup = BeautifulSoup(html, "html.parser")

    audio_tag = soup.find("audio")
    if not audio_tag:
        log(f"Kein Audio gefunden für: {title}")
        return None

    audio_src = audio_tag.get("src")
    if not audio_src:
        log(f"Audio-Tag ohne src für: {title}")
        return None

    filename = title.replace(" ", "_").replace("/", "_") + ".mp3"
    filepath = os.path.join(MEDIA_DIR, filename)

    log(f"Lade Audio: {audio_src}")
    r = requests.get(audio_src, timeout=30)
    r.raise_for_status()

    with open(filepath, "wb") as f:
        f.write(r.content)

    log(f"Audio gespeichert: {filepath}")
    return filepath

def build_rss(items):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "Apolut – Gesamtfeed"
    ET.SubElement(channel, "link").text = SOURCE_URL
    ET.SubElement(channel, "description").text = "Automatisch generierter Podcast-Feed"
    ET.SubElement(channel, "language").text = "de-DE"

    for ep in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = ep["title"]
        ET.SubElement(item, "link").text = ep["url"]

        guid = hashlib.md5(ep["url"].encode()).hexdigest()
        ET.SubElement(item, "guid").text = guid

        pub_date = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        ET.SubElement(item, "pubDate").text = pub_date

        if ep.get("audio"):
            enclosure = ET.SubElement(item, "enclosure")
            enclosure.set("url", ep["audio"])
            enclosure.set("type", "audio/mpeg")

    tree = ET.ElementTree(rss)
    tree.write(FEED_OUTPUT, encoding="utf-8", xml_declaration=True)
    log(f"RSS-Feed erstellt: {FEED_OUTPUT}")

def main():
    log("Starte Apolut Gesamtfeed Generator")

    ensure_directories()

    html = fetch_page(SOURCE_URL)
    episodes = extract_articles(html)

    final_items = []

    for ep in episodes:
        log(f"Verarbeite: {ep['title']}")
        audio_path = download_audio(ep["url"], ep["title"])

        if audio_path:
            ep["audio"] = audio_path

        final_items.append(ep)

    build_rss(final_items)

    log("Fertig!")

if __name__ == "__main__":
    main()

