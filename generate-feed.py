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

MAX_SIZE = 50 * 1024 * 1024  # 50 MB

def debug(msg: str):
    print(f"[DEBUG] {msg}")

def slugify(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")

def extract_slug_from_url(url: str) -> str:
    try:
        slug = url.rstrip("/").split("/")[-1]
        debug(f"Slug aus URL extrahiert: {slug}")
        return slug
    except:
        debug("Konnte Slug aus URL nicht extrahieren.")
        return ""

def extract_apolut_id(item) -> str:
    """
    Holt die Apolut-ID aus dem <guid> oder <dc:identifier> oder <id>-ähnlichen Feldern.
    Fallback: Hash aus Link.
    """
    possible_tags = ["guid", "id", "dc:identifier"]

    for tag in possible_tags:
        elem = item.find(tag)
        if elem is not None and elem.text:
            text = elem.text.strip()
            if re.fullmatch(r"[0-9a-f]{8,32}", text):
                debug(f"Apolut-ID gefunden: {text}")
                return text

    # Fallback: Hash aus Link
    link = item.findtext("link", "")
    fallback = re.sub(r"[^0-9a-f]", "", link.lower())[:16]
    debug(f"Apolut-ID Fallback: {fallback}")
    return fallback

def fetch_rss(url: str) -> str | None:
    try:
        debug(f"Lade RSS: {url}")
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        debug("RSS erfolgreich geladen.")
        return r.text
    except Exception as e:
        print(f"RSS-Fehler: {e}")
        return None

def extract_mp3_from_page(url: str) -> str | None:
    debug(f"HTML-Fallback: Lade Seite: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        debug(f"HTML-Fallback fehlgeschlagen: {e}")
        return None

    m = re.search(r"https://apolut\.net/content/media/[0-9]{4}/[0-9]{2}/[^\"']+\.mp3", html)
    if m:
        debug(f"HTML-Fallback MP3 gefunden: {m.group(0)}")
        return m.group(0)

    debug("HTML-Fallback: Keine MP3 gefunden.")
    return None

def try_construct_mp3_urls(date: str, title: str, url_slug: str) -> list[str]:
    dt = parsedate_to_datetime(date)
    yyyy = dt.strftime("%Y")
    mm = dt.strftime("%m")
    ymd = dt.strftime("%Y%m%d")

    title_slug = slugify(title)
    debug(f"Slug aus Titel: {title_slug}")

    title_slug_short = title_slug.split("-von-")[0] if "-von-" in title_slug else title_slug

    base = f"https://apolut.net/content/media/{yyyy}/{mm}"

    candidates = [
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

    debug("Generierte MP3-Kandidaten:")
    for c in candidates:
        debug(f"  {c}")

    return candidates

def check_url_exists(url: str) -> bool:
    try:
        r = requests.head(url, headers=HEADERS, timeout=10)
        debug(f"HEAD {url} → {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        debug(f"HEAD fehlgeschlagen: {e}")
        return False

def download_file(url: str, filename: Path) -> bool:
    debug(f"Starte Download: {url}")

    for attempt in range(3):
        try:
            debug(f"Download Versuch {attempt+1}")
            r = requests.get(url, headers=HEADERS, timeout=180, stream=True)
            r.raise_for_status()

            with open(filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)

            debug("Download erfolgreich.")
            return True

        except Exception as e:
            debug(f"Download fehlgeschlagen: {e}")
            time.sleep(5)

    debug("Download endgültig gescheitert.")
    return False

def compress_mp3(input_file: Path):
    bitrates = ["48k", "40k", "32k", "24k", "16k"]

    for br in bitrates:
        debug(f"Komprimiere mit {br}…")
        temp = input_file.with_suffix(f".{br}.tmp.mp3")

        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i", str(input_file),
                    "-b:a", br,
                    "-ac", "2",
                    str(temp)
                ],
                check=True
            )
        except Exception as e:
            debug(f"Komprimierung fehlgeschlagen: {e}")
            return False

        input_file.unlink()
        temp.rename(input_file)

        size = input_file.stat().st_size
        debug(f"Dateigröße nach {br}: {size/1024/1024:.2f} MB")

        if size <= MAX_SIZE:
            debug("Datei ist unter 50 MB → fertig.")
            return True

    debug("Selbst 16kbit ist noch zu groß → Datei wird gelöscht.")
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

        debug("---")
        debug(f"Episode: {title}")
        debug(f"Link: {link}")
        debug(f"Datum: {pubDate}")

        url_slug = extract_slug_from_url(link)
        apolut_id = extract_apolut_id(item)

        mp3 = enclosure.attrib.get("url", "") if enclosure is not None else None
        if mp3:
            debug(f"MP3 aus RSS: {mp3}")

        if not mp3:
            debug("Keine MP3 im RSS → HTML-Fallback")
            mp3 = extract_mp3_from_page(link)

        if not mp3:
            debug("HTML-Fallback erfolglos → Ultra-Fallback")
            for candidate in try_construct_mp3_urls(pubDate, title, url_slug):
                if check_url_exists(candidate):
                    debug(f"Ultra-Fallback Treffer: {candidate}")
                    mp3 = candidate
                    break

        if not mp3:
            debug("KEINE MP3 GEFUNDEN → EPISODE ÜBERSPRUNGEN")
            continue

        items.append({
            "title": title,
            "link": link,
            "date": pubDate,
            "mp3": mp3,
            "id": apolut_id
        })

    return items

def build_rss(items: list[dict]) -> str:
    xml_items = []
    for t in items:
        if "local_mp3" not in t:
            debug(f"Episode ohne lokale MP3 → übersprungen: {t['title']}")
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
<description>Automatisch generierter Feed mit eindeutigen Dateinamen</description>
<language>de-de</language>
{''.join(xml_items)}
</channel>
</rss>
"""

def main():
    debug("Starte Feed-Generator…")

    xml = fetch_rss(RSS_URL)
    if not xml:
        print("FEHLER: Konnte RSS nicht laden.")
        return

    items = parse_rss(xml)

    debug("Lösche alte MP3-Dateien…")
    for f in MEDIA_DIR.glob("*.mp3"):
        try:
            f.unlink()
        except Exception as e:
            debug(f"Konnte alte Datei nicht löschen: {e}")

    for item in items:
        dt = parsedate_to_datetime(item["date"])
        date_str = dt.strftime("%Y-%m-%d")
        title_slug = slugify(item["title"])
        apolut_id = item["id"]

        base = f"{date_str}_{title_slug}_{apolut_id}"
        mp3_file = MEDIA_DIR / f"{base}.mp3"

        debug(f"Lade MP3: {mp3_file.name}")
        ok = download_file(item["mp3"], mp3_file)
        if not ok:
            debug("Download fehlgeschlagen → übersprungen.")
            continue

        debug("Komprimiere MP3…")
        ok = compress_mp3(mp3_file)
        if not ok:
            debug("Kompression fehlgeschlagen → übersprungen.")
            continue

        item["local_mp3"] = mp3_file.name

    rss = build_rss(items)
    Path("feed.xml").write_text(rss, encoding="utf-8")

    debug("Feed erfolgreich erzeugt.")

if __name__ == "__main__":
    main()

