import requests
from datetime import datetime, timedelta
import streamlit as st

AMADEUS_API_KEY = st.secrets["AMADEUS_KEY"]
AMADEUS_API_SECRET = st.secrets["AMADEUS_SECRET"]

def get_amadeus_token():
    res = requests.post("https://test.api.amadeus.com/v1/security/oauth2/token", data={
        "grant_type": "client_credentials",
        "client_id": AMADEUS_API_KEY,
        "client_secret": AMADEUS_API_SECRET
    })
    if res.status_code == 200:
        return res.json()["access_token"]
    return None

def get_nearest_airport_by_coords(lat, lon, token):
    res = requests.get("https://test.api.amadeus.com/v1/reference-data/locations", params={
        "latitude": lat,
        "longitude": lon,
        "radius": 50,  # kilometers radius
        "subType": "AIRPORT",
        "page[limit]": 3
    }, headers={"Authorization": f"Bearer {token}"})

    if res.status_code == 200 and res.json().get("data"):
        return res.json()["data"][0]["iataCode"]
    return None

def get_flights(from_coords, to_coords):
    token = get_amadeus_token()
    if not token:
        return None, "Auth failed"

    from_iata = get_nearest_airport_by_coords(from_coords[0], from_coords[1], token)
    to_iata = get_nearest_airport_by_coords(to_coords[0], to_coords[1], token)

    if not from_iata or not to_iata:
        return None, "Could not find airports"

    departure_date = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")

    res = requests.get("https://test.api.amadeus.com/v2/shopping/flight-offers", params={
        "originLocationCode": from_iata,
        "destinationLocationCode": to_iata,
        "departureDate": departure_date,
        "adults": 1,
        "max": 3,
        "currencyCode": "USD"
    }, headers={"Authorization": f"Bearer {token}"})

    if res.status_code != 200 or "data" not in res.json():
        return None, f"No flights found from {from_iata} to {to_iata}"

    flights = []
    for flight in res.json()["data"]:
        price = flight["price"]["total"]
        duration = flight["itineraries"][0]["duration"].replace("PT", "").lower()
        airline = flight["validatingAirlineCodes"][0]
        flights.append({
            "from": from_iata,
            "to": to_iata,
            "airline": airline,
            "price": price,
            "duration": duration
        })

    return flights, None
