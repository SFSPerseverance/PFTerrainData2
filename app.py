import os
import json
import requests
from flask import Flask, request, jsonify
from PIL import Image
from io import BytesIO
import numpy as np
import mercantile

# =====================
# CONFIG
# =====================
TILE_CACHE_DIR = "tiles_json"
WMTS_URL = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg"
DEFAULT_TILE_ZOOM = 12

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
    arr = np.array(img)
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

def bilinear_sample(tile_data, px, py):
    """Bilinear sample a pixel in a 256x256 tile."""
    x0 = int(np.floor(px))
    y0 = int(np.floor(py))
    x1 = min(x0 + 1, 255)
    y1 = min(y0 + 1, 255)

    fx = px - x0
    fy = py - y0

    c00 = np.array(tile_data[y0][x0])
    c10 = np.array(tile_data[y0][x1])
    c01 = np.array(tile_data[y1][x0])
    c11 = np.array(tile_data[y1][x1])

    top = c00 * (1 - fx) + c10 * fx
    bottom = c01 * (1 - fx) + c11 * fx
    return ((top * (1 - fy) + bottom * fy)).astype(np.uint8)

# =====================
# Routes
# =====================
@app.route("/")
def index():
    return jsonify({
        "endpoints": {
            "/tile": "/tile?x=<x>&y=<y>&z=<z>",
            "/bbox": "/bbox?min_lon=<>&min_lat=<>&max_lon=<>&max_lat=<>&texture_width=<>&texture_height=<>"
        }
    })

@app.route("/tile", methods=["GET"])
def get_tile():
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
    Returns a single stitched texture exactly covering the requested bbox.
    /bbox?min_lon=-74.1&min_lat=40.6&max_lon=-73.7&max_lat=40.9&texture_width=1024&texture_height=1024
    """
    try:
        min_lon = float(request.args["min_lon"])
        min_lat = float(request.args["min_lat"])
        max_lon = float(request.args["max_lon"])
        max_lat = float(request.args["max_lat"])
        texture_width = int(request.args.get("texture_width", 1024))
        texture_height = int(request.args.get("texture_height", 1024))
        zoom = int(request.args.get("zoom", DEFAULT_TILE_ZOOM))
    except (KeyError, ValueError):
        return jsonify({"error": "Invalid bbox parameters"}), 400

    # Generate pixel grid over bbox
    lons = np.linspace(min_lon, max_lon, texture_width)
    lats = np.linspace(max_lat, min_lat, texture_height)  # top to bottom

    # Prepare final RGB array
    final_texture = np.zeros((texture_height, texture_width, 3), dtype=np.uint8)

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

            # fractional pixel within the tile
            bounds = mercantile.bounds(tile)
            fx = (lon - bounds.west) / (bounds.east - bounds.west)
            fy = (bounds.north - lat) / (bounds.north - bounds.south)
            px = fx * 255
            py = fy * 255

            final_texture[i, j] = bilinear_sample(tile_data, px, py)

    return jsonify({"texture": final_texture.tolist()})

# =====================
# Run locally
# =====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
