"""
Sprite sheet loader and frame extractor.

Supports the SWIFT manifest format (JSON) with explicit frameRects.
When the actual image dimensions differ from sourceImage in the manifest,
frame rects are scaled proportionally (handles @2x / retina exports).
"""
import json
import os
from dataclasses import dataclass, field
from typing import Dict, Optional

from PIL import Image


@dataclass
class AnimationDef:
    name: str
    frames: list        # list of frame IDs, e.g. ["F01", "F02"]
    fps: int
    loop: bool


@dataclass
class WorldStateRef:
    """
    Maps a SHADED world-state name (e.g. "dust", "aging") to a procedural
    transform descriptor so SWIFT actors are parameterizable by explicit world
    states. Serializes cleanly to a JSON object:
        {"name": "dust", "transform": "dust", "intensity": 0.5,
         "variant_path": "actor_dust.png", "params": {...}}

    Backward compatible: legacy manifests stored `palette` (preset key) and an
    `intensity` range [min, max]; both load fine, and `transform` defaults to
    the preset key or the state name.
    """
    name: str
    transform: Optional[str] = None                    # procedural transform name (e.g. "dust")
    intensity: float = 0.5                             # scalar intensity [0, 1]
    palette: Optional[str] = None                      # legacy preset palette key (backward compat)
    variant_path: Optional[str] = None                 # path (basename) of the generated variant PNG
    params: Optional[Dict] = None                      # optional extra transform params

    def to_dict(self) -> dict:
        d: Dict = {"name": self.name}
        if self.transform is not None:
            d["transform"] = self.transform
        elif self.palette is not None:
            d["palette"] = self.palette
        d["intensity"] = self.intensity
        if self.variant_path is not None:
            d["variant_path"] = self.variant_path
        if self.params is not None:
            d["params"] = self.params
        return d

    @classmethod
    def from_dict(cls, data) -> "WorldStateRef":
        if isinstance(data, str):
            return cls(name=data)
        raw_intensity = data.get("intensity", 0.5)
        if isinstance(raw_intensity, (list, tuple)):
            # Legacy range format: keep tuple for backward-compatible round-trip.
            intensity = (float(raw_intensity[0]), float(raw_intensity[1]))
        else:
            intensity = float(raw_intensity)
        transform = data.get("transform") or data.get("palette")
        return cls(
            name=data.get("name", ""),
            transform=transform,
            palette=data.get("palette"),
            intensity=intensity,
            variant_path=data.get("variant_path"),
            params=data.get("params"),
        )


class SpriteSheetManifest:
    """
    Parses a SWIFT sprite sheet manifest JSON.
    Supports two rect sources (in priority order):
      1. frameRects  – explicit pre-computed pixel rects (authoritative)
      2. grid        – computed from column/row definitions (fallback)
    """

    def __init__(self):
        self.source_w: int = 0
        self.source_h: int = 0
        self.frame_ids: list[str] = []
        self.frame_rects: dict[str, tuple] = {}   # id → (x, y, w, h)
        self.frame_keys: dict[str, str] = {}       # id → semantic key
        self.key_to_id: dict[str, str] = {}        # semantic key → id
        self.animations: dict[str, AnimationDef] = {}
        self.applies_to: list[str] = []
        self.depth_image: Optional[str] = None     # optional path to depth map PNG
        self.depth_frame_rects: dict[str, tuple] = {}  # id → (x, y, w, h) for depth frames
        self.depth_source_w: int = 0               # depth map source width
        self.depth_source_h: int = 0               # depth map source height
        self.normal_image: Optional[str] = None    # optional path to normal-map PNG
        self.normal_frame_rects: dict[str, tuple] = {}  # id → (x, y, w, h) for normal frames
        self.normal_source_w: int = 0              # normal map source width
        self.normal_source_h: int = 0              # normal map source height
        self.emissive_image: Optional[str] = None  # optional path to emissive PNG
        self.emissive_frame_rects: dict[str, tuple] = {}  # id → (x, y, w, h) for emissive frames
        self.emissive_source_w: int = 0            # emissive map source width
        self.emissive_source_h: int = 0            # emissive map source height
        self.world_states: Dict[str, WorldStateRef] = {}   # world-state name → descriptor

    @classmethod
    def from_file(cls, path: str) -> "SpriteSheetManifest":
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "SpriteSheetManifest":
        m = cls()
        src = data.get("sourceImage", {})
        m.source_w = src.get("w", 0)
        m.source_h = src.get("h", 0)
        m.applies_to = data.get("appliesTo", [])
        m.depth_image = data.get("depthImage")
        m.normal_image = data.get("normalImage")
        m.emissive_image = data.get("emissiveImage")

        # Parse world-state descriptors (optional; SHADED world-state hooks)
        for ws_name, ws_entry in data.get("worldStates", {}).items():
            if isinstance(ws_entry, dict) and not ws_entry.get("name"):
                ws_entry = dict(ws_entry)
                ws_entry["name"] = ws_name
            m.world_states[ws_name] = WorldStateRef.from_dict(ws_entry)

        # Parse depth image dimensions (optional)
        depth_src = data.get("depthSourceImage", {})
        m.depth_source_w = depth_src.get("w", 0)
        m.depth_source_h = depth_src.get("h", 0)

        # Parse normal-map image dimensions (optional)
        normal_src = data.get("normalSourceImage", {})
        m.normal_source_w = normal_src.get("w", 0)
        m.normal_source_h = normal_src.get("h", 0)

        # Parse emissive image dimensions (optional)
        emissive_src = data.get("emissiveSourceImage", {})
        m.emissive_source_w = emissive_src.get("w", 0)
        m.emissive_source_h = emissive_src.get("h", 0)

        # Build frame id → key map
        for f in data.get("frames", []):
            fid = f["id"]
            key = f.get("key", fid)
            m.frame_ids.append(fid)
            m.frame_keys[fid] = key
            m.key_to_id[key] = fid

        # Resolve frame rects: prefer explicit frameRects, fallback to grid
        explicit = data.get("frameRects", {})
        if explicit:
            for fid in m.frame_ids:
                r = explicit.get(fid)
                if r:
                    m.frame_rects[fid] = (r["x"], r["y"], r["w"], r["h"])
        else:
            m._compute_from_grid(data, m.frame_ids, data.get("frames", []))

        # Resolve depth frame rects (if present)
        depth_rects = data.get("depthFrameRects", {})
        if depth_rects:
            for fid in m.frame_ids:
                r = depth_rects.get(fid)
                if r:
                    m.depth_frame_rects[fid] = (r["x"], r["y"], r["w"], r["h"])

        # Resolve normal-map frame rects (if present)
        normal_rects = data.get("normalFrameRects", {})
        if normal_rects:
            for fid in m.frame_ids:
                r = normal_rects.get(fid)
                if r:
                    m.normal_frame_rects[fid] = (r["x"], r["y"], r["w"], r["h"])

        # Resolve emissive frame rects (if present)
        emissive_rects = data.get("emissiveFrameRects", {})
        if emissive_rects:
            for fid in m.frame_ids:
                r = emissive_rects.get(fid)
                if r:
                    m.emissive_frame_rects[fid] = (r["x"], r["y"], r["w"], r["h"])

        # Parse animations
        for anim_name, anim_data in data.get("animations", {}).items():
            m.animations[anim_name] = AnimationDef(
                name=anim_name,
                frames=anim_data["frames"],
                fps=anim_data.get("fps", 12),
                loop=anim_data.get("loop", True),
            )

        return m

    def _compute_from_grid(self, data: dict, frame_ids: list, frames_raw: list):
        grid = data.get("grid", {})
        cols = grid.get("columns", {})
        rows = grid.get("rows", {})
        id_to_rowcol = {f["id"]: (str(f["row"]), str(f["col"])) for f in frames_raw}

        for fid in frame_ids:
            rc = id_to_rowcol.get(fid)
            if not rc:
                continue
            row_key, col_key = rc
            col_def = cols.get(col_key, {})
            row_def = rows.get(row_key, {})
            x = col_def.get("x", 0)
            y = row_def.get("y", 0)
            w = col_def.get("w", 0)
            h = row_def.get("h", 0)
            self.frame_rects[fid] = (x, y, w, h)


class SpriteSheet:
    """
    Loads a sprite sheet PNG and extracts frames using a SpriteSheetManifest.

    If the image dimensions differ from manifest.source_w/h, frame rects are
    scaled proportionally — handles @2x or retina exports automatically.
    """

    def __init__(self, image_path: str, manifest: SpriteSheetManifest):
        if not os.path.isfile(image_path):
            raise FileNotFoundError(f"Sprite sheet not found: {image_path}")
        self._path = image_path
        self._manifest = manifest
        self._image: Optional[Image.Image] = None
        self._scale_x: float = 1.0
        self._scale_y: float = 1.0
        self._compute_scale()

    def _compute_scale(self):
        img = self._get_image()
        iw, ih = img.size
        if self._manifest.source_w and self._manifest.source_h:
            self._scale_x = iw / self._manifest.source_w
            self._scale_y = ih / self._manifest.source_h

    def _get_image(self) -> Image.Image:
        if self._image is None:
            self._image = Image.open(self._path).convert("RGBA")
        return self._image

    def _scaled_rect(self, frame_id: str) -> tuple:
        """Return (x, y, w, h) scaled to actual image dimensions."""
        x, y, w, h = self._manifest.frame_rects[frame_id]
        sx, sy = self._scale_x, self._scale_y
        return (
            round(x * sx),
            round(y * sy),
            round(w * sx),
            round(h * sy),
        )

    def extract_frame(self, frame_id: str) -> Image.Image:
        """Crop and return a single frame by ID."""
        if frame_id not in self._manifest.frame_rects:
            raise KeyError(f"Unknown frame ID: {frame_id!r}")
        x, y, w, h = self._scaled_rect(frame_id)
        img = self._get_image()
        return img.crop((x, y, x + w, y + h))

    def extract_frame_by_key(self, key: str) -> Image.Image:
        """Crop and return a frame by semantic key (e.g. 'idle_stand')."""
        fid = self._manifest.key_to_id.get(key)
        if not fid:
            raise KeyError(f"Unknown frame key: {key!r}")
        return self.extract_frame(fid)

    def extract_all_frames(self) -> dict:
        """Return all frames as {frame_id: PIL.Image}."""
        return {fid: self.extract_frame(fid) for fid in self._manifest.frame_ids}

    def get_animation(self, name: str) -> list:
        """Return ordered list of PIL.Image frames for a named animation."""
        anim = self._manifest.animations.get(name)
        if anim is None:
            raise KeyError(f"Unknown animation: {name!r}")
        return [self.extract_frame(fid) for fid in anim.frames]

    def animation_fps(self, name: str) -> int:
        anim = self._manifest.animations.get(name)
        if anim is None:
            raise KeyError(f"Unknown animation: {name!r}")
        return anim.fps

    def animation_loops(self, name: str) -> bool:
        return self._manifest.animations[name].loop

    def list_animations(self) -> list[str]:
        return list(self._manifest.animations.keys())

    def list_frame_ids(self) -> list[str]:
        return list(self._manifest.frame_ids)

    def frame_size(self, frame_id: str) -> tuple:
        """Return (w, h) of a frame in actual image pixels."""
        _, _, w, h = self._scaled_rect(frame_id)
        return (w, h)

    # ── Export helpers ────────────────────────────────────────────────────────

    def export_animation_gif(
        self,
        name: str,
        out_path: str,
        loop: Optional[int] = None,
    ) -> str:
        from core.exporter import export_gif_from_images
        frames = self.get_animation(name)
        fps = self.animation_fps(name)
        loop_val = loop if loop is not None else (0 if self.animation_loops(name) else 1)
        return export_gif_from_images(frames, out_path, fps=fps, loop=loop_val)

    def export_animation_sheet(
        self,
        name: str,
        out_path: str,
        columns: Optional[int] = None,
        padding: int = 0,
    ) -> str:
        from core.exporter import export_sprite_sheet_from_images
        frames = self.get_animation(name)
        return export_sprite_sheet_from_images(frames, out_path, columns=columns, padding=padding)

    def export_full_sheet(self, out_path: str) -> str:
        """Re-export the original sheet (identity copy as RGBA PNG)."""
        img = self._get_image()
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        img.save(out_path, "PNG")
        return out_path
