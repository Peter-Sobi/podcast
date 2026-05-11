import re

# Read release URLs
urls = {}
with open("release_urls.txt") as f:
    for line in f:
        name, url = line.strip().split("|")
        urls[name] = url

# Read asset sizes
sizes = {}
with open("auf1_assets.txt") as f:
    for line in f:
        file, size = line.strip().split("|")
        sizes[file.split("/")[-1]] = size

# Build feed
items = []
for name in urls:
    items.append(f"""
<item>
<title>{name}</title>
<link>https://auf1.radio</link>
<description><![CDATA[{name}]]></description>
<enclosure url="{urls[name]}" length="{sizes[name]}" type="audio/mpeg"/>
<guid isPermaLink="false">{urls[name]}</guid>
<pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
</item>
""")

rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>AUF1 Kombinierter Podcast</title>
<link>https://auf1.radio</link>
<description>Automatisch generierter Feed</description>
<language>de-de</language>
{''.join(items)}
</channel>
</rss>
"""

open("feed_auf1.xml", "w").write(rss)

