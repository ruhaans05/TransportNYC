import streamlit as st

def get_nearest_airport(location_query, token):
    location_query = location_query.strip()

    def query_airports(query):
        res = requests.get("https://test.api.amadeus.com/v1/reference-data/locations", params={
            "keyword": query,
            "subType": "AIRPORT",
            "view": "FULL",
            "page[limit]": 5
        }, headers={"Authorization": f"Bearer {token}"})
        if res.status_code == 200:
            data = res.json().get("data", [])
            return data
        return []

    # First try with original query
    airports = query_airports(location_query)
    st.write(f"Airport search results for '{location_query}':", airports)

    # Fallback: if no results, try splitting by space and retry with first word (e.g., 'Edison NJ' -> 'Edison')
    if not airports and " " in location_query:
        first_word = location_query.split(" ")[0]
        airports = query_airports(first_word)
        st.write(f"Fallback airport search results for '{first_word}':", airports)

    if airports:
        # Optionally: pick the closest airport by some criteria
        return airports[0]["iataCode"]
    else:
        return None
