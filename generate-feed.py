import requests
from pathlib import Path
from xml.etree import ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
import hashlib
import re
import subprocess
import time

# ---------------------------------------------------------
# Einstellungen
# ---------------------------------------------------------

RSS_URL = "https://api.allorigins.win/raw?url=https://apolut.net/podcast/rss"
JINA_PREFIX = "https://r.jina.ai/"
MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)

TARGET_SIZE = 50 * 1024 * 1024
KEEP_EPISODES = 10

# ---------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------

def fetch(url: str) -> str | None:
    """Lädt eine URL mit Timeout und Fehlerbehandlung."""
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return r.text
    except:
        return None

def hash_id(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]

def extract_mp3_links(html: str) -> list[str]:
    """Findet ALLE MP3-Links in einer HTML-Seite."""
    patterns = [
        r"https://apolut\.net/content/media/[0-9]{4}/[0-9]{2}/[^\"']+\.mp3",
        r"https://apolut\.net/wp-content/uploads/[0-9]{4}/[0-9]{2}/[^\"']+\.mp3",
        r"https://apolut\.net/wp-content/uploads/[^\"']+\.mp3",
        r"<audio[^>]+src=\"(https://[^\"]+\.mp3)\"",
        r"property=\"og:audio\" content=\"(https://[^\"]+\.mp3)\""
    ]

    links = []
    for p in patterns:
        for m in re.findall(p, html):
            links.append(m if isinstance(m, str) else m[0])

    return list(dict.fromkeys(links))  # Duplikate entfernen

def extract_date_from_mp3(mp3_url: str) -> str:
    """Extrahiert Datum aus MP3-Dateinamen (Option B)."""
    m = re.search(r"tagesdosis-(\d{8})", mp3_url)
    if not m:
        return datetime.now().strftime("%d.%m.%Y")

    d = datetime.strptime(m.group(1), "%Y%m%d")
    return d.strftime("%d.%m.%Y")

def download_file(url: str, filename: Path) -> bool:
    """Lädt eine Datei herunter."""
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
    """Komprimiert MP3 auf 12k Mono."""
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
# Tagesdosis finden
# ---------------------------------------------------------

def find_latest_tagesdosis():
    """Findet die neueste Tagesdosis über die Startseite (via Jina)."""
    html = fetch(JINA_PREFIX + "https://apolut.net/")
    if not html:
        return None

    # Alle Links extrahieren
    links = re.findall(r"https://apolut\.net/[^\"]+/", html)

    # Nur Tagesdosis-Links
    td_links = [l for l in links if "tagesdosis" in l]

    if not td_links:
        return None

    # Neuesten Link nehmen
    return sorted(set(td_links))[-1]

def process_tagesdosis():
    """Lädt Tagesdosis + MP3."""
    url = find_latest_tagesdosis()
    if not url:
        return None

    html = fetch(JINA_PREFIX + url)
    if not html:
        return None

    mp3s = extract_mp3_links(html)
    if not mp3s:
        return None

    mp3 = mp3s[0]

    # Titel extrahieren
    m = re.search(r"<title>([^<]+)</title>", html)
    title = m.group(1).replace(" – apolut.net", "") if m else "Tagesdosis"
    title = f"Tagesdosis – {title}"

    # Datum aus MP3
    date_str = extract_date_from_mp3(mp3)

    # ID
    guid = hash_id(title)

    # Dateiname
    filename = MEDIA_DIR / f"{date_str}_tagesdosis_{guid}.mp3"

    if download_file(mp3, filename):
        compress_12k_mono(filename)
        return {
            "title": title,
            "link": url,
            "date": datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000"),
            "local_mp3": filename.name,
            "id": guid
        }

    return None

# ---------------------------------------------------------
# RSS verarbeiten
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

        dt = parsedate_to_datetime(pub)
        date_str = dt.strftime("%a_%d_%b_%Y")

        filename = MEDIA_DIR / f"{date_str}_{guid}.mp3"

        if download_file(mp3, filename):
            compress_12k_mono(filename)
            items.append({
                "title": title,
                "link": link,
                "date": pub,
                "local_mp3": filename.name,
                "id": guid
            })

        if len(items) >= KEEP_EPISODES - 1:
            break

    return items

# ---------------------------------------------------------
# RSS bauen
# ---------------------------------------------------------

def build_rss(items):
    xml_items = []
    for t in items:
        xml_items.append(f"""
<item>
<title>{t['title']}</title>
<link>{t['link']}</link>
<description><![CDATA[{t['title']}]]></description>
<enclosure url="https://peter-sobi.github.io/podcast/media/{t['local_mp3']}" length="0" type="audio/mpeg"/>
<guid>{t['id']}</guid>
<pubDate>{t['date']}</pubDate>
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
# Hauptprogramm
# ---------------------------------------------------------

def main():
    # Tagesdosis
    td = process_tagesdosis()

    # RSS
    rss_items = process_rss()

    # Wenn NICHTS gefunden → NICHT überschreiben (Option A)
    if not td and not rss_items:
        print("Nichts gefunden – alter Feed bleibt erhalten.")
        return

    items = []
    if td:
        items.append(td)
    items.extend(rss_items)

    rss = build_rss(items)
    Path("feed.xml").write_text(rss, encoding="utf-8")
    print("Feed erfolgreich aktualisiert.")

if __name__ == "__main__":
    main()

