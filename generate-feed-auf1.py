#!/usr/bin/env python3
import os
from pathlib import Path

# Basisverzeichnis = Repo-Root (dort, wo der Workflow läuft)
BASE_DIR = Path(__file__).resolve().parent
MEDIA_DIR = BASE_DIR / "media_auf1"
ASSET_LIST = BASE_DIR / "auf1_assets.txt"

def ensure_media_dir():
    """
    Stellt sicher, dass der Medienordner existiert.
    Falls du hier später Download-Logik einbaust, ist der Ordner schon da.
    """
    MEDIA_DIR.mkdir(exist_ok=True)

def build_asset_list():
    """
    Erzeugt auf1_assets.txt im Format:
    media_auf1/DATEINAME.mp3|BYTES
    und stellt sicher, dass ALLE MP3s erfasst werden.
    """
    files = []

    for entry in MEDIA_DIR.iterdir():
        if entry.is_file() and entry.suffix.lower() == ".mp3":
            size = entry.stat().st_size
            # relativer Pfad, wie er im Workflow zum Upload verwendet wird
            rel_path = f"media_auf1/{entry.name}"
            files.append((rel_path, size))

    # Optional: sortieren, z.B. alphabetisch
    files.sort(key=lambda x: x[0])

    with ASSET_LIST.open("w", encoding="utf-8") as f:
        for path, size in files:
            f.write(f"{path}|{size}\n")

    print(f"Geschrieben: {ASSET_LIST} mit {len(files)} Einträgen")

def main():
    ensure_media_dir()
    # HIER wäre ggf. deine Download-Logik für AUF1,
    # z.B. neue Folgen holen und in MEDIA_DIR speichern.
    #
    # Beispiel (Pseudo):
    # download_new_auf1_episodes(MEDIA_DIR)
    #
    # Danach wird IMMER die aktuelle Liste gebaut:
    build_asset_list()

if __name__ == "__main__":
    main()

