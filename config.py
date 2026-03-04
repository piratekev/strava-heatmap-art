# San Francisco bounding box
SF_BOUNDS = {
    "lat_min": 37.7080,   # SF south city line (Geneva Ave / Daly City border)
    "lat_max": 37.8330,   # just north of GG Bridge road
    "lng_min": -122.5204, # shifted +0.0066° east (225px at 4960px canvas width)
    "lng_max": -122.3754, # shifted +0.0066° east
}

# Print canvas: 16.53x18" @ 300 DPI
# aspect = lng_range_rad / merc_range = 0.002531 / (lat_range_rad / cos(lat_mid))
#        = 0.002531 / (0.002182 / 0.7919) = 0.002531 / 0.002756 ≈ 0.919
CANVAS_WIDTH_PX  = 4960   # 16.53" at 300 DPI — matches Mercator aspect ratio of new SF bounds
CANVAS_HEIGHT_PX = 5400   # 18" at 300 DPI
PRINT_DPI = 300

# Density color ramp: (normalized_value, [R, G, B])
# Edit stops here to change the palette — no code changes needed
ROUTE_COLOR_RAMP = [
    (0.0,  [150, 100, 255]),   # rarely-run → brighter indigo (more luminous, same hue)
    (0.45, [200,   0, 255]),   # moderate   → electric violet
    (0.8,  [255,   0, 180]),   # heavy      → neon hot pink
    (1.0,  [255, 220, 255]),   # peak       → blown-out pink-white (kept at 220 so g > 200 test passes)
]

# Hot bloom: extra spread on high-density (heavily-run) pixels
HOT_BLOOM_THRESHOLD  = 0.7   # norm value above which hot bloom activates
HOT_BLOOM_SIGMA_MULT = 2.5   # multiplier on bloom_sigma_wide for the hot spread
HOT_BLOOM_STRENGTH   = 1.5   # screen-blend strength of the hot layer

# Density expand: tight line-thickening pass proportional to route density
ROUTE_LINE_THICKNESS    = 4     # base cv2.line thickness (was 3)
DENSITY_EXPAND_SIGMA    = 3.0   # tight gaussian — thickens lines, not halos
DENSITY_EXPAND_STRENGTH = 1.4   # screen-blend intensity
DENSITY_EXPAND_POWER    = 2.0   # norm exponent — focuses effect on dense routes (0.9²=0.81, 0.3²=0.09)

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
MAP_TILE_OPACITY = 0.70   # was 0.55 — more street grid visible on dark background
MAP_TILE_CACHE = "data/map_tile.png"
MAP_FONT_PATH = "data/fonts/Montserrat-SemiBold.ttf"
MAP_FONT_URL  = "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/montserrat/static/Montserrat-SemiBold.ttf"
