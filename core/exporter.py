"""
Export rendered frames to sprite sheet PNG, animated GIF, or frames + JSON metadata.
"""
import os
import json
from pathlib import Path
from typing import Optional

from PIL import Image


def _load_frames(frame_paths: list[str]) -> list[Image.Image]:
    frames = []
    for p in frame_paths:
        img = Image.open(p).convert("RGBA")
        frames.append(img)
    return frames


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
    fw, fh = frames[0].size
    count = len(frames)
    cols = columns or count  # default: single row
    rows = (count + cols - 1) // cols

    sheet_w = cols * (fw + padding) - padding
    sheet_h = rows * (fh + padding) - padding
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))

    for i, frame in enumerate(frames):
        col = i % cols
        row = i // cols
        x = col * (fw + padding)
        y = row * (fh + padding)
        sheet.paste(frame, (x, y))

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    sheet.save(out_path, "PNG")
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


class Exporter:
    def __init__(self, frame_paths: list[str], fps: int = 12):
        self.frame_paths = frame_paths
        self.fps = fps

    def to_sprite_sheet(self, out_path: str, columns: Optional[int] = None, padding: int = 0) -> str:
        return export_sprite_sheet(self.frame_paths, out_path, columns, padding)

    def to_gif(self, out_path: str, loop: int = 0) -> str:
        return export_gif(self.frame_paths, out_path, self.fps, loop)

    def to_frames_json(self, out_dir: str, animation_name: str = "animation") -> str:
        return export_frames_with_metadata(self.frame_paths, out_dir, self.fps, animation_name)
