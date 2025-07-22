import openrouteservice
from openrouteservice import convert
import polyline
import requests
import streamlit as st

ORS_API_KEY = os.getenv("ORS_API_KEY")
client = openrouteservice.Client(key=ORS_API_KEY)

def get_driving_route(origin_coords, dest_coords, avoid_tolls=False):
    options = {}
    if avoid_tolls:
        options["avoid_features"] = ["tollways"]

    route = client.directions(
        coordinates=[origin_coords[::-1], dest_coords[::-1]],
        profile='driving-car',
        format='json',
        instructions=True,
        options=options
    )

    route_info = route['routes'][0]
    steps = route_info['segments'][0]['steps']
    duration_sec = route_info['summary']['duration']
    distance_m = route_info['summary']['distance']
    polyline_str = route_info['geometry']

    return {
        "duration_mins": duration_sec / 60,
        "distance_miles": distance_m / 1609.34,
        "steps": steps,
        "polyline": polyline_str,
        "traffic_color": "gray"
    }

def get_interval_coords(polyline_str, num_intervals):
    coords = polyline.decode(polyline_str)
    total_len = len(coords)
    interval_len = total_len // (num_intervals + 1)
    return [coords[i * interval_len] for i in range(1, num_intervals + 1)]

def search_nearby_pois(lat, lon, kind, radius=5000):
    keyword_map = {
        "gas": "gas station",
        "food": "restaurant",
        "hotel": "hotel"
    }
    query = keyword_map.get(kind.lower(), kind)
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "json",
        "limit": 3,
        "lat": lat,
        "lon": lon,
        "radius": radius
    }
    headers = {"User-Agent": "TransportNYC-App"}
    res = requests.get(url, params=params, headers=headers)
    return res.json() if res.status_code == 200 else []
