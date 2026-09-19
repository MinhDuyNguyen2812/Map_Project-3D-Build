"""
Run this once to download all frontend libraries locally.
After running, the app works without CDN dependencies.

    python download_assets.py
"""

import requests
import os

ASSETS = {
    # Leaflet — for the map view
    "ui/leaflet.js":   "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
    "ui/leaflet.css":  "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",

    # Three.js r128 — for the 3D viewport
    "ui/three.min.js": "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js",
}


def download():
    for path, url in ASSETS.items():
        os.makedirs(os.path.dirname(path), exist_ok=True)

        if os.path.exists(path):
            size_kb = os.path.getsize(path) / 1024
            print(f"⏭  Already exists: {path} ({size_kb:.0f} KB)")
            continue

        print(f"⬇  Downloading {url} ...")
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                with open(path, "wb") as f:
                    f.write(r.content)
                size_kb = len(r.content) / 1024
                print(f"Saved: {path} ({size_kb:.0f} KB)")
            else:
                print(f"❌ Failed ({r.status_code}): {url}")
        except Exception as e:
            print(f"❌ Error: {e}")

    print("\nDone.")


if __name__ == "__main__":
    download()