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

# ── Typography ───────────────────────────────────────────────────────────────
# One combined year range top-center (over the bay); two stat blocks bottom-center
# (count / miles), runs left of center, bikes right; color legends underneath.
SHOW_ELEVATION = False

# Size of the top-center year range / animation month line, relative to stat text.
COMBO_DATE_SCALE = 1.2
COMBO_MONTH_SCALE = 0.7
# Top edge of the year range, as a fraction of canvas height.
COMBO_DATE_TOP = 0.075

# Gutter between the two blocks, as a fraction of canvas width.
COMBO_CENTER_GAP = 0.08

# Width multiplier for each legend bar (1.0 = 3/8 of canvas width).
COMBO_LEGEND_WIDTH_SCALE = 0.55

# ── Animation (combo_animate.py) ─────────────────────────────────────────────
# Sequential build (after a 0.5s blank intro): runs + rides merged in date order, paced by activity count
# (each activity gets an equal slice of the timeline), each route drawn over
# COMBO_ANIM_ROUTE_DRAW_S so dozens grow at once. Stats tally up live.
COMBO_ANIM_RESOLUTION = (1080, 1350)  # 4:5, same aspect as the poster
COMBO_ANIM_FPS = 30
COMBO_ANIM_INTRO_S = 0.5              # blank map + zeroed stats before drawing starts
COMBO_ANIM_DURATION_S = 30            # drawing time
COMBO_ANIM_HOLD_S = 2                 # hold on the finished map
COMBO_ANIM_ROUTE_DRAW_S = 0.6         # time for one route to draw start → end
COMBO_ANIM_TRACER_RADIUS = 2          # px, dot at each growing route's tip
# Tracer dot colors per layer — bright versions of each ramp so runs/rides read apart.
COMBO_ANIM_DOT_COLORS = {"run": [120, 240, 255], "bike": [255, 70, 215]}
# Soft glow around each dot (Gaussian sigma in px, strength) so a dot still pops
# when it sits on a line of its own color. 0 strength = hard dots only.
COMBO_ANIM_DOT_GLOW_SIGMA = 2.5
COMBO_ANIM_DOT_GLOW_STRENGTH = 1.5
