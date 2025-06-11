
import streamlit as st
import requests
import folium
from streamlit_folium import st_folium

GAS_PRICE = 2.972
MPG = 25

TOLL_ZONES = {
    "GWB": {"lat_min": 40.85, "lat_max": 40.87, "lon_min": -73.96, "lon_max": -73.93, "toll": 16.06},
    "HOLLAND_TUNNEL": {"lat_min": 40.72, "lat_max": 40.74, "lon_min": -74.02, "lon_max": -74.0, "toll": 16.06},
    "LINCOLN_TUNNEL": {"lat_min": 40.76, "lat_max": 40.78, "lon_min": -74.01, "lon_max": -73.99, "toll": 16.06},
    "VERRAZZANO": {"lat_min": 40.6, "lat_max": 40.62, "lon_min": -74.05, "lon_max": -74.02, "toll": 6.94},
    "NJ_TPK": {"lat_min": 40.65, "lat_max": 40.85, "lon_min": -74.3, "lon_max": -74.1, "toll": 7.0},
    "GSP": {"lat_min": 40.4, "lat_max": 40.9, "lon_min": -74.3, "lon_max": -74.0, "toll": 2.0}
}

def estimate_toll_from_geometry(geometry):
    toll_total = 0.0
    visited = set()
    toll_events = []
    for coord in geometry['coordinates']:
        lat, lon = coord[1], coord[0]
        for zone, bounds in TOLL_ZONES.items():
            if bounds["lat_min"] <= lat <= bounds["lat_max"] and bounds["lon_min"] <= lon <= bounds["lon_max"]:
                if zone not in visited:
                    toll_total += bounds["toll"]
                    visited.add(zone)
                    toll_events.append({
                        "zone": zone,
                        "lat": round(lat, 5),
                        "lon": round(lon, 5),
                        "amount": bounds["toll"]
                    })
    return round(toll_total, 2), toll_events

def get_town_name(lat, lon):
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {"lat": lat, "lon": lon, "format": "json", "zoom": 10, "addressdetails": 1}
        headers = {"User-Agent": "TransportNYC-App"}
        res = requests.get(url, params=params, headers=headers, timeout=4)
        if res.status_code == 200:
            data = res.json()
            return data["address"].get("town") or data["address"].get("city") or data["address"].get("village") or "Unknown area"
    except:
        pass
    return "Unknown area"

def get_weather_forecast(lat, lon):
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,precipitation",
            "temperature_unit": "fahrenheit",
            "precipitation_unit": "inch"
        }
        res = requests.get(url, params=params, timeout=5)
        if res.status_code == 200:
            data = res.json()
            temp = data["current"]["temperature_2m"]
            precip = data["current"]["precipitation"]
            return f"{temp}°F, {'Rainy' if precip > 0 else 'Clear'}"
    except:
        pass
    return "Weather unavailable"

def get_directions_osrm(start_coords, end_coords):
    base = f"http://router.project-osrm.org/route/v1/driving/{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "alternatives": "false",
        "steps": "false"
    }
    response = requests.get(base, params=params)
    if response.status_code != 200:
        return None
    data = response.json()
    if not data.get("routes"):
        return None
    route = data["routes"][0]
    return {
        "duration_mins": route["duration"] / 60,
        "distance_miles": route["distance"] / 1609.34,
        "geometry": route["geometry"]
    }

def estimate_gas_cost(miles):
    return (miles / MPG) * GAS_PRICE

def show_map(geometry, start_coords, end_coords):
    m = folium.Map(location=[(start_coords[0] + end_coords[0]) / 2,
                             (start_coords[1] + end_coords[1]) / 2], zoom_start=11)
    folium.GeoJson(geometry).add_to(m)
    folium.Marker(start_coords, tooltip="Start", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker(end_coords, tooltip="End", icon=folium.Icon(color="red")).add_to(m)
    return m

def get_place_suggestions(query):
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": query, "format": "json", "addressdetails": 1, "limit": 5}
        headers = {"User-Agent": "TransportNYC-App"}
        res = requests.get(url, params=params, headers=headers)
        return [{"label": i["display_name"], "value": (float(i["lat"]), float(i["lon"]))} for i in res.json()]
    except:
        return []

# === Streamlit UI ===
st.set_page_config(page_title="TransportNYC", layout="centered")
st.title("🚦 TransportNYC")
st.subheader("Optimize your routes for cost, gas, and time")

origin_query = st.text_input("Starting Point", key="origin_input")
destination_query = st.text_input("Destination", key="dest_input")

if origin_query and len(origin_query) >= 3:
    origin_opts = get_place_suggestions(origin_query)
    if origin_opts:
        origin_coords = st.selectbox("Select Start", origin_opts, format_func=lambda x: x["label"], key="origin_select")["value"]

if destination_query and len(destination_query) >= 3:
    dest_opts = get_place_suggestions(destination_query)
    if dest_opts:
        dest_coords = st.selectbox("Select Destination", dest_opts, format_func=lambda x: x["label"], key="dest_select")["value"]

if st.button("Compare Routes"):
    with st.spinner("Fetching main route..."):
        primary = get_directions_osrm(origin_coords, dest_coords)
    if not primary:
        st.error("Primary route failed.")
    else:
        gas_used = primary['distance_miles'] / MPG
        gas_cost = estimate_gas_cost(primary['distance_miles'])
        toll_cost, toll_events = estimate_toll_from_geometry(primary["geometry"])
        total = gas_cost + toll_cost

        col1, col2 = st.columns([1, 1.4])
        with col1:
            st_folium(show_map(primary["geometry"], origin_coords, dest_coords), width=400, height=300)
        with col2:
            st.markdown("### 🚗 Main Route")
            st.write(f"Time: {primary['duration_mins']:.1f} min")
            st.write(f"Distance: {primary['distance_miles']:.2f} mi")
            st.write(f"Gas Used: {gas_used:.2f} gal")
            st.write(f"Toll Cost: ${toll_cost:.2f}")
            st.write(f"Total Cost: ${total:.2f}")
            if toll_events:
                st.write("**Toll Points:**")
                for t in toll_events:
                    place = get_town_name(t['lat'], t['lon'])
                    name = t['zone'].replace("_", " ").title()
                    st.write(f"• {name} in **{place}** (${t['amount']})")
            else:
                st.write("✅ No tolls on this route.")

        st.markdown("### 🌦️ Forecast Along Route")
        coords = primary["geometry"]["coordinates"]
        sample_points = coords[::max(1, len(coords) // 5)]
        for i, point in enumerate(sample_points):
            lat, lon = point[1], point[0]
            weather = get_weather_forecast(lat, lon)
            loc = get_town_name(lat, lon)
            st.write(f"📍 {loc}: {weather}")
