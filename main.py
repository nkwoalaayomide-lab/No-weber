import requests
import csv

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def find_businesses(city, category):
    print(f"Searching for {category} in {city}...")

    geocode_url = "https://nominatim.openstreetmap.org/search"

    location = requests.get(
        geocode_url,
        params={
            "q": city,
            "format": "json",
            "limit": 1
        },
        headers={"User-Agent": "WeblessHunter/1.0"},
        timeout=30
    ).json()

    if not location:
        print("Location not found.")
        return

    south, north, west, east = location[0]["boundingbox"]

    query = f"""
    [out:json][timeout:60];
    (
      node["name"]["amenity"="{category}"]({south},{west},{north},{east});
      way["name"]["amenity"="{category}"]({south},{west},{north},{east});
      relation["name"]["amenity"="{category}"]({south},{west},{north},{east});
    );
    out center tags;
    """

    response = requests.post(
        OVERPASS_URL,
        data={"data": query},
        timeout=90
    )
    response.raise_for_status()

    businesses = response.json()["elements"]

    with open("businesses.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["Business Name", "Phone", "Email", "Website"])

        for business in businesses:
            tags = business.get("tags", {})
            writer.writerow([
                tags.get("name", ""),
                tags.get("phone", ""),
                tags.get("email", ""),
                tags.get("website", "")
            ])

    print(f"Found {len(businesses)} businesses.")
    print("Exported to businesses.csv")


if __name__ == "__main__":
    city = input("City: ")
    category = input("Amenity category (e.g. restaurant, pharmacy): ")
    find_businesses(city, category)
