import requests
import pandas as pd

def fetch_evyatra():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://evyatra.beeindia.gov.in/"
    }

    # Try three endpoints as per playbook
    endpoints = [
        "https://evyatra.beeindia.gov.in/api/chargingstations/",
        "https://evyatra.beeindia.gov.in/api/get-charging-station-list/",
        "https://evyatra.beeindia.gov.in/api/stations/"
    ]

    data = None
    working_url = None

    for url in endpoints:
        print(f"Trying {url} ...")
        try:
            response = requests.get(url, headers=headers, timeout=30)
            print(f"  Status code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                working_url = url
                print(f"  Success!")
                break
            else:
                print(f"  Failed with status {response.status_code}")
        except Exception as e:
            print(f"  Error: {e}")

    if not data:
        print("\nAll EV Yatra endpoints failed.")
        print("This is expected — the endpoint rotates periodically.")
        print("We'll rely on OSM data alone for now.")
        return None

    print(f"\nWorking endpoint: {working_url}")
    print(f"Total records received: {len(data)}")

    # Parse into dataframe
    rows = []
    for station in data:
        # Filter to Karnataka / Bengaluru
        state = str(station.get("state", "") or station.get("State", "")).lower()
        city  = str(station.get("city",  "") or station.get("City",  "")).lower()

        if "karnataka" not in state and "bengaluru" not in city and "bangalore" not in city:
            continue

        rows.append({
            "station_name":          station.get("name") or station.get("station_name") or "Unknown",
            "operator":              station.get("operator") or station.get("cpo_name") or "Unknown",
            "address":               station.get("address") or station.get("location") or "",
            "lat":                   station.get("lat") or station.get("latitude"),
            "lon":                   station.get("lon") or station.get("longitude") or station.get("lng"),
            "power_kw":              station.get("power") or station.get("power_kw") or "",
            "charger_type_dc_fast":  False,  # will classify after
            "source":                "EV Yatra",
            "review_count":          0
        })

    df = pd.DataFrame(rows)
    
    if df.empty:
        print("No Bengaluru stations found in response.")
        return None

    # Drop rows with no coordinates
    df = df.dropna(subset=["lat", "lon"])
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])

    print(f"Bengaluru stations found: {len(df)}")
    df.to_csv("m2_chargers_evyatra.csv", index=False)
    print("Saved to m2_chargers_evyatra.csv")
    return df

if __name__ == "__main__":
    fetch_evyatra()