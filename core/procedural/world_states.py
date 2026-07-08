"""
Real SHADED world-state procedural transforms.

Each world state (dust, aging, heat, soot, sunbleach, humidity, haze) is a
genuine visual transform that operates on a rendered actor sprite sheet and
produces a variant that genuinely reflects that environmental condition, so
SHADED can pick the right variant per world state without re-rendering.

All transforms have the signature:
    (PIL.Image, intensity: float in [0,1]) -> PIL.Image

They are fully deterministic: any noise/dither is seeded from the image content
plus the state name, so identical inputs always produce identical outputs and
tests reproduce.
"""
import zlib
from typing import Callable, Dict, List, Optional

import numpy as np
from PIL import Image, ImageFilter


# ── helpers ──────────────────────────────────────────────────────────────────

def _to_float(img: Image.Image):
    img = img.convert("RGBA")
    arr = np.asarray(img, dtype=np.float32)
    rgb = arr[..., :3]
    alpha = arr[..., 3]
    return rgb, alpha


def _from_float(rgb: np.ndarray, alpha: np.ndarray) -> Image.Image:
    rgb = np.clip(rgb, 0.0, 255.0).astype(np.uint8)
    out = np.empty((*rgb.shape[:2], 4), dtype=np.uint8)
    out[..., :3] = rgb
    out[..., 3] = alpha.astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _rng(rgb: np.ndarray, salt: str):
    """Deterministic RNG seeded from image content + state name."""
    payload = rgb.tobytes()
    h = zlib.crc32(payload) & 0xFFFFFFFF
    h ^= (zlib.crc32(salt.encode("utf-8")) & 0xFFFFFFFF)
    return np.random.default_rng(h)


def _noise_field(shape, scale: float, rng, smooth: bool = True) -> np.ndarray:
    """Low-frequency noise field resized up to `shape` (h, w), normalized 0..1."""
    h, w = shape
    sh = max(1, int(h / scale))
    sw = max(1, int(w / scale))
    n = rng.standard_normal((sh, sw)).astype(np.float32)
    lo, hi = float(n.min()), float(n.max())
    n = (n - lo) / (hi - lo + 1e-6)
    nimg = Image.fromarray((n * 255).astype(np.uint8)).resize(
        (w, h), Image.BICUBIC if smooth else Image.NEAREST
    )
    return np.asarray(nimg, dtype=np.float32) / 255.0


def _luminance(rgb: np.ndarray) -> np.ndarray:
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def _rgb_to_hsv(rgb: np.ndarray):
    r = rgb[..., 0] / 255.0
    g = rgb[..., 1] / 255.0
    b = rgb[..., 2] / 255.0
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    d = mx - mn + 1e-9
    hue = np.zeros_like(mx)
    sat = np.where(mx > 0, d / (mx + 1e-9), 0.0)
    return hue, sat, mx


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _identity(img: Image.Image, intensity: float) -> Image.Image:
    return img.convert("RGBA")


# ── transforms ───────────────────────────────────────────────────────────────

def dust_transform(img: Image.Image, intensity: float) -> Image.Image:
    """Warm desaturation + fine grain/noise overlay + slight haze (lower contrast)."""
    if intensity <= 0:
        return img.convert("RGBA")
    rgb, alpha = _to_float(img)
    k = _clamp01(intensity)
    rng = _rng(rgb, "dust")

    # Warm desaturation: blend toward luminance, then push warm.
    lum = _luminance(rgb)
    gray = np.stack([lum, lum, lum], axis=-1)
    desat = 0.35 * k
    rgb = rgb * (1 - desat) + gray * desat
    rgb[..., 0] += 0.18 * k * 255 * 0.3   # warm (R up)
    rgb[..., 2] -= 0.15 * k * 255 * 0.3   # warm (B down)

    # Fine grain overlay.
    grain = rng.standard_normal(rgb.shape[:2]).astype(np.float32)
    grain = grain - grain.min()
    grain = (grain / (grain.max() + 1e-6)) * 2 - 1  # -1..1
    rgb += grain[..., None] * (12.0 * k)

    # Slight haze: blend toward a warm pale wash (lowers contrast).
    wash = np.array([200, 190, 170], dtype=np.float32)
    rgb = rgb * (1 - 0.15 * k) + wash * (0.15 * k)

    return _from_float(rgb, alpha)


def aging_transform(img: Image.Image, intensity: float) -> Image.Image:
    """Darkening + low-frequency mottling/scuff + edge wear."""
    if intensity <= 0:
        return img.convert("RGBA")
    rgb, alpha = _to_float(img)
    k = _clamp01(intensity)
    rng = _rng(rgb, "aging")
    h, w = rgb.shape[:2]

    # Overall darkening.
    rgb *= (1 - 0.25 * k)

    # Low-frequency mottling/scuff: darken patches + lighten others.
    mottle = _noise_field((h, w), max(8, min(h, w) / 6), rng)
    rgb += (mottle - 0.5)[..., None] * (40.0 * k)

    # Edge wear: darken along strong luminance gradients.
    lum = _luminance(rgb)
    gy, gx = np.gradient(lum)
    edge = np.sqrt(gx ** 2 + gy ** 2)
    edge = edge / (edge.max() + 1e-6)
    rgb *= (1 - 0.5 * k * edge[..., None])

    return _from_float(rgb, alpha)


def heat_transform(img: Image.Image, intensity: float) -> Image.Image:
    """Subtle vertical shimmer/displacement + warm tint + slight blur halo."""
    if intensity <= 0:
        return img.convert("RGBA")
    rgb, alpha = _to_float(img)
    k = _clamp01(intensity)
    h, w = rgb.shape[:2]

    # Warm tint.
    rgb[..., 0] += 0.30 * k * 255 * 0.4
    rgb[..., 2] -= 0.25 * k * 255 * 0.4

    # Vertical shimmer: per-row horizontal displacement (sinusoidal).
    amp = max(0.0, 2.0 * k)
    freq = 2 * np.pi * 6.0 / max(1, h)
    out = rgb.copy()
    for y in range(h):
        s = int(round(amp * np.sin(y * freq)))
        if s != 0:
            out[y] = np.roll(rgb[y], s, axis=0)
    rgb = out

    # Slight blur halo.
    img_rgb = _from_float(rgb, alpha).convert("RGB")
    blurred = img_rgb.filter(ImageFilter.GaussianBlur(radius=max(0.0, 1.0 * k)))
    blur_arr = np.asarray(blurred, dtype=np.float32)
    rgb = rgb * (1 - 0.25 * k) + blur_arr * (0.25 * k)

    return _from_float(rgb, alpha)


def soot_transform(img: Image.Image, intensity: float) -> Image.Image:
    """Multiply darkening + smudge noise + cool/warm patches."""
    if intensity <= 0:
        return img.convert("RGBA")
    rgb, alpha = _to_float(img)
    k = _clamp01(intensity)
    rng = _rng(rgb, "soot")
    h, w = rgb.shape[:2]

    # Multiply darkening.
    rgb *= (1 - 0.35 * k)

    # Smudge noise: mid-frequency modulation (soot streaks).
    smudge = _noise_field((h, w), max(6, min(h, w) / 4), rng)
    rgb *= (1 - 0.25 * k * smudge[..., None])

    # Cool/warm patches: tint some areas warm, others cool.
    patch = _noise_field((h, w), max(10, min(h, w) / 8), rng)
    warm = patch > 0.5
    cool = ~warm
    rgb[..., 0] += warm.astype(np.float32) * (15.0 * k)
    rgb[..., 2] += cool.astype(np.float32) * (15.0 * k)

    return _from_float(rgb, alpha)


def sunbleach_transform(img: Image.Image, intensity: float) -> Image.Image:
    """Lift blacks + desaturate highlights + pale wash."""
    if intensity <= 0:
        return img.convert("RGBA")
    rgb, alpha = _to_float(img)
    k = _clamp01(intensity)

    # Lift blacks / wash toward white.
    lift = 0.30 * k
    rgb = rgb * (1 - lift) + 255.0 * lift

    # Desaturate highlights (only the bright part).
    hue, sat, val = _rgb_to_hsv(rgb)
    hi = np.clip((val - 0.5) * 2.0, 0.0, 1.0)
    desat = 0.4 * k * hi
    lum = _luminance(rgb)
    gray = np.stack([lum, lum, lum], axis=-1)
    rgb = rgb * (1 - desat[..., None]) + gray * desat[..., None]

    # Pale wash.
    wash = np.array([235, 232, 225], dtype=np.float32)
    rgb = rgb * (1 - 0.12 * k) + wash * (0.12 * k)

    return _from_float(rgb, alpha)


def humidity_transform(img: Image.Image, intensity: float) -> Image.Image:
    """Cool tint + low-contrast fog + moisture sheen."""
    if intensity <= 0:
        return img.convert("RGBA")
    rgb, alpha = _to_float(img)
    k = _clamp01(intensity)
    rng = _rng(rgb, "humidity")
    h, w = rgb.shape[:2]

    # Cool tint.
    rgb[..., 2] += 0.20 * k * 255 * 0.4
    rgb[..., 0] -= 0.12 * k * 255 * 0.4

    # Low-contrast fog: blend toward cool gray.
    fog = np.array([150, 165, 175], dtype=np.float32)
    rgb = rgb * (1 - 0.25 * k) + fog * (0.25 * k)

    # Moisture sheen: soft bright specular overlay (smooth noise).
    sheen = _noise_field((h, w), max(8, min(h, w) / 6), rng)
    sheen = np.clip((sheen - 0.6) * 3.0, 0.0, 1.0)
    rgb += sheen[..., None] * (35.0 * k)

    return _from_float(rgb, alpha)


def haze_transform(img: Image.Image, intensity: float) -> Image.Image:
    """Global low-contrast veiling + desaturation."""
    if intensity <= 0:
        return img.convert("RGBA")
    rgb, alpha = _to_float(img)
    k = _clamp01(intensity)

    # Desaturate toward luminance.
    lum = _luminance(rgb)
    gray = np.stack([lum, lum, lum], axis=-1)
    rgb = rgb * (1 - 0.3 * k) + gray * (0.3 * k)

    # Low-contrast veiling toward a flat light gray.
    veil = np.array([185, 185, 185], dtype=np.float32)
    rgb = rgb * (1 - 0.25 * k) + veil * (0.25 * k)

    return _from_float(rgb, alpha)


# ── registry ──────────────────────────────────────────────────────────────────

WORLD_STATE_TRANSFORMS: Dict[str, Callable[[Image.Image, float], Image.Image]] = {
    "dust": dust_transform,
    "aging": aging_transform,
    "heat": heat_transform,
    "soot": soot_transform,
    "sunbleach": sunbleach_transform,
    "humidity": humidity_transform,
    "haze": haze_transform,
}


def list_world_states() -> List[str]:
    """Return the registered SHADED world-state transform names."""
    return sorted(WORLD_STATE_TRANSFORMS.keys())


def get_world_state_transform(name: str) -> Callable[[Image.Image, float], Image.Image]:
    """Return the transform callable for `name` (raises KeyError)."""
    if name not in WORLD_STATE_TRANSFORMS:
        raise KeyError(f"Unknown world state: {name!r}")
    return WORLD_STATE_TRANSFORMS[name]


def apply_world_state(img: Image.Image, state_name: str, intensity: float = 0.5) -> Image.Image:
    """Apply the registered world-state transform `state_name` at `intensity`."""
    return get_world_state_transform(state_name)(img, intensity)
