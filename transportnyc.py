import streamlit as st
import requests
import folium
from streamlit_folium import st_folium

from google_maps import get_driving_route
from flight_data import get_flights

GAS_PRICE = 3.140
MPG = 22.5

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

def show_map_with_route(start_coords, end_coords, polyline):
    m = folium.Map(location=[(start_coords[0] + end_coords[0]) / 2,
                             (start_coords[1] + end_coords[1]) / 2], zoom_start=11)
    folium.Marker(start_coords, tooltip="Start", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker(end_coords, tooltip="End", icon=folium.Icon(color="red")).add_to(m)

    # Decode polyline and add route line
    import polyline as pl
    points = pl.decode(polyline)
    folium.PolyLine(points, color="blue", weight=5, opacity=0.7).add_to(m)
    return m

def format_coords(coords):
    return f"{coords[0]},{coords[1]}"

if "origin_coords" not in st.session_state:
    st.session_state.origin_coords = None
if "dest_coords" not in st.session_state:
    st.session_state.dest_coords = None
if "run_triggered" not in st.session_state:
    st.session_state.run_triggered = False

st.set_page_config(page_title="TransportNYC", layout="centered")
st.title("🚦 TransportNYC")
st.subheader("Optimize your routes for cost, gas, and time")

origin_query = st.text_input("Starting Point", key="origin_input")
destination_query = st.text_input("Destination", key="dest_input")

# Removed Transit option here
transport_modes = st.multiselect("Compare transport modes", [
    "Drive (with tolls)",
    "Drive (no tolls)",
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

if st.session_state.run_triggered and st.session_state.origin_coords and st.session_state.dest_coords:
    origin = st.session_state.origin_coords
    destination = st.session_state.dest_coords
    results = []

    with st.spinner("Fetching route data..."):

        # Keep these so we get route data for maps too
        tolled_route = None
        nontolled_route = None

        if "Drive (with tolls)" in transport_modes:
            tolled_route = get_driving_route(format_coords(origin), format_coords(destination), avoid_tolls=False)
            if tolled_route:
                gas_cost = estimate_gas_cost(tolled_route["distance_miles"])
                results.append(("Drive (with tolls)", tolled_route["duration_mins"], tolled_route["distance_miles"], gas_cost))

        if "Drive (no tolls)" in transport_modes:
            nontolled_route = get_driving_route(format_coords(origin), format_coords(destination), avoid_tolls=True)
            if nontolled_route:
                gas_cost = estimate_gas_cost(nontolled_route["distance_miles"])
                results.append(("Drive (no tolls)", nontolled_route["duration_mins"], nontolled_route["distance_miles"], gas_cost))

        if "Flight" in transport_modes:
            flights, error = get_flights(origin, destination)
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
            if distance is not None:
                st.write(f"**Distance:** {distance:.2f} miles")
            label = "Gas Cost" if "Drive" in mode else "Fare"
            st.write(f"**{label}:** ${cost:.2f}")

        st.markdown("### 🗺 Route Maps")

        # Show side-by-side maps for tolled and non-tolled routes if both exist
        cols = st.columns(2 if (tolled_route and nontolled_route) else 1)

        if tolled_route:
            with cols[0]:
                st.markdown("#### Drive (with tolls)")
                map_tolled = show_map_with_route(origin, destination, tolled_route["polyline"])
                st_folium(map_tolled, width=700, height=400)

        if nontolled_route:
            with cols[1 if tolled_route else 0]:
                st.markdown("#### Drive (no tolls)")
                map_nontolled = show_map_with_route(origin, destination, nontolled_route["polyline"])
                st_folium(map_nontolled, width=700, height=400)
