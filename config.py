# San Francisco bounding box
CITY_BOUNDS = {
    "lat_min": 37.7057,     # was 37.7068 — extended south ~50px
    "lat_max": 37.8392,     # unchanged
    "lng_min": -122.5163,   # was -122.5152 — extended west 40px (+40 × 0.00002863°/px)
    "lng_max": -122.3812,   # unchanged
}

# Print canvas: 16x20" aspect ratio (4:5) — prints at ~295 DPI
CANVAS_WIDTH_PX  = 4720   # was 4680 — +40px west
CANVAS_HEIGHT_PX = 5900   # was 5850 — +50px south (maintains 4:5 ratio)
PRINT_DPI = 285
CANVAS_ROTATION_DEGREES = 0  # degrees clockwise. 0 = north-up (SF). 29 = Manhattan-axis-up (NYC).

# Optional: decouple intermediate canvas scale from final output dimensions.
# When set, the intermediate canvas is computed from these dimensions instead of
# CANVAS_WIDTH_PX / CANVAS_HEIGHT_PX, allowing a non-centered crop without
# changing the geographic scale. None = use CANVAS_WIDTH_PX / CANVAS_HEIGHT_PX.
CANVAS_RENDER_WIDTH  = None
CANVAS_RENDER_HEIGHT = None

# Optional: top-left pixel of the crop in the rotated intermediate canvas.
# None = centered crop (default). Set in city configs when a non-centered crop is needed.
CANVAS_CROP_X = None
CANVAS_CROP_Y = None

# Scale factor applied to all typography sizes and margins (font size, margin, bar width, etc.).
# 1.0 = default (sized for SF). Set < 1 for configs with different canvas proportions (e.g. NYC).
TYPOGRAPHY_SCALE = 1.0

# Additional font-size multiplier applied on top of TYPOGRAPHY_SCALE to narrow the text block.
# 1.0 = no change. 0.7 = text 30% less wide (and tall).
TYPOGRAPHY_WIDTH_SCALE = 1.0

# Horizontal pixel offset applied to the text block (positive = toward right edge).
# 0 = default (right-aligned with margin). Set in city configs to fine-tune placement.
TYPOGRAPHY_X_OFFSET = 0

# Where to position the legend bar horizontally: "center" (default) or "left".
LEGEND_POSITION = "center"

# Additional width multiplier for the legend bar, applied on top of TYPOGRAPHY_SCALE.
# 1.0 = no change. 0.7 = bar 30% less wide.
LEGEND_WIDTH_SCALE = 1.0

# Vertical pixel offset for the legend bar (positive = lower, negative = higher).
# 0 = default (centered on text block). Adjust per city config for fine-tuning.
LEGEND_Y_OFFSET = 0

# Show or hide elevation gain in the typography block.
# True = show (SF default). False = hide (e.g. NYC).
SHOW_ELEVATION = True

# Density color ramp: (normalized_value, [R, G, B])
# Edit stops here to change the palette — no code changes needed
ROUTE_COLOR_RAMP = [
    (0.0,  [100, 100, 255]),   # rarely-run → brighter indigo (more luminous, same hue)
    (0.45, [200,   0, 255]),   # moderate   → electric violet
    (0.8,  [255,   0, 180]),   # heavy      → neon hot pink
    (1.0,  [255, 220, 255]),   # peak       → blown-out pink-white (kept at 220 so g > 200 test passes)
]

# ── Line drawing ─────────────────────────────────────────────────────────────

# Base stroke width in pixels at full 4560×5700 canvas.
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
#   15 = neighbourhood detail — clear streets, ~150 tiles for SF
#   16 = current default — sharper detail (~600 tiles, 2–3 min first download)
#   17 = near-max print quality (~2,400 tiles — may hit CARTO rate limits)
# Set high (16–17) only when producing the final print file.
MAP_TILE_ZOOM = 17

MAP_TILE_OPACITY = 0.85   # lightened for more visible street grid
# Brightness multiplier applied to the map tile before compositing.
# 1.0 = no change. > 1.0 = brighter streets/water. Start at 1.3 and iterate.
MAP_TILE_BRIGHTNESS = 1.5
MAP_TILE_CACHE = "data/map_tile.png"
MAP_FONT_PATH = "data/fonts/Montserrat-SemiBold.ttf"
MAP_FONT_URL  = "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/montserrat/static/Montserrat-SemiBold.ttf"

# ── Animation ─────────────────────────────────────────────────────────────────
ANIMATION_FPS = 60
ANIMATION_DRAWING_SPEED = 160  # pixels/frame at ANIMATION_OUTPUT_RESOLUTION; tune to hit ~60s
ANIMATION_DRAWING_SPEED_SLOW = 10  # px/frame for first and last run (~1-3s depending on distance)
ANIMATION_SPEED_RAMP_RUNS = 3  # runs over which speed ramps from slow → full after run 1 (and back)
ANIMATION_DOT_RADIUS = 6       # cursor dot radius in pixels at ANIMATION_OUTPUT_RESOLUTION
ANIMATION_DOT_BLUR = 4         # Gaussian sigma for dot halo; 0 = hard edge
ANIMATION_DOT_BRIGHTNESS = 2.0 # multiply dot layer after blur to saturate the core; 1.0 = no boost
ANIMATION_HOLD_SECONDS = 3     # seconds to hold on final frame
ANIMATION_OUTPUT_RESOLUTION = (1080, 1350)  # (width, height) — 4:5 for Instagram
