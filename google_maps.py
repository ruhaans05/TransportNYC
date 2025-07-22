import googlemaps
import streamlit as st

gmaps = googlemaps.Client(key=st.secrets["GCP_API_KEY"])

def get_driving_route(origin_str, destination_str, avoid_tolls=False, use_live_traffic=True):
    directions = gmaps.directions(
        origin_str,
        destination_str,
        mode="driving",
        avoid="tolls" if avoid_tolls else None,
        departure_time="now" if use_live_traffic else None,
        traffic_model="best_guess"
    )
    if not directions:
        return None

    leg = directions[0]["legs"][0]
    duration = leg["duration"]["value"]
    duration_in_traffic = leg.get("duration_in_traffic", {}).get("value", duration)
    delay_ratio = (duration_in_traffic - duration) / duration if duration > 0 else 0

    if delay_ratio > 0.3:
        traffic_color = "red"
    elif delay_ratio > 0.1:
        traffic_color = "orange"
    else:
        traffic_color = "green"

    return {
        "duration_mins": duration_in_traffic / 60,
        "distance_miles": leg["distance"]["value"] / 1609.34,
        "steps": leg["steps"],
        "polyline": directions[0]["overview_polyline"]["points"],
        "traffic_color": traffic_color
    }

def get_transit_route(origin_str, destination_str):
    directions = gmaps.directions(
        origin_str,
        destination_str,
        mode="transit",
        departure_time="now"
    )
    if not directions:
        return None
    leg = directions[0]["legs"][0]

    fare_info = leg.get("fare", {})
    fare_value = fare_info.get("value") if fare_info else None
    fare_currency = fare_info.get("currency") if fare_info else "USD"

    return {
        "duration_mins": leg["duration"]["value"] / 60,
        "fare": fare_value,
        "currency": fare_currency,
        "steps": leg["steps"]
    }
