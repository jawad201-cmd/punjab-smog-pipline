import requests
import pandas as pd
from datetime import datetime
import time
import os
from sqlalchemy import create_engine, text
from locations import DISTRICTS, PUNJAB_MACRO_BBOX

# --- CONFIGURATION ---
# 1. Get sensitive data from Environment Variables
# (This works locally if you set them, and on GitHub Actions automatically)
NASA_KEY = os.environ.get("NASA_API_KEY")
OPENWEATHER_KEY = os.environ.get("OWM_API_KEY")
DB_CONNECTION_STR = os.environ.get("DATABASE_URL")

# 2. Safety Check: Stop immediately if keys are missing
if not all([NASA_KEY, OPENWEATHER_KEY, DB_CONNECTION_STR]):
    raise ValueError("Critical Error: Missing Environment Variables. Check your .env file or GitHub Secrets!")

# --- 1. GET FIRE DATA (Provincial Context) ---
def get_provincial_fires():
    """Fetches ALL fires in Punjab once to avoid API rate limits."""
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{NASA_KEY}/VIIRS_NOAA20_NRT/{PUNJAB_MACRO_BBOX}/1"
    try:
        df = pd.read_csv(url)
        # Filter out low confidence fires ('l' = low)
        df = df[df['confidence'] != 'l']
        return df
    except Exception as e:
        print(f"NASA Fetch Failed: {e}")
        return pd.DataFrame()

# --- 2. CALCULATE LOCAL IMPACT ---
def calculate_local_impact(city_lat, city_lon, all_fires_df):
    """Filters provincial fires to find those within ~55km of the city."""
    if all_fires_df.empty:
        return 0, 0

    # Approx 0.5 deg = 55km radius box
    lat_min, lat_max = city_lat - 0.5, city_lat + 0.5
    lon_min, lon_max = city_lon - 0.5, city_lon + 0.5

    local_fires = all_fires_df[
        (all_fires_df['latitude'] >= lat_min) & 
        (all_fires_df['latitude'] <= lat_max) & 
        (all_fires_df['longitude'] >= lon_min) & 
        (all_fires_df['longitude'] <= lon_max)
    ]
    
    return len(local_fires), local_fires['frp'].sum()

# --- 3. FETCH CITY DATA ---
def fetch_city_data(city_name, lat, lon, all_fires_df, provincial_load):
    # A. Local Fire Stats
    local_count, local_intensity = calculate_local_impact(lat, lon, all_fires_df)

    # B. OpenWeather (Smog)
    ow_url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={OPENWEATHER_KEY}"
    pm2_5, pm10 = None, None
    
    try:
        resp = requests.get(ow_url, timeout=10)
        if resp.status_code == 200:
            d = resp.json()['list'][0]['components']
            pm2_5, pm10 = d['pm2_5'], d['pm10']
    except Exception as e:
        print(f"   Smog fetch failed for {city_name}: {e}")

# ---------------------------------------------------------
    # C. WIND DATA (Dual-Source Strategy)
    # ---------------------------------------------------------
    wind_spd, wind_dir = None, None
    
    # --- PRIMARY SOURCE: OpenMeteo ---
    om_url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, 
        "longitude": lon, 
        "current": "wind_speed_10m,wind_direction_10m",
        "wind_speed_unit": "kmh"
    }
    
    # Try OpenMeteo (Plan A)
    try:
        resp = requests.get(om_url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if 'current' in data:
                wind_spd = data['current']['wind_speed_10m']
                wind_dir = data['current']['wind_direction_10m']
    except Exception as e:
        print(f"   OpenMeteo failed for {city_name}: {e}")

    # --- SECONDARY SOURCE: OpenWeatherMap (Fallback) ---
    # If Plan A failed (wind_spd is still None), use Plan B
    if wind_spd is None:
        print(f"   Triggering Backup (OWM) for {city_name}...")
        # Note: We use the 'weather' endpoint, not 'air_pollution'
        owm_url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_KEY}&units=metric"
        
        try:
            r = requests.get(owm_url, timeout=10)
            if r.status_code == 200:
                d = r.json()
                # OWM gives speed in m/s, so we convert to km/h (x 3.6)
                wind_spd = d['wind']['speed'] * 3.6
                wind_dir = d['wind']['deg']
                print(f"   Backup Saved the day: {wind_spd:.1f} km/h")
            else:
                print(f"   Backup also failed: {r.status_code}")
        except Exception as e:
            print(f"   Backup Error: {e}")
            
    # --- FINAL SAFETY NET ---
    # If both failed, use 0.0 so the Database doesn't crash with NULLs
    if wind_spd is None: 
        wind_spd = 0.0
    if wind_dir is None: 
        wind_dir = 0.0

    # Return the row
    return {
        # CRITICAL: We use 'now()' here, but we will floor it to the hour later
        "timestamp": datetime.now(), 
        "district": city_name,
        "pm2_5": pm2_5,
        "pm10": pm10,
        "wind_speed": wind_spd,
        "wind_dir": wind_dir,
        "provincial_fire_load": provincial_load,
        "local_fire_count": local_count,
        "local_fire_frp": local_intensity
    }

# --- 4. MAIN PIPELINE (With Idempotency) ---
def run_pipeline():
    print(f"--- Starting Pipeline at {datetime.now()} ---")
    
    # Step 1: Fetch Provincial Context
    all_fires_df = get_provincial_fires()
    provincial_load = all_fires_df['frp'].sum() if not all_fires_df.empty else 0
    print(f"Provincial Fire Load: {provincial_load} MW")

    # Step 2: Loop through Districts
    batch_data = []
    print(f"Processing {len(DISTRICTS)} districts...")
    
    for city, coords in DISTRICTS.items():
        print(f"   Fetching {city}...")
        row = fetch_city_data(city, coords['lat'], coords['lon'], all_fires_df, provincial_load)
        batch_data.append(row)
        time.sleep(1) # Respect API limits

    if not batch_data:
        print("No data collected. Exiting.")
        return

    # Step 3: Prepare Data for Database
    print("Preparing Database Upload...")
    df = pd.DataFrame(batch_data)
    
    # DATA CLEANING: Floor timestamp to the nearest hour
    # This ensures 10:05 and 10:55 both become "10:00:00"
    # This allows our Primary Key (timestamp + district) to reject duplicates
    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.floor('H')
    
    try:
        # Create Engine
        engine = create_engine(DB_CONNECTION_STR)
        
        with engine.connect() as conn:
            # A. Upload to "Staging" (Temporary Table)
            # 'if_exists="replace"' clears the staging table from any previous failed runs
            df.to_sql('smog_staging', conn, if_exists='replace', index=False)
            
            # B. Perform the "Upsert" (Merge)
            # This SQL moves data from Staging -> Main, IGNORING duplicates
            merge_query = text("""
                INSERT INTO smog_metrics (
                    timestamp, district, pm2_5, pm10, wind_speed, wind_dir, 
                    provincial_fire_load, local_fire_count, local_fire_frp
                )
                SELECT 
                    timestamp, district, pm2_5, pm10, wind_speed, wind_dir, 
                    provincial_fire_load, local_fire_count, local_fire_frp
                FROM smog_staging
                ON CONFLICT (timestamp, district) DO NOTHING;
            """)
            
            conn.execute(merge_query)
            conn.commit() # Commit the transaction
            
            print(f"SUCCESS: Processed {len(df)} rows. Duplicates were safely ignored.")
            
    except Exception as e:
        print(f"DATABASE ERROR: {e}")

if __name__ == "__main__":
    run_pipeline()