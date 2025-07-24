import openrouteservice
from openrouteservice import convert
import requests
import os
import streamlit as st
import math
import polyline as pl

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

def haversine(coord1, coord2):
    R = 6371e3  # Earth radius in meters
    lat1 = math.radians(coord1[0])
    lon1 = math.radians(coord1[1])
    lat2 = math.radians(coord2[0])
    lon2 = math.radians(coord2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_interval_coords(polyline_str, num_intervals):
    coords = pl.decode(polyline_str)
    total_dist = 0
    dists = [0]

    for i in range(1, len(coords)):
        dist = haversine(coords[i - 1], coords[i])
        total_dist += dist
        dists.append(total_dist)

    step_dist = total_dist / (num_intervals + 1)
    result = []
    next_target = step_dist
    j = 1

    for i in range(1, len(dists)):
        while j <= num_intervals and dists[i] >= next_target:
            result.append(coords[i])
            j += 1
            next_target = step_dist * j

    return result

def reverse_geocode(lat, lon):
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "format": "json",
        "lat": lat,
        "lon": lon,
        "zoom": 10,
        "addressdetails": 1
    }
    headers = {"User-Agent": "TransportNYC-App"}

    res = requests.get(url, params=params, headers=headers)
    if res.status_code == 200:
        data = res.json()
        addr = data.get("address", {})
        return addr.get("county") or addr.get("city") or addr.get("state") or "Unknown location"
    return "Unknown location"

def search_nearby_pois(lat, lon, kind, delta=0.1):
    keyword_map = {
        "gas": "gas station",
        "food": "restaurant",
        "hotel": "hotel"
    }
    query = keyword_map.get(kind.lower(), kind)

    viewbox = f"{lon - delta},{lat - delta},{lon + delta},{lat + delta}"

    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "json",
        "limit": 3,
        "viewbox": viewbox,
        "bounded": 1
    }
    headers = {"User-Agent": "TransportNYC-App"}

    res = requests.get(url, params=params, headers=headers)
    return res.json() if res.status_code == 200 else []
