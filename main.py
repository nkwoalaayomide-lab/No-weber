
import requests
import csv
import argparse
import time

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

HEADERS = {
    "User-Agent": "WeblessHunter/1.0 (business discovery project)"
}

CATEGORIES = {
    "restaurants": {
        "amenity": ["restaurant", "cafe", "fast_food"]
    },
    "salons": {
        "shop": ["hairdresser", "beauty"]
    },
    "hotels": {
        "tourism": ["hotel", "guest_house", "hostel"]
    },
    "pharmacies": {
        "amenity": ["pharmacy"]
    },
    "shops": {
        "shop": ["supermarket", "convenience", "clothes", "electronics"]
    }
}


def get_location(location):
    response = requests.get(
        NOMINATIM_URL,
        params={
            "q": location,
            "format": "json",
            "limit": 1
        },
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()

    results = response.json()

    if not results:
        raise ValueError("Location not found.")

    return results[0]["boundingbox"]


def search_businesses(location, category):
    if category not in CATEGORIES:
        raise ValueError(
            f"Unknown category. Available: {', '.join(CATEGORIES)}"
        )

    south, north, west, east = get_location(location)

    selectors = []

    for key, values in CATEGORIES[category].items():
        for value in values:
            area = f"({south},{west},{north},{east})"

            for element_type in ["node", "way", "relation"]:
                selectors.append(
                    f'{element_type}["{key}"="{value}"]["name"]{area};'
                )

    query = f"""
    [out:json][timeout:90];
    (
        {"".join(selectors)}
    );
    out center tags;
    """

    response = requests.post(
        OVERPASS_URL,
        data={"data": query},
        headers=HEADERS,
        timeout=120
    )
    response.raise_for_status()

    return response.json().get("elements", [])


def export_csv(businesses, location, category):
    filename = f"{category}_leads.csv"
    seen = set()
    rows = []

    for business in businesses:
        tags = business.get("tags", {})
        name = tags.get("name", "").strip()

        if not name:
            continue

        osm_id = f'{business["type"]}/{business["id"]}'

        if osm_id in seen:
            continue

        seen.add(osm_id)

        coordinates = business.get("center", business)

        website = (
            tags.get("website")
            or tags.get("contact:website")
            or ""
        )

        rows.append({
            "business_name": name,
            "category": category,
            "location": location,
            "phone": tags.get("phone") or tags.get("contact:phone", ""),
            "email": tags.get("email") or tags.get("contact:email", ""),
            "website": website,
            "website_status": (
                "website_listed"
                if website
                else "no_website_listed_needs_verification"
            ),
            "latitude": coordinates.get("lat", ""),
            "longitude": coordinates.get("lon", ""),
            "osm_id": osm_id,
            "source": "OpenStreetMap"
        })

    if not rows:
        print("No businesses found.")
        return

    with open(filename, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nFound: {len(rows)} businesses")
    print(f"CSV created: {filename}")


def main():
    parser = argparse.ArgumentParser(
        description="Webless Hunter Business Discovery"
    )

    parser.add_argument("--location", required=True)
    parser.add_argument(
        "--category",
        required=True,
        choices=CATEGORIES.keys()
    )

    args = parser.parse_args()

    print("WEBLESS HUNTER")
    print("----------------------")
    print(f"Location: {args.location}")
    print(f"Category: {args.category}")
    print("Searching OpenStreetMap APIs...")

    businesses = search_businesses(
        args.location,
        args.category
    )

    export_csv(
        businesses,
        args.location,
        args.category
    )


if __name__ == "__main__":
    main()
