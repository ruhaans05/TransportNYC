import streamlit as st
import requests
import folium
import os
from datetime import datetime, timedelta
from streamlit_folium import st_folium

from google_maps import get_driving_route, get_transit_route
from flight_data import get_flights

GAS_PRICE = 2.972
MPG = 25

def estimate_gas_cost(miles):
    return round((miles / MPG) * GAS_PRICE, 2)

def get_place_suggestions(query):
    try:
        res = requests.get("https://nominatim.openstreetmap.org/search", params={
            "q": query, "format": "json", "addressdetails": 1, "limit": 5
        }, headers={"User-Agent": "TransportNYC-App"})
        return [{"label": i["display_name"], "value": (float(i["lat"]), float(i["lon"]))} for i in res.json()]
    except:
        return []

def show_map(start_coords, end_coords):
    m = folium.Map(location=[(start_coords[0] + end_coords[0]) / 2,
                             (start_coords[1] + end_coords[1]) / 2], zoom_start=11)
    folium.Marker(start_coords, tooltip="Start", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker(end_coords, tooltip="End", icon=folium.Icon(color="red")).add_to(m)
    return m

# === Streamlit UI ===
st.set_page_config(page_title="TransportNYC", layout="centered")
st.title("🚦 TransportNYC")
st.subheader("Optimize your routes for cost, gas, and time")

origin_query = st.text_input("Starting Point", key="origin_input")
destination_query = st.text_input("Destination", key="dest_input")

transport_modes = st.multiselect("Compare transport modes", [
    "Drive (with tolls)",
    "Drive (no tolls)",
    "Transit",
    "Flight"
], default=["Drive (no tolls)"])

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
    origin = st.session_state.origin_coords
    destination = st.session_state.dest_coords
    results = []

    with st.spinner("Fetching route data..."):

        if "Drive (with tolls)" in transport_modes:
            route = get_driving_route(origin, destination, avoid_tolls=False)
            if route:
                gas_cost = estimate_gas_cost(route["distance_miles"])
                results.append(("Drive (with tolls)", route["duration_mins"], route["distance_miles"], gas_cost))

        if "Drive (no tolls)" in transport_modes:
            route = get_driving_route(origin, destination, avoid_tolls=True)
            if route:
                gas_cost = estimate_gas_cost(route["distance_miles"])
                results.append(("Drive (no tolls)", route["duration_mins"], route["distance_miles"], gas_cost))

        if "Transit" in transport_modes:
            transit = get_transit_route(origin, destination)
            if transit:
                fare = transit["fare"] if transit["fare"] else 0
                results.append(("Transit", transit["duration_mins"], None, fare))

        if "Flight" in transport_modes:
            city_from = origin_query
            city_to = destination_query
            flights, error = get_flights(city_from, city_to)
            if error:
                st.write(f"✈️ Flight search failed: {error}")
            elif not flights:
                st.write("✈️ No flights found.")
            else:
                st.markdown("### ✈️ Flight Options")
                for f in flights:
                    st.write(f"• {f['from']} → {f['to']} | Airline: {f['airline']} | Duration: {f['duration']} | Price: ${f['price']}")

    if results:
        for mode, time, distance, cost in results:
            st.markdown(f"### 🚀 {mode}")
            st.write(f"**Time:** {time:.1f} minutes")
            if distance:
                st.write(f"**Distance:** {distance:.2f} miles")
            label = "Gas Cost" if "Drive" in mode else "Fare"
            st.write(f"**{label}:** ${cost:.2f}")

        st.markdown("### 🗺 Route Map")
        st_folium(show_map(origin, destination), width=700, height=400)
