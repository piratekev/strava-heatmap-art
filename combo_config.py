from config import *  # same SF map: bounds, canvas, tiles, effects

# Run + Baywheels combo poster — rendered by combo_export.py.
# Both datasets share the SF map; each gets its own palette, and the two route
# layers are screen-blended together before compositing onto the map tiles.

# Bike data lives in the sibling repo (dict keyed by ride_id, decoded coordinates).
BIKE_RIDES_PATH = "../baywheels-art/data/repaired_rides.json"

# ── Runs: bright electric cyan (complement of Lyft pink, stays distinct on overlap)
RUN_COLOR_RAMP = [
    (0.0,  [0,   140, 200]),   # rarely-run → bright cerulean
    (0.45, [0,   215, 255]),   # moderate   → electric cyan
    (0.8,  [130, 245, 255]),   # heavy      → pale cyan glow
    (1.0,  [240, 255, 255]),   # peak       → white-hot
]
RUN_GAMMA = 0.5
RUN_HOT_BLOOM_THRESHOLD = HOT_BLOOM_THRESHOLD
RUN_HOT_BLOOM_SIGMA_MULT = HOT_BLOOM_SIGMA_MULT

# ── Bikes: Lyft pink (from baywheels-art config.py) ──────────────────────────
BIKE_COLOR_RAMP = [
    (0.0,  [200,   0, 140]),   # rarely-ridden → dim magenta
    (0.45, [255,   0, 191]),   # moderate      → Lyft Pink #FF00BF
    (0.8,  [255,  80, 220]),   # heavy         → hot pink glow
    (1.0,  [255, 220, 250]),   # peak          → blown-out pink-white
]
BIKE_GAMMA = 0.5               # baywheels-art uses 0.4; toned down so runs aren't buried
BIKE_HOT_BLOOM_THRESHOLD = 0.85  # baywheels-art uses 0.75
BIKE_HOT_BLOOM_SIGMA_MULT = 5.0

# ── Typography: both blocks bottom-center, runs left of center, bikes right ──
# Elevation is off so both blocks are the same 3 lines (years / count / miles).
SHOW_ELEVATION = False

# Gutter between the two blocks, as a fraction of canvas width.
COMBO_CENTER_GAP = 0.08

# Width multiplier for each legend bar (1.0 = 3/8 of canvas width).
COMBO_LEGEND_WIDTH_SCALE = 0.55
