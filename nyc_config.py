from config import *  # inherit all SF defaults

# New York City bounding box
# Covers: full NYC marathon course (Staten Island → Brooklyn → Queens → Bronx → Manhattan),
# Hoboken to the west, Washington Heights to the north.
CITY_BOUNDS = {
    "lat_min": 40.575,   # Verrazzano Bridge / Staten Island marathon start
    "lat_max": 40.875,   # Washington Heights
    "lng_min": -74.105,  # Hoboken
    "lng_max": -73.730,  # eastern Brooklyn/Queens
}

# Rotation: Manhattan's street grid runs ~29° from true north.
# Setting this rotates the final output so Manhattan's long axis is vertical.
CANVAS_ROTATION_DEGREES = 29

# Canvas: final output dimensions.
# Derived so the intermediate (pre-rotation) canvas matches the NYC Mercator aspect ratio.
# Formula: render_w/render_h = geo_aspect (0.9473) → W/H ≈ 0.8276
# render_w = 4800*cos(29°) + 5800*sin(29°) ≈ 7010
# render_h = 4800*sin(29°) + 5800*cos(29°) ≈ 7400
# 7010/7400 ≈ 0.9473 (matches NYC geo_aspect)
CANVAS_WIDTH_PX  = 4800
CANVAS_HEIGHT_PX = 5800

# Separate tile cache so SF and NYC renders don't stomp each other.
MAP_TILE_CACHE = "data/map_tile_nyc.png"
