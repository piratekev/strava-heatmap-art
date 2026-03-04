import numpy as np
from config import SF_BOUNDS, CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX


class StravaRenderer:
    # Background color: near-black navy
    BG_COLOR = np.array([10, 15, 30], dtype=np.float32)
    # Route color: warm gold/white
    ROUTE_COLOR = np.array([255, 240, 180], dtype=np.float32)

    def __init__(self, width=CANVAS_WIDTH_PX, height=CANVAS_HEIGHT_PX):
        self.width = width
        self.height = height
        self.canvas = np.zeros((height, width), dtype=np.float32)

    def project(self, lat, lng):
        """Map (lat, lng) to (x, y) pixel coordinates."""
        x = int((lng - SF_BOUNDS["lng_min"]) /
                (SF_BOUNDS["lng_max"] - SF_BOUNDS["lng_min"]) * (self.width - 1))
        # Latitude is inverted: higher lat = lower y
        y = int((SF_BOUNDS["lat_max"] - lat) /
                (SF_BOUNDS["lat_max"] - SF_BOUNDS["lat_min"]) * (self.height - 1))
        return x, y
