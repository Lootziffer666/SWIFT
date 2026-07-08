"""
Export rendered frames to sprite sheet PNG, animated GIF, or frames + JSON metadata.
"""
import os
import json
from pathlib import Path
from typing import Dict, Optional

from PIL import Image

from core.sprite_sheet import WorldStateRef


def _load_frames(frame_paths: list[str]) -> list[Image.Image]:
    frames = []
    for p in frame_paths:
        img = Image.open(p).convert("RGBA")
        frames.append(img)
    return frames


def _compute_frame_layout(
    frame_size: tuple,
    count: int,
    columns: Optional[int] = None,
    padding: int = 0,
) -> tuple:
    """Compute frame rects + sheet size for a grid packing of `count` equal-sized
    frames. Shared by export_sprite_sheet/export_sprite_sheet_from_images and
    export_manifest so the manifest's frameRects always match the packed sheet."""
    fw, fh = frame_size
    cols = columns or count  # default: single row
    rows = (count + cols - 1) // cols
    sheet_w = cols * (fw + padding) - padding
    sheet_h = rows * (fh + padding) - padding
    rects = []
    for i in range(count):
        col = i % cols
        row = i // cols
        rects.append((col * (fw + padding), row * (fh + padding), fw, fh))
    return rects, (sheet_w, sheet_h), cols


def export_sprite_sheet(
    frame_paths: list[str],
    out_path: str,
    columns: Optional[int] = None,
    padding: int = 0,
) -> str:
    """Pack frames into a single sprite sheet PNG."""
    if not frame_paths:
        raise ValueError("No frames to export")

    frames = _load_frames(frame_paths)
    rects, (sheet_w, sheet_h), _ = _compute_frame_layout(frames[0].size, len(frames), columns, padding)
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))

    for frame, (x, y, _fw, _fh) in zip(frames, rects):
        sheet.paste(frame, (x, y))

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    sheet.save(out_path, "PNG")
    return out_path


def export_depth_sheet(
    depth_frame_paths: list[str],
    out_path: str,
    columns: Optional[int] = None,
    padding: int = 0,
) -> str:
    """Pack depth frames (8-bit grayscale) into a sprite sheet."""
    if not depth_frame_paths:
        raise ValueError("No depth frames to export")

    # Load as grayscale (L mode)
    depth_frames = []
    for p in depth_frame_paths:
        img = Image.open(p).convert("L")  # 8-bit grayscale
        depth_frames.append(img)

    rects, (sheet_w, sheet_h), _ = _compute_frame_layout(
        depth_frames[0].size, len(depth_frames), columns, padding
    )
    sheet = Image.new("L", (sheet_w, sheet_h), 0)  # Black background

    for frame, (x, y, _fw, _fh) in zip(depth_frames, rects):
        sheet.paste(frame, (x, y))

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    sheet.save(out_path, "PNG")
    return out_path


def export_manifest(
    frame_paths: list[str],
    out_path: str,
    anim_name: str = "animation",
    fps: int = 12,
    loop: bool = True,
    columns: Optional[int] = None,
    padding: int = 0,
    depth_image: Optional[str] = None,
    depth_frame_paths: Optional[list[str]] = None,
    world_states: Optional[Dict[str, WorldStateRef]] = None,
) -> str:
    """Write a SWIFT sprite-sheet manifest JSON (SpriteSheetManifest schema v1.4.0+)
    describing the layout export_sprite_sheet() packs these same frames into.
    Consumable by core.sprite_sheet.SpriteSheetManifest and by SHADED's actor
    loader. Optionally includes depthImage path and depthFrameRects for spatial
    rendering via depth-layer ordering."""
    if not frame_paths:
        raise ValueError("No frames to export")

    frames = _load_frames(frame_paths)
    rects, (sheet_w, sheet_h), cols = _compute_frame_layout(frames[0].size, len(frames), columns, padding)
    frame_ids = [f"F{i + 1:02d}" for i in range(len(frames))]

    manifest = {
        "mappingVersion": "1.4.0",
        "appliesTo": [os.path.splitext(os.path.basename(out_path))[0]],
        "sourceImage": {"w": sheet_w, "h": sheet_h},
        "frameRects": {
            fid: {"x": x, "y": y, "w": w, "h": h}
            for fid, (x, y, w, h) in zip(frame_ids, rects)
        },
        "frames": [
            {"id": fid, "row": i // cols + 1, "col": i % cols + 1, "key": fid}
            for i, fid in enumerate(frame_ids)
        ],
        "animations": {
            anim_name: {"frames": frame_ids, "fps": fps, "loop": loop}
        },
    }

    # Add depth information if provided
    if depth_image:
        manifest["depthImage"] = depth_image

    if depth_frame_paths:
        # Depth frames use same layout as color frames
        if len(depth_frame_paths) != len(frame_paths):
            raise ValueError(
                f"Depth frame count ({len(depth_frame_paths)}) "
                f"must match color frame count ({len(frame_paths)})"
            )
        depth_frames = _load_frames(depth_frame_paths)
        depth_rects, (depth_w, depth_h), _ = _compute_frame_layout(
            depth_frames[0].size, len(depth_frames), columns, padding
        )
        manifest["depthFrameRects"] = {
            fid: {"x": x, "y": y, "w": w, "h": h}
            for fid, (x, y, w, h) in zip(frame_ids, depth_rects)
        }
        manifest["depthSourceImage"] = {"w": depth_w, "h": depth_h}

    # Add SHADED world-state hooks (optional; additive field)
    if world_states:
        manifest["worldStates"] = {
            ws_name: ws_ref.to_dict() for ws_name, ws_ref in world_states.items()
        }

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(manifest, f, indent=2)
    return out_path


def export_gif(
    frame_paths: list[str],
    out_path: str,
    fps: int = 12,
    loop: int = 0,
) -> str:
    """Export frames as animated GIF."""
    if not frame_paths:
        raise ValueError("No frames to export")

    frames = _load_frames(frame_paths)
    duration_ms = max(1, int(1000 / fps))

    # Convert RGBA → RGBA palettized (GIF requires palette mode)
    gif_frames = []
    for frame in frames:
        # FASTOCTREE supports RGBA; convert transparency to P+A for GIF
        quantized = frame.quantize(colors=256, method=Image.Quantize.FASTOCTREE)
        gif_frames.append(quantized)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    gif_frames[0].save(
        out_path,
        format="GIF",
        save_all=True,
        append_images=gif_frames[1:],
        duration=duration_ms,
        loop=loop,
        disposal=2,
    )
    return out_path


def export_frames_with_metadata(
    frame_paths: list[str],
    out_dir: str,
    fps: int = 12,
    animation_name: str = "animation",
) -> str:
    """Copy frames and write a JSON metadata file."""
    import shutil

    os.makedirs(out_dir, exist_ok=True)
    meta_frames = []
    for i, src in enumerate(frame_paths):
        dst_name = f"frame_{i:04d}.png"
        dst = os.path.join(out_dir, dst_name)
        shutil.copy2(src, dst)
        meta_frames.append({
            "index": i,
            "file": dst_name,
            "duration_ms": int(1000 / fps),
        })

    meta = {
        "animation": animation_name,
        "frame_count": len(frame_paths),
        "fps": fps,
        "frames": meta_frames,
    }
    meta_path = os.path.join(out_dir, "animation.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    return meta_path


def export_sprite_sheet_from_images(
    frames: list,
    out_path: str,
    columns: Optional[int] = None,
    padding: int = 0,
) -> str:
    """Pack PIL.Image frames into a sprite sheet without temp files."""
    if not frames:
        raise ValueError("No frames to export")
    frames = [f.convert("RGBA") for f in frames]
    fw, fh = frames[0].size
    count = len(frames)
    cols = columns or count
    rows = (count + cols - 1) // cols
    sheet_w = cols * (fw + padding) - padding
    sheet_h = rows * (fh + padding) - padding
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))
    for i, frame in enumerate(frames):
        col = i % cols
        row = i // cols
        sheet.paste(frame, (col * (fw + padding), row * (fh + padding)))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    sheet.save(out_path, "PNG")
    return out_path


def export_gif_from_images(
    frames: list,
    out_path: str,
    fps: int = 12,
    loop: int = 0,
) -> str:
    """Export PIL.Image frames as animated GIF without temp files."""
    if not frames:
        raise ValueError("No frames to export")
    frames = [f.convert("RGBA") for f in frames]
    duration_ms = max(1, int(1000 / fps))
    gif_frames = [f.quantize(colors=256, method=Image.Quantize.FASTOCTREE) for f in frames]
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    gif_frames[0].save(
        out_path,
        format="GIF",
        save_all=True,
        append_images=gif_frames[1:],
        duration=duration_ms,
        loop=loop,
        disposal=2,
    )
    return out_path


class Exporter:
    def __init__(self, frame_paths: list[str], fps: int = 12, depth_frame_paths: Optional[list[str]] = None):
        self.frame_paths = frame_paths
        self.depth_frame_paths = depth_frame_paths or []
        self.fps = fps

    def to_sprite_sheet(self, out_path: str, columns: Optional[int] = None, padding: int = 0) -> str:
        return export_sprite_sheet(self.frame_paths, out_path, columns, padding)

    def to_depth_sheet(self, out_path: str, columns: Optional[int] = None, padding: int = 0) -> str:
        """Export depth frames as grayscale sprite sheet."""
        if not self.depth_frame_paths:
            raise ValueError("No depth frames available")
        return export_depth_sheet(self.depth_frame_paths, out_path, columns, padding)

    def to_gif(self, out_path: str, loop: int = 0) -> str:
        return export_gif(self.frame_paths, out_path, self.fps, loop)

    def to_frames_json(self, out_dir: str, animation_name: str = "animation") -> str:
        return export_frames_with_metadata(self.frame_paths, out_dir, self.fps, animation_name)

    def to_manifest(
        self,
        out_path: str,
        animation_name: str = "animation",
        loop: bool = True,
        depth_image: Optional[str] = None,
        world_states: Optional[Dict[str, WorldStateRef]] = None,
    ) -> str:
        """Export manifest with optional depth frame and world-state metadata."""
        return export_manifest(
            self.frame_paths,
            out_path,
            animation_name,
            self.fps,
            loop,
            depth_image=depth_image,
            depth_frame_paths=self.depth_frame_paths if self.depth_frame_paths else None,
            world_states=world_states,
        )
