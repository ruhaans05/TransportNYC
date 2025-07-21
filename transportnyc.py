import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
import polyline as pl
from datetime import datetime

from google_maps import get_driving_route
from flight_data import get_flights, get_airports_by_coords

import googlemaps

# --- Google Places setup
PLACES_API_KEY = st.secrets["GCP"]["PLACES_API_KEY"]
gmaps_places = googlemaps.Client(key=PLACES_API_KEY)

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

    highways = extract_highways_from_steps(steps)
    if highways:
        folium.Marker(
            location=start_coords,
            icon=folium.DivIcon(html=f'<div style="font-size: 10pt">{label} uses:<br>' + "<br>".join(highways) + '</div>')
        ).add_to(m)
    return m

def format_coords(coords):
    return f"{coords[0]},{coords[1]}"

def find_nearby(category, lat, lon, radius=4000):
    """category: 'lodging', 'gas_station', or 'restaurant'"""
    try:
        res = gmaps_places.places_nearby(
            location=(lat, lon),
            radius=radius,
            type=category
        )
        results = res.get("results", [])
        if not results:
            return None
        r = results[0]
        return {
            "name": r.get("name"),
            "address": r.get("vicinity"),
            "rating": r.get("rating"),
            "maps_url": f"https://maps.google.com/?q={r['geometry']['location']['lat']},{r['geometry']['location']['lng']}"
        }
    except Exception as e:
        return None

# --- Initialize session state ---
for key in [
    "origin_coords", "dest_coords", "run_triggered",
    "flight_origin_airport", "flight_dest_airport"
]:
    if key not in st.session_state:
        st.session_state[key] = None if key != "run_triggered" else False

st.set_page_config(page_title="TransportNYC", layout="centered")
st.title("🚦 Hustler")
st.subheader("Optimize your routes for cost, gas, and time")

# 1. Transport mode selection
transport_modes = st.multiselect(
    "Choose transport modes", [
        "Drive (with tolls)",
        "Drive (no tolls)",
        "Flight"
    ],
    default=["Drive (no tolls)"]
)

# 2. MPG input (AFTER transport mode)
mpg_input = st.text_input("Optional: Enter your vehicle's mpg:", value="")
try:
    mpg_val = float(mpg_input)
    if mpg_val <= 0:
        raise ValueError
except:
    mpg_val = 22  # Default

# 3. Location selection
origin_query = st.text_input("Starting Point", key="origin_input")
destination_query = st.text_input("Destination", key="dest_input")

origin_coords, dest_coords = None, None

if origin_query and len(origin_query) >= 3:
    origin_opts = get_place_suggestions(origin_query)
    if origin_opts:
        st.session_state.origin_coords = st.selectbox(
            "Select Start", origin_opts,
            format_func=lambda x: x["label"], key="origin_select"
        )["value"]
        origin_coords = st.session_state.origin_coords

if destination_query and len(destination_query) >= 3:
    dest_opts = get_place_suggestions(destination_query)
    if dest_opts:
        st.session_state.dest_coords = st.selectbox(
            "Select Destination", dest_opts,
            format_func=lambda x: x["label"], key="dest_select"
        )["value"]
        dest_coords = st.session_state.dest_coords

# 4. Flight: Show dropdowns for airport selection if both coords exist
if "Flight" in transport_modes and origin_coords and dest_coords:
    airports_from = get_airports_by_coords(origin_coords[0], origin_coords[1])
    airports_to = get_airports_by_coords(dest_coords[0], dest_coords[1])
    st.session_state.flight_origin_airport = None
    st.session_state.flight_dest_airport = None
    if airports_from:
        st.session_state.flight_origin_airport = st.selectbox(
            "Select Departure Airport", airports_from,
            format_func=lambda x: f"{x['name']} ({x['iataCode']})", key="origin_airport_select"
        )
    if airports_to:
        st.session_state.flight_dest_airport = st.selectbox(
            "Select Arrival Airport", airports_to,
            format_func=lambda x: f"{x['name']} ({x['iataCode']})", key="dest_airport_select"
        )

if st.button("Find Routes"):
    st.session_state.run_triggered = True

if st.session_state.run_triggered and origin_coords and dest_coords:
    results = []
    with st.spinner("Fetching route data..."):
        tolled_route = None
        nontolled_route = None

        if "Drive (with tolls)" in transport_modes:
            tolled_route = get_driving_route(format_coords(origin_coords), format_coords(dest_coords), avoid_tolls=False)
            if tolled_route:
                gas_cost = estimate_gas_cost(tolled_route["distance_miles"], mpg_val)
                results.append(("Drive (with tolls)", tolled_route["duration_mins"], tolled_route["distance_miles"], gas_cost))

        if "Drive (no tolls)" in transport_modes:
            nontolled_route = get_driving_route(format_coords(origin_coords), format_coords(dest_coords), avoid_tolls=True)
            if nontolled_route:
                gas_cost = estimate_gas_cost(nontolled_route["distance_miles"], mpg_val)
                results.append(("Drive (no tolls)", nontolled_route["duration_mins"], nontolled_route["distance_miles"], gas_cost))

        if "Flight" in transport_modes:
            if st.session_state.flight_origin_airport and st.session_state.flight_dest_airport:
                flights, error = get_flights(
                    st.session_state.flight_origin_airport["iataCode"],
                    st.session_state.flight_dest_airport["iataCode"]
                )
                if error:
                    st.write(f"✈️ Airport error: {error}")
                elif not flights:
                    date_str = datetime.utcnow().strftime("%Y-%m-%d")
                    origin_txt = st.session_state.flight_origin_airport["iataCode"]
                    dest_txt = st.session_state.flight_dest_airport["iataCode"]
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
            label = "Approx. Gas Cost" if "Drive" in mode else "Fare"
            st.write(f"**{label}:** ${cost:.2f}")

        st.markdown("### 🗺 Route Maps")
        cols = st.columns(2 if (tolled_route and nontolled_route) else 1)

        if tolled_route:
            with cols[0]:
                st.markdown("#### Drive (with tolls)")
                map_tolled = show_map_with_route(
                    origin_coords, dest_coords,
                    tolled_route["polyline"], tolled_route["steps"], "With Tolls"
                )
                st_folium(map_tolled, width=700, height=400)

        if nontolled_route:
            with cols[1 if tolled_route else 0]:
                st.markdown("#### Drive (no tolls)")
                map_nontolled = show_map_with_route(
                    origin_coords, dest_coords,
                    nontolled_route["polyline"], nontolled_route["steps"], "No Tolls"
                )
                st_folium(map_nontolled, width=700, height=400)

        # ---- REST STOP PLANNER ----
        st.markdown("### 🚏 Plan your rest stops")
        interval_hours = st.number_input(
            "How many hours do you want between stops? (e.g., enter 3 for every 3 hours)",
            min_value=1, max_value=12, value=3, step=1
        )

        active_route = tolled_route if tolled_route else nontolled_route
        if active_route:
            steps = active_route["steps"]
            stops = []
            cum_time = 0
            intervals = []
            total_time = active_route["duration_mins"] / 60  # hours
            step_times = [s["duration"]["value"] / 60 for s in steps]

            next_stop = interval_hours
            for i, step in enumerate(steps):
                cum_time += step_times[i]
                if cum_time >= next_stop and next_stop < total_time:
                    loc = step["end_location"]
                    lat, lon = loc["lat"], loc["lng"]
                    intervals.append((next_stop, lat, lon))
                    next_stop += interval_hours

            if not intervals:
                st.write("Your route is too short for any stops with the current interval.")
            else:
                for i, (hr, lat, lon) in enumerate(intervals, 1):
                    st.markdown(f"#### Stop #{i} (Around {hr:.1f} hours from start)")
                    hotel = find_nearby('lodging', lat, lon)
                    gas = find_nearby('gas_station', lat, lon)
                    food = find_nearby('restaurant', lat, lon)

                    cols = st.columns(3)
                    with cols[0]:
                        if hotel:
                            st.write(f"🏨 **Hotel**: [{hotel['name']}]({hotel['maps_url']})")
                            st.write(f"Address: {hotel['address']}")
                            if hotel.get("rating"): st.write(f"Rating: {hotel['rating']}")
                        else:
                            st.write("No hotel found nearby.")
                    with cols[1]:
                        if gas:
                            st.write(f"⛽ **Gas**: [{gas['name']}]({gas['maps_url']})")
                            st.write(f"Address: {gas['address']}")
                            if gas.get("rating"): st.write(f"Rating: {gas['rating']}")
                        else:
                            st.write("No gas station found nearby.")
                    with cols[2]:
                        if food:
                            st.write(f"🍔 **Food**: [{food['name']}]({food['maps_url']})")
                            st.write(f"Address: {food['address']}")
                            if food.get("rating"): st.write(f"Rating: {food['rating']}")
                        else:
                            st.write("No restaurant found nearby.")
