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
        res = requests.get("https://nominatim.openstreetmap.org/reverse", params={
            "lat": lat, "lon": lon, "format": "json", "zoom": 10, "addressdetails": 1
        }, headers={"User-Agent": "TransportNYC-App"}, timeout=4)
        if res.status_code == 200:
            data = res.json()
            return data["address"].get("town") or data["address"].get("city") or data["address"].get("village") or "Unknown"
    except:
        return "Unknown"
    return "Unknown"

def get_weather_forecast(lat, lon):
    try:
        res = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,precipitation",
            "temperature_unit": "fahrenheit",
            "precipitation_unit": "inch"
        }, timeout=5)
        if res.status_code == 200:
            current = res.json()["current"]
            return f"{current['temperature_2m']}°F, {'Rainy' if current['precipitation'] > 0 else 'Clear'}"
    except:
        return "Weather unavailable"
    return "Weather unavailable"

def get_directions_osrm(start_coords, end_coords):
    res = requests.get(f"http://router.project-osrm.org/route/v1/driving/{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}", params={
        "overview": "full",
        "geometries": "geojson",
        "alternatives": "false",
        "steps": "false"
    })
    if res.status_code == 200 and res.json().get("routes"):
        route = res.json()["routes"][0]
        return {
            "duration_mins": route["duration"] / 60,
            "distance_miles": route["distance"] / 1609.34,
            "geometry": route["geometry"]
        }
    return None

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
        res = requests.get("https://nominatim.openstreetmap.org/search", params={
            "q": query, "format": "json", "addressdetails": 1, "limit": 5
        }, headers={"User-Agent": "TransportNYC-App"})
        return [{"label": i["display_name"], "value": (float(i["lat"]), float(i["lon"]))} for i in res.json()]
    except:
        return []

def describe_route(geometry):
    coords = geometry["coordinates"]
    water_hits = 0
    urban_hits = 0
    for lon, lat in coords:
        if -74.05 <= lon <= -73.95 and 40.5 <= lat <= 40.9:
            urban_hits += 1
        if any(abs(lat - b) < 0.01 for b in [40.6, 40.7, 40.85]):
            water_hits += 1
    total = len(coords)
    summary = []
    if urban_hits / total > 0.7:
        summary.append("mostly urban")
    elif urban_hits / total > 0.3:
        summary.append("mixed urban/suburban")
    else:
        summary.append("mostly suburban/rural")
    if water_hits > 2:
        summary.append("crosses rivers or bridges")
    if urban_hits / total > 0.6:
        summary.append("possible traffic and aggressive drivers")
    return ", ".join(summary).capitalize() + "."

# === Streamlit UI ===
st.set_page_config(page_title="TransportNYC", layout="centered")
st.title("🚦 TransportNYC")
st.subheader("Optimize your routes for cost, gas, and time")

origin_query = st.text_input("Starting Point", key="origin_input")
destination_query = st.text_input("Destination", key="dest_input")

if origin_query and len(origin_query) >= 3:
    origin_opts = get_place_suggestions(origin_query)
    if origin_opts:
        st.session_state.origin_coords = st.selectbox("Select Start", origin_opts, format_func=lambda x: x["label"], key="origin_select")["value"]

if destination_query and len(destination_query) >= 3:
    dest_opts = get_place_suggestions(destination_query)
    if dest_opts:
        st.session_state.dest_coords = st.selectbox("Select Destination", dest_opts, format_func=lambda x: x["label"], key="dest_select")["value"]

if st.button("Compare Routes"):
    st.session_state.run_triggered = True

if st.session_state.get("run_triggered") and st.session_state.get("origin_coords") and st.session_state.get("dest_coords"):
    with st.spinner("Fetching route..."):
        primary = get_directions_osrm(st.session_state.origin_coords, st.session_state.dest_coords)

    if not primary:
        st.error("Route fetch failed.")
    else:
        gas_used = primary['distance_miles'] / MPG
        gas_cost = estimate_gas_cost(primary['distance_miles'])
        toll_cost, toll_events = estimate_toll_from_geometry(primary["geometry"])
        total = gas_cost + toll_cost

        st.markdown("### 🚗 Route Summary")
        st.write(f"**Time:** {primary['duration_mins']:.1f} min")
        st.write(f"**Distance:** {primary['distance_miles']:.2f} mi")
        st.write(f"**Gas Used:** {gas_used:.2f} gal → ${gas_cost:.2f}")
        st.write(f"**Toll Cost:** ${toll_cost:.2f}")
        st.write(f"**Total Cost:** ${total:.2f}")
        st.markdown(f"**Route Style:** {describe_route(primary['geometry'])}")

        if toll_events:
            st.write("**Toll Points:**")
            for t in toll_events:
                name = t['zone'].replace("_", " ").title()
                town = get_town_name(t['lat'], t['lon'])
                st.write(f"• {name} in **{town}** (${t['amount']})")
        else:
            st.write("✅ No tolls on this route.")

        st.markdown("### 🌦️ Weather Forecast")
        for point in primary["geometry"]["coordinates"][::max(1, len(primary["geometry"]["coordinates"]) // 5)]:
            lat, lon = point[1], point[0]
            town = get_town_name(lat, lon)
            forecast = get_weather_forecast(lat, lon)
            st.write(f"📍 {town}: {forecast}")

        st.markdown("### 🗺 Route Map")
        st_folium(show_map(primary["geometry"], st.session_state.origin_coords, st.session_state.dest_coords), width=700, height=400)
