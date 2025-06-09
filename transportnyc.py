import streamlit as st
import requests
import folium
from streamlit_folium import st_folium

GAS_PRICE = 2.972  # NYC MSA average gas price (June 2025)
MPG = 25

# === Toll Estimator ===
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

# === Session State ===
if "origin_coords" not in st.session_state:
    st.session_state.origin_coords = None
if "dest_coords" not in st.session_state:
    st.session_state.dest_coords = None
if "compare_clicked" not in st.session_state:
    st.session_state.compare_clicked = False

# === Route Description ===
def generate_route_description(geometry):
    description = []
    urban_coords = 0
    rural_coords = 0
    hill_coords = 0
    enforcement_zone_hits = 0

    for coord in geometry['coordinates']:
        lat, lon = coord[1], coord[0]
        if 40.5 <= lat <= 40.9 and -74.2 <= lon <= -73.7:
            urban_coords += 1
        else:
            rural_coords += 1
        if lat > 40.8 and lon < -74.0:
            hill_coords += 1
        if 40.7 < lat < 40.85 and -74.05 < lon < -73.95:
            enforcement_zone_hits += 1

    total = urban_coords + rural_coords
    if total == 0:
        return "No geographic context available."

    if urban_coords / total > 0.6:
        description.append("🚦 Primarily urban route—expect traffic, especially during peak hours.")
    elif rural_coords / total > 0.6:
        description.append("🌲 Mostly rural/suburban—less traffic but faster speeds.")
    else:
        description.append("🛣️ Mix of urban and suburban travel zones.")

    if enforcement_zone_hits > 20:
        description.append("🚓 Likely moderate to heavy police presence.")
    else:
        description.append("🆗 Minimal enforcement zones.")

    if hill_coords > 10:
        description.append("⛰️ Hilly terrain ahead—watch for conditions.")
    else:
        description.append("🌇 Mostly flat driving terrain.")

    return " ".join(description)

# === Helper Functions ===
def get_place_suggestions(input_text):
    if not input_text or len(input_text) < 3:
        return []
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": input_text, "format": "json", "addressdetails": 1, "limit": 5}
        headers = {"User-Agent": "TransportNYC-App"}
        res = requests.get(url, params=params, headers=headers, timeout=5)
        if res.status_code != 200:
            return []
        return [{"label": item["display_name"], "value": (float(item["lat"]), float(item["lon"]))} for item in res.json()]
    except requests.exceptions.RequestException:
        return []

def get_directions_osrm(start_coords, end_coords):
    url = f"http://router.project-osrm.org/route/v1/driving/{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}"
    params = {"overview": "full", "geometries": "geojson", "alternatives": "false", "steps": "false"}
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return None
    data = response.json()
    if not data.get("routes"):
        return None
    route = data["routes"][0]
    return {"duration_mins": route["duration"] / 60, "distance_miles": route["distance"] / 1609.34, "geometry": route["geometry"]}

def estimate_gas_cost(miles):
    return (miles / MPG) * GAS_PRICE

def show_osrm_route(geometry, start_coords, end_coords):
    m = folium.Map(location=[(start_coords[0] + end_coords[0]) / 2, (start_coords[1] + end_coords[1]) / 2], zoom_start=13)
    folium.GeoJson(geometry).add_to(m)
    folium.Marker(start_coords, tooltip="Start", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker(end_coords, tooltip="End", icon=folium.Icon(color="red")).add_to(m)
    return m

# === UI ===
st.set_page_config(page_title="TransportNYC", layout="centered")
st.title("🚦 TransportNYC")
st.subheader("Optimize your routes for cost, gas, and time")

origin_query = st.text_input("Starting Point (address, city, or landmark)", key="origin_input")
if len(origin_query) >= 3:
    origin_options = get_place_suggestions(origin_query)
    if origin_options:
        selected_origin = st.selectbox("Choose Starting Location", origin_options, format_func=lambda x: x["label"], key="origin_select")
        st.session_state.origin_coords = selected_origin["value"]

destination_query = st.text_input("Destination (address, city, or landmark)", key="dest_input")
if len(destination_query) >= 3:
    dest_options = get_place_suggestions(destination_query)
    if dest_options:
        selected_dest = st.selectbox("Choose Destination", dest_options, format_func=lambda x: x["label"], key="dest_select")
        st.session_state.dest_coords = selected_dest["value"]

if st.button("Compare Routes"):
    st.session_state.compare_clicked = True

if st.session_state.compare_clicked:
    if not st.session_state.origin_coords or not st.session_state.dest_coords:
        st.warning("Please enter and select both a starting point and a destination.")
    else:
        with st.spinner("Fetching route details..."):
            drive = get_directions_osrm(st.session_state.origin_coords, st.session_state.dest_coords)
            if not drive:
                st.error("Failed to retrieve route data. Please try different locations.")
            else:
                gas_used = drive['distance_miles'] / MPG
                gas_cost = estimate_gas_cost(drive['distance_miles'])
                toll_cost, toll_events = estimate_toll_from_geometry(drive["geometry"])
                total_cost = gas_cost + toll_cost
                description = generate_route_description(drive["geometry"])

                col1, col2 = st.columns([1.1, 1.4])
                with col1:
                    map_object = show_osrm_route(drive["geometry"], st.session_state.origin_coords, st.session_state.dest_coords)
                    st_folium(map_object, width=350, height=300)
                with col2:
                    st.markdown("### 🧭 Route Summary")
                    st.subheader("🚗 Driving")
                    st.write(f"Time: {drive['duration_mins']:.1f} min")
                    st.write(f"Distance: {drive['distance_miles']:.2f} mi")
                    st.write(f"Gas Used: {gas_used:.2f} gal")
                    st.write(f"Gas Cost: ${gas_cost:.2f}")
                    st.write(f"Toll Cost: ${toll_cost:.2f}")
                    st.write(f"Total Estimated Cost: ${total_cost:.2f}")
                    if toll_events:
                        st.markdown("#### 🧾 Toll Payment Points")
                        for toll in toll_events:
                            name = toll["zone"].replace("_", " ").title()
                            if toll["zone"] == "NJ_TPK":
                                st.write(f"🛣️ {name} - Est. ${toll['amount']} (mileage-based system).")
                            else:
                                st.write(f"🪙 {name} - ${toll['amount']} near ({toll['lat']}°N, {toll['lon']}°W)")
                    else:
                        st.write("💸 No toll zones detected along this route.")
                    st.markdown("---")
                    st.subheader("📊 Efficiency Results")
                    st.write(f"⏱ **Most Time Efficient:** Driving (only mode supported)")
                    st.write(f"💸 **Estimated Total Cost (Gas + Tolls):** ${total_cost:.2f}")
                    st.write(f"⛽ **Gas Efficiency:** {gas_used:.2f} gallons used")
                    st.markdown("---")
                    st.subheader("📍 Route Description")
                    st.write(description)
