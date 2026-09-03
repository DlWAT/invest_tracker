"""Configuration for the French Airbnb Investment Scanner.

Mirrors ``ph_scanner.config`` so the same web app can drive both countries.
A French "province" is a department; the target zones are the ten departments
of Hauts-de-France and Pays de la Loire.
"""

# Currency thresholds. 500 k EUR budget.
MAX_PRICE_EUR = 500_000
MIN_PRICE_EUR = 0

# Residential property types exposed by the Bien'ici search API.
PROPERTY_TYPES = ["flat", "house"]

# Target departments, mapped to their Bien'ici internal zone id (resolved via
# zones.json?name=...&postalCode=...). ``slug`` is the stable key stored in the
# ``province`` column; ``name`` matches the GeoJSON ``adm2_en`` property.
DEPARTMENTS = [
    {"slug": "nord",             "name": "Nord",             "postal": "59", "zone_id": "-7400"},
    {"slug": "pas-de-calais",    "name": "Pas-de-Calais",    "postal": "62", "zone_id": "-7394"},
    {"slug": "somme",            "name": "Somme",            "postal": "80", "zone_id": "-7463"},
    {"slug": "aisne",            "name": "Aisne",            "postal": "02", "zone_id": "-7411"},
    {"slug": "oise",             "name": "Oise",             "postal": "60", "zone_id": "-7427"},
    {"slug": "loire-atlantique", "name": "Loire-Atlantique", "postal": "44", "zone_id": "-7432"},
    {"slug": "maine-et-loire",   "name": "Maine-et-Loire",   "postal": "49", "zone_id": "-7409"},
    {"slug": "mayenne",          "name": "Mayenne",          "postal": "53", "zone_id": "-7438"},
    {"slug": "sarthe",           "name": "Sarthe",           "postal": "72", "zone_id": "-7443"},
    {"slug": "vendee",           "name": "Vendee",           "postal": "85", "zone_id": "-7402"},
]

REGIONS = [
    {"name": "Hauts-de-France", "provinces": ["nord", "pas-de-calais", "somme", "aisne", "oise"]},
    {"name": "Pays de la Loire", "provinces": ["loire-atlantique", "maine-et-loire", "mayenne", "sarthe", "vendee"]},
]

# Flat list of all departments, derived from REGIONS (kept as "provinces" for
# compatibility with the shared web app).
PROVINCES = [p for region in REGIONS for p in region["provinces"]]

# No favorite-zone shortcuts for France yet (the bar is hidden when empty).
FAVORITE_ZONES = []

DEPARTMENTS_BY_SLUG = {d["slug"]: d for d in DEPARTMENTS}


def assign_zone(province: str | None, title: str, location_text: str) -> str | None:
    """For France, the target zone is the department itself."""
    if province in DEPARTMENTS_BY_SLUG:
        return province
    return None


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

BASE_URL = "https://www.bienici.com"

# Respectful defaults.
REQUEST_TIMEOUT = 30
DELAY_BETWEEN_REQUESTS = 1.0
MAX_PAGES_PER_SEARCH = 40
