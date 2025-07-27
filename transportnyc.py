import streamlit as st
import os
import json
from datetime import datetime
import hashlib
import requests
import folium
from streamlit_folium import st_folium
import polyline as pl
import time
from PIL import Image
import base64
from io import BytesIO
from openrouteservice_api import get_driving_route, get_interval_coords, search_nearby_pois
from db import init_db, create_user, get_user, increment_count

init_db()

def get_image_base64(image_path):
    img = Image.open(image_path)
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

# Logo
logo_path = "router-logo.png"
if os.path.exists(logo_path):
    logo_base64 = get_image_base64(logo_path)
    st.markdown(
        f"""
        <div style="text-align: center; margin-bottom: -1.2rem;">
            <img src="data:image/png;base64,{logo_base64}" width="170"/>
        </div>
        """,
        unsafe_allow_html=True
    )
else:
    st.warning("Logo could not load. Continue scrolling though to use the app!")

# Chat history
CHAT_FILE = "chat.json"
def load_json(filename, default):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    return default
def save_json(filename, obj):
    with open(filename, "w") as f:
        json.dump(obj, f, indent=2)
chat_log = load_json(CHAT_FILE, [])

st.set_page_config(page_title="TransportNYC", layout="centered")
main_col, ai_col = st.columns([3, 1])

# Sidebar Login
with st.sidebar:
    st.header("👤 Account")
    if "username" not in st.session_state:
        login_tab, signup_tab = st.tabs(["Login", "Create Account"])
        with login_tab:
            login_user = st.text_input("Username", key="login_user")
            login_pass = st.text_input("Password", type="password", key="login_pass")
            if st.button("Login"):
                user = get_user(login_user)
                if user and user[1] == hashlib.sha256(login_pass.encode()).hexdigest():
                    st.session_state.username = login_user
                    st.success(f"Welcome back, {login_user}!")
                else:
                    st.error("Invalid credentials")
        with signup_tab:
            new_user = st.text_input("New Username", key="signup_user")
            new_pass = st.text_input("New Password", type="password", key="signup_pass")
            if st.button("Create Account"):
                if get_user(new_user):
                    st.error("Username already exists")
                else:
                    hashed = hashlib.sha256(new_pass.encode()).hexdigest()
                    create_user(new_user, hashed)
                    st.success("Account created. Please log in.")
    else:
        st.write(f"👋 Logged in as `{st.session_state.username}`")
        user_data = get_user(st.session_state.username)
        st.write(f"💬 Chat used: {user_data[2]} times")
        st.write(f"🤖 AI used: {user_data[3]} times")
        if st.button("Logout"):
            del st.session_state["username"]

# Chat
if "username" in st.session_state:
    with st.sidebar:
        st.header("💬 Chat")
        st.write("Type a public message or tag a user with `@username` for private message.")
        message = st.text_input("Message")
        if st.button("Send") and message.strip():
            private_to = None
            if message.strip().startswith("@"):
                parts = message.strip().split(" ", 1)
                if len(parts) > 1:
                    private_to = parts[0][1:]
            chat_entry = {
                "timestamp": datetime.now().isoformat(),
                "sender": st.session_state.username,
                "recipient": private_to,
                "message": message.strip()
            }
            chat_log.append(chat_entry)
            save_json(CHAT_FILE, chat_log)
            increment_count(st.session_state.username, "chat_count")

        st.write("### 📜 Recent Messages:")
        for c in reversed(chat_log[-20:]):
            if not c.get("message") or not c.get("sender"):
                continue
            is_global = c.get("recipient") is None
            is_private_to_me = c.get("recipient") == st.session_state.username
            is_sent_by_me = c.get("sender") == st.session_state.username
            if is_global or is_private_to_me or is_sent_by_me:
                ts_fmt = "Unknown"
                try:
                    ts_fmt = datetime.fromisoformat(c.get("timestamp", "")).strftime("%Y-%m-%d %H:%M")
                except:
                    pass
                prefix = "🔒 " if c.get("recipient") else ""
                st.write(f"`{ts_fmt}` {prefix}**{c['sender']}**: {c['message']}")

# Main Route Form
with main_col:
    st.title("🚦 Router")
    st.subheader("Optimize your routes for cost, gas, and time")

    GAS_PRICE = 3.140
    LOCATIONIQ_KEY = st.secrets["LOCATIONIQ_KEY"]
    OPENCAGE_KEY = st.secrets["OPENCAGE_KEY"]

    def estimate_gas_cost(miles, mpg):
        return round((miles / mpg) * GAS_PRICE, 2)

    def get_place_suggestions(query):
        try:
            time.sleep(0.5)
            res = requests.get("https://api.opencagedata.com/geocode/v1/json", params={
                "q": query,
                "key": OPENCAGE_KEY,
                "limit": 5,
                "no_annotations": 1
            })
            res.raise_for_status()
            results = res.json().get("results", [])
            return [{"label": i["formatted"], "value": (i["geometry"]["lat"], i["geometry"]["lng"])} for i in results]
        except Exception as e:
            st.error(f"Geocoding failed: {e}")
            return []

    def extract_highways_from_steps(steps):
        highways = set()
        for step in steps:
            instruction = step.get("instruction", "")
            tokens = instruction.split()
            for token in tokens:
                if any(prefix in token for prefix in ["I-", "US-", "Route", "Hwy", "Highway", "Turnpike", "Freeway", "Parkway"]):
                    highways.add(token.strip(",."))
        return sorted(highways)

    def generate_route_guide(route_obj, label):
        steps = route_obj.get("steps", [])
        highways = extract_highways_from_steps(steps)
        if not highways:
            return f"{label} route uses local roads and does not pass through major highways."
        highway_list = ", ".join(highways[:-1]) + f", and {highways[-1]}" if len(highways) > 1 else highways[0]
        return f"The {label} route takes you through: {highway_list}."

    def show_map_with_route(start_coords, end_coords, polyline_str, steps, label, color="blue"):
        m = folium.Map()
        m.fit_bounds([start_coords, end_coords])
        folium.Marker(start_coords, tooltip="Start", icon=folium.Icon(color="green")).add_to(m)
        folium.Marker(end_coords, tooltip="End", icon=folium.Icon(color="red")).add_to(m)
        folium.PolyLine(pl.decode(polyline_str), color=color, weight=5, opacity=0.7).add_to(m)
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
            if mpg_val <= 0: raise ValueError
        except: mpg_val = 22
        origin_query = st.text_input("Starting Point", key="origin_input")
        destination_query = st.text_input("Destination", key="dest_input")
        num_intervals = st.number_input("How many breaks do you want to take during the trip?", min_value=0, max_value=10, step=1)

        origin_coords, dest_coords = None, None
        if origin_query and len(origin_query) >= 3:
            origin_opts = get_place_suggestions(origin_query)
            if origin_opts:
                selected_origin = st.selectbox("Select Start", origin_opts, format_func=lambda x: x["label"], key="origin_select")
                origin_coords = selected_origin["value"]
        if destination_query and len(destination_query) >= 3:
            dest_opts = get_place_suggestions(destination_query)
            if dest_opts:
                selected_dest = st.selectbox("Select Destination", dest_opts, format_func=lambda x: x["label"], key="dest_select")
                dest_coords = selected_dest["value"]

        submit = st.form_submit_button("Find Routes")

    if submit and origin_coords and dest_coords:
        st.session_state.origin_coords = origin_coords
        st.session_state.dest_coords = dest_coords
        st.session_state.run_triggered = True

        results = []
        with st.spinner("Fetching route data..."):
            if "Drive (with tolls)" in transport_modes:
                route = get_driving_route(origin_coords, dest_coords, avoid_tolls=False)
                if route:
                    results.append(("Drive (with tolls)", route["duration_mins"], route["distance_miles"], estimate_gas_cost(route["distance_miles"], mpg_val), route["traffic_color"]))
                    st.session_state.tolled_route = route
            if "Drive (no tolls)" in transport_modes:
                route = get_driving_route(origin_coords, dest_coords, avoid_tolls=True)
                if route:
                    results.append(("Drive (no tolls)", route["duration_mins"], route["distance_miles"], estimate_gas_cost(route["distance_miles"], mpg_val), route["traffic_color"]))
                    st.session_state.nontolled_route = route
        st.session_state.results = results
        st.session_state.num_intervals = num_intervals

    if st.session_state.run_triggered and st.session_state.results:
        for mode, time_min, dist, cost, color in st.session_state.results:
            st.markdown(f"### 🚀 {mode}")
            st.write(f"**Time:** {round(time_min / 60, 1)} hours\n**Distance:** {dist:.2f} miles\n**Gas Cost:** ${cost:.2f}\n**Traffic:** `{color.upper()}`")
        st.markdown("### 🗺 Route Maps")
        cols = st.columns(2 if st.session_state.tolled_route and st.session_state.nontolled_route else 1)
        if st.session_state.tolled_route:
            with cols[0]:
                st.markdown("#### Drive (with tolls)")
                m1 = show_map_with_route(st.session_state.origin_coords, st.session_state.dest_coords, st.session_state.tolled_route["polyline"], st.session_state.tolled_route["steps"], "With Tolls", st.session_state.tolled_route["traffic_color"])
                st_folium(m1, width=700, height=400)
        if st.session_state.nontolled_route:
            with cols[1 if st.session_state.tolled_route else 0]:
                st.markdown("#### Drive (no tolls)")
                m2 = show_map_with_route(st.session_state.origin_coords, st.session_state.dest_coords, st.session_state.nontolled_route["polyline"], st.session_state.nontolled_route["steps"], "No Tolls", st.session_state.nontolled_route["traffic_color"])
                st_folium(m2, width=700, height=400)

        # 🧭 Route Guide
        st.markdown("### 🧭 Route Guide")
        if st.session_state.tolled_route:
            guide = generate_route_guide(st.session_state.tolled_route, "Toll")
            st.markdown(f"**Toll Route:** {guide}")
        if st.session_state.nontolled_route:
            guide = generate_route_guide(st.session_state.nontolled_route, "No-Toll")
            st.markdown(f"**No-Toll Route:** {guide}")

        # 🛑 Suggested Stops
        if st.session_state.num_intervals > 0:
            route_used = st.session_state.nontolled_route or st.session_state.tolled_route
            interval_coords = get_interval_coords(route_used["polyline"], st.session_state.num_intervals)
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

# AI Companion
with ai_col:
    st.markdown("## 🤖 RouterAI")
    import openai
    openai.api_key = st.secrets["OPENAI_API_KEY"]

    def ask_hustlerai(question, context=None):
        system = "You are RouterAI, a friendly and knowledgeable transportation assistant, especially on specific routes and the weather/traffic conditions along them and what food, gas, and lodging options there are. You also know what routes are scenic and not...."
        if context:
            system += f" Context: {context}"
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": system}, {"role": "user", "content": question}],
                max_tokens=500,
                temperature=0.25
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"Error from RouterAI: {e}"

    if st.session_state.get("username"):
        context = f"Origin: {st.session_state.origin_coords}, Destination: {st.session_state.dest_coords}" if st.session_state.get("origin_coords") and st.session_state.get("dest_coords") else ""
        ai_question = st.text_area("Ask RouterAI about your trip!", key="hustlerai_input_area")
        if st.button("Ask RouterAI", key="hustlerai_btn") and ai_question.strip():
            with st.spinner("RouterAI is thinking..."):
                ai_reply = ask_hustlerai(ai_question, context)
                st.success(f"**RouterAI:** {ai_reply}")
                increment_count(st.session_state.username, "ai_count")
    else:
        st.info("Login to use RouterAI")
