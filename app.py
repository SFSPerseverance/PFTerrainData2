import os
import json
import requests
import numpy as np
from flask import Flask, request, jsonify
from PIL import Image
from io import BytesIO

# -------------------------
# Config
# -------------------------
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)
TILE_URL = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2018_3857/default/g/{z}/{y}/{x}.jpg"

app = Flask(__name__)

def fetch_tile_as_json(x: int, y: int, z: int) -> list:
    """
    Download a Sentinel-2 Cloudless tile and return it as a Python list
    of shape [256][256][3] (RGB values 0–255).
    """
    url = TILE_URL.format(z=z, x=x, y=y)
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()

    img = Image.open(BytesIO(resp.content)).convert("RGB")
    arr = np.array(img, dtype=np.uint8)   # shape (256,256,3)
    return arr.tolist()                   # convert to JSON-serializable list

def cache_path(z: int, x: int, y: int) -> str:
    return os.path.join(CACHE_DIR, f"{z}_{x}_{y}.json")

@app.route("/tile", methods=["GET"])
def get_tile():
    """
    Endpoint: /tile?x=...&y=...&z=...
    Returns: JSON array of [R,G,B] pixels
    """
    try:
        x = int(request.args.get("x"))
        y = int(request.args.get("y"))
        z = int(request.args.get("z", 12))  # default zoom 12
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid x/y/z parameters"}), 400

    path = cache_path(z, x, y)

    if os.path.exists(path):
        # Serve cached tile
        with open(path, "r") as f:
            data = json.load(f)
    else:
        # Fetch from Sentinel-2 and cache
        try:
            data = fetch_tile_as_json(x, y, z)
        except Exception as e:
            return jsonify({"error": f"Tile fetch failed: {e}"}), 502
        with open(path, "w") as f:
            json.dump(data, f)

    return jsonify(data)

@app.route("/")
def index():
    return jsonify({
        "message": "Sentinel-2 JSON Tile API",
        "usage": "/tile?x=<x>&y=<y>&z=<zoom>"
    })

if __name__ == "__main__":
    # For local dev; Render/Heroku will use gunicorn
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
