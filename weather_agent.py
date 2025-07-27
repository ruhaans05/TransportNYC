import requests
from polyline import decode

def extract_route_coords(polyline_str, interval=15):
    """
    Extract every nth coordinate from polyline for weather lookup.
    """
    coords = decode(polyline_str)
    return coords[::interval]

def get_weather_for_coords(coords):
    """
    Fetch hourly temperature data from Open-Meteo for selected route points.
    """
    weather_data = []
    for lat, lon in coords:
        try:
            res = requests.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": lat,
                "longitude": lon,
                "hourly": "temperature_2m",
                "timezone": "auto"
            })
            res.raise_for_status()
            data = res.json()
            hourly_temps = data.get("hourly", {}).get("temperature_2m", [])
            hours = data.get("hourly", {}).get("time", [])
            temp = hourly_temps[0] if hourly_temps else None
            timestamp = hours[0] if hours else "Unknown"
            weather_data.append({
                "lat": lat,
                "lon": lon,
                "temp_c": temp,
                "timestamp": timestamp
            })
        except Exception as e:
            weather_data.append({
                "lat": lat,
                "lon": lon,
                "error": str(e)
            })
    return weather_data

def show_weather_along_route(coords, weather_info):
    """
    Render weather data points on a folium map.
    """
    import folium
    m = folium.Map(location=coords[0], zoom_start=6)
    for w in weather_info:
        if "error" in w:
            continue
        popup = f"Temp: {w['temp_c']}°C<br>Time: {w['timestamp']}"
        folium.Marker(
            location=(w["lat"], w["lon"]),
            icon=folium.Icon(color="blue", icon="cloud"),
            popup=popup
        ).add_to(m)
    return m
