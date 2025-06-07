import streamlit as st
import requests
import os
import folium
from streamlit_folium import st_folium
from dotenv import load_dotenv

# === Constants ===
GAS_PRICE = 2.972  # NYC MSA average June 2025
MPG = 25
DEFAULT_TRANSIT_FARE = 2.90

# === Load Google API Key ===
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")

# === Nominatim (Free) for Autocomplete ===
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

    return [item["display_name"] for item in res.json()]

# === Google Directions API ===
def get_directions(start, end, mode, stop=None):
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": start,
        "destination": end,
        "mode": mode,
        "departure_time": "now",
        "key": API_KEY,
        "region": "us",
        "units": "imperial"
    }
    if stop:
        params["waypoints"] = stop
    if mode == "driving":
        params["traffic_model"] = "best_guess"
        params["avoid"] = "ferries"

    res = requests.get(url, params=params).json()
    if res["status"] != "OK":
        return None

    route = res["routes"][0]["legs"][0]
    polyline = res["routes"][0]["overview_polyline"]["points"]
    duration = route.get("duration_in_traffic", route["duration"])["value"] / 60
    distance = route["distance"]["value"] / 1609.34
    fare = route.get("fare", {}).get("value", None)
    steps = route["steps"]

    tolls_present = any("toll" in step.get("html_instructions", "").lower() for step in steps)

    return {
        "duration_mins": duration,
        "distance_miles": distance,
        "fare": fare,
        "toll_flag": tolls_present,
        "polyline": polyline,
        "start_location": route["start_location"],
        "end_location": route["end_location"]
    }

# === Utilities ===
def estimate_gas_cost(miles):
    return (miles / MPG) * GAS_PRICE

def estimate_tolls(origin, destination):
    crossing_toll = ["nj", "ct", "long island", "brooklyn", "bronx", "queens"]
    if any(loc in origin.lower() for loc in crossing_toll) and "manhattan" in destination.lower():
        return 13.38
    return 0

def show_map(start_latlon, end_latlon):
    m = folium.Map(location=[(start_latlon['lat'] + end_latlon['lat']) / 2,
                             (start_latlon['lng'] + end_latlon['lng']) / 2],
                   zoom_start=11)
    folium.Marker([start_latlon['lat'], start_latlon['lng']], tooltip="Start", icon=folium.Icon(color='green')).add_to(m)
    folium.Marker([end_latlon['lat'], end_latlon['lng']], tooltip="End", icon=folium.Icon(color='red')).add_to(m)
    st_folium(m, width=700)

# === UI ===
st.set_page_config(page_title="TransportNYC", layout="centered")
st.title("🚦 TransportNYC")
st.subheader("Optimize your routes for cost, gas, and time")

# === Inputs with Dynamic Autocomplete ===
st.write("### 📍 Enter Your Route")

origin = None
origin_query = st.text_input("Starting Point (address, city, landmark)")
if len(origin_query) >= 3:
    origin_suggestions = get_place_suggestions(origin_query)
    if origin_suggestions:
        origin = st.selectbox("Choose Starting Location", origin_suggestions)

destination = None
destination_query = st.text_input("Destination (address, city, landmark)")
if len(destination_query) >= 3:
    destination_suggestions = get_place_suggestions(destination_query)
    if destination_suggestions:
        destination = st.selectbox("Choose Destination", destination_suggestions)

stopover = None
stop_query = st.text_input("Optional Stopover")
if len(stop_query) >= 3:
    stop_suggestions = get_place_suggestions(stop_query)
    if stop_suggestions:
        stopover = st.selectbox("Choose Stopover", stop_suggestions)

# === Compare Button ===
if st.button("Compare Routes"):
    if not origin or not destination:
        st.warning("Please enter and select both a starting point and a destination.")
    else:
        with st.spinner("Fetching route details..."):
            drive = get_directions(origin, destination, "driving", stopover)
            transit = get_directions(origin, destination, "transit", stopover)

            if not drive or not transit:
                st.error("Failed to retrieve route data. Please try different locations.")
            else:
                gas_used = drive['distance_miles'] / MPG
                gas_cost = estimate_gas_cost(drive['distance_miles'])
                toll_cost = estimate_tolls(origin, destination) if drive["toll_flag"] else 0
                drive_cost = gas_cost + toll_cost
                transit_cost = transit["fare"] if transit["fare"] is not None else DEFAULT_TRANSIT_FARE

                show_map(drive["start_location"], drive["end_location"])

                st.markdown("### 🧭 Route Summary")
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("🚗 Driving")
                    st.write(f"Time: {drive['duration_mins']:.1f} min")
                    st.write(f"Distance: {drive['distance_miles']:.2f} mi")
                    st.write(f"Gas Used: {gas_used:.2f} gal")
                    st.write(f"Gas Cost: ${gas_cost:.2f}")
                    st.write(f"Tolls: ${toll_cost:.2f}")
                    st.write(f"Total Cost: ${drive_cost:.2f}")
                with col2:
                    st.subheader("🚌 Public Transport")
                    st.write(f"Time: {transit['duration_mins']:.1f} min")
                    st.write(f"Fare: ${transit_cost:.2f}")

                st.markdown("---")
                st.subheader("📊 Efficiency Results")
                faster = "Driving" if drive["duration_mins"] < transit["duration_mins"] else "Transit"
                cheaper = "Driving" if drive_cost < transit_cost else "Transit"
                st.write(f"⏱ **Most Time Efficient:** {faster}")
                st.write(f"💸 **Most Cost Efficient:** {cheaper}")
                st.write(f"⛽ **Gas Efficiency:** {gas_used:.2f} gallons used")

                if drive["toll_flag"]:
                    st.info("This route contains toll roads.")
