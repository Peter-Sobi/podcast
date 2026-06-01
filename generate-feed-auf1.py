#!/usr/bin/env python3
# generate-feed-auf1.py
# Optimiertes Script: schneller, sicherer, schreibt zuerst in media_auf1_tmp und promoted bei Erfolg.
# Merkmale:
# - Default seriell (workers=1) für schnellen Testlauf
# - HEAD-Check vor Download
# - ffprobe-Check: reencode nur wenn nötig
# - ffmpeg mit "-threads 1" und -ar 22050 für schnellere Reencodes
# - größere Download-Chunks, Time-Logging pro Schritt
# - atomarer Swap: media_auf1_tmp -> media_auf1 bei Erfolg
# - robustes Logging in logs/auf1.log

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import re
import os
import html
from datetime import datetime
from urllib.parse import quote, urlparse
import sys
import time
import subprocess
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil

# -------------------------
# Konfiguration
# -------------------------
FEED_URL = "https://auf1.radio/api/feed"
MEDIA_DIR = "media_auf1"
TMP_MEDIA_DIR = "media_auf1_tmp"
OUTPUT_FEED = "feed_auf1.xml"
BASE_URL = "https://peter-sobi.github.io/podcast/media_auf1/"
API_GET = "https://auf1.radio/api/get/"

USER_AGENT = "github-actions/auf1-feed-generator (+https://github.com/peter-sobi/podcast)"
REQUEST_TIMEOUT = 12
MAX_ITEMS = 20
MIN_SIZE_BYTES = 30 * 1024           # 30 KB minimal
MAX_SIZE_BYTES = 6 * 1024 * 1024     # 6 MB threshold to consider reencode
REENCODE_BITRATE = "32k"
REENCODE_SAMPLE_RATE = 22050         # schneller für Sprache
LOG_FILE = "logs/auf1.log"
RETRY_TOTAL = 3
RETRY_BACKOFF = 0.5
DEFAULT_WORKERS = 1                  # Default seriell; CLI-Arg erlaubt Änderung
DOWNLOAD_CHUNK = 65536               # größere Chunks für schnelleren Download

# -------------------------
# Setup Verzeichnisse + Logging
# -------------------------
os.makedirs(TMP_MEDIA_DIR, exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("auf1")

# -------------------------
# HTTP Session mit Retries
# -------------------------
def requests_session_with_retries(retries=RETRY_TOTAL, backoff=RETRY_BACKOFF, status_forcelist=(500,502,503,504)):
    s = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "POST", "HEAD"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": USER_AGENT})
    return s

session = requests_session_with_retries()

# -------------------------
# Hilfsfunktionen
# -------------------------
def sanitize_filename(name):
    name = name.strip()
    name = name.replace(" ", "_")
    name = re.sub(r"[^A-Za-z0-9_\-äöüÄÖÜß\.]", "", name)
    return name[:120]

def slug_from_link(link):
    try:
        p = urlparse(link)
        path = p.path.rstrip("/")
        if not path:
            return None
        slug = path.split("/")[-1]
        return slug
    except Exception:
        return None

def remote_size(url):
    try:
        r = session.head(url, timeout=8, allow_redirects=True)
        if r.status_code == 200 and 'Content-Length' in r.headers:
            return int(r.headers['Content-Length'])
    except Exception:
        pass
    return None

def probe_audio(path):
    # Gibt dict mit 'channels' und 'bit_rate' zurück, falls verfügbar
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=channels,bit_rate,sample_rate",
        "-of", "default=noprint_wrappers=1:nokey=0",
        path
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode()
        info = {}
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                info[k.strip()] = v.strip()
        return info
    except Exception:
        return {}

def reencode_to_32k(src_path, dst_path):
    # ffmpeg auf 1 Thread begrenzen, Sample-Rate 22050 für schnellere Verarbeitung
    cmd = [
        "ffmpeg", "-y", "-threads", "1", "-i", src_path,
        "-ac", "1", "-ar", str(REENCODE_SAMPLE_RATE),
        "-b:a", REENCODE_BITRATE,
        "-af", "loudnorm",
        dst_path
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        logger.warning("ffmpeg Fehler: %s", e)
        return False

def get_audio_url_from_api(slug):
    if not slug:
        return None
    api_url = API_GET + slug
    try:
        logger.info("API Anfrage: %s", api_url)
        r = session.get(api_url, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            logger.warning("API %s returned %s", api_url, r.status_code)
            return None
        data = r.json()
        audiofile = data.get("audiofile") or data.get("audio") or data.get("file")
        if not audiofile:
            logger.warning("Kein 'audiofile' in API-Antwort: %s", api_url)
            return None
        if audiofile.startswith("http://") or audiofile.startswith("https://"):
            return audiofile
        return f"https://auf1.radio/storage/{audiofile}"
    except Exception as e:
        logger.warning("Fehler beim API-Abruf %s: %s", api_url, e)
        return None

def download_stream(url, tmp_path, chunk_size=DOWNLOAD_CHUNK):
    try:
        logger.info("Lade herunter: %s", url)
        with session.get(url, timeout=REQUEST_TIMEOUT, stream=True) as r:
            if r.status_code != 200:
                logger.warning("Download fehlgeschlagen: %s %s", r.status_code, url)
                return False
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
        return True
    except Exception as e:
        logger.warning("Fehler beim Herunterladen %s: %s", url, e)
        return False

# -------------------------
# Download + Vorbereitung (schreibt in TMP_MEDIA_DIR)
# -------------------------
def download_and_prepare(audio_url, title):
    filename = sanitize_filename(title) + ".mp3"
    filepath = os.path.join(TMP_MEDIA_DIR, filename)
    tmp = filepath + ".part"

    # HEAD-Check
    rsize = remote_size(audio_url)
    if rsize is not None:
        logger.info("Remote Content-Length: %d bytes for %s", rsize, audio_url)
        if rsize < MIN_SIZE_BYTES:
            logger.warning("Remote Datei zu klein (%d bytes), überspringe: %s", rsize, audio_url)
            return None
        if rsize > 50 * 1024 * 1024:
            logger.info("Remote Datei sehr groß (%d bytes), wird heruntergeladen und ggf. reencoded.", rsize)

    # Download mit Zeitmessung
    t0 = time.time()
    ok = download_stream(audio_url, tmp)
    download_time = time.time() - t0
    logger.info("Download Dauer für '%s': %.1f s", title, download_time)

    if not ok:
        if os.path.exists(tmp):
            os.remove(tmp)
        return None

    # Größe prüfen
    try:
        size = os.path.getsize(tmp)
    except Exception as e:
        logger.warning("Fehler beim Lesen der Dateigröße: %s", e)
        if os.path.exists(tmp):
            os.remove(tmp)
        return None

    if size < MIN_SIZE_BYTES:
        logger.warning("Datei zu klein (%d bytes), verwerfe: %s", size, filename)
        os.remove(tmp)
        return None

    # ffprobe prüfen
    t_probe = time.time()
    info = probe_audio(tmp)
    probe_time = time.time() - t_probe
    logger.info("ffprobe Dauer für '%s': %.1f s", title, probe_time)

    channels = int(info.get("channels", "2")) if info.get("channels") else 2
    bit_rate = int(info.get("bit_rate", "0")) if info.get("bit_rate") else 0

    logger.info("Probe info for %s: channels=%s bit_rate=%s", filename, channels, bit_rate)

    # Reencode nur wenn nötig
    need_reencode = False
    if channels != 1:
        need_reencode = True
    if bit_rate and bit_rate > 32000:
        need_reencode = True
    if size > MAX_SIZE_BYTES:
        need_reencode = True

    if need_reencode:
        reencoded = filepath + ".re.mp3"
        logger.info("Reencode erforderlich für %s (Größe %d).", filename, size)
        t_re = time.time()
        ok = reencode_to_32k(tmp, reencoded)
        reencode_time = time.time() - t_re
        logger.info("Reencode Dauer für '%s': %.1f s", title, reencode_time)
        try:
            os.remove(tmp)
        except Exception:
            pass
        if not ok:
            logger.warning("Reencode fehlgeschlagen für %s", filename)
            if os.path.exists(reencoded):
                os.remove(reencoded)
            return None
        os.replace(reencoded, filepath)
    else:
        # Reencode überspringen spart Zeit
        os.replace(tmp, filepath)
        logger.info("Reencode übersprungen für %s (bereits mono/klein genug).", filename)

    final_size = os.path.getsize(filepath)
    logger.info("Gespeichert: %s (Größe: %d bytes)", filename, final_size)
    return filename

# -------------------------
# Worker-Funktion
# -------------------------
def process_entry(entry):
    title = getattr(entry, "title", "AUF1 Beitrag")
    link = getattr(entry, "link", None)
    pubdate = getattr(entry, "published", None) or getattr(entry, "updated", None)

    logger.info("Starte Verarbeitung: %s", title)
    slug = slug_from_link(link)
    if not slug:
        logger.warning("Keine slug aus Link extrahierbar: %s", link)
        return None

    audio_url = get_audio_url_from_api(slug)
    if not audio_url:
        logger.warning("Keine Audio-URL gefunden für slug: %s", slug)
        return None

    filename = download_and_prepare(audio_url, title)
    if filename:
        return (title, filename, pubdate)
    else:
        logger.warning("Download/Reencode fehlgeschlagen für: %s", title)
        return None

# -------------------------
# Feed-Erzeugung
# -------------------------
def build_feed(entries):
    items_xml = ""
    for title, filename, pubdate in entries:
        url = BASE_URL + quote(filename)
        pd = pubdate or datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        items_xml += f"""
        <item>
            <title>{html.escape(title)}</title>
            <link>{url}</link>
            <enclosure url="{url}" type="audio/mpeg" />
            <pubDate>{pd}</pubDate>
        </item>
        """

    feed_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
    <title>AUF1 Radio (32kbps)</title>
    <link>https://peter-sobi.github.io/podcast/</link>
    <description>Automatisch generierter AUF1 Radio Feed</description>
    {items_xml}
</channel>
</rss>
"""
    with open(OUTPUT_FEED, "w", encoding="utf-8") as f:
        f.write(feed_xml)
    logger.info("Feed erzeugt: %s", OUTPUT_FEED)

# -------------------------
# Main
# -------------------------
def main(max_workers=DEFAULT_WORKERS):
    logger.info("Lade RSS-Feed… %s", FEED_URL)
    try:
        feed = feedparser.parse(FEED_URL)
    except Exception as e:
        logger.error("Feedparser Fehler: %s", e)
        sys.exit(1)

    if not hasattr(feed, "entries") or len(feed.entries) == 0:
        logger.error("Feed enthält keine Einträge.")
        sys.exit(1)

    # Sortiere nach Datum absteigend (neueste zuerst)
    try:
        entries = sorted(feed.entries, key=lambda e: getattr(e, "published_parsed", time.gmtime(0)), reverse=True)
    except Exception:
        entries = feed.entries

    processed = []
    # Parallelisierung optional; default seriell (1)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(process_entry, e): e for e in entries}
        for fut in as_completed(futures):
            try:
                res = fut.result()
            except Exception as e:
                logger.warning("Worker Exception: %s", e)
                res = None
            if res:
                processed.append(res)
            if len(processed) >= MAX_ITEMS:
                logger.info("Maximale Anzahl Items erreicht (%d).", MAX_ITEMS)
                break

    if not processed:
        logger.error("Keine Dateien heruntergeladen. Feed wird nicht erzeugt.")
        sys.exit(2)

    processed = processed[:MAX_ITEMS]
    build_feed(processed)
    logger.info("Feed erzeugt, bereite Promotion des Media-Ordners vor.")

    # Atomare Promotion: tmp -> media_auf1
    try:
        # Backup alten Ordner falls vorhanden
        if os.path.isdir(MEDIA_DIR):
            backup = MEDIA_DIR + ".old"
            if os.path.isdir(backup):
                shutil.rmtree(backup)
            os.replace(MEDIA_DIR, backup)
            logger.info("Altes %s nach %s verschoben.", MEDIA_DIR, backup)
        os.replace(TMP_MEDIA_DIR, MEDIA_DIR)
        logger.info("Promotion abgeschlossen: %s -> %s", TMP_MEDIA_DIR, MEDIA_DIR)
    except Exception as e:
        logger.warning("Promotion fehlgeschlagen: %s", e)
        logger.info("Stelle sicher, dass %s existiert und manuell verschiebe falls nötig.", TMP_MEDIA_DIR)

    logger.info("Fertig. %d Dateien verarbeitet.", len(processed))

if __name__ == "__main__":
    # CLI-Arg erlaubt Änderung der Worker-Anzahl: z.B. python3 generate-feed-auf1.py 1
    workers = DEFAULT_WORKERS
    if len(sys.argv) > 1:
        try:
            workers = int(sys.argv[1])
        except Exception:
            pass
    main(max_workers=workers)
