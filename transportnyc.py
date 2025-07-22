import streamlit as st
import os
import json
from datetime import datetime
import hashlib
import requests
import folium
from streamlit_folium import st_folium
import polyline as pl
from openrouteservice_api import get_driving_route, get_interval_coords, search_nearby_pois

# ================= USER & CHAT SYSTEM ====================
USERS_FILE = "users.json"
CHAT_FILE = "chat.json"

def load_json(filename, default):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    return default

def save_json(filename, obj):
    with open(filename, "w") as f:
        json.dump(obj, f, indent=2)

def hash_pw(password):
    return hashlib.sha256(password.encode()).hexdigest()

users = load_json(USERS_FILE, [])
chat_log = load_json(CHAT_FILE, [])

if users and isinstance(users[0], str):
    users = [{"username": u, "password": ""} for u in users]
    save_json(USERS_FILE, users)

def get_user_obj(username, users_list=None):
    if users_list is None:
        users_list = users
    for user in users_list:
        if user["username"] == username:
            return user

# ================= MAIN APP COLUMN LAYOUT =====================
st.set_page_config(page_title="TransportNYC", layout="centered")
main_col, ai_col = st.columns([3, 1])

# ================= LOGIN & ACCOUNT MANAGEMENT =================
with st.sidebar:
    st.header("👤 Account")
    if "username" not in st.session_state:
        login_tab, signup_tab = st.tabs(["Login", "Create Account"])

        with login_tab:
            login_user = st.text_input("Username", key="login_user")
            login_pass = st.text_input("Password", type="password", key="login_pass")
            if st.button("Login"):
                user = get_user_obj(login_user)
                if user and user["password"] == hash_pw(login_pass):
                    st.session_state.username = login_user
                    st.success(f"Welcome back, {login_user}!")
                else:
                    st.error("Invalid credentials")

        with signup_tab:
            new_user = st.text_input("New Username", key="signup_user")
            new_pass = st.text_input("New Password", type="password", key="signup_pass")
            if st.button("Create Account"):
                if get_user_obj(new_user):
                    st.error("Username already exists")
                else:
                    users.append({"username": new_user, "password": hash_pw(new_pass)})
                    save_json(USERS_FILE, users)
                    st.success("Account created. Please log in.")
    else:
        st.write(f"👋 Logged in as `{st.session_state.username}`")
        if st.button("Logout"):
            del st.session_state["username"]

# ================= CHAT (OPTIONAL) ====================
if "username" in st.session_state:
    with st.sidebar:
        st.header("💬 Chat")
        st.write("Type a public message or tag a user with `@username` for a private message.")
        message = st.text_input("Message")

        if st.button("Send") and message.strip():
            private_to = None
            if message.strip().startswith("@"):
                parts = message.strip().split(" ", 1)
                if len(parts) > 1:
                    mentioned = parts[0][1:]
                    if any(u["username"] == mentioned for u in users):
                        private_to = mentioned

            chat_entry = {
                "timestamp": datetime.now().isoformat(),
                "sender": st.session_state.username,
                "recipient": private_to,
                "message": message.strip()
            }
            chat_log.append(chat_entry)
            save_json(CHAT_FILE, chat_log)

        st.write("### 📜 Recent Messages:")
        for c in reversed(chat_log[-20:]):
            if not c.get("message") or not c.get("sender"):
                continue  # skip malformed entries
        
            is_global = c.get("recipient") is None
            is_private_to_me = c.get("recipient") == st.session_state.username
            is_sent_by_me = c.get("sender") == st.session_state.username
        
            if is_global or is_private_to_me or is_sent_by_me:
                ts = c.get("timestamp", "")
                try:
                    ts_fmt = datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M") if ts else "Unknown time"
                except:
                    ts_fmt = "Invalid time"
                prefix = "🔒 " if c.get("recipient") else ""
                st.write(f"`{ts_fmt}` {prefix}**{c['sender']}**: {c['message']}")





# ================= MAIN APP COLUMN LAYOUT =====================
st.set_page_config(page_title="TransportNYC", layout="centered")
main_col, ai_col = st.columns([3, 1])

with main_col:
    st.title("🚦 Router")
    st.subheader("Optimize your routes for cost, gas, and time")

    GAS_PRICE = 3.140

    def estimate_gas_cost(miles, mpg):
        return round((miles / mpg) * GAS_PRICE, 2)

    def get_place_suggestions(query):
        try:
            res = requests.get("https://geocode.maps.co/search", params={
                "q": query,
                "limit": 5
            }, headers={"User-Agent": "TransportNYC-App"})
            res.raise_for_status()
            raw = res.json()
            if not raw:
                return []
            return [{"label": i["display_name"], "value": (float(i["lat"]), float(i["lon"]))} for i in raw]
        except Exception as e:
            st.error(f"Geocoding failed: {e}")
            return []



    def extract_highways_from_steps(steps):
        highways = []
        for step in steps:
            instr = step.get("instruction", "")
            if any(k in instr for k in ["I-", "US-", "Route", "Hwy", "Highway", "Turnpike", "Freeway", "Parkway"]):
                highways.append(instr)
        return list(set(highways))[:6]

    def show_map_with_route(start_coords, end_coords, polyline_str, steps, label, color="blue"):
        m = folium.Map()
        m.fit_bounds([start_coords, end_coords])
    
        folium.Marker(start_coords, tooltip="Start", icon=folium.Icon(color="green")).add_to(m)
        folium.Marker(end_coords, tooltip="End", icon=folium.Icon(color="red")).add_to(m)
    
        points = pl.decode(polyline_str)
        folium.PolyLine(points, color=color, weight=5, opacity=0.7).add_to(m)
    
        highways = extract_highways_from_steps(steps)
        if highways:
            folium.Marker(
                location=start_coords,
                icon=folium.DivIcon(html=f'<div style="font-size: 10pt">{label} uses:<br>' + "<br>".join(highways) + '</div>')
            ).add_to(m)
    
        return m


    for key in ["origin_coords", "dest_coords", "run_triggered", "tolled_route", "nontolled_route", "results"]:
        if key not in st.session_state:
            st.session_state[key] = None if key != "run_triggered" else False

    with st.form(key="route_form"):
        transport_modes = st.multiselect("Choose transport modes", [
            "Drive (with tolls)", "Drive (no tolls)"
        ], default=["Drive (no tolls)"])

        mpg_input = st.text_input("Optional: Enter your vehicle's mpg:", value="")
        try:
            mpg_val = float(mpg_input)
            if mpg_val <= 0:
                raise ValueError
        except:
            mpg_val = 22

        origin_query = st.text_input("Starting Point", key="origin_input")
        destination_query = st.text_input("Destination", key="dest_input")

        num_intervals = st.number_input("How many breaks do you want to take during the trip?", min_value=0, max_value=10, step=1)

        origin_coords, dest_coords = None, None
        origin_opts, dest_opts = [], []
        
        if origin_query and len(origin_query) >= 3:
            origin_opts = get_place_suggestions(origin_query)
            if origin_opts:
                selected_origin = st.selectbox("Select Start", origin_opts, format_func=lambda x: x["label"], key="origin_select")
                origin_coords = selected_origin["value"]
            else:
                st.warning("No results found for origin.")
        
        if destination_query and len(destination_query) >= 3:
            dest_opts = get_place_suggestions(destination_query)
            if dest_opts:
                selected_dest = st.selectbox("Select Destination", dest_opts, format_func=lambda x: x["label"], key="dest_select")
                dest_coords = selected_dest["value"]
            else:
                st.warning("No results found for destination.")


        submit = st.form_submit_button("Find Routes")

    if submit and origin_coords and dest_coords:
        st.session_state.origin_coords = origin_coords
        st.session_state.dest_coords = dest_coords
        st.session_state.run_triggered = True

        results = []
        with st.spinner("Fetching route data..."):
            tolled_route = None
            nontolled_route = None

            if "Drive (with tolls)" in transport_modes:
                tolled_route = get_driving_route(origin_coords, dest_coords, avoid_tolls=False)
                if tolled_route:
                    gas_cost = estimate_gas_cost(tolled_route["distance_miles"], mpg_val)
                    results.append(("Drive (with tolls)", tolled_route["duration_mins"], tolled_route["distance_miles"], gas_cost, tolled_route["traffic_color"]))

            if "Drive (no tolls)" in transport_modes:
                nontolled_route = get_driving_route(origin_coords, dest_coords, avoid_tolls=True)
                if nontolled_route:
                    gas_cost = estimate_gas_cost(nontolled_route["distance_miles"], mpg_val)
                    results.append(("Drive (no tolls)", nontolled_route["duration_mins"], nontolled_route["distance_miles"], gas_cost, nontolled_route["traffic_color"]))

        st.session_state.tolled_route = tolled_route
        st.session_state.nontolled_route = nontolled_route
        st.session_state.results = results
        st.session_state.num_intervals = num_intervals

    if st.session_state.run_triggered and st.session_state.results:
        for mode, time, distance, cost, color in st.session_state.results:
            st.markdown(f"### 🚀 {mode}")
            st.write(f"**Time:** {time:.1f} minutes")
            st.write(f"**Distance:** {distance:.2f} miles")
            st.write(f"**Approx. Gas Cost:** ${cost:.2f}")
            st.write(f"**Traffic Condition:** `{color.upper()}`")

        st.markdown("### 🗺 Route Maps")
        cols = st.columns(2 if (st.session_state.tolled_route and st.session_state.nontolled_route) else 1)
        if st.session_state.tolled_route:
            with cols[0]:
                st.markdown("#### Drive (with tolls)")
                m1 = show_map_with_route(
                    st.session_state.origin_coords, st.session_state.dest_coords,
                    st.session_state.tolled_route["polyline"], st.session_state.tolled_route["steps"],
                    "With Tolls", color=st.session_state.tolled_route["traffic_color"]
                )
                st_folium(m1, width=700, height=400)

        if st.session_state.nontolled_route:
            with cols[1 if st.session_state.tolled_route else 0]:
                st.markdown("#### Drive (no tolls)")
                m2 = show_map_with_route(
                    st.session_state.origin_coords, st.session_state.dest_coords,
                    st.session_state.nontolled_route["polyline"], st.session_state.nontolled_route["steps"],
                    "No Tolls", color=st.session_state.nontolled_route["traffic_color"]
                )
                st_folium(m2, width=700, height=400)

        # INTERVAL STOPS
        if st.session_state.num_intervals > 0:
            route_used = st.session_state.nontolled_route or st.session_state.tolled_route
            polyline_str = route_used["polyline"]
            interval_coords = get_interval_coords(polyline_str, st.session_state.num_intervals)

            st.markdown("### 🛑 Suggested Stops Along the Route")
            for i, (lat, lon) in enumerate(interval_coords):
                gas = search_nearby_pois(lat, lon, "gas")
                food = search_nearby_pois(lat, lon, "food")
                hotel = search_nearby_pois(lat, lon, "hotel")

                st.markdown(f"#### Stop {i+1} near ({round(lat, 3)}, {round(lon, 3)})")
                if gas: st.markdown(f"- ⛽ Gas: **{gas[0]['display_name']}**")
                if food: st.markdown(f"- 🍴 Food: **{food[0]['display_name']}**")
                if hotel: st.markdown(f"- 🛏 Hotel: **{hotel[0]['display_name']}**")
                st.markdown("---")

# ================= RIGHT TOOLBAR: HustlerAI =========================
with ai_col:
    st.markdown("## 🤖 RouterAI\nAsk any route/travel questions to our AI Companion!")
    import openai
    openai.api_key = st.secrets["OPENAI_API_KEY"]

    def ask_hustlerai(question, context=None):
        system = "You are HustlerAI, a friendly and knowledgeable NYC transportation assistant. Answer user questions clearly and accurately. You know about driving, gas prices, travel time, and trip planning."
        if context:
            system += f" The current route or plan context is: {context}"
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": question}
                ],
                max_tokens=500,
                temperature=0.25
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"Error from RouterAI: {e}"

    if st.session_state.get("username"):
        context = f"Origin: {st.session_state.origin_coords}, Destination: {st.session_state.dest_coords}" if st.session_state.get("origin_coords") and st.session_state.get("dest_coords") else ""
        ai_question = st.text_area("Ask RouterAI about your trip, routes, or planning!", key="hustlerai_input_area")
        if st.button("Ask RouterAI", key="hustlerai_btn"):
            if ai_question.strip():
                with st.spinner("RouterAI is thinking..."):
                    ai_reply = ask_hustlerai(ai_question, context)
                    st.success(f"**HustlerAI:** {ai_reply}")
    else:
        st.info("Login to use RouterAI.")
