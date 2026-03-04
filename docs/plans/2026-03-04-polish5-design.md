# Polish Pass 5 Design

**Date:** 2026-03-04

**Goal:** Three targeted fixes — map/route alignment (stale tile cache), font re-download guard, lighter street grid.

---

## Changes

### 1. Tile cache — bounds-aware filename

**Problem:** `fetch_map_tile` caches to a fixed path (`data/map_tile.png`). When `SF_BOUNDS` shifted east in polish pass 4, the routes re-projected correctly but the cached tile still covered the old area, causing misalignment.

**Fix:** Derive the cache filename from a short hash of the bounds dict. The `MAP_TILE_CACHE` config value becomes a filename prefix; the actual path becomes `data/map_tile-<hash6>.png`. When bounds change, the hash changes and a fresh tile is fetched automatically.

- `src/tiles.py` — `fetch_map_tile`: compute `hashlib.md5` of bounds repr, use first 6 hex chars in path
- `export.py` — pass the prefix-based cache path (no change needed if tiles.py builds the path internally)
- `config.py` — `MAP_TILE_CACHE` stays as-is (used as prefix)

---

### 2. Font — minimum-size guard before skipping download

**Problem:** A pre-User-Agent-fix download wrote a corrupt/empty file to `data/fonts/Montserrat-SemiBold.ttf`. The existence check in `_download_font` skips re-download, so the corrupt file persists and `_load_font` silently falls back to PIL default.

**Fix:** In `_download_font`, if the file exists but is under 50 000 bytes, delete it and proceed with download. Montserrat-SemiBold TTF is ~300 KB, so 50 KB is a safe threshold that won't false-positive on legitimate partial writes.

**File:** `src/typography.py` — `_download_font`

---

### 3. Street grid — increase tile opacity

`MAP_TILE_OPACITY`: 0.70 → 0.85. Makes the underlying street grid more legible against the dark background.

**File:** `config.py` — `MAP_TILE_OPACITY`

---

## Architecture

All changes confined to `src/tiles.py`, `src/typography.py`, and `config.py`. No new modules.

Existing tests cover font download (mock-based) and tile fetching — both need minor updates to reflect new behavior.
