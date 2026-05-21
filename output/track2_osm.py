import requests
import pandas as pd
import json
from math import radians, sin, cos, sqrt, asin

# ── Haversine distance in metres ──────────────────────────────────────────────
def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlam = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dlam/2)**2
    return 2 * R * asin(sqrt(a))

# ── Query Overpass API ─────────────────────────────────────────────────────────
def query_overpass(query):
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (EV Research Project)"
    }
    
    url = "https://overpass-api.de/api/interpreter"
    try:
        response = requests.post(url, data={"data": query}, headers=headers, timeout=90)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"  Primary server failed: {e}")
        print("  Trying mirror...")
        try:
            url2 = "https://overpass.kumi.systems/api/interpreter"
            response = requests.post(url2, data={"data": query}, headers=headers, timeout=90)
            response.raise_for_status()
            return response.json()
        except Exception as e2:
            print(f"  Mirror also failed: {e2}")
            return None

# ── Classify DC vs AC ──────────────────────────────────────────────────────────
def is_dc_fast(tags):
    power = tags.get("capacity:electrical", "") or tags.get("electrical_power", "") or ""
    name  = (tags.get("name", "") + tags.get("operator", "")).lower()
    
    dc_keywords = ["dc", "ccs", "chademo", "fast", "50kw", "60kw",
                   "120kw", "150kw", "240kw"]
    
    # Check power rating
    try:
        kw = float(str(power).replace("kW","").replace("kw","").strip())
        if kw >= 25:
            return True
    except:
        pass
    
    # Check OSM socket tags
    if tags.get("socket:type2_combo") or tags.get("socket:chademo"):
        return True
    
    # Check name/operator keywords
    if any(kw in name for kw in dc_keywords):
        return True
    
    return False

# ── Main collection ────────────────────────────────────────────────────────────
def collect_osm_chargers():
    print("Querying OpenStreetMap for EV chargers in Bengaluru...")
    
    # Bengaluru bounding box: south, west, north, east
    bbox = "12.834,77.480,13.139,77.780"
    
    query = f"""
    [out:json][timeout:90];
    (
      node["amenity"="charging_station"]({bbox});
      way["amenity"="charging_station"]({bbox});
      relation["amenity"="charging_station"]({bbox});
    );
    out center tags;
    """
    
    data = query_overpass(query)
    
    if not data:
        print("Failed to get data from Overpass API.")
        return
    
    elements = data.get("elements", [])
    print(f"Raw results: {len(elements)} elements found")
    
    # ── Parse each element ─────────────────────────────────────────────────────
    rows = []
    for el in elements:
        tags = el.get("tags", {})
        
        # Get coordinates (ways have a 'center', nodes have direct lat/lon)
        if el["type"] == "node":
            lat = el.get("lat")
            lon = el.get("lon")
        else:
            center = el.get("center", {})
            lat = center.get("lat")
            lon = center.get("lon")
        
        if not lat or not lon:
            continue
        
        rows.append({
            "osm_id":       el.get("id"),
            "station_name": tags.get("name", "Unknown"),
            "operator":     tags.get("operator", "Unknown"),
            "address":      tags.get("addr:full", tags.get("addr:street", "")),
            "lat":          lat,
            "lon":          lon,
            "power_kw":     tags.get("capacity:electrical", tags.get("electrical_power", "")),
            "charger_type_dc_fast": is_dc_fast(tags),
            "socket_ccs":   tags.get("socket:type2_combo", ""),
            "socket_chademo": tags.get("socket:chademo", ""),
            "source":       "OSM",
            "review_count": 0
        })
    
    df = pd.DataFrame(rows)
    print(f"Parsed {len(df)} stations before deduplication")
    
    # ── Deduplicate by proximity (50 metres) ───────────────────────────────────
    keep = []
    dropped = 0
    for i, row in df.iterrows():
        duplicate = False
        for j in keep:
            dist = haversine_m(row["lat"], row["lon"],
                               df.loc[j, "lat"], df.loc[j, "lon"])
            if dist < 50:
                duplicate = True
                dropped += 1
                break
        if not duplicate:
            keep.append(i)
    
    df_clean = df.loc[keep].reset_index(drop=True)
    print(f"After deduplication: {len(df_clean)} unique stations ({dropped} duplicates removed)")
    
    # ── Save ───────────────────────────────────────────────────────────────────
    df_clean.to_csv("m2_chargers_osm.csv", index=False)
    print(f"\nSaved to m2_chargers_osm.csv")
    
    # ── Quick summary ──────────────────────────────────────────────────────────
    dc_count = df_clean["charger_type_dc_fast"].sum()
    ac_count = len(df_clean) - dc_count
    print(f"\nSummary:")
    print(f"  Total unique stations : {len(df_clean)}")
    print(f"  DC fast chargers      : {dc_count}")
    print(f"  AC slow chargers      : {ac_count}")
    print(f"\nTop operators:")
    print(df_clean["operator"].value_counts().head(10).to_string())

if __name__ == "__main__":
    collect_osm_chargers()