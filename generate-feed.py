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

def extract_mp3_from_page(url: str) -> str | None:
    print(f"Fallback: Lade Episodenseite: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        print(f"Fallback-Fehler: Konnte Seite nicht laden ({e})")
        return None

    m = re.search(r"https://apolut\.net/content/media/[0-9]{4}/[0-9]{2}/[^\"']+\.mp3", html)
    if m:
        print(f"Fallback: MP3 auf Seite gefunden: {m.group(0)}")
        return m.group(0)

    print("Fallback: Keine MP3 auf der Seite gefunden.")
    return None

# ---------------------------------------------------------
# Ultra-Fallback 3.0 — deckt ALLE neuen Apolut-Muster ab
# ---------------------------------------------------------

def try_construct_mp3_urls(date: str, title: str) -> list[str]:
    dt = parsedate_to_datetime(date)
    yyyy = dt.strftime("%Y")
    mm = dt.strftime("%m")
    dd = dt.strftime("%d")
    ymd = dt.strftime("%Y%m%d")

    slug = slugify(title)

    slug_short = slug
    if "-von-" in slug:
        slug_short = slug.split("-von-")[0]

    base = f"https://apolut.net/content/media/{yyyy}/{mm}"

    candidates = [
        # 1. Slug direkt
        f"{base}/{slug}.mp3",
        f"{base}/{slug_short}.mp3",

        # 2. Slug + Datum
        f"{base}/{slug}-{ymd}.mp3",
        f"{base}/{slug_short}-{ymd}.mp3",

        # 3. Slug + Datum + apolut
        f"{base}/{slug}-{ymd}-apolut.mp3",
        f"{base}/{slug_short}-{ymd}-apolut.mp3",

        # 4. Tagesdosis klassische Muster
        f"{base}/tagesdosis-{ymd}.mp3",
        f"{base}/tagesdosis-{ymd}-apolut.mp3",

        # 5. Tagesdosis + Slug
        f"{base}/tagesdosis-{slug}.mp3",
        f"{base}/tagesdosis-{slug_short}.mp3",

        # 6. Slug + Tagesdosis
        f"{base}/{slug}-tagesdosis.mp3",
        f"{base}/{slug_short}-tagesdosis.mp3",
    ]

    return candidates

def check_url_exists(url: str) -> bool:
    try:
        r = requests.head(url, headers=HEADERS, timeout=10)
        return r.status_code == 200
    except:
        return False

def download_file(url: str, filename: Path) -> bool:
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

        mp3 = None
        if enclosure is not None:
            mp3 = enclosure.attrib.get("url", "")

        if not mp3:
            print(f"WARNUNG: Keine MP3 im RSS → versuche HTML-Fallback: {title}")
            mp3 = extract_mp3_from_page(link)

        if not mp3:
            print(f"WARNUNG: Ultra-Fallback aktiv für: {title}")
            for candidate in try_construct_mp3_urls(pubDate, title):
                print(f"Prüfe: {candidate}")
                if check_url_exists(candidate):
                    print(f"Ultra-Fallback: MP3 gefunden: {candidate}")
                    mp3 = candidate
                    break

        if not mp3:
            print(f"WARNUNG: Keine MP3 gefunden → übersprungen: {title}")
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
        if "local_mp3" not in t:
            print(f"WARNUNG: Episode ohne lokale MP3 → übersprungen: {t['title']}")
            continue

        xml_items.append(
f"""
<item>
<title>{t['title']}</title>
<link>{t['link']}</link>
<description><![CDATA[{t['title']}]]></description>
<enclosure url="https://peter-sobi.github.io/podcast/media/{t['local_mp3']}" length="0" type="audio/mpeg"/>
<guid>{t['link']}</guid>
<pubDate>{t['date']}</pubDate>
</item>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Apolut Kombinierter Podcast (48kbit)</title>
<link>https://apolut.net</link>
<description>Automatisch generierter Feed mit Ultra-Fallback 3.0</description>
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

    for f in MEDIA_DIR.glob("*.mp3"):
        try:
            f.unlink()
        except Exception as e:
            print(f"Konnte alte Datei nicht löschen: {e}")

    for item in items:
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

        item["local_mp3"] = mp3_file.name

    rss = build_rss(items)
    Path("feed.xml").write_text(rss, encoding="utf-8")

    print("feed.xml erfolgreich erzeugt.")

if __name__ == "__main__":
    main()

