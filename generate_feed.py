import requests
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
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text

def find_between(text, start, end):
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
    return dt

def extract_mp3(html):
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
    title = extract_title(html)
    date = extract_date(html)
    mp3 = extract_mp3(html)
    return {
        "title": title,
        "date": date,
        "link": url,
        "mp3": mp3
    }

# ---------------------------------------------------------
# Robuste Datumskorrektur
# ---------------------------------------------------------

def fix_date(d):
    # Leere oder ungültige Daten → sehr altes Datum
    if not d or d.strip() == "":
        return datetime(1970, 1, 1)

    d = d.strip()

    # Falls nur YYYY-MM-DD → Uhrzeit anhängen
    if len(d) == 10:
        d = d + "T00:00:00"

    # Try/except für alle anderen Fälle
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
        # Sicherstellen, dass mp3 vorhanden ist
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
        try:
            print("Tag:", tag)
            html = fetch(f"{BASE}/tag/{tag}/")
            links = extract_articles_from_tagpage(html)
            all_articles.extend(links)
        except Exception as e:
            print("Fehler beim Laden der Tag-Seite", tag, e)

    # Duplikate entfernen
    all_articles = list(dict.fromkeys(all_articles))

    print("Gefundene Artikel:", len(all_articles))

    parsed = []
    for url in all_articles:
        try:
            info = parse_article(url)
            if info["mp3"]:
                parsed.append(info)
                print("OK:", info["title"])
            else:
                print("Kein MP3:", url)
        except Exception as e:
            print("Fehler bei", url, e)

    # Sortieren nach Datum (robust)
    parsed.sort(key=lambda x: fix_date(x.get("date", "")), reverse=True)

    # Die neuesten 10
    latest = parsed[:10]

    print("\nErzeuge RSS für", len(latest), "Folgen...")

    xml = build_rss(latest)

    Path("feed.xml").write_text(xml, encoding="utf-8")

    print("\n===== RSS =====\n")
    print(xml)

if __name__ == "__main__":
    main()

