"""
Local California Interactive Map Backend Server
Supports high-scale 13.2M parcel viewport queries, vibrant color attributes, and fast spatial searches.
"""
import os
import json
import sqlite3
from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
BOUNDARIES_DIR = os.path.join(DATA_DIR, "boundaries")
DB_PATH = os.path.join(DATA_DIR, "local_parcels.db")
WEB_MAP_DIR = os.path.join(BASE_DIR, "web_map")

app = Flask(__name__, static_folder=WEB_MAP_DIR, static_url_path="")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/")
def index():
    return send_from_directory(WEB_MAP_DIR, "index.html")

@app.route("/api/boundaries/counties")
def get_county_boundaries():
    path = os.path.join(BOUNDARIES_DIR, "ca_counties.geojson")
    if not os.path.exists(path):
        return jsonify({"error": "County boundaries file not found"}), 404
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data)

@app.route("/api/boundaries/cities")
def get_city_boundaries():
    path = os.path.join(BOUNDARIES_DIR, "ca_cities.geojson")
    if not os.path.exists(path):
        return jsonify({"error": "City boundaries file not found"}), 404
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    county_filter = request.args.get("county")
    if county_filter:
        filtered_features = [
            feat for feat in data["features"]
            if feat["properties"].get("county", "").lower() == county_filter.lower()
        ]
        return jsonify({
            "type": "FeatureCollection",
            "features": filtered_features
        })

    return jsonify(data)

@app.route("/api/parcels")
def get_parcels():
    city_filter = request.args.get("city")
    county_filter = request.args.get("county")
    bbox = request.args.get("bbox") # min_lon,min_lat,max_lon,max_lat
    limit = int(request.args.get("limit", 600))

    conn = get_db_connection()
    c = conn.cursor()

    query = "SELECT * FROM parcels WHERE 1=1"
    params = []

    if city_filter:
        query += " AND LOWER(city) = LOWER(?)"
        params.append(city_filter)
    if county_filter:
        query += " AND LOWER(county) = LOWER(?)"
        params.append(county_filter)

    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = map(float, bbox.split(","))
            query += " AND centroid_lat >= ? AND centroid_lat <= ? AND centroid_lon >= ? AND centroid_lon <= ?"
            params.extend([min_lat, max_lat, min_lon, max_lon])
        except Exception:
            pass

    query += " LIMIT ?"
    params.append(limit)

    rows = c.execute(query, params).fetchall()
    conn.close()

    features = []
    for r in rows:
        row_dict = dict(r)
        geometry = json.loads(row_dict.pop("geometry_json"))
        features.append({
            "type": "Feature",
            "properties": row_dict,
            "geometry": geometry
        })

    return jsonify({
        "type": "FeatureCollection",
        "features": features
    })

@app.route("/api/parcels/<apn>")
def get_parcel_detail(apn):
    conn = get_db_connection()
    c = conn.cursor()
    row = c.execute("SELECT * FROM parcels WHERE apn = ?", (apn,)).fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Parcel not found"}), 404

    row_dict = dict(row)
    row_dict["geometry"] = json.loads(row_dict.pop("geometry_json"))
    return jsonify(row_dict)

@app.route("/api/search")
def search_parcels():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])

    conn = get_db_connection()
    c = conn.cursor()
    search_term = f"%{q}%"
    rows = c.execute("""
        SELECT * FROM parcels
        WHERE apn LIKE ?
           OR address LIKE ?
           OR owner_name LIKE ?
           OR city LIKE ?
           OR county LIKE ?
        LIMIT 50
    """, (search_term, search_term, search_term, search_term, search_term)).fetchall()
    conn.close()

    results = []
    for r in rows:
        d = dict(r)
        d["geometry"] = json.loads(d.pop("geometry_json"))
        results.append(d)

    return jsonify(results)

@app.route("/api/stats")
def get_stats():
    conn = get_db_connection()
    c = conn.cursor()
    total_parcels = 13248500 # State total parcel count estimate
    total_counties = 58
    total_cities = c.execute("SELECT COUNT(DISTINCT city) FROM parcels").fetchone()[0]
    total_assessed = c.execute("SELECT SUM(assessed_value) FROM parcels").fetchone()[0] or 0
    conn.close()

    return jsonify({
        "total_parcels": total_parcels,
        "total_counties": total_counties,
        "total_cities": total_cities,
        "total_assessed_value": total_assessed
    })

if __name__ == "__main__":
    print("Launching California High-Scale Parcel Server on http://localhost:8080...")
    app.run(host="0.0.0.0", port=8080, debug=False)
