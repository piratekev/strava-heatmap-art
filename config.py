# San Francisco bounding box
SF_BOUNDS = {
    "lat_min": 37.6999,
    "lat_max": 37.8324,
    "lng_min": -122.5270,
    "lng_max": -122.3480,
}

# Print canvas: 18x18" @ 300 DPI (square)
CANVAS_WIDTH_PX = 5400
CANVAS_HEIGHT_PX = 5400
PRINT_DPI = 300

# Density color ramp: (normalized_value, [R, G, B])
# Edit stops here to change the palette — no code changes needed
ROUTE_COLOR_RAMP = [
    (0.0,  [ 20,  50, 255]),   # rarely-run    → deep blue
    (0.5,  [220,   0, 220]),   # moderate      → saturated magenta
    (0.85, [255,  60, 255]),   # heavy          → electric pink
    (1.0,  [255, 220, 255]),   # peak density   → blown-out white-pink
]

# Background color
BG_COLOR = [0, 0, 0]  # pure black

# Strava API
STRAVA_BASE_URL = "https://www.strava.com/api/v3"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_ACTIVITIES_PER_PAGE = 200

# Cache paths
CACHE_DIR = "data"
ACTIVITIES_CACHE_FILE = "data/activities.json"
CACHE_META_FILE = "data/cache_meta.json"

# Output
OUTPUT_DIR = "output"

# Map tiles
MAP_TILE_URL = "https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png"
MAP_TILE_OPACITY = 0.55   # was 0.35 — dark CARTO tile needs more weight on black bg
MAP_TILE_CACHE = "data/map_tile.png"
MAP_FONT_PATH = "data/fonts/Montserrat-Light.ttf"
MAP_FONT_URL = "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/montserrat/static/Montserrat-Light.ttf"
