#!/usr/bin/env python3
# generate-feed-auf1.py
# Updated: ensure enclosure length, HEAD-check for accessibility and Accept-Ranges,
# write directly into media_auf1, no extra folders.

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import re
import os
import html
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import quote, urlparse
import sys
import time
import subprocess
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil

# -------------------------
# Configuration
# -------------------------
FEED_URL = "https://auf1.radio/api/feed"
API_GET = "https://auf1.radio/api/get/"
MEDIA_DIR = "media_auf1"
OUTPUT_FEED = "feed_auf1.xml"
BASE_URL = "https://peter-sobi.github.io/podcast/media_auf1/"  # must match your Pages URL

USER_AGENT = "github-actions/auf1-feed-generator (+https://github.com/peter-sobi/podcast)"
REQUEST_TIMEOUT = 12
MAX_ITEMS = 20
MIN_SIZE_BYTES = 30 * 1024
MAX_SIZE_BYTES = 8 * 1024 * 1024
KEEP_STEREO_MAX_BITRATE = 64000
REENCODE_BITRATE = "32k"
REENCODE_SAMPLE_RATE = 22050
LOG_FILE = "logs/auf1.log"
RETRY_TOTAL = 2
RETRY_BACKOFF = 0.5
DEFAULT_WORKERS = 1
DOWNLOAD_CHUNK = 131072
ALLOW_KEEP_STEREO = True

# Network-specific
MAX_DOWNLOAD_ATTEMPTS = 4
INITIAL_BACKOFF = 1.0
MAX_BACKOFF = 16.0

# Ensure directories exist
os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# -------------------------
# Logging
# -------------------------
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
# HTTP session
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
# Helpers
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
        logger.warning("ffmpeg error: %s", e)
        return False

def copy_without_reencode(src_path, dst_path):
    try:
        cmd = ["ffmpeg", "-y", "-threads", "1", "-i", src_path, "-c:a", "copy", dst_path]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False

# -------------------------
# Download with resume into MEDIA_DIR using .part files
# -------------------------
def download_with_resume(url, part_path):
    attempt = 0
    backoff = INITIAL_BACKOFF
    while attempt < MAX_DOWNLOAD_ATTEMPTS:
        attempt += 1
        try:
            headers = {}
            existing_size = 0
            if os.path.exists(part_path):
                existing_size = os.path.getsize(part_path)
                if existing_size > 0:
                    headers['Range'] = f'bytes={existing_size}-'
                    logger.info("Resuming download from byte %d for %s", existing_size, url)
            with session.get(url, timeout=REQUEST_TIMEOUT, stream=True, headers=headers) as r:
                if r.status_code in (200, 206):
                    mode = "ab" if 'Range' in headers and r.status_code == 206 else "wb"
                    with open(part_path, mode) as f:
                        for chunk in r.iter_content(chunk_size=DOWNLOAD_CHUNK):
                            if chunk:
                                f.write(chunk)
                    size = os.path.getsize(part_path)
                    if size < MIN_SIZE_BYTES:
                        logger.warning("Downloaded size too small (%d) for %s", size, url)
                        raise IOError("Downloaded too small")
                    return True
                else:
                    logger.warning("Unexpected status %s for %s", r.status_code, url)
                    if r.status_code == 416 and os.path.exists(part_path):
                        os.remove(part_path)
        except Exception as e:
            logger.warning("Download attempt %d failed for %s: %s", attempt, url, e)
            time.sleep(min(backoff, MAX_BACKOFF))
            backoff *= 2
            continue
    logger.error("All download attempts failed for %s", url)
    return False

# -------------------------
# Download + prepare (writes into MEDIA_DIR)
# -------------------------
def download_and_prepare(audio_url, title):
    filename = sanitize_filename(title) + ".mp3"
    final_path = os.path.join(MEDIA_DIR, filename)
    part_path = final_path + ".part"

    # HEAD quick check
    try:
        h = session.head(audio_url, timeout=8, allow_redirects=True)
        if h.status_code == 200:
            ctype = h.headers.get("Content-Type","")
            clen = h.headers.get("Content-Length")
            if ctype and "audio" not in ctype and "mpeg" not in ctype:
                logger.warning("Content-Type not audio for %s: %s", audio_url, ctype)
                return None
            if clen:
                try:
                    if int(clen) < MIN_SIZE_BYTES:
                        logger.warning("Remote Content-Length too small (%s) for %s", clen, audio_url)
                        return None
                except Exception:
                    pass
    except Exception as e:
        logger.info("HEAD failed (will attempt download): %s", e)

    # If final exists and valid, skip
    if os.path.exists(final_path):
        try:
            size = os.path.getsize(final_path)
            if size >= MIN_SIZE_BYTES:
                logger.info("Final file already exists, skipping download: %s", filename)
                return filename
        except Exception:
            pass

    t0 = time.time()
    ok = download_with_resume(audio_url, part_path)
    dt = time.time() - t0
    logger.info("Download step for '%s' finished status=%s duration=%.1f s", title, ok, dt)
    if not ok:
        return None

    # Probe
    info = probe_audio(part_path)
    channels = int(info.get("channels","2")) if info.get("channels") else 2
    bit_rate = int(info.get("bit_rate","0")) if info.get("bit_rate") else 0
    try:
        size = os.path.getsize(part_path)
    except Exception:
        size = 0
    logger.info("Probe info for %s: channels=%s bit_rate=%s size=%d", filename, channels, bit_rate, size)

    try_copy = False
    need_reencode = False

    if ALLOW_KEEP_STEREO and channels == 2 and bit_rate and bit_rate <= KEEP_STEREO_MAX_BITRATE:
        try_copy = True
    elif channels == 1 and bit_rate and bit_rate <= 32000:
        try_copy = True
    elif size > MAX_SIZE_BYTES or (bit_rate and bit_rate > KEEP_STEREO_MAX_BITRATE):
        need_reencode = True
    else:
        try_copy = True

    if try_copy:
        ok_copy = copy_without_reencode(part_path, final_path)
        logger.info("Copy attempt for '%s' result=%s", title, ok_copy)
        if ok_copy:
            try:
                os.remove(part_path)
            except Exception:
                pass
            # quick HEAD to ensure file is served by hosting
            time.sleep(0.5)
            if not verify_remote_file(final_path, filename):
                logger.warning("After copy, remote HEAD check failed for %s", filename)
            return filename
        else:
            logger.info("Copy failed, will reencode for %s", title)
            need_reencode = True

    if need_reencode:
        reencoded = final_path + ".re.mp3"
        ok_re = reencode_to_32k(part_path, reencoded)
        logger.info("Reencode for '%s' result=%s", title, ok_re)
        try:
            os.remove(part_path)
        except Exception:
            pass
        if not ok_re:
            if os.path.exists(reencoded):
                os.remove(reencoded)
            return None
        os.replace(reencoded, final_path)
        time.sleep(0.5)
        if not verify_remote_file(final_path, filename):
            logger.warning("After reencode, remote HEAD check failed for %s", filename)
        return filename

    # fallback
    try:
        os.replace(part_path, final_path)
        time.sleep(0.5)
        if not verify_remote_file(final_path, filename):
            logger.warning("After move, remote HEAD check failed for %s", filename)
        return filename
    except Exception as e:
        logger.warning("Fallback move failed for %s: %s", filename, e)
        return None

# -------------------------
# Verify remote HEAD for BASE_URL + filename (only logs; hosting must serve files)
# -------------------------
def verify_remote_file(local_path, filename):
    url = BASE_URL + quote(filename)
    try:
        r = session.head(url, timeout=8, allow_redirects=True)
        if r.status_code == 200:
            # check Accept-Ranges header
            ar = r.headers.get("Accept-Ranges", "")
            if not ar:
                logger.warning("Remote does not advertise Accept-Ranges for %s (may break mobile playback).", url)
            return True
        else:
            logger.warning("Remote HEAD returned %s for %s", r.status_code, url)
            return False
    except Exception as e:
        logger.warning("Remote HEAD failed for %s: %s", url, e)
        return False

# -------------------------
# Worker
# -------------------------
def process_entry(entry):
    title = getattr(entry, "title", "AUF1 Beitrag")
    link = getattr(entry, "link", None)
    pubdate = getattr(entry, "published", None) or getattr(entry, "updated", None)
    logger.info("Processing: %s", title)
    slug = slug_from_link(link)
    if not slug:
        logger.warning("No slug from link: %s", link)
        return None
    audio_url = get_audio_url_from_api(slug)
    if not audio_url:
        logger.warning("No audio URL for slug: %s", slug)
        return None
    filename = download_and_prepare(audio_url, title)
    if filename:
        return (title, filename, pubdate)
    else:
        logger.warning("Failed to get file for: %s", title)
        return None

# -------------------------
# API helper
# -------------------------
def get_audio_url_from_api(slug):
    api_url = API_GET + slug
    try:
        logger.info("API request: %s", api_url)
        r = session.get(api_url, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            logger.warning("API returned %s for %s", r.status_code, api_url)
            return None
        data = r.json()
        audiofile = data.get("audiofile") or data.get("audio") or data.get("file")
        if not audiofile:
            logger.warning("No audiofile in API response for %s", api_url)
            return None
        if audiofile.startswith("http://") or audiofile.startswith("https://"):
            return audiofile
        return f"https://auf1.radio/storage/{audiofile}"
    except Exception as e:
        logger.warning("API error for %s: %s", api_url, e)
        return None

# -------------------------
# Feed builder (includes enclosure length and type)
# -------------------------
def build_feed(entries):
    items_xml = ""
    for title, filename, pubdate in entries:
        url = BASE_URL + quote(filename)
        local_path = os.path.join(MEDIA_DIR, filename)
        length = 0
        try:
            length = os.path.getsize(local_path)
        except Exception:
            length = 0
        pd = pubdate
        if pd:
            try:
                # feedparser gives structured time; convert if needed
                pd = format_datetime(datetime.now(timezone.utc))
            except Exception:
                pd = format_datetime(datetime.now(timezone.utc))
        else:
            pd = format_datetime(datetime.now(timezone.utc))
        items_xml += f"""
        <item>
            <title>{html.escape(title)}</title>
            <link>{url}</link>
            <enclosure url="{url}" length="{length}" type="audio/mpeg" />
            <guid isPermaLink="false">{html.escape(url)}</guid>
            <pubDate>{pd}</pubDate>
        </item>
        """

    feed_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
    <title>AUF1 Radio</title>
    <link>https://peter-sobi.github.io/podcast/</link>
    <description>Automatisch generierter AUF1 Radio Feed</description>
    {items_xml}
</channel>
</rss>
"""
    with open(OUTPUT_FEED, "w", encoding="utf-8") as f:
        f.write(feed_xml)
    logger.info("Feed written: %s", OUTPUT_FEED)

# -------------------------
# Main
# -------------------------
def main(max_workers=DEFAULT_WORKERS):
    logger.info("Loading feed: %s", FEED_URL)
    try:
        feed = feedparser.parse(FEED_URL)
    except Exception as e:
        logger.error("Feedparser error: %s", e)
        sys.exit(1)
    if not hasattr(feed, "entries") or len(feed.entries) == 0:
        logger.error("No entries in feed.")
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
                logger.warning("Worker exception: %s", e)
                res = None
            if res:
                processed.append(res)
            if len(processed) >= MAX_ITEMS:
                logger.info("Reached MAX_ITEMS (%d).", MAX_ITEMS)
                break

    if not processed:
        logger.error("No files downloaded; aborting.")
        sys.exit(2)

    processed = processed[:MAX_ITEMS]
    build_feed(processed)
    logger.info("Done. %d files processed.", len(processed))

if __name__ == "__main__":
    workers = DEFAULT_WORKERS
    if len(sys.argv) > 1:
        try:
            workers = int(sys.argv[1])
        except Exception:
            pass
    main(max_workers=workers)
