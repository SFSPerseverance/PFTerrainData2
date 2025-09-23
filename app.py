import os
import json
import math
import requests
from flask import Flask, request, jsonify
from PIL import Image
from io import BytesIO
import numpy as np
import mercantile   # make sure mercantile is pinned in requirements

# =====================
# CONFIG
# =====================
TILE_CACHE_DIR = "tiles_json"
WMTS_URL = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg"

os.makedirs(TILE_CACHE_DIR, exist_ok=True)
app = Flask(__name__)

# =====================
# Helpers
# =====================

def cache_path(z, x, y):
    return os.path.join(TILE_CACHE_DIR, f"tile_{z}_{x}_{y}.json")

def fetch_tile_as_json(x: int, y: int, z: int):
    """Fetch a single Sentinel-2 tile and convert to a 256x256 RGB list."""
    url = WMTS_URL.format(z=z, x=x, y=y)
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    img = Image.open(BytesIO(r.content)).convert("RGB")
    arr = np.array(img)  # shape (256,256,3)
    return arr.tolist()

def cache_tile_json(data, x, y, z):
    with open(cache_path(z, x, y), "w") as f:
        json.dump(data, f)

def load_or_fetch_tile(x, y, z):
    path = cache_path(z, x, y)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    data = fetch_tile_as_json(x, y, z)
    cache_tile_json(data, x, y, z)
    return data

# =====================
# Routes
# =====================

@app.route("/")
def index():
    return jsonify({
        "endpoints": {
            "/tile": "/tile?x=<x>&y=<y>&z=<z>",
            "/bbox": "/bbox?min_lon=<>&min_lat=<>&max_lon=<>&max_lat=<>&z=<zoom>"
        }
    })

@app.route("/tile", methods=["GET"])
def get_tile():
    """
    Request a single tile:
    /tile?x=2100&y=1400&z=12
    Returns JSON array of [ [ [R,G,B], ... ], ... ]
    """
    try:
        x = int(request.args["x"])
        y = int(request.args["y"])
        z = int(request.args["z"])
    except (KeyError, ValueError):
        return jsonify({"error": "Missing or invalid x,y,z"}), 400

    try:
        data = load_or_fetch_tile(x, y, z)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return jsonify(data)

@app.route("/bbox", methods=["GET"])
def get_bbox():
    """
    Request a bounding box of tiles:
    /bbox?min_lon=-74.1&min_lat=40.6&max_lon=-73.7&max_lat=40.9&z=12
    Returns { "tiles": [ {x,y,z,data}, ... ] }
    """
    try:
        min_lon = float(request.args["min_lon"])
        min_lat = float(request.args["min_lat"])
        max_lon = float(request.args["max_lon"])
        max_lat = float(request.args["max_lat"])
        z = int(request.args.get("z", 12))
    except (KeyError, ValueError):
        return jsonify({"error": "Invalid bbox parameters"}), 400

    tile_list = []
    for tile in mercantile.tiles(min_lon, min_lat, max_lon, max_lat, z):
        try:
            data = load_or_fetch_tile(tile.x, tile.y, tile.z)
        except Exception as e:
            return jsonify({"error": f"Failed tile {tile}: {e}"}), 502
        tile_list.append({
            "x": tile.x,
            "y": tile.y,
            "z": tile.z,
            "data": data
        })

    return jsonify({"tiles": tile_list})

# =====================
# Run locally
# =====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
