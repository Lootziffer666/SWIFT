"""
Algorithmic pixel art conversion: downscale + palette quantization.
Used as the fast baseline before AI stylization.
"""
import os
from dataclasses import dataclass
from typing import Optional

from PIL import Image


@dataclass
class PixelizeConfig:
    target_width: int = 64
    target_height: int = 64
    palette_colors: int = 16
    lock_palette: bool = False          # if True, use anchor_palette
    anchor_palette: Optional[list] = None   # list of (R,G,B) tuples


def _build_palette_image(colors: list) -> Image.Image:
    """Build a dummy palette image for quantize() with locked colors."""
    pal_img = Image.new("P", (1, 1))
    flat = []
    for r, g, b in colors[:256]:
        flat += [r, g, b]
    flat += [0] * (768 - len(flat))
    pal_img.putpalette(flat)
    return pal_img


def pixelize(
    src: Image.Image,
    config: Optional[PixelizeConfig] = None,
) -> Image.Image:
    cfg = config or PixelizeConfig()

    # Downscale with nearest-neighbor to get blocky pixel art look
    small = src.resize(
        (cfg.target_width, cfg.target_height),
        resample=Image.NEAREST,
    ).convert("RGBA")

    if cfg.lock_palette and cfg.anchor_palette:
        pal_img = _build_palette_image(cfg.anchor_palette)
        rgb = small.convert("RGB")
        quantized = rgb.quantize(palette=pal_img, dither=0)
        result = quantized.convert("RGBA")
        # Re-apply original alpha channel
        alpha = small.split()[3]
        result.putalpha(alpha)
    else:
        rgb = small.convert("RGB")
        quantized = rgb.quantize(colors=cfg.palette_colors, method=Image.Quantize.MEDIANCUT)
        result = quantized.convert("RGBA")
        alpha = small.split()[3]
        result.putalpha(alpha)

    return result


def extract_palette(img: Image.Image, max_colors: int = 16) -> list:
    """Extract dominant colors from an image as (R,G,B) tuples."""
    rgb = img.convert("RGB")
    quantized = rgb.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette() or []
    usable = min(max_colors * 3, len(palette))
    return [(palette[i], palette[i+1], palette[i+2]) for i in range(0, usable, 3)]


def pixelize_sequence(
    frame_paths: list[str],
    out_dir: str,
    config: Optional[PixelizeConfig] = None,
) -> list[str]:
    """
    Pixelize a sequence of frames with consistent palette.
    First frame sets the anchor palette if lock_palette is True.
    """
    cfg = config or PixelizeConfig()
    os.makedirs(out_dir, exist_ok=True)
    out_paths = []

    for i, path in enumerate(frame_paths):
        img = Image.open(path).convert("RGBA")

        # Extract anchor palette from first frame
        if cfg.lock_palette and cfg.anchor_palette is None and i == 0:
            cfg.anchor_palette = extract_palette(img, cfg.palette_colors)

        result = pixelize(img, cfg)
        out_name = f"pixel_{i:04d}.png"
        out_path = os.path.join(out_dir, out_name)
        result.save(out_path, "PNG")
        out_paths.append(out_path)

    return out_paths
