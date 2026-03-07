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

# Intermediate render scale: determines the geographic scale (zoom level).
# The intermediate canvas is computed from these dimensions:
#   render_w = 4800*cos(29°) + 5800*sin(29°) ≈ 7010
#   render_h = 4800*sin(29°) + 5800*cos(29°) ≈ 7400
#   7010/7400 ≈ 0.9473 (matches NYC geo_aspect → no distortion)
CANVAS_RENDER_WIDTH  = 4800
CANVAS_RENDER_HEIGHT = 5800

# Final output dimensions (after crop).
# Derived from the render dimensions by removing/adding pixels on each edge:
#   -660 left, -1000 top, -2400 right, +200 bottom
CANVAS_WIDTH_PX  = 4800 - 660 - 2400   # 1740
CANVAS_HEIGHT_PX = 5800 - 1000 + 200   # 5000

# Crop origin in the rotated intermediate canvas (top-left of the desired output region).
# Centered crop of CANVAS_RENDER_WIDTH×CANVAS_RENDER_HEIGHT in the 7010×7399 intermediate:
#   x0 = (7010 - 4800) // 2 = 1105,  y0 = (7399 - 5800) // 2 = 799
# Then offset by the left/top trim amounts:
CANVAS_CROP_X = 1105 + 660   # 1765
CANVAS_CROP_Y = 799  + 1000  # 1799

# Separate tile cache so SF and NYC renders don't stomp each other.
MAP_TILE_CACHE = "data/map_tile_nyc.png"

# Typography is designed for the SF canvas proportions. Scale down for NYC.
TYPOGRAPHY_SCALE = .7

# Legend: left-aligned and 30% narrower than the already-scaled width.
LEGEND_POSITION   = "left"
LEGEND_WIDTH_SCALE = .8

# Text block: 30% narrower (smaller font = narrower lines).
TYPOGRAPHY_WIDTH_SCALE = .7

# Horizontal offset for the text block in final canvas pixels (positive = toward right edge).
TYPOGRAPHY_X_OFFSET = -400
