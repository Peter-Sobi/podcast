#!/usr/bin/env python3
# generate-feed-auf1.py
# Optimiert: Stereo bis 64k wird übernommen (kein reencode), reencode nur wenn nötig.
# Features: HEAD-Check, ffprobe, ffmpeg -threads 1, time logs, tmp->media promotion

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
API_GET = "https://auf1.radio/api/get/"
TMP_MEDIA_DIR = "media_auf1_tmp"
MEDIA_DIR = "media_auf1"
OUTPUT_FEED = "feed_auf1.xml"
BASE_URL = "https://peter-sobi.github.io/podcast/media_auf1/"

USER_AGENT = "github-actions/auf1-feed-generator (+https://github.com/peter-sobi/podcast)"
REQUEST_TIMEOUT = 12
MAX_ITEMS = 20
MIN_SIZE_BYTES = 30 * 1024           # 30 KB minimal
MAX_SIZE_BYTES = 8 * 1024 * 1024     # 8 MB threshold to consider reencode
# Wenn Original-Bitrate <= KEEP_STEREO_MAX_BITRATE und Stereo erlaubt, dann kein reencode
KEEP_STEREO_MAX_BITRATE = 64000      # 64 kbps
REENCODE_BITRATE = "32k"
REENCODE_SAMPLE_RATE = 22050
LOG_FILE = "logs/auf1.log"
RETRY_TOTAL = 3
RETRY_BACKOFF = 0.5
DEFAULT_WORKERS = 1
DOWNLOAD_CHUNK = 65536

# Wenn True: akzeptiere Stereo-Audio (kein erzwungener Mono-Reencode) solange bitrate <= KEEP_STEREO_MAX_BITRATE
ALLOW_KEEP_STEREO = True

# -------------------------
# Setup
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
    retry = Retry(total=retries, backoff_factor=backoff, status_forcelist=status_forcelist, allowed_methods=["GET","POST","HEAD"])
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
        return path.split("/")[-1]
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

def copy_without_reencode(src_path, dst_path):
    # Versuche Container/Codec unverändert zu kopieren; falls nicht möglich, fallback auf reencode
    try:
        cmd = ["ffmpeg", "-y", "-threads", "1", "-i", src_path, "-c:a", "copy", dst_path]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        # fallback: reencode
        return reencode_to_32k(src_path, dst_path)

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
    tmp_path = os.path.join(TMP_MEDIA_DIR, filename + ".part")
    final_path = os.path.join(TMP_MEDIA_DIR, filename)
    # HEAD-Check
    rsize = remote_size(audio_url)
    if rsize is not None:
        logger.info("Remote Content-Length: %d bytes for %s", rsize, audio_url)
        if rsize < MIN_SIZE_BYTES:
            logger.warning("Remote Datei zu klein (%d bytes), überspringe: %s", rsize, audio_url)
            return None
        if rsize > 100 * 1024 * 1024:
            logger.warning("Remote Datei extrem groß (%d bytes), überspringe: %s", rsize, audio_url)
            return None

    # Download
    t0 = time.time()
    ok = download_stream(audio_url, tmp_path)
    download_time = time.time() - t0
    logger.info("Download Dauer für '%s': %.1f s", title, download_time)
    if not ok:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return None

    # Größe prüfen
    try:
        size = os.path.getsize(tmp_path)
    except Exception as e:
        logger.warning("Fehler beim Lesen der Dateigröße: %s", e)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return None

    if size < MIN_SIZE_BYTES:
        logger.warning("Datei zu klein (%d bytes), verwerfe: %s", size, filename)
        os.remove(tmp_path)
        return None

    # ffprobe
    t_probe = time.time()
    info = probe_audio(tmp_path)
    probe_time = time.time() - t_probe
    logger.info("ffprobe Dauer für '%s': %.1f s", title, probe_time)

    channels = int(info.get("channels", "2")) if info.get("channels") else 2
    bit_rate = int(info.get("bit_rate", "0")) if info.get("bit_rate") else 0
    logger.info("Probe info for %s: channels=%s bit_rate=%s size=%d", filename, channels, bit_rate, size)

    # Entscheidung: übernehmen, copy oder reencode
    # 1) Wenn ALLOW_KEEP_STEREO und channels==2 und bit_rate <= KEEP_STEREO_MAX_BITRATE -> copy (kein reencode)
    # 2) Wenn bit_rate <= 32000 and channels==1 -> copy (bereits ok)
    # 3) Wenn size > MAX_SIZE_BYTES oder bit_rate > KEEP_STEREO_MAX_BITRATE -> reencode auf 32k mono
    # 4) Sonst: copy if possible, else reencode
    try_copy = False
    need_reencode = False

    if ALLOW_KEEP_STEREO and channels == 2 and bit_rate and bit_rate <= KEEP_STEREO_MAX_BITRATE:
        logger.info("Stereo <= %d detected and allowed — versuche Copy ohne Reencode.", KEEP_STEREO_MAX_BITRATE)
        try_copy = True
    elif channels == 1 and bit_rate and bit_rate <= 32000:
        logger.info("Mono <=32k detected — Copy ohne Reencode.")
        try_copy = True
    elif size > MAX_SIZE_BYTES or (bit_rate and bit_rate > KEEP_STEREO_MAX_BITRATE):
        logger.info("Datei zu groß oder Bitrate zu hoch — Reencode erforderlich.")
        need_reencode = True
    else:
        # Default: try copy first to save time
        try_copy = True

    if try_copy:
        t_copy = time.time()
        ok_copy = copy_without_reencode(tmp_path, final_path)
        copy_time = time.time() - t_copy
        logger.info("Copy/Rewrap Dauer für '%s': %.1f s (ok=%s)", title, copy_time, ok_copy)
        if ok_copy:
            final_size = os.path.getsize(final_path)
            logger.info("Gespeichert (copy): %s (Größe: %d bytes)", filename, final_size)
            # remove tmp if exists
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            return filename
        else:
            logger.info("Copy fehlgeschlagen, fallback auf Reencode.")
            need_reencode = True

    if need_reencode:
        reencoded = final_path + ".re.mp3"
        t_re = time.time()
        ok_re = reencode_to_32k(tmp_path, reencoded)
        re_time = time.time() - t_re
        logger.info("Reencode Dauer für '%s': %.1f s (ok=%s)", title, re_time, ok_re)
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        if not ok_re:
            logger.warning("Reencode fehlgeschlagen für %s", filename)
            if os.path.exists(reencoded):
                os.remove(reencoded)
            return None
        os.replace(reencoded, final_path)
        final_size = os.path.getsize(final_path)
        logger.info("Gespeichert (reencode): %s (Größe: %d bytes)", filename, final_size)
        return filename

    # Fallback: falls nichts oben zurückgegeben wurde
    if os.path.exists(tmp_path):
        try:
            os.replace(tmp_path, final_path)
            logger.info("Gespeichert (fallback move): %s", filename)
            return filename
        except Exception as e:
            logger.warning("Fallback move fehlgeschlagen: %s", e)
            return None
    return None

# -------------------------
# Worker
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
# Feed builder
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
    <title>AUF1 Radio (optimized)</title>
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

    try:
        entries = sorted(feed.entries, key=lambda e: getattr(e, "published_parsed", time.gmtime(0)), reverse=True)
    except Exception:
        entries = feed.entries

    processed = []
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
    logger.info("Feed erzeugt, versuche Promotion des Media-Ordners.")

    # Atomare Promotion: tmp -> media_auf1
    try:
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
        logger.info("Stelle sicher, dass %s existiert und verschiebe manuell falls nötig.", TMP_MEDIA_DIR)

    logger.info("Fertig. %d Dateien verarbeitet.", len(processed))

if __name__ == "__main__":
    workers = DEFAULT_WORKERS
    if len(sys.argv) > 1:
        try:
            workers = int(sys.argv[1])
        except Exception:
            pass
    main(max_workers=workers)
