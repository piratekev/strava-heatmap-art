import math
import os
import numpy as np
import cv2
from PIL import Image
from scipy.ndimage import gaussian_filter
from config import (CITY_BOUNDS, CANVAS_WIDTH_PX, CANVAS_HEIGHT_PX, CANVAS_ROTATION_DEGREES,
                    CANVAS_RENDER_WIDTH, CANVAS_RENDER_HEIGHT, CANVAS_CROP_X, CANVAS_CROP_Y,
                    ROUTE_COLOR_RAMP, BG_COLOR,
                    HOT_BLOOM_THRESHOLD, HOT_BLOOM_SIGMA_MULT, HOT_BLOOM_STRENGTH,
                    ROUTE_LINE_THICKNESS, ROUTE_LINE_THICKNESS_50_BONUS, ROUTE_LINE_THICKNESS_10_BONUS,
                    DENSITY_EXPAND_SIGMA, DENSITY_EXPAND_STRENGTH,
                    DENSITY_EXPAND_POWER, GAMMA)


def _expand_bounds(bounds, lng_scale, lat_scale):
    """Expand geographic bounds by scale factors around their center (in Mercator space)."""
    lng_center = (bounds["lng_min"] + bounds["lng_max"]) / 2
    half_lng = (bounds["lng_max"] - bounds["lng_min"]) / 2 * lng_scale

    lat_min_rad = math.radians(bounds["lat_min"])
    lat_max_rad = math.radians(bounds["lat_max"])
    merc_min = math.asinh(math.tan(lat_min_rad))
    merc_max = math.asinh(math.tan(lat_max_rad))
    merc_center = (merc_min + merc_max) / 2
    half_merc = (merc_max - merc_min) / 2 * lat_scale

    return {
        "lat_min": math.degrees(math.atan(math.sinh(merc_center - half_merc))),
        "lat_max": math.degrees(math.atan(math.sinh(merc_center + half_merc))),
        "lng_min": lng_center - half_lng,
        "lng_max": lng_center + half_lng,
    }


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
        self.final_width = width
        self.final_height = height
        self._rotation_degrees = CANVAS_ROTATION_DEGREES

        if CANVAS_RENDER_WIDTH is not None:
            # Scale factor from full-resolution to the requested size (e.g. 0.1 for preview).
            # render_w/h drive the intermediate canvas size; they differ from final_width/height
            # when a non-centered crop is in use (e.g. NYC config).
            scale = width / CANVAS_WIDTH_PX if CANVAS_WIDTH_PX else 1.0
            render_w = int(CANVAS_RENDER_WIDTH  * scale)
            render_h = int(CANVAS_RENDER_HEIGHT * scale)
            self._crop_x = int(CANVAS_CROP_X * scale) if CANVAS_CROP_X is not None else None
            self._crop_y = int(CANVAS_CROP_Y * scale) if CANVAS_CROP_Y is not None else None
        else:
            render_w = width
            render_h = height
            self._crop_x = None
            self._crop_y = None

        if CANVAS_ROTATION_DEGREES != 0:
            cos_r = math.cos(math.radians(CANVAS_ROTATION_DEGREES))
            sin_r = math.sin(math.radians(CANVAS_ROTATION_DEGREES))
            self.width  = int(render_w * cos_r + render_h * sin_r)
            self.height = int(render_w * sin_r + render_h * cos_r)
            self.bounds = _expand_bounds(
                CITY_BOUNDS,
                lng_scale=self.width  / render_w,
                lat_scale=self.height / render_h,
            )
        else:
            self.width  = render_w
            self.height = render_h
            self.bounds = CITY_BOUNDS.copy()

        self.canvas = np.zeros((self.height, self.width), dtype=np.float32)

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

    def rasterize_run(self, coords, weight=1.0, thickness=ROUTE_LINE_THICKNESS):
        """Draw anti-aliased route onto the density canvas."""
        if len(coords) < 2:
            return
        points = [self.project(lat, lng) for lat, lng in coords]
        buf = np.zeros((self.height, self.width), dtype=np.float32)
        for i in range(len(points) - 1):
            cv2.line(buf, points[i], points[i + 1],
                     color=weight, thickness=thickness, lineType=cv2.LINE_AA)
        self.canvas += buf

    def _density_score(self, coords):
        """Mean canvas value sampled along this route's projected path.

        Called after pass-1 rasterization so the canvas reflects all routes.
        Higher score = route passes through heavily-run corridors.
        """
        if len(coords) < 2:
            return 0.0
        values = []
        for lat, lng in coords:
            x, y = self.project(lat, lng)
            x_c = max(0, min(x, self.width - 1))
            y_c = max(0, min(y, self.height - 1))
            values.append(float(self.canvas[y_c, x_c]))
        return float(np.mean(values)) if values else 0.0

    def rasterize_all(self, runs, weight=1.0):
        """Rasterize all runs with a two-pass density-proportional thickness.

        Pass 1: draw every run at base ROUTE_LINE_THICKNESS.
        Pass 2: score each run by mean canvas density along its path, then
                re-draw top-50% routes at base+50-bonus and top-10% at base+10-bonus.
        Only the highest bonus fires per run (they don't stack).
        """
        # Pass 1 — build the density canvas
        for run in runs:
            self.rasterize_run(run["coords"], weight=weight)

        if len(runs) < 2:
            return

        # Score and rank
        scores = [self._density_score(run["coords"]) for run in runs]
        sorted_scores = sorted(scores)
        p50 = sorted_scores[int(len(runs) * 0.50)]
        p90 = sorted_scores[int(len(runs) * 0.90)]

        # Pass 2 — re-draw hot routes thicker
        for run, score in zip(runs, scores):
            if score >= p90:
                self.rasterize_run(run["coords"], weight=weight,
                                   thickness=ROUTE_LINE_THICKNESS + ROUTE_LINE_THICKNESS_10_BONUS)
            elif score >= p50:
                self.rasterize_run(run["coords"], weight=weight,
                                   thickness=ROUTE_LINE_THICKNESS + ROUTE_LINE_THICKNESS_50_BONUS)

    def _make_vignette(self, strength=0.5):
        """Radial gradient mask: 1.0 at center, (1-strength) at corners."""
        cx, cy = self.width / 2, self.height / 2
        y_idx, x_idx = np.ogrid[:self.height, :self.width]
        dist = np.sqrt(((x_idx - cx) / cx) ** 2 + ((y_idx - cy) / cy) ** 2)
        mask = 1 - strength * np.clip(dist, 0, 1)
        return mask.astype(np.float32)

    def rotate_and_crop(self, img_array):
        """Rotate by _rotation_degrees and crop to final_width × final_height.
        Returns img_array unchanged when _rotation_degrees == 0.
        img_array must be HxWx3 uint8 or float32.
        """
        if self._rotation_degrees == 0:
            return img_array
        h, w = img_array.shape[:2]
        M = cv2.getRotationMatrix2D((w / 2, h / 2), self._rotation_degrees, 1.0)
        rotated = cv2.warpAffine(img_array, M, (w, h))
        x0 = self._crop_x if self._crop_x is not None else (w - self.final_width)  // 2
        y0 = self._crop_y if self._crop_y is not None else (h - self.final_height) // 2
        return rotated[y0:y0 + self.final_height, x0:x0 + self.final_width]

    def to_image(self, bloom=True, bloom_sigma_tight=4.0, bloom_sigma_wide=16.0,
                 bloom_strength=0.6, glow=True, glow_strength=1.0,
                 vignette=True, vignette_strength=0.5,
                 grain=True, grain_amount=0.025,
                 gamma=GAMMA, hot_bloom=True, density_expand=True):
        """Normalize density canvas, apply color ramp and effects. Returns HxWx3 uint8."""
        bg = np.array(BG_COLOR, dtype=np.float32)
        max_val = self.canvas.max()
        if max_val == 0:
            norm = self.canvas.copy()
        else:
            norm = np.log1p(self.canvas) / np.log1p(max_val)

        norm = norm ** gamma  # lift mid-density routes (gamma < 1 brightens)

        if density_expand:
            expanded = gaussian_filter(norm ** DENSITY_EXPAND_POWER, sigma=DENSITY_EXPAND_SIGMA)
            norm = 1 - (1 - norm) * (1 - expanded * DENSITY_EXPAND_STRENGTH)

        if bloom:
            tight = gaussian_filter(norm, sigma=bloom_sigma_tight)
            wide = gaussian_filter(norm, sigma=bloom_sigma_wide)
            bloom_layer = tight * 0.4 + wide * 0.6
            norm = 1 - (1 - norm) * (1 - bloom_layer * bloom_strength)

        if hot_bloom:
            hot_mask = np.clip(
                (norm - HOT_BLOOM_THRESHOLD) / (1.0 - HOT_BLOOM_THRESHOLD), 0, 1
            )
            hot_layer = gaussian_filter(hot_mask, sigma=bloom_sigma_wide * HOT_BLOOM_SIGMA_MULT)
            norm = 1 - (1 - norm) * (1 - hot_layer * HOT_BLOOM_STRENGTH)

        norm = np.clip(norm, 0.0, 1.0)  # screen-blend ops can push norm > 1; clamp before colour mapping
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
