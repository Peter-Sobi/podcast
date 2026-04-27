import requests
from xml.etree import ElementTree as ET
from pathlib import Path
import subprocess
import re
from email.utils import parsedate_to_datetime

RSS_URL = "https://apolut.net/podcast/rss"
HEADERS = {"User-Agent": "Mozilla/5.0"}

MEDIA_DIR = Path("media_test")
MEDIA_DIR.mkdir(exist_ok=True)

def fetch_rss():
    r = requests.get(RSS_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def find_tagesdosis(xml_text):
    root = ET.fromstring(xml_text)
    channel = root.find("channel")

    for item in channel.findall("item"):
        title = item.findtext("title", "").lower()
        if "tagesdosis" in title:
            enclosure = item.find("enclosure")
            if enclosure is not None:
                return enclosure.attrib.get("url"), item.findtext("title")
    return None, None

def download(url, filename):
    r = requests.get(url, headers=HEADERS, timeout=180, stream=True)
    r.raise_for_status()
    with open(filename, "wb") as f:
        for chunk in r.iter_content(1024 * 256):
            if chunk:
                f.write(chunk)

def compress_12k_mono(input_file):
    temp = input_file.with_suffix(".tmp.mp3")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", str(input_file),
            "-b:a", "12k",
            "-ac", "1",
            str(temp)
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True
    )
    input_file.unlink()
    temp.rename(input_file)

def main():
    print("Lade RSS…")
    xml = fetch_rss()

    print("Suche Tagesdosis…")
    mp3_url, title = find_tagesdosis(xml)

    if not mp3_url:
        print("Keine Tagesdosis gefunden!")
        return

    print("Gefunden:", title)
    print("URL:", mp3_url)

    out = MEDIA_DIR / "tagesdosis_test.mp3"

    print("Lade Datei…")
    download(mp3_url, out)

    print("Komprimiere auf 12 kbit Mono…")
    compress_12k_mono(out)

    size = out.stat().st_size / 1024 / 1024
    print(f"FERTIG! Größe: {size:.2f} MB")

if __name__ == "__main__":
    main()
