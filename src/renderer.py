import os
import numpy as np
import cv2
from PIL import Image
from scipy.ndimage import gaussian_filter
from config import SF_BOUNDS, CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX, ROUTE_COLOR_RAMP, BG_COLOR


class StravaRenderer:
    def __init__(self, width=CANVAS_WIDTH_PX, height=CANVAS_HEIGHT_PX):
        self.width = width
        self.height = height
        self.canvas = np.zeros((height, width), dtype=np.float32)
        self.bounds = SF_BOUNDS.copy()  # default; overridden by set_bounds()

    def set_bounds(self, runs, padding=0.05):
        """Compute lat/lng extent from run coords and store with padding."""
        all_lats = [lat for run in runs for lat, lng in run["coords"]]
        all_lngs = [lng for run in runs for lat, lng in run["coords"]]
        lat_min, lat_max = min(all_lats), max(all_lats)
        lng_min, lng_max = min(all_lngs), max(all_lngs)
        lat_pad = (lat_max - lat_min) * padding
        lng_pad = (lng_max - lng_min) * padding
        self.bounds = {
            "lat_min": lat_min - lat_pad,
            "lat_max": lat_max + lat_pad,
            "lng_min": lng_min - lng_pad,
            "lng_max": lng_max + lng_pad,
        }

    def project(self, lat, lng):
        """Map (lat, lng) to (x, y) pixel coordinates using current bounds."""
        x = int((lng - self.bounds["lng_min"]) /
                (self.bounds["lng_max"] - self.bounds["lng_min"]) * (self.width - 1))
        y = int((self.bounds["lat_max"] - lat) /
                (self.bounds["lat_max"] - self.bounds["lat_min"]) * (self.height - 1))
        return x, y

    def rasterize_run(self, coords, weight=1.0):
        """Draw anti-aliased route onto the density canvas."""
        if len(coords) < 2:
            return
        points = [self.project(lat, lng) for lat, lng in coords]
        buf = np.zeros((self.height, self.width), dtype=np.float32)
        for i in range(len(points) - 1):
            cv2.line(buf, points[i], points[i + 1],
                     color=weight, thickness=1, lineType=cv2.LINE_AA)
        self.canvas += buf

    def rasterize_all(self, runs, weight=1.0):
        """Rasterize all runs onto the canvas."""
        for run in runs:
            self.rasterize_run(run["coords"], weight=weight)

    def _make_vignette(self, strength=0.5):
        """Radial gradient mask: 1.0 at center, (1-strength) at corners."""
        cx, cy = self.width / 2, self.height / 2
        y_idx, x_idx = np.ogrid[:self.height, :self.width]
        dist = np.sqrt(((x_idx - cx) / cx) ** 2 + ((y_idx - cy) / cy) ** 2)
        mask = 1 - strength * np.clip(dist, 0, 1)
        return mask.astype(np.float32)

    def to_image(self, bloom=True, bloom_sigma=8.0, bloom_strength=0.6,
                 vignette=True, vignette_strength=0.5,
                 grain=True, grain_amount=0.025):
        """Normalize density canvas and apply luminosity colormap. Returns HxWx3 uint8 array."""
        bg = np.array(BG_COLOR, dtype=np.float32)
        route_color = np.array([255, 240, 180], dtype=np.float32)
        max_val = self.canvas.max()
        if max_val == 0:
            norm = self.canvas.copy()
        else:
            norm = np.log1p(self.canvas) / np.log1p(max_val)

        if bloom:
            blurred = gaussian_filter(norm, sigma=bloom_sigma)
            norm = 1 - (1 - norm) * (1 - blurred * bloom_strength)

        rgb = np.zeros((self.height, self.width, 3), dtype=np.float32)
        for c in range(3):
            rgb[:, :, c] = bg[c] * (1 - norm) + route_color[c] * norm

        if vignette:
            mask = self._make_vignette(strength=vignette_strength)
            rgb *= mask[:, :, np.newaxis]

        if grain:
            noise = np.random.normal(0, grain_amount * 255, rgb.shape).astype(np.float32)
            rgb += noise

        return np.clip(rgb, 0, 255).astype(np.uint8)

    def save(self, path, dpi=300, **kwargs):
        """Save the rendered image as a PNG at the given DPI."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        img_array = self.to_image(**kwargs)
        img = Image.fromarray(img_array, mode="RGB")
        img.save(path, dpi=(dpi, dpi))
        print(f"Saved: {path}")
