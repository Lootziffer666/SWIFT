"""
Deterministic pixel-art post-processing for SWIFT's video-to-sprite pipeline.

The module intentionally keeps the AI-facing parts out of the runtime path: it
implements the local, engine-friendly parts described in spritepipeline.md —
smart crop, grid/scale detection, majority-vote downsampling and palette locks.
"""
import math
import os
from collections import Counter
from dataclasses import dataclass
from functools import reduce
from typing import Optional

import numpy as np
from PIL import Image


@dataclass
class PixelizeConfig:
    target_width: int = 64
    target_height: int = 64
    palette_colors: int = 16
    lock_palette: bool = False              # if True, use anchor_palette
    anchor_palette: Optional[list] = None   # list of (R,G,B) tuples
    true_pixel: bool = True                 # run SWIFT's deterministic cleanup path
    smart_crop: bool = False                # tight transparent crop before resizing
    crop_padding: int = 0                   # transparent padding after smart crop
    auto_scale: bool = False                # detect source pixel grid before resize
    source_pixel_size: Optional[int] = None # explicit grid size override
    defringe: bool = False                  # snap semi-transparent edges to hard alpha
    alpha_threshold: int = 8                # alpha <= threshold becomes transparent


def _build_palette_image(colors: list) -> Image.Image:
    """Build a dummy palette image for quantize() with locked colors."""
    pal_img = Image.new("P", (1, 1))
    flat = []
    for r, g, b in colors[:256]:
        flat += [r, g, b]
    flat += [0] * (768 - len(flat))
    pal_img.putpalette(flat)
    return pal_img


def smart_crop_image(src: Image.Image, padding: int = 0, alpha_threshold: int = 0) -> Image.Image:
    """Crop transparent borders tightly while preserving transparent padding."""
    rgba = src.convert("RGBA")
    alpha = np.array(rgba.getchannel("A"))
    ys, xs = np.where(alpha > alpha_threshold)
    if len(xs) == 0 or len(ys) == 0:
        return rgba
    left = max(0, int(xs.min()) - padding)
    top = max(0, int(ys.min()) - padding)
    right = min(rgba.width, int(xs.max()) + 1 + padding)
    bottom = min(rgba.height, int(ys.max()) + 1 + padding)
    return rgba.crop((left, top, right, bottom))


def _run_lengths_1d(values: np.ndarray) -> list[int]:
    if values.size == 0:
        return []
    changes = np.flatnonzero(np.any(values[1:] != values[:-1], axis=1)) + 1
    cuts = np.concatenate(([0], changes, [len(values)]))
    return [int(b - a) for a, b in zip(cuts[:-1], cuts[1:]) if b > a]


def detect_pixel_scale(src: Image.Image, max_scale: int = 16) -> int:
    """Estimate an existing logical pixel size with a runs-based GCD heuristic."""
    rgba = src.convert("RGBA")
    arr = np.array(rgba)
    opaque = arr[:, :, 3] > 0
    lengths: list[int] = []

    for y in range(arr.shape[0]):
        row = arr[y]
        row_mask = opaque[y]
        if row_mask.any():
            lengths.extend(_run_lengths_1d(row[row_mask]))
    for x in range(arr.shape[1]):
        col = arr[:, x, :]
        col_mask = opaque[:, x]
        if col_mask.any():
            lengths.extend(_run_lengths_1d(col[col_mask]))

    candidates = [l for l in lengths if 1 < l <= max_scale * 4]
    if not candidates:
        return 1
    gcd = reduce(math.gcd, candidates)
    return max(1, min(max_scale, gcd))


def qvote_downsample(src: Image.Image, scale: int) -> Image.Image:
    """Downsample by choosing the most frequent RGBA tuple in each S×S block."""
    if scale <= 1:
        return src.convert("RGBA")
    rgba = src.convert("RGBA")
    w, h = rgba.size
    out_w = max(1, w // scale)
    out_h = max(1, h // scale)
    cropped = rgba.crop((0, 0, out_w * scale, out_h * scale))
    arr = np.array(cropped)
    out = np.zeros((out_h, out_w, 4), dtype=np.uint8)
    for oy in range(out_h):
        for ox in range(out_w):
            block = arr[oy * scale:(oy + 1) * scale, ox * scale:(ox + 1) * scale].reshape(-1, 4)
            opaque = block[block[:, 3] > 0]
            sample = opaque if len(opaque) else block
            out[oy, ox] = Counter(map(tuple, sample.tolist())).most_common(1)[0][0]
    return Image.fromarray(out, "RGBA")


def defringe_alpha(src: Image.Image, alpha_threshold: int = 8) -> Image.Image:
    """Remove faint alpha halos and snap visible pixels to fully opaque."""
    arr = np.array(src.convert("RGBA"))
    low = arr[:, :, 3] <= alpha_threshold
    high = arr[:, :, 3] > alpha_threshold
    arr[low] = (0, 0, 0, 0)
    arr[:, :, 3][high] = 255
    return Image.fromarray(arr, "RGBA")


def _quantize_rgba(small: Image.Image, cfg: PixelizeConfig) -> Image.Image:
    if cfg.lock_palette and cfg.anchor_palette:
        pal_img = _build_palette_image(cfg.anchor_palette)
        quantized = small.convert("RGB").quantize(palette=pal_img, dither=0)
    else:
        quantized = small.convert("RGB").quantize(colors=cfg.palette_colors, method=Image.Quantize.MEDIANCUT, dither=0)
    result = quantized.convert("RGBA")
    result.putalpha(small.split()[3])
    return result


def pixelize(src: Image.Image, config: Optional[PixelizeConfig] = None) -> Image.Image:
    cfg = config or PixelizeConfig()
    working = src.convert("RGBA")

    if cfg.smart_crop:
        working = smart_crop_image(working, cfg.crop_padding, cfg.alpha_threshold)

    if cfg.source_pixel_size or cfg.auto_scale:
        scale = cfg.source_pixel_size or detect_pixel_scale(working)
        working = qvote_downsample(working, scale)

    resample = Image.Resampling.NEAREST if cfg.true_pixel else Image.Resampling.BICUBIC
    small = working.resize((cfg.target_width, cfg.target_height), resample=resample).convert("RGBA")

    if cfg.defringe:
        small = defringe_alpha(small, cfg.alpha_threshold)

    return _quantize_rgba(small, cfg)


def extract_palette(img: Image.Image, max_colors: int = 16) -> list:
    """Extract dominant colors from an image as (R,G,B) tuples."""
    rgb = img.convert("RGB")
    quantized = rgb.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT, dither=0)
    palette = quantized.getpalette() or []
    usable = min(max_colors * 3, len(palette))
    return [(palette[i], palette[i+1], palette[i+2]) for i in range(0, usable, 3)]


def pixelize_sequence(frame_paths: list[str], out_dir: str, config: Optional[PixelizeConfig] = None) -> list[str]:
    """Pixelize frames with an optional first-frame anchor palette for consistency."""
    cfg = config or PixelizeConfig()
    os.makedirs(out_dir, exist_ok=True)
    out_paths = []

    for i, path in enumerate(frame_paths):
        img = Image.open(path).convert("RGBA")
        if cfg.lock_palette and cfg.anchor_palette is None and i == 0:
            cfg.anchor_palette = extract_palette(img, cfg.palette_colors)
        result = pixelize(img, cfg)
        out_path = os.path.join(out_dir, f"pixel_{i:04d}.png")
        result.save(out_path, "PNG")
        out_paths.append(out_path)

    return out_paths
