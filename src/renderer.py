import os
import numpy as np
import cv2
from PIL import Image
from scipy.ndimage import gaussian_filter
from config import SF_BOUNDS, CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX, ROUTE_COLOR_RAMP, BG_COLOR


def _ramp_colors(norm, ramp):
    """Vectorized color ramp: for each pixel in norm [0,1], return interpolated RGB."""
    result = np.zeros((*norm.shape, 3), dtype=np.float32)
    for i in range(len(ramp) - 1):
        t0, c0 = ramp[i]
        t1, c1 = ramp[i + 1]
        in_seg = (norm >= t0) & (norm <= t1) if i == len(ramp) - 2 else (norm >= t0) & (norm < t1)
        alpha = np.where(in_seg, (norm - t0) / (t1 - t0), 0.0)
        for c in range(3):
            route_c = c0[c] * (1 - alpha) + c1[c] * alpha
            result[:, :, c] += np.where(in_seg, route_c, 0.0)
    return result


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
        """Map (lat, lng) to (x, y) pixel using Web Mercator Y projection."""
        lat_rad = np.radians(lat)
        merc_y = np.arcsinh(np.tan(lat_rad))

        lat_min_rad = np.radians(self.bounds["lat_min"])
        lat_max_rad = np.radians(self.bounds["lat_max"])
        merc_min = np.arcsinh(np.tan(lat_min_rad))
        merc_max = np.arcsinh(np.tan(lat_max_rad))

        x = int((lng - self.bounds["lng_min"]) /
                (self.bounds["lng_max"] - self.bounds["lng_min"]) * (self.width - 1))
        y = int((merc_max - merc_y) / (merc_max - merc_min) * (self.height - 1))
        return x, y

    def rasterize_run(self, coords, weight=1.0):
        """Draw anti-aliased route onto the density canvas."""
        if len(coords) < 2:
            return
        points = [self.project(lat, lng) for lat, lng in coords]
        buf = np.zeros((self.height, self.width), dtype=np.float32)
        for i in range(len(points) - 1):
            cv2.line(buf, points[i], points[i + 1],
                     color=weight, thickness=2, lineType=cv2.LINE_AA)
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

    def to_image(self, bloom=True, bloom_sigma_tight=4.0, bloom_sigma_wide=16.0,
                 bloom_strength=0.6, glow=True, glow_strength=1.0,
                 vignette=True, vignette_strength=0.5,
                 grain=True, grain_amount=0.025):
        """Normalize density canvas, apply color ramp and effects. Returns HxWx3 uint8."""
        bg = np.array(BG_COLOR, dtype=np.float32)
        max_val = self.canvas.max()
        if max_val == 0:
            norm = self.canvas.copy()
        else:
            norm = np.log1p(self.canvas) / np.log1p(max_val)

        if bloom:
            tight = gaussian_filter(norm, sigma=bloom_sigma_tight)
            wide = gaussian_filter(norm, sigma=bloom_sigma_wide)
            bloom_layer = tight * 0.4 + wide * 0.6
            norm = 1 - (1 - norm) * (1 - bloom_layer * bloom_strength)

        route_colors = _ramp_colors(norm, ROUTE_COLOR_RAMP)
        rgb = np.zeros((self.height, self.width, 3), dtype=np.float32)
        for c in range(3):
            rgb[:, :, c] = bg[c] * (1 - norm) + route_colors[:, :, c] * norm

        if glow:
            sigma = self.height / 40.0
            for c in range(3):
                glow_ch = gaussian_filter(rgb[:, :, c], sigma=sigma)
                rgb[:, :, c] = 255 - (255 - rgb[:, :, c]) * (255 - glow_ch * glow_strength) / 255

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
