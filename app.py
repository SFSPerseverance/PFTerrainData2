import mercantile   # Add at the top with other imports

@app.route("/bbox", methods=["GET"])
def get_bbox():
    """
    Example:
    /bbox?min_lon=-74.1&min_lat=40.6&max_lon=-73.7&max_lat=40.9&z=12
    Returns: { "tiles": [ {x,y,z,data}, ... ] }
    """
    try:
        min_lon = float(request.args.get("min_lon"))
        min_lat = float(request.args.get("min_lat"))
        max_lon = float(request.args.get("max_lon"))
        max_lat = float(request.args.get("max_lat"))
        z = int(request.args.get("z", 12))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid bbox parameters"}), 400

    tile_list = []
    for tile in mercantile.tiles(min_lon, min_lat, max_lon, max_lat, z):
        path = cache_path(tile.z, tile.x, tile.y)
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
        else:
            try:
                data = fetch_tile_as_json(tile.x, tile.y, tile.z)
                cache_tile_json(data, tile.x, tile.y, tile.z)
            except Exception as e:
                return jsonify({"error": f"Failed tile {tile}: {e}"}), 502
        tile_list.append({
            "x": tile.x,
            "y": tile.y,
            "z": tile.z,
            "data": data
        })

    return jsonify({"tiles": tile_list})
