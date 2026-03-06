# San Francisco bounding box
SF_BOUNDS = {
    "lat_min": 37.7080,   # SF south city line (Geneva Ave / Daly City border)
    "lat_max": 37.8330,   # just north of GG Bridge road
    "lng_min": -122.5204, # shifted +0.0066° east (225px at 4960px canvas width)
    "lng_max": -122.3754, # shifted +0.0066° east
}

# Print canvas: 16x18" @ 300 DPI (standard print size)
CANVAS_WIDTH_PX  = 4800   # 16" at 300 DPI
CANVAS_HEIGHT_PX = 5400   # 18" at 300 DPI
PRINT_DPI = 300

# Density color ramp: (normalized_value, [R, G, B])
# Edit stops here to change the palette — no code changes needed
ROUTE_COLOR_RAMP = [
    (0.0,  [100, 100, 255]),   # rarely-run → brighter indigo (more luminous, same hue)
    (0.45, [200,   0, 255]),   # moderate   → electric violet
    (0.8,  [255,   0, 180]),   # heavy      → neon hot pink
    (1.0,  [255, 220, 255]),   # peak       → blown-out pink-white (kept at 220 so g > 200 test passes)
]

# ── Line drawing ─────────────────────────────────────────────────────────────

# Base stroke width in pixels at full 4800×5400 canvas.
# Thicker = bolder single-run routes; hot-bloom + density-expand will still make
# heavily-run corridors *appear* thicker even with a lower base value.
#   16 = original (chunky)   12 = 25% thinner (current)
ROUTE_LINE_THICKNESS = 2

# Extra stroke width (px) added to the base for routes in the top 50% by
# density score (mean canvas value along their path after pass-1 rasterize).
# Only the highest applicable bonus fires — 50-bonus does NOT stack with 10-bonus.
ROUTE_LINE_THICKNESS_50_BONUS = 4

# Extra stroke width (px) for routes in the top 10% by density score.
# Much thicker than 50-bonus to make the hottest corridors visually dominant.
ROUTE_LINE_THICKNESS_10_BONUS = 10

# Gamma: controls how bright dim / rarely-run routes appear.
# Applied as:  norm = norm ** GAMMA  (before colour mapping)
# Values below 1.0 lift low-density pixels (makes single-run lines more visible).
# Values above 1.0 suppress them (good if you want only hot routes to pop).
#   1.0 = linear (no lift)   0.7 = old default   0.5 = current (single-run lines clearly visible)
GAMMA = 0.4

# ── Density expand ───────────────────────────────────────────────────────────
# Thickens corridors proportional to how many times they were run.
# Has almost no effect on once-run routes (0.3^2 = 0.09) but strongly
# amplifies heavy corridors (0.9^2 = 0.81).

# Gaussian sigma for the tight spread (pixels at full canvas).
# Smaller = thickens lines without creating halos.   Good range: 2–5.
DENSITY_EXPAND_SIGMA = 3.0

# Screen-blend intensity of the expanded layer.
# Higher = denser routes appear thicker / brighter.   Good range: 1.0–2.0.
DENSITY_EXPAND_STRENGTH = 1.4

# Exponent applied to norm before expanding.
# Higher = effect concentrates on the most-run corridors only.   Good range: 1.5–3.0.
DENSITY_EXPAND_POWER = 2.0

# ── Hot bloom ────────────────────────────────────────────────────────────────
# Adds an intense wide glow ONLY on white-hot (peak-density) pixels.
# Regular bloom is disabled in export.py; this is the only glow that fires.

# Normalised density above which hot bloom activates (0–1 scale after gamma).
# With low GAMMA values (e.g. 0.4) the gamma lift pushes medium-density pixels
# above 0.5, so raise this threshold to keep hot bloom focused on true peaks only.
#   0.5 = broad (fires on many routes when GAMMA < 0.7)
#   0.75 = focused — with GAMMA=0.4, fires only where raw norm > ~0.49 (top half of density)
HOT_BLOOM_THRESHOLD = 0.75

# Width of the hot-bloom gaussian (multiplied by bloom_sigma_wide in renderer).
# Increase when line thickness is low — thinner source lines need wider spread
# to produce the same visible halo.   Good range: 3–6.
HOT_BLOOM_SIGMA_MULT = 5.0

# Screen-blend strength of the hot-bloom layer.
# Higher = brighter / more blown-out white cores.   Good range: 1.0–5.0.
HOT_BLOOM_STRENGTH = 4.0

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

# Map tile zoom level — controls street detail and download cost.
# Each step up doubles resolution in each dimension (4× tile count).
#   11 = fast preview, city-level blobs
#   13 = neighbourhood streets visible
#   15 = current default — clear streets, ~150 tiles for SF, cached after first run
#   16 = sharper detail (~600 tiles, 2–3 min first download)
#   17 = near-max print quality (~2,400 tiles — may hit CARTO rate limits)
# Set high (16–17) only when producing the final print file.
MAP_TILE_ZOOM = 15

MAP_TILE_OPACITY = 0.85   # lightened for more visible street grid
MAP_TILE_CACHE = "data/map_tile.png"
MAP_FONT_PATH = "data/fonts/Montserrat-SemiBold.ttf"
MAP_FONT_URL  = "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/montserrat/static/Montserrat-SemiBold.ttf"
