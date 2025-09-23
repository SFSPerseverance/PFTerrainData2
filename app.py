import os
import json
import math
import requests
from flask import Flask, request, jsonify
from PIL import Image
from io import BytesIO
import numpy as np
import mercantile  # pip install mercantile

# =====================
# CONFIG
# =====================
TILE_CACHE_DIR = "tiles_json"
WMTS_URL = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2018_3857/default/g/{z}/{y}/{x}.jpg"
DEFAULT_TILE_ZOOM = 12  # zoom to fetch tiles for sampling

os.makedirs(TILE_CACHE_DIR, exist_ok=True)
app = Flask(__name__)

# =====================
# Helpers
# =====================
def cache_path(z, x, y):
    return os.path.join(TILE_CACHE_DIR, f"tile_{z}_{x}_{y}.json")

def fetch_tile_as_json(x: int, y: int, z: int):
    """Fetch a single tile and convert to 256x256 RGB array."""
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
            "/bbox": "/bbox?min_lon=<>&min_lat=<>&max_lon=<>&max_lat=<>&texture_size=<pixels>"
        }
    })

@app.route("/tile", methods=["GET"])
def get_tile():
    """Return single tile JSON"""
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
    Returns a single stitched texture for the bbox.
    /bbox?min_lon=-74.1&min_lat=40.6&max_lon=-73.7&max_lat=40.9&texture_size=1024
    """
    try:
        min_lon = float(request.args["min_lon"])
        min_lat = float(request.args["min_lat"])
        max_lon = float(request.args["max_lon"])
        max_lat = float(request.args["max_lat"])
        texture_size = int(request.args.get("texture_size", 1024))
        zoom = int(request.args.get("zoom", DEFAULT_TILE_ZOOM))
    except (KeyError, ValueError):
        return jsonify({"error": "Invalid bbox parameters"}), 400

    # Generate pixel grid over bbox
    lats = np.linspace(max_lat, min_lat, texture_size)  # top to bottom
    lons = np.linspace(min_lon, max_lon, texture_size)  # left to right

    # Prepare final RGB array
    final_texture = np.zeros((texture_size, texture_size, 3), dtype=np.uint8)

    # Pre-cache needed tiles
    tile_cache = {}

    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            # Determine which tile contains this pixel
            tile = mercantile.tile(lon, lat, zoom)
            tile_key = (tile.x, tile.y, tile.z)
            if tile_key not in tile_cache:
                tile_cache[tile_key] = load_or_fetch_tile(tile.x, tile.y, tile.z)
            tile_data = tile_cache[tile_key]

            # Compute pixel within the tile
            bounds = mercantile.bounds(tile)
            px = int((lon - bounds.west) / (bounds.east - bounds.west) * 255)
            py = int((bounds.north - lat) / (bounds.north - bounds.south) * 255)
            px = min(max(px, 0), 255)
            py = min(max(py, 0), 255)

            final_texture[i, j] = tile_data[py][px]

    return jsonify({"texture": final_texture.tolist()})

# =====================
# Run locally
# =====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
