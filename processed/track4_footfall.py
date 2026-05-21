import requests
import pandas as pd

def query_overpass(query):
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (EV Research Project)"
    }
    
    servers = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
    ]
    
    import time
    
    for server in servers:
        print(f"  Trying {server}...")
        try:
            time.sleep(10)  # wait 10 seconds between attempts
            response = requests.post(
                server,
                data={"data": query},
                headers=headers,
                timeout=120
            )
            if response.status_code == 200:
                return response.json()
            else:
                print(f"  Status {response.status_code}, trying next...")
        except Exception as e:
            print(f"  Error: {e}, trying next...")
    
    return None

def main():
    print("Fetching restaurants and food places from OSM...")

    bbox = "12.834,77.480,13.139,77.780"

    query = f"""
    [out:json][timeout:90];
    (
      node["amenity"~"restaurant|cafe|fast_food|food_court"]({bbox});
      way["amenity"~"restaurant|cafe|fast_food|food_court"]({bbox});
    );
    out center tags;
    """

    data = query_overpass(query)

    if not data:
        print("Failed to fetch data.")
        return

    elements = data.get("elements", [])
    print(f"Raw results: {len(elements)} food places found")

    rows = []
    for el in elements:
        if el["type"] == "node":
            lat = el.get("lat")
            lon = el.get("lon")
        else:
            center = el.get("center", {})
            lat = center.get("lat")
            lon = center.get("lon")

        if not lat or not lon:
            continue

        tags = el.get("tags", {})
        rows.append({
            "name":     tags.get("name", "Unknown"),
            "type":     tags.get("amenity", ""),
            "lat":      lat,
            "lon":      lon,
            "cuisine":  tags.get("cuisine", ""),
            "source":   "OSM"
        })

    df = pd.DataFrame(rows)
    df.to_csv("m4_restaurants_raw.csv", index=False)

    print(f"Saved {len(df)} food places to m4_restaurants_raw.csv")
    print("\nBreakdown by type:")
    print(df["type"].value_counts().to_string())

if __name__ == "__main__":
    main()