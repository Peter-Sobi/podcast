#!/usr/bin/env python3
# AUF1 – lädt nur neue Episoden, niemals alte

import feedparser, requests, os, re, sys, subprocess, logging, html
from urllib.parse import urlparse, quote
from datetime import datetime, timezone
from email.utils import format_datetime

FEED_URL = "https://auf1.radio/api/feed"
API_GET = "https://auf1.radio/api/get/"
MEDIA_DIR = "media_auf1"
OUTPUT_FEED = "feed_auf1.xml"
BASE_URL = "https://peter-sobi.github.io/podcast/media_auf1/"

USER_AGENT = "auf1-feed-generator"
REQUEST_TIMEOUT = 15
MIN_SIZE = 30 * 1024
KEEP_STEREO_MAX = 64000
REENCODE_RATE = "32k"
REENCODE_SR = 22050

os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[logging.FileHandler("logs/auf1.log", encoding="utf-8"),
              logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("auf1")

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

def sanitize(name):
    name = name.strip().replace(" ", "_")
    return re.sub(r"[^A-Za-z0-9_\-äöüÄÖÜß\.]", "", name)[:120]

def slug_from_link(link):
    try:
        p = urlparse(link)
        return p.path.rstrip("/").split("/")[-1]
    except:
        return None

def probe(path):
    try:
        out = subprocess.check_output([
            "ffprobe","-v","error","-select_streams","a:0",
            "-show_entries","stream=channels,bit_rate",
            "-of","default=noprint_wrappers=1:nokey=0", path
        ], stderr=subprocess.DEVNULL).decode()
        info = {}
        for line in out.splitlines():
            if "=" in line:
                k,v = line.split("=",1)
                info[k]=v
        return info
    except:
        return {}

def reencode(src, dst):
    try:
        subprocess.run([
            "ffmpeg","-y","-threads","1","-i",src,
            "-ac","1","-ar",str(REENCODE_SR),
            "-b:a",REENCODE_RATE,"-af","loudnorm",dst
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except:
        return False

def copy_audio(src, dst):
    try:
        subprocess.run([
            "ffmpeg","-y","-threads","1","-i",src,
            "-c:a","copy",dst
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except:
        return False

def get_audio_url(slug):
    try:
        r = session.get(API_GET + slug, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None
        j = r.json()
        f = j.get("audiofile") or j.get("audio") or j.get("file")
        if not f:
            return None
        return f if f.startswith("http") else "https://auf1.radio/storage/" + f
    except:
        return None

def download(url, path):
    try:
        with session.get(url, timeout=REQUEST_TIMEOUT, stream=True) as r:
            if r.status_code != 200:
                return False
            with open(path, "wb") as f:
                for chunk in r.iter_content(65536):
                    if chunk:
                        f.write(chunk)
        return True
    except:
        return False

def process(entry):
    title = getattr(entry, "title", "AUF1 Beitrag")
    link = getattr(entry, "link", None)
    slug = slug_from_link(link)
    if not slug:
        return None

    audio = get_audio_url(slug)
    if not audio:
        return None

    filename = sanitize(title) + ".mp3"
    final = os.path.join(MEDIA_DIR, filename)
    tmp = final + ".part"

    # WICHTIG: Nur neue Episoden laden
    if os.path.exists(final) and os.path.getsize(final) > MIN_SIZE:
        log.info("Skip existing: %s", filename)
        return filename

    log.info("Downloading NEW: %s", filename)

    if not download(audio, tmp):
        log.warning("Download failed: %s", audio)
        return None

    size = os.path.getsize(tmp)
    if size < MIN_SIZE:
        log.warning("Too small: %s", filename)
        os.remove(tmp)
        return None

    info = probe(tmp)
    ch = int(info.get("channels","2"))
    br = int(info.get("bit_rate","0"))

    if ch == 2 and br <= KEEP_STEREO_MAX:
        if copy_audio(tmp, final):
            os.remove(tmp)
            return filename

    if reencode(tmp, final):
        os.remove(tmp)
        return filename

    return None

def build_feed(items):
    xml = ""
    for title, fn, pd in items:
        url = BASE_URL + quote(fn)
        length = os.path.getsize(os.path.join(MEDIA_DIR, fn))
        pub = format_datetime(datetime.now(timezone.utc))
        xml += f"""
        <item>
            <title>{html.escape(title)}</title>
            <link>{url}</link>
            <enclosure url="{url}" length="{length}" type="audio/mpeg" />
            <guid isPermaLink="false">{html.escape(url)}</guid>
            <pubDate>{pub}</pubDate>
        </item>
        """
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>AUF1 Radio</title>
<link>https://peter-sobi.github.io/podcast/</link>
<description>Automatisch generierter AUF1 Radio Feed</description>
{xml}
</channel></rss>"""
    with open(OUTPUT_FEED,"w",encoding="utf-8") as f:
        f.write(feed)

def main():
    log.info("Loading feed…")
    feed = feedparser.parse(FEED_URL)
    if not feed.entries:
        log.error("No entries")
        sys.exit(1)

    items = []
    for e in feed.entries:   # ALLE prüfen, aber nur neue laden
        r = process(e)
        if r:
            items.append((e.title, r, getattr(e,"published",None)))

    if not items:
        log.error("No files processed")
        sys.exit(2)

    build_feed(items)
    log.info("Done.")

if __name__ == "__main__":
    main()

