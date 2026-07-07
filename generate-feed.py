#!/usr/bin/env python3
import os
import sys
import re
import subprocess
import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

RSS_URL = "https://apolut.net/podcast/rss"
MEDIA_DIR = "media"
FEED_FILE = "feed.xml"

# Wie viele MP3-Dateien maximal behalten?
MAX_FILES = 60


def log(msg):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")


def sanitize_filename(name):
    bad = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for b in bad:
        name = name.replace(b, "")
    return name.replace(" ", "_")


def extract_date_from_url(url):
    """
    Extrahiert YYYYMMDD aus Apolut-Dateinamen.
    Gibt DD.MM zurück oder None.
    """
    m = re.search(r"(20\d{6})", url)
    if not m:
        return None

    yyyymmdd = m.group(1)
    year = int(yyyymmdd[0:4])
    month = int(yyyymmdd[4:6])
    day = int(yyyymmdd[6:8])

    return f"{day:02d}.{month:02d}"


def date_to_sort_key(date_prefix):
    """
    DD.MM → YYYYMMDD (für Sortierung)
    Episoden ohne Datum → sehr kleines Datum
    """
    if not date_prefix:
        return 0

    day, month = date_prefix.split(".")
    # Jahr ist unbekannt → wir nehmen 2026 (nur für Sortierung)
    return int(f"2026{month}{day}")


def download_file(url, path):
    log(f"[download] Lade Original-MP3: {url}")
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        log(f"[download] Fertig: {path}")
        return True
    except Exception as e:
        log(f"[error] Download fehlgeschlagen: {e}")
        return False


def reencode_to_32kbps(src, dst):
    """
    Reencode mit ffmpeg auf 32kbps MP3 (mono).
    """
    log(f"[ffmpeg] Reencode auf 32kbps: {dst}")
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", src,
                "-ac", "1",          # mono
                "-b:a", "32k",       # 32 kbps
                "-codec:a", "libmp3lame",
                dst,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        log(f"[error] ffmpeg Fehler: {e}")
        return False


def generate_feed(items):
    log("[feed] Erzeuge neuen RSS-Feed")

    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        '<channel>',
        '<title>Apolut Podcast – 32kbps Feed</title>',
        '<link>https://apolut.net</link>',
        '<description>Automatisch generierter Feed (32kbps, alte Dateien werden gelöscht)</description>'
    ]

    for item in items:
        xml.append("<item>")
        xml.append(f"<title>{item['feed_title']}</title>")
        xml.append(f"<link>{item['url']}</link>")
        xml.append(
            f"<enclosure url=\"{item['local_url']}\" type=\"audio/mpeg\"/>"
        )
        xml.append("</item>")

    xml.append("</channel>")
    xml.append("</rss>")

    with open(FEED_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(xml))

    log(f"[feed] Feed gespeichert: {FEED_FILE}")


def auto_delete_old_files():
    """
    Löscht alte MP3-Dateien im MEDIA_DIR, so dass maximal MAX_FILES übrig bleiben.
    Sortierung nach Änderungszeit (älteste zuerst).
    """
    log("[cleanup] Starte automatische Löschung alter Dateien")
    media_path = Path(MEDIA_DIR)
    files = sorted(
        [p for p in media_path.glob("*.mp3") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,  # neueste zuerst
    )

    if len(files) <= MAX_FILES:
        log(f"[cleanup] Es gibt nur {len(files)} Dateien – nichts zu löschen.")
        return

    to_delete = files[MAX_FILES:]
    for f in to_delete:
        log(f"[cleanup] Lösche alte Datei: {f.name}")
        try:
            f.unlink()
        except Exception as e:
            log(f"[cleanup] Fehler beim Löschen von {f.name}: {e}")


def main():
    log("[apolut] Starte MP3-Feed-Generator (32kbps + Auto-Delete)")
    log(f"[rss] Lade RSS: {RSS_URL}")

    try:
        r = requests.get(RSS_URL, timeout=30)
        r.raise_for_status()
    except Exception as e:
        log(f"[error] RSS konnte nicht geladen werden: {e}")
        sys.exit(1)

    soup = BeautifulSoup(r.text, "lxml-xml")
    rss_items = soup.find_all("item")

    if not rss_items:
        log("[apolut] FEHLER: RSS enthält keine Items – Abbruch.")
        sys.exit(0)

    os.makedirs(MEDIA_DIR, exist_ok=True)

    downloaded_items = []
    new_files = 0

    for item in rss_items:
        title_tag = item.find("title")
        enclosure = item.find("enclosure")

        if not title_tag or not enclosure:
            continue

        title = title_tag.text.strip()
        url = enclosure.get("url", "").strip()

        if not url or not url.endswith(".mp3"):
            log(f"[skip] Keine MP3-Datei: {url}")
            continue

        # Datum extrahieren
        date_prefix = extract_date_from_url(url)
        sort_key = date_to_sort_key(date_prefix)

        if date_prefix:
            feed_title = f"{date_prefix} – {title}"
            base_name = f"{date_prefix}_{sanitize_filename(title)}.mp3"
        else:
            feed_title = title
            base_name = sanitize_filename(title) + ".mp3"

        final_path = os.path.join(MEDIA_DIR, base_name)
        orig_path = final_path + ".orig"

        log(f"[episode] Gefunden: {feed_title}")

        if os.path.exists(final_path):
            log(f"[skip] Datei existiert bereits: {base_name}")
        else:
            # Original laden
            if download_file(url, orig_path):
                # Reencode
                if reencode_to_32kbps(orig_path, final_path):
                    new_files += 1
                    # Original nach erfolgreichem Reencode löschen
                    try:
                        os.remove(orig_path)
                    except OSError:
                        pass
                else:
                    # Bei ffmpeg-Fehler: Original behalten, aber nicht in Feed aufnehmen
                    log("[episode] ffmpeg fehlgeschlagen – Original bleibt als .orig, wird aber nicht in den Feed aufgenommen.")
            else:
                log("[episode] Download fehlgeschlagen – Episode wird übersprungen.")

        # Nur Episoden mit fertiger MP3 in den Feed aufnehmen
        if os.path.exists(final_path):
            downloaded_items.append({
                "title": title,
                "feed_title": feed_title,
                "url": url,
                "local_url": f"{base_name}",  # relativer Pfad im Repo
                "file": final_path,
                "sort_key": sort_key
            })

    if not downloaded_items:
        log("[apolut] WARNUNG: Keine MP3-Episoden gefunden – alter Feed bleibt bestehen.")
        sys.exit(0)

    # Neueste zuerst
    downloaded_items.sort(key=lambda x: x["sort_key"], reverse=True)

    # Feed erzeugen
    generate_feed(downloaded_items)

    # Alte Dateien löschen
    auto_delete_old_files()

    log(f"[apolut] Fertig. {new_files} neue Episoden verarbeitet.")


if __name__ == "__main__":
    main()

