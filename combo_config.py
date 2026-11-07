from config import *  # same SF map: bounds, canvas, tiles, effects

# Run + Baywheels combo poster — rendered by combo_export.py.
# Both datasets share the SF map; each gets its own palette, and the two route
# layers are screen-blended together before compositing onto the map tiles.

# Bike data lives in the sibling repo (dict keyed by ride_id, decoded coordinates).
BIKE_RIDES_PATH = "../baywheels-art/data/repaired_rides.json"

# ── Runs: SF default green ───────────────────────────────────────────────────
RUN_COLOR_RAMP = ROUTE_COLOR_RAMP
RUN_GAMMA = GAMMA
RUN_HOT_BLOOM_THRESHOLD = HOT_BLOOM_THRESHOLD
RUN_HOT_BLOOM_SIGMA_MULT = HOT_BLOOM_SIGMA_MULT

# ── Bikes: Lyft pink (from baywheels-art config.py) ──────────────────────────
BIKE_COLOR_RAMP = [
    (0.0,  [200,   0, 140]),   # rarely-ridden → dim magenta
    (0.45, [255,   0, 191]),   # moderate      → Lyft Pink #FF00BF
    (0.8,  [255,  80, 220]),   # heavy         → hot pink glow
    (1.0,  [255, 220, 250]),   # peak          → blown-out pink-white
]
BIKE_GAMMA = 0.4
BIKE_HOT_BLOOM_THRESHOLD = 0.75
BIKE_HOT_BLOOM_SIGMA_MULT = 5.0

# ── Typography: runs bottom-left, bikes bottom-right ─────────────────────────
# Elevation is off so both corner blocks are the same 3 lines (years / count / miles).
SHOW_ELEVATION = False

# Width multiplier for each corner legend bar (1.0 = 3/8 of canvas width).
COMBO_LEGEND_WIDTH_SCALE = 0.55
