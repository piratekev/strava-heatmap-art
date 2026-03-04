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
    (0.0, [255, 200,  80]),   # low density  → warm gold
    (0.5, [255, 240, 180]),   # mid density  → white-gold
    (1.0, [200, 230, 255]),   # high density → blue-white
]

# Background color
BG_COLOR = [10, 15, 30]

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

# Mapbox
MAP_TILE_ZOOM = 13
MAP_TILE_OPACITY = 0.15
MAP_TILE_CACHE = "data/map_tile.png"
MAP_FONT_PATH = "data/fonts/Montserrat-Light.ttf"
MAP_FONT_URL = "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-Light.ttf"
