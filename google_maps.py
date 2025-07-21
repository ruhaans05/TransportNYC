import googlemaps
import os
import streamlit as st

gmaps = googlemaps.Client(key=st.secrets["GCP_API_KEY"])

def get_driving_route(origin, destination, avoid_tolls=False):
    directions = gmaps.directions(
        origin,
        destination,
        mode="driving",
        avoid="tolls" if avoid_tolls else None,
        departure_time="now"
    )
    if not directions:
        return None
    leg = directions[0]["legs"][0]
    return {
        "duration_mins": leg["duration"]["value"] / 60,
        "distance_miles": leg["distance"]["value"] / 1609.34,
        "steps": leg["steps"],
        "polyline": directions[0]["overview_polyline"]["points"]
    }

def get_transit_route(origin, destination):
    directions = gmaps.directions(
        origin,
        destination,
        mode="transit",
        departure_time="now"
    )
    if not directions:
        return None
    leg = directions[0]["legs"][0]
    return {
        "duration_mins": leg["duration"]["value"] / 60,
        "fare": leg.get("fare", {}).get("value", None),
        "currency": leg.get("fare", {}).get("currency", "USD"),
        "steps": leg["steps"]
    }
