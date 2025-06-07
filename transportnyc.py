import streamlit as st
import requests
import folium
from streamlit_folium import st_folium

# === Constants ===
GAS_PRICE = 2.972  # NYC MSA average gas price (June 2025)
MPG = 25

# === Nominatim Autocomplete ===
def get_place_suggestions(input_text):
    if not input_text or len(input_text) < 3:
        return []

    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": input_text,
        "format": "json",
        "addressdetails": 1,
        "limit": 5
    }
    headers = {
        "User-Agent": "TransportNYC-App"
    }

    res = requests.get(url, params=params, headers=headers)
    if res.status_code != 200:
        return []

    return [
        {
            "label": item["display_name"],
            "value": (float(item["lat"]), float(item["lon"]))
        }
        for item in res.json()
    ]

# === OSRM Directions API ===
def get_directions_osrm(start_coords, end_coords):
    url = f"http://router.project-osrm.org/route/v1/driving/{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "alternatives": "false",
        "steps": "false"
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return None
    data = response.json()
    if not data.get("routes"):
        return None
    route = data["routes"][0]
    duration = route["duration"] / 60  # seconds to minutes
    distance = route["distance"] / 1609.34  # meters to miles
    geometry = route["geometry"]
    return {
        "duration_mins": duration,
        "distance_miles": distance,
        "geometry": geometry
    }

# === Utilities ===
def estimate_gas_cost(miles):
    return (miles / MPG) * GAS_PRICE

def show_osrm_route(geometry, start_coords, end_coords):
    m = folium.Map(location=[(start_coords[0] + end_coords[0]) / 2,
                             (start_coords[1] + end_coords[1]) / 2],
                   zoom_start=13)
    folium.GeoJson(geometry, name="route").add_to(m)
    folium.Marker(location=start_coords, tooltip="Start", icon=folium.Icon(color='green')).add_to(m)
    folium.Marker(location=end_coords, tooltip="End", icon=folium.Icon(color='red')).add_to(m)
    st_folium(m, width=700)

# === UI ===
st.set_page_config(page_title="TransportNYC", layout="centered")
st.title("🚦 TransportNYC")
st.subheader("Optimize your routes for cost, gas, and time")

st.write("### 📍 Enter Your Route")

origin_query = st.text_input("Starting Point (address, city, or landmark)")
origin = None
if len(origin_query) >= 3:
    origin_options = get_place_suggestions(origin_query)
    if origin_options:
        selected = st.selectbox("Choose Starting Location", origin_options, format_func=lambda x: x["label"], key="origin")
        origin = selected["value"]

destination_query = st.text_input("Destination (address, city, or landmark)")
destination = None
if len(destination_query) >= 3:
    dest_options = get_place_suggestions(destination_query)
    if dest_options:
        selected = st.selectbox("Choose Destination", dest_options, format_func=lambda x: x["label"], key="dest")
        destination = selected["value"]

# === Compare Button ===
if st.button("Compare Routes"):
    if not origin or not destination:
        st.warning("Please enter and select both a starting point and a destination.")
    else:
        with st.spinner("Fetching route details..."):
            drive = get_directions_osrm(origin, destination)
            if not drive:
                st.error("Failed to retrieve route data. Please try different locations.")
            else:
                gas_used = drive['distance_miles'] / MPG
                gas_cost = estimate_gas_cost(drive['distance_miles'])

                show_osrm_route(drive["geometry"], origin, destination)

                st.markdown("### 🧭 Route Summary")
                st.subheader("🚗 Driving")
                st.write(f"Time: {drive['duration_mins']:.1f} min")
                st.write(f"Distance: {drive['distance_miles']:.2f} mi")
                st.write(f"Gas Used: {gas_used:.2f} gal")
                st.write(f"Gas Cost: ${gas_cost:.2f}")
                st.markdown("---")
                st.subheader("📊 Efficiency Results")
                st.write(f"⏱ **Most Time Efficient:** Driving (only mode supported)")
                st.write(f"💸 **Estimated Cost (Gas only):** ${gas_cost:.2f}")
                st.write(f"⛽ **Gas Efficiency:** {gas_used:.2f} gallons used")
