"""Configuration for the Philippine Airbnb Investment Scanner.

Zones map a target area (e.g. Boracay) to the DotProperty province slug
plus keyword filters used to narrow results to the micro-location.
"""

# Currency thresholds. 100k EUR ~= 6.3M PHP (approximate).
MAX_PRICE_PHP = 6_000_000
MIN_PRICE_PHP = 0

# Property types exposed by DotProperty as URL segments.
# Order matters for readability only.
PROPERTY_TYPES = ["condos", "houses", "villas", "hotels", "land"]

ZONES = [
    {
        "id": "boracay",
        "province_slug": "aklan",
        "keywords": ["boracay", "malay", "station 1", "station 2",
                     "station 3", "yapak", "manoc-manoc", "balabag",
                     "newcoast"],
    },
    {
        "id": "el_nido",
        "province_slug": "palawan",
        "keywords": ["el nido", "corong", "nacpan", "las cabanas",
                     "lio", "vanilla beach", "buena suerte"],
    },
    {
        "id": "batangas",
        "province_slug": "batangas",
        "keywords": ["nasugbu", "calatagan", "laiya", "san juan",
                     "matabungkay", "fortune island", "lian", "batulao"],
    },
]

# All Philippine provinces grouped by administrative region. DotProperty slugs.
# Edge cases: DotProperty still uses "compostela-valley" (not the renamed
# "davao-de-oro") and "cotabato" (for North Cotabato).
REGIONS = [
    {"name": "Région I — Ilocos", "provinces": [
        "ilocos-norte", "ilocos-sur", "la-union", "pangasinan"]},
    {"name": "CAR — Cordillère", "provinces": [
        "abra", "apayao", "benguet", "ifugao", "kalinga", "mountain-province"]},
    {"name": "Région II — Vallée de Cagayan", "provinces": [
        "batanes", "cagayan", "isabela", "nueva-vizcaya", "quirino"]},
    {"name": "Région III — Luçon centrale", "provinces": [
        "aurora", "bataan", "bulacan", "nueva-ecija", "pampanga", "tarlac", "zambales"]},
    {"name": "Région IV-A — CALABARZON", "provinces": [
        "batangas", "cavite", "laguna", "quezon", "rizal"]},
    {"name": "MIMAROPA", "provinces": [
        "marinduque", "occidental-mindoro", "oriental-mindoro", "palawan", "romblon"]},
    {"name": "Région V — Bicol", "provinces": [
        "albay", "camarines-norte", "camarines-sur", "catanduanes", "masbate", "sorsogon"]},
    {"name": "Région VI — Visayas occidentales", "provinces": [
        "aklan", "antique", "capiz", "guimaras", "iloilo", "negros-occidental"]},
    {"name": "Région VII — Visayas centrales", "provinces": [
        "bohol", "cebu", "negros-oriental", "siquijor"]},
    {"name": "Région VIII — Visayas orientales", "provinces": [
        "biliran", "eastern-samar", "leyte", "northern-samar", "samar", "southern-leyte"]},
    {"name": "Région IX — Péninsule de Zamboanga", "provinces": [
        "zamboanga-del-norte", "zamboanga-del-sur", "zamboanga-sibugay"]},
    {"name": "Région X — Mindanao du Nord", "provinces": [
        "bukidnon", "camiguin", "lanao-del-norte", "misamis-occidental", "misamis-oriental"]},
    {"name": "Région XI — Davao", "provinces": [
        "compostela-valley", "davao-del-norte", "davao-del-sur",
        "davao-occidental", "davao-oriental"]},
    {"name": "Région XII — SOCCSKSARGEN", "provinces": [
        "cotabato", "sarangani", "south-cotabato", "sultan-kudarat"]},
    {"name": "Région XIII — Caraga", "provinces": [
        "agusan-del-norte", "agusan-del-sur", "dinagat-islands",
        "surigao-del-norte", "surigao-del-sur"]},
    {"name": "BARMM", "provinces": [
        "basilan", "lanao-del-sur", "maguindanao", "sulu", "tawi-tawi"]},
    {"name": "NCR — Metro Manila", "provinces": ["metro-manila"]},
]

# Flat list of all provinces, derived from REGIONS.
PROVINCES = [p for region in REGIONS for p in region["provinces"]]


def assign_zone(province: str | None, title: str, location_text: str) -> str | None:
    """Map a listing to one of the priority ZONES, or None."""
    full = f"{title or ''} {location_text or ''}".lower()
    for zone in ZONES:
        if zone["province_slug"] == province:
            if not zone.get("keywords") or any(k in full for k in zone["keywords"]):
                return zone["id"]
    return None

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

BASE_URL = "https://www.dotproperty.com.ph"

# Respectful defaults.
REQUEST_TIMEOUT = 30
DELAY_BETWEEN_REQUESTS = 1.0
MAX_PAGES_PER_SEARCH = 40
