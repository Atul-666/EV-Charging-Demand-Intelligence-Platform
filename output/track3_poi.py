import requests
import pandas as pd

def query_overpass(query):
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (EV Research Project)"
    }
    url = "https://overpass.kumi.systems/api/interpreter"
    try:
        response = requests.post(url, data={"data": query}, headers=headers, timeout=90)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"  Failed: {e}")
        return None

def count_poi(bbox, amenity_filter):
    query = f"""
    [out:json][timeout:60];
    (
      nwr{amenity_filter}({bbox});
    );
    out center;
    """
    data = query_overpass(query)
    if not data:
        return []
    return data.get("elements", [])

def main():
    # Bengaluru bounding box
    bbox = "12.834,77.480,13.139,77.780"

    poi_types = {
        "hospital":      '["amenity"="hospital"]',
        "petrol_pump":   '["amenity"="fuel"]',
        "university":    '["amenity"~"university|college"]',
        "metro":         '["railway"="station"]',
        "mall":          '["shop"="mall"]',
        "hotel":         '["tourism"="hotel"]',
        "it_park":       '["landuse"~"commercial|industrial"]["name"~"IT|Tech|Software|Infosys|Wipro|TCS|Manyata|Embassy|Prestige",i]',
    }

    # POI weights from playbook
    weights = {
        "it_park":    3.0,
        "hotel":      2.5,
        "mall":       2.0,
        "metro":      1.5,
        "hospital":   1.5,
        "university": 1.5,
        "petrol_pump":1.0,
    }

    all_pois = []

    for poi_type, amenity_filter in poi_types.items():
        print(f"Fetching {poi_type}s...")
        elements = count_poi(bbox, amenity_filter)
        print(f"  Found {len(elements)} {poi_type}s")

        for el in elements:
            if el["type"] == "node":
                lat = el.get("lat")
                lon = el.get("lon")
            else:
                center = el.get("center", {})
                lat = center.get("lat")
                lon = center.get("lon")

            if lat and lon:
                all_pois.append({
                    "poi_type": poi_type,
                    "lat":      lat,
                    "lon":      lon,
                    "weight":   weights[poi_type],
                    "name":     el.get("tags", {}).get("name", "Unknown")
                })

    df = pd.DataFrame(all_pois)

    if df.empty:
        print("No POI data collected.")
        return

    df.to_csv("m3_poi_raw.csv", index=False)
    print(f"\nTotal POIs collected: {len(df)}")
    print("\nBreakdown by type:")
    print(df["poi_type"].value_counts().to_string())
    print("\nSaved to m3_poi_raw.csv")

if __name__ == "__main__":
    # Retry only the failed ones
    retry_types = {
        "hospital":   '["amenity"="hospital"]',
        "university": '["amenity"~"university|college"]',
        "metro":      '["railway"="station"]',
    }

    bbox = "12.834,77.480,13.139,77.780"
    weights = {"hospital": 1.5, "university": 1.5, "metro": 1.5}

    # Load existing data
    existing = pd.read_csv("m3_poi_raw.csv")
    print(f"Existing POIs loaded: {len(existing)}")

    retry_rows = []
    for poi_type, amenity_filter in retry_types.items():
        print(f"Retrying {poi_type}...")
        import time
        time.sleep(5)  # wait 5 seconds before each query
        elements = count_poi(bbox, amenity_filter)
        print(f"  Found {len(elements)} {poi_type}s")

        for el in elements:
            if el["type"] == "node":
                lat = el.get("lat")
                lon = el.get("lon")
            else:
                center = el.get("center", {})
                lat = center.get("lat")
                lon = center.get("lon")

            if lat and lon:
                retry_rows.append({
                    "poi_type": poi_type,
                    "lat":      lat,
                    "lon":      lon,
                    "weight":   weights[poi_type],
                    "name":     el.get("tags", {}).get("name", "Unknown")
                })

    if retry_rows:
        retry_df = pd.DataFrame(retry_rows)
        combined = pd.concat([existing, retry_df], ignore_index=True)
        combined.to_csv("m3_poi_raw.csv", index=False)
        print(f"\nUpdated total POIs: {len(combined)}")
        print("\nFull breakdown:")
        print(combined["poi_type"].value_counts().to_string())
        print("\nSaved to m3_poi_raw.csv")
    else:
        print("No new data retrieved in retry.")
    