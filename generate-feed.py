import requests
from datetime import datetime
from pathlib import Path

BASE = "https://apolut.net"
TAGS = ["tagesdosis", "standpunkte", "im-gespraech"]
HEADERS = {"User-Agent": "Mozilla/5.0"}

# ---------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------

def safe_fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"[FEHLER] Laden fehlgeschlagen: {url} -> {e}")
        return None

def find_between(text: str | None, start: str, end: str) -> str | None:
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

def extract_articles(html: str | None) -> list[str]:
    if not html:
        return []
    links: list[str] = []
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
        if href.startswith("/") and any(tag in href for tag in TAGS):
            full = BASE + href
            if full not in links:
                links.append(full)
    return links

def extract_title(html: str | None) -> str:
    h1 = find_between(html, "<h1", "</h1>")
    if not h1:
        return "Ohne Titel"
    gt = h1.find(">")
    if gt != -1:
        h1 = h1[gt + 1 :]
    return h1.strip()

def extract_date(html: str | None) -> str:
    dt = find_between(html, 'datetime="', '"')
    return dt.strip() if dt else ""

def extract_mp3(html: str | None) -> str | None:
    if not html:
        return None
    for marker in ['src="', 'href="']:
        pos = 0
        while True:
            pos = html.find(marker, pos)
            if pos == -1:
                break
            pos += len(marker)
            end = html.find('"', pos)
            if end == -1:
                break
            url = html[pos:end]
            if url.endswith(".mp3"):
                return url
    return None

def parse_article(url: str) -> dict:
    try:
        html = safe_fetch(url)
        if not html:
            return {"title": "Fehler beim Laden", "date": "", "link": url, "mp3": None}
        return {
            "title": extract_title(html),
            "date": extract_date(html),
            "link": url,
            "mp3": extract_mp3(html),
        }
    except Exception as e:
        print(f"[FEHLER] Parsing fehlgeschlagen: {url} -> {e}")
        return {"title": "Parsing-Fehler", "date": "", "link": url, "mp3": None}

def fix_date(d: str) -> datetime:
    try:
        if not d or d.strip() == "":
            return datetime(1970, 1, 1)
        d = d.strip()
        if len(d) == 10:
            d += "T00:00:00"
        return datetime.fromisoformat(d.replace("Z", ""))
    except Exception:
        return datetime(1970, 1, 1)

# ---------------------------------------------------------
# RSS-Erzeugung
# ---------------------------------------------------------

def build_rss(items: list[dict]) -> str:
    xml_items: list[str] = []
    for t in items:
        mp3 = t.get("mp3") or ""
        xml_items.append(
            f"""
<item>
<title>{t['title']}</title>
<link>{t['link']}</link>
<description><![CDATA[{t['title']}]]></description>
<enclosure url="{mp3}" length="0" type="audio/mpeg"/>
<guid>{t['link']}</guid>
<pubDate>{t['date']}</pubDate>
</item>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
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

# ---------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------

def main() -> None:
    print("Starte Feed-Generierung…")

    all_links: list[str] = []
    for tag in TAGS:
        print(f"Lade Tag-Seite: {tag}")
        html = safe_fetch(f"{BASE}/tag/{tag}/")
        links = extract_articles(html)
        print(f"  Gefunden: {len(links)}")
        all_links.extend(links)

    # Duplikate entfernen, Reihenfolge beibehalten
    all_links = list(dict.fromkeys(all_links))
    print("Gesamt:", len(all_links))

    parsed: list[dict] = []
    for url in all_links:
        info = parse_article(url)
        parsed.append(info)
        print("OK:", info["title"])

    # Nach Datum sortieren, neueste zuerst
    parsed.sort(key=lambda x: fix_date(x["date"]), reverse=True)
    latest = parsed[:10]

    xml = build_rss(latest)
    Path("feed.xml").write_text(xml, encoding="utf-8")
    print("feed.xml geschrieben.")

if __name__ == "__main__":
    main()

