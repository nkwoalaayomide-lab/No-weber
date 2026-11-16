
from flask import Flask, request, render_template_string, send_file
import requests
import csv
import io
import uuid

app = Flask(__name__)

HEADERS = {
    "User-Agent": "WeblessHunter/1.0 (business discovery application)"
}

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"

CATEGORIES = {
    "Restaurants": [
        ("amenity", "restaurant"),
        ("amenity", "cafe"),
        ("amenity", "fast_food")
    ],
    "Salons": [
        ("shop", "hairdresser"),
        ("shop", "beauty")
    ],
    "Hotels": [
        ("tourism", "hotel"),
        ("tourism", "guest_house"),
        ("tourism", "hostel")
    ],
    "Pharmacies": [
        ("amenity", "pharmacy")
    ],
    "Shops": [
        ("shop", "supermarket"),
        ("shop", "convenience"),
        ("shop", "clothes"),
        ("shop", "electronics")
    ]
}

# Temporary download storage for this running application.
downloads = {}

PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Webless Hunter</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #101827;
            color: white;
            margin: 0;
            padding: 30px 16px;
        }
        .container {
            max-width: 950px;
            margin: auto;
        }
        h1 { color: #65d6a3; }
        .panel {
            background: #1c293b;
            padding: 22px;
            border-radius: 12px;
            margin-bottom: 20px;
        }
        input, select, button {
            box-sizing: border-box;
            width: 100%;
            padding: 13px;
            margin: 8px 0;
            border-radius: 7px;
            border: 0;
            font-size: 15px;
        }
        button {
            background: #20b981;
            color: #071b13;
            font-weight: bold;
            cursor: pointer;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }
        th, td {
            padding: 11px;
            border-bottom: 1px solid #354258;
            text-align: left;
        }
        .table-wrap { overflow-x: auto; }
        .muted { color: #aab8ca; }
        a { color: #65d6a3; }
        .error { color: #ff8c8c; }
    </style>
</head>
<body>
<div class="container">
    <h1>WEBLESS HUNTER</h1>
    <p class="muted">Discover businesses and identify potential website clients.</p>

    <div class="panel">
        <h2>Find businesses</h2>
        <form method="POST">
            <label>Location</label>
            <input name="location" placeholder="Lagos, Nigeria"
                   value="{{ location }}" required>

            <label>Business category</label>
            <select name="category">
                {% for item in categories %}
                <option value="{{ item }}"
                    {% if item == category %}selected{% endif %}>
                    {{ item }}
                </option>
                {% endfor %}
            </select>

            <button type="submit">Search businesses</button>
        </form>
    </div>

    {% if error %}
        <div class="panel error">{{ error }}</div>
    {% endif %}

    {% if results is not none %}
    <div class="panel">
        <h2>Search results</h2>
        <p>{{ results|length }} businesses discovered</p>

        {% if download_url %}
        <a href="{{ download_url }}">Download CSV results</a>
        {% endif %}

        <div class="table-wrap">
        <table>
            <tr>
                <th>Business</th>
                <th>Phone</th>
                <th>Website</th>
                <th>Status</th>
            </tr>
            {% for item in results %}
            <tr>
                <td>{{ item.business_name }}</td>
                <td>{{ item.phone or "Not listed" }}</td>
                <td>{{ item.website or "Not listed" }}</td>
                <td>{{ item.website_status }}</td>
            </tr>
            {% endfor %}
        </table>
        </div>
    </div>
    {% endif %}
</div>
</body>
</html>
"""


def get_businesses(location, category):
    geo = requests.get(
        NOMINATIM,
        params={
            "q": location,
            "format": "json",
            "limit": 1
        },
        headers=HEADERS,
        timeout=30
    )
    geo.raise_for_status()

    locations = geo.json()

    if not locations:
        raise ValueError("Location could not be found.")

    south, north, west, east = locations[0]["boundingbox"]

    selectors = []

    for key, value in CATEGORIES[category]:
        area = f"({south},{west},{north},{east})"

        for element_type in ("node", "way", "relation"):
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
        OVERPASS,
        data={"data": query},
        headers=HEADERS,
        timeout=120
    )
    response.raise_for_status()

    elements = response.json().get("elements", [])

    results = []
    seen = set()

    for element in elements:
        tags = element.get("tags", {})
        name = tags.get("name", "").strip()

        if not name:
            continue

        osm_id = f'{element["type"]}/{element["id"]}'

        if osm_id in seen:
            continue

        seen.add(osm_id)

        coordinates = element.get("center", element)

        website = (
            tags.get("website")
            or tags.get("contact:website")
            or ""
        )

        address = ", ".join(filter(None, [
            tags.get("addr:housenumber"),
            tags.get("addr:street"),
            tags.get("addr:suburb"),
            tags.get("addr:city")
        ]))

        results.append({
            "business_name": name,
            "category": category,
            "location": location,
            "address": address,
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

    return results


@app.route("/", methods=["GET", "POST"])
def home():
    results = None
    error = None
    download_url = None
    location = ""
    category = "Restaurants"

    if request.method == "POST":
        location = request.form.get("location", "").strip()
        category = request.form.get("category", "Restaurants")

        try:
            if not location:
                raise ValueError("Enter a location.")

            results = get_businesses(location, category)

            if results:
                token = str(uuid.uuid4())
                downloads[token] = results
                download_url = f"/download/{token}"

        except requests.RequestException:
            error = "The search service is temporarily unavailable. Try again later."
        except ValueError as exc:
            error = str(exc)
        except Exception:
            error = "Something went wrong while searching."

    return render_template_string(
        PAGE,
        categories=CATEGORIES.keys(),
        results=results,
        error=error,
        location=location,
        category=category,
        download_url=download_url
    )


@app.route("/download/<token>")
def download(token):
    rows = downloads.get(token)

    if not rows:
        return "Download expired. Run the search again.", 404

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

    file_data = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    file_data.seek(0)

    return send_file(
        file_data,
        mimetype="text/csv",
        as_attachment=True,
        download_name="webless_hunter_leads.csv"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
