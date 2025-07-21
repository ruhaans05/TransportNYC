import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
import polyline as pl
from datetime import datetime

from google_maps import get_driving_route
from flight_data import get_flights

GAS_PRICE = 3.140

def estimate_gas_cost(miles, mpg):
    return round((miles / mpg) * GAS_PRICE, 2)

def get_place_suggestions(query):
    try:
        res = requests.get("https://nominatim.openstreetmap.org/search", params={
            "q": query, "format": "json", "addressdetails": 1, "limit": 5
        }, headers={"User-Agent": "TransportNYC-App"})
        return [{"label": i["display_name"], "value": (float(i["lat"]), float(i["lon"]))} for i in res.json()]
    except:
        return []

def extract_highways_from_steps(steps):
    highways = []
    for step in steps:
        instr = step.get("html_instructions", "")
        if any(k in instr for k in ["I-", "US-", "Route", "Hwy", "Highway", "Turnpike", "Freeway", "Parkway"]):
            highways.append(instr)
    return list(set(highways))[:6]

def show_map_with_route(start_coords, end_coords, polyline_str, steps, label):
    m = folium.Map(location=[(start_coords[0] + end_coords[0]) / 2,
                             (start_coords[1] + end_coords[1]) / 2], zoom_start=11)
    folium.Marker(start_coords, tooltip="Start", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker(end_coords, tooltip="End", icon=folium.Icon(color="red")).add_to(m)
    points = pl.decode(polyline_str)
    folium.PolyLine(points, color="blue", weight=5, opacity=0.7).add_to(m)

    # Add highway info as floating text
    highways = extract_highways_from_steps(steps)
    if highways:
        folium.Marker(
            location=start_coords,
            icon=folium.DivIcon(html=f'<div style="font-size: 10pt">{label} uses:<br>' + "<br>".join(highways) + '</div>')
        ).add_to(m)

    return m

def format_coords(coords):
    return f"{coords[0]},{coords[1]}"

# Initialize session state
for key in ["origin_coords", "dest_coords", "run_triggered"]:
    if key not in st.session_state:
        st.session_state[key] = None if key != "run_triggered" else False

st.set_page_config(page_title="TransportNYC", layout="centered")
st.title("🚦 Hustler")
st.subheader("Optimize your routes for cost, gas, and time")

mpg_input = st.text_input("Optional: Enter your car's MPG (miles per gallon)", value="")
try:
    mpg_val = float(mpg_input)
    if mpg_val <= 0:
        raise ValueError
except:
    mpg_val = 22  # Default if blank/invalid

origin_query = st.text_input("Starting Point", key="origin_input")
destination_query = st.text_input("Destination", key="dest_input")

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
        tolled_route = None
        nontolled_route = None

        if "Drive (with tolls)" in transport_modes:
            tolled_route = get_driving_route(format_coords(origin), format_coords(destination), avoid_tolls=False)
            if tolled_route:
                gas_cost = estimate_gas_cost(tolled_route["distance_miles"], mpg_val)
                results.append(("Drive (with tolls)", tolled_route["duration_mins"], tolled_route["distance_miles"], gas_cost))

        if "Drive (no tolls)" in transport_modes:
            nontolled_route = get_driving_route(format_coords(origin), format_coords(destination), avoid_tolls=True)
            if nontolled_route:
                gas_cost = estimate_gas_cost(nontolled_route["distance_miles"], mpg_val)
                results.append(("Drive (no tolls)", nontolled_route["duration_mins"], nontolled_route["distance_miles"], gas_cost))

        if "Flight" in transport_modes:
            flights, error = get_flights(origin, destination)
            if error:
                st.write(f"✈️ Airport error: {error}")
            elif not flights:
                date_str = datetime.utcnow().strftime("%Y-%m-%d")
                origin_txt = origin_query.replace(" ", "+")
                dest_txt = destination_query.replace(" ", "+")
                link = f"https://www.google.com/travel/flights?q=flights+from+{origin_txt}+to+{dest_txt}+on+{date_str}"
                st.markdown(f"✈️ No flights found. [Search on Google Flights]({link})")
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
        cols = st.columns(2 if (tolled_route and nontolled_route) else 1)

        if tolled_route:
            with cols[0]:
                st.markdown("#### Drive (with tolls)")
                map_tolled = show_map_with_route(origin, destination, tolled_route["polyline"], tolled_route["steps"], "With Tolls")
                st_folium(map_tolled, width=700, height=400)

        if nontolled_route:
            with cols[1 if tolled_route else 0]:
                st.markdown("#### Drive (no tolls)")
                map_nontolled = show_map_with_route(origin, destination, nontolled_route["polyline"], nontolled_route["steps"], "No Tolls")
                st_folium(map_nontolled, width=700, height=400)
