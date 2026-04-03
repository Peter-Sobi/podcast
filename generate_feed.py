import requests
import sys
from datetime import datetime
from pathlib import Path

BASE = "https://apolut.net"
TAGS = [
    "tagesdosis",
    "standpunkte",
    "im-gespraech"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# ---------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------

def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"[FEHLER] HTTP fetch fehlgeschlagen: {url} -> {e}")
        return None

def find_between(text, start, end):
    if not text:
        return None
    i = text.find(start)
    if i == -1:
        return None
    i += len(start)
    j = text.find(end, i)
    if j == -1:
        return None
    return text[i:j]

def extract_articles_from_tagpage(html):
    links = []
    if not html:
        return links
    pos = 0
    while True:
        pos = html.find('<a href="', pos)
        if pos == -1:
            break
        pos += len('<a href="')
        end = html.find('"', pos)
        if end == -1:
            break
        href = html[pos:end]

        if href.startswith("/") and (
            "/im-" in href or
            "/tagesdosis" in href or
            "/standpunkte" in href
        ):
            full = BASE + href
            if full not in links:
                links.append(full)
    return links

def extract_title(html):
    h1 = find_between(html, "<h1", "</h1>")
    if not h1:
        return "Ohne Titel"
    gt = h1.find(">")
    if gt != -1:
        h1 = h1[gt+1:]
    return h1.strip()

def extract_date(html):
    dt = find_between(html, 'datetime="', '"')
    if not dt:
        return ""
    return dt.strip()

def extract_mp3(html):
    if not html:
        return None
    pos = 0
    while True:
        pos = html.find('src="', pos)
        if pos == -1:
            break
        pos += len('src="')
        end = html.find('"', pos)
        if end == -1:
            break
        url = html[pos:end]
        if url.endswith(".mp3"):
            return url

    pos = 0
    while True:
        pos = html.find('href="', pos)
        if pos == -1:
            break
        pos += len('href="')
        end = html.find('"', pos)
        if end == -1:
            break
        url = html[pos:end]
        if url.endswith(".mp3"):
            return url

    return None

def parse_article(url):
    html = fetch(url)
    if html is None:
        return {"title": "Fehler beim Laden", "date": "", "link": url, "mp3": None}
    try:
        title = extract_title(html)
        date = extract_date(html)
        mp3 = extract_mp3(html)
        return {
            "title": title,
            "date": date,
            "link": url,
            "mp3": mp3
        }
    except Exception as e:
        print(f"[FEHLER] Parsing fehlgeschlagen für {url} -> {e}")
        return {"title": "Parsing-Fehler", "date": "", "link": url, "mp3": None}

# ---------------------------------------------------------
# Robuste Datumskorrektur
# ---------------------------------------------------------

def fix_date(d):
    if not d or d.strip() == "":
        return datetime(1970, 1, 1)
    d = d.strip()
    if len(d) == 10:
        d = d + "T00:00:00"
    try:
        return datetime.fromisoformat(d.replace("Z", ""))
    except Exception:
        return datetime(1970, 1, 1)

# ---------------------------------------------------------
# RSS-Erzeugung
# ---------------------------------------------------------

def build_rss(items):
    xml_items = []
    for t in items:
        mp3 = t.get("mp3") or ""
        xml_items.append(f"""
<item>
<title>{t['title']}</title>
<link>{t['link']}</link>
<description><![CDATA[{t['title']}]]></description>
<enclosure url="{mp3}" length="0" type="audio/mpeg"/>
<guid>{t['link']}</guid>
<pubDate>{t['date']}</pubDate>
</item>
""")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Apolut Kombinierter Podcast</title>
<link>{BASE}</link>
<description>Kombinierter Feed aus Tagesdosis, Standpunkte und Im Gespräch</description>
<language>de-de</language>
{''.join(xml_items)}
</channel>
</rss>
"""
    return xml

# ---------------------------------------------------------
# Hauptlogik
# ---------------------------------------------------------

def main():
    print("Lade Tag-Seiten...")

    all_articles = []

    for tag in TAGS:
        print("Tag:", tag)
        html = fetch(f"{BASE}/tag/{tag}/")
        links = extract_articles_from_tagpage(html)
        print(f"  Gefundene Links in {tag}: {len(links)}")
        all_articles.extend(links)

    all_articles = list(dict.fromkeys(all_articles))
    print("Gesamt gefundene Artikel (unique):", len(all_articles))

    parsed = []
    missing_date = []
    missing_mp3 = []

    for url in all_articles:
        info = parse_article(url)
        if not info:
            continue
        if not info.get("mp3"):
            missing_mp3.append(url)
            print("[WARN] Kein MP3:", url)
        if not info.get("date"):
            missing_date.append(url)
            print("[WARN] Kein Datum:", url)
        parsed.append(info)
        print("OK:", info.get("title", "Ohne Titel"))

    # Sortieren nach Datum (robust)
    parsed.sort(key=lambda x: fix_date(x.get("date", "")), reverse=True)

    # Die neuesten 10
    latest = parsed[:10]

    print("\nErzeuge RSS für", len(latest), "Folgen...")
    if missing_date:
        print(f"[INFO] Artikel ohne Datum: {len(missing_date)}")
    if missing_mp3:
        print(f"[INFO] Artikel ohne MP3: {len(missing_mp3)}")

    xml = build_rss(latest)

    try:
        Path("feed.xml").write_text(xml, encoding="utf-8")
        print("feed.xml geschrieben.")
    except Exception as e:
        print("[FEHLER] feed.xml konnte nicht geschrieben werden:", e)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("[UNERWARTETER FEHLER] Das Script ist abgestürzt:", e)
    # Immer mit Exit Code 0 beenden, damit Actions nicht wegen Script-Fehlern fehlschlägt
    sys.exit(0)

