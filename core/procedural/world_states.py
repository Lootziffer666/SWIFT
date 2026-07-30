"""SHADED world-state transforms — one finishing pass, seven recipes.

Each world state (dust, aging, heat, soot, sunbleach, humidity, haze) turns a rendered
actor sheet into a variant that reflects that environmental condition, so SHADED can
pick the right variant per world state without re-rendering.

All transforms keep the signature ``(PIL.Image, intensity: float in [0,1]) -> PIL.Image``
and are fully deterministic: noise is seeded from the image content plus the state name,
so identical inputs always produce identical outputs.

Where the relief comes from
---------------------------
Weathering is a property of a *surface*, not of an image. Dirt collects in crevices;
paint wears through on ridges. Neither is visible in RGB — a painted stripe and a real
groove look the same to a colour gradient, which is why the earlier version of this
module produced "edge wear" that followed the artwork instead of the geometry.

So the relief comes from :mod:`core.procedural.surface`, which reads it from the render's
depth pass (2D) or the geometry itself (3D). Pass ``depth``/``normal`` and the grime and
wear channels engage; omit them and those channels contribute nothing. They are never
guessed from luminance.

Recipes, not code
-----------------
A state is a :class:`SurfaceRecipe` — a set of numbers — and one shared pass applies it.
Adding a state is adding data. This mirrors what ``spar/rigs/*.json`` did for skeletons:
the interesting variation belongs in a table, not in a seventh near-copy of the same
function.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import numpy as np
from PIL import Image, ImageFilter

from .surface import SurfaceField, from_depth, macro_field

# ── helpers ──────────────────────────────────────────────────────────────────


def _to_float(img: Image.Image):
    img = img.convert("RGBA")
    arr = np.asarray(img, dtype=np.float32)
    return arr[..., :3], arr[..., 3]


def _from_float(rgb: np.ndarray, alpha: np.ndarray) -> Image.Image:
    rgb = np.clip(rgb, 0.0, 255.0).astype(np.uint8)
    out = np.empty((*rgb.shape[:2], 4), dtype=np.uint8)
    out[..., :3] = rgb
    out[..., 3] = alpha.astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _rng(rgb: np.ndarray, salt: str, seed: Optional[int] = None):
    """Deterministic RNG seeded from image content + state name.

    Content-addressed on purpose: the same sheet always weathers the same way, and two
    different sheets differ. ``apply_world_state`` runs once over a whole sprite sheet
    rather than per frame (see ``main.py``), so every frame of an animation draws from
    one field and the grain does not crawl between them. Pass ``seed`` to pin the noise
    to a sheet identity instead of its pixels.
    """
    if seed is not None:
        return np.random.default_rng(seed & 0xFFFFFFFF)
    h = zlib.crc32(rgb.tobytes()) & 0xFFFFFFFF
    h ^= zlib.crc32(salt.encode("utf-8")) & 0xFFFFFFFF
    return np.random.default_rng(h)


def _luminance(rgb: np.ndarray) -> np.ndarray:
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def _rgb_to_hsv(rgb: np.ndarray):
    r, g, b = rgb[..., 0] / 255.0, rgb[..., 1] / 255.0, rgb[..., 2] / 255.0
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    d = mx - mn + 1e-9
    return np.zeros_like(mx), np.where(mx > 0, d / (mx + 1e-9), 0.0), mx


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _noise_field(shape, scale: float, rng, smooth: bool = True) -> np.ndarray:
    """Low-frequency noise field resized up to `shape` (h, w), normalized 0..1."""
    h, w = shape
    sh, sw = max(1, int(h / scale)), max(1, int(w / scale))
    n = rng.standard_normal((sh, sw)).astype(np.float32)
    lo, hi = float(n.min()), float(n.max())
    n = (n - lo) / (hi - lo + 1e-6)
    nimg = Image.fromarray((n * 255).astype(np.uint8)).resize(
        (w, h), Image.BICUBIC if smooth else Image.NEAREST
    )
    return np.asarray(nimg, dtype=np.float32) / 255.0


# ── the recipe ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SurfaceRecipe:
    """What distinguishes one world state from another.

    Every field is scaled by ``intensity`` at apply time, so 0 is always the identity.
    ``grime``, ``wear`` and ``dust`` need a :class:`SurfaceField`; without one they are
    inert rather than approximated.
    """

    tone: tuple = (128.0, 128.0, 128.0)
    """Colour the surface washes toward."""
    wash: float = 0.0
    """How far toward ``tone``."""
    grime: float = 0.0
    """Darkening and warming in cavities. Needs relief."""
    wear: float = 0.0
    """Lightening and desaturation on exposed edges. Needs relief."""
    dust: float = 0.0
    """Settling toward ``tone`` on upward-facing surfaces. Needs relief."""
    macro: float = 0.0
    """Low-frequency value drift, against the flatness of a uniform wash."""
    darken: float = 0.0
    """Overall multiply."""
    desat: float = 0.0
    """Blend toward luminance."""
    warm: float = 0.0
    """Positive pushes red up and blue down; negative cools."""
    lift: float = 0.0
    """Raise blacks toward white."""
    grain: float = 0.0
    """Fine per-pixel noise, in 0..255 units."""
    highlight_desat: float = 0.0
    """Desaturate only the bright end (sun-bleached paint keeps its shadows)."""
    sheen: float = 0.0
    """Soft bright specular patches (wet surfaces)."""


WORLD_STATE_RECIPES: Dict[str, SurfaceRecipe] = {
    "dust": SurfaceRecipe(
        tone=(200.0, 190.0, 170.0), wash=0.15, desat=0.35, warm=0.055,
        grain=12.0, dust=0.30, grime=0.20, macro=0.10,
    ),
    "aging": SurfaceRecipe(
        tone=(120.0, 108.0, 92.0), wash=0.04, darken=0.25, macro=0.30,
        grime=0.45, wear=0.40,
    ),
    "heat": SurfaceRecipe(
        tone=(220.0, 150.0, 110.0), wash=0.05, warm=0.135, wear=0.15,
    ),
    "soot": SurfaceRecipe(
        tone=(40.0, 38.0, 38.0), wash=0.06, darken=0.35, macro=0.25,
        grime=0.55, wear=0.10,
    ),
    "sunbleach": SurfaceRecipe(
        tone=(235.0, 232.0, 225.0), wash=0.12, lift=0.30,
        highlight_desat=0.40, wear=0.30,
    ),
    "humidity": SurfaceRecipe(
        tone=(150.0, 165.0, 175.0), wash=0.25, warm=-0.08, sheen=0.35,
        grime=0.25,
    ),
    "haze": SurfaceRecipe(
        tone=(185.0, 185.0, 185.0), wash=0.25, desat=0.30,
    ),
}

MAX_SATURATION = 0.72
"""Ceiling on mean saturation, enforced mechanically.

A weathered world is a desaturated one. Left to itself a warm tint plus a wash can
push a variant *more* colourful than the source, which reads as a filter rather than
as an environment — and across several generators feeding SHADED, the drift compounds
until nothing looks like it shares a world.
"""


# ── the shared pass ──────────────────────────────────────────────────────────


def _apply_recipe(
    img: Image.Image,
    recipe: SurfaceRecipe,
    intensity: float,
    salt: str,
    depth: Optional[np.ndarray] = None,
    normal: Optional[np.ndarray] = None,
    seed: Optional[int] = None,
) -> Image.Image:
    if intensity <= 0:
        return img.convert("RGBA")

    rgb, alpha = _to_float(img)
    k = _clamp01(intensity)
    rng = _rng(rgb, salt, seed)
    h, w = rgb.shape[:2]

    field = (
        from_depth(depth, alpha=alpha, normal=normal)
        if depth is not None
        else SurfaceField.flat((h, w))
    )

    # Low-frequency breakup first, so everything after sits on an uneven base.
    if recipe.macro:
        rgb += (macro_field((h, w), rng, scale=max(6.0, min(h, w) / 6)) - 0.5)[..., None] * (
            80.0 * recipe.macro * k
        )

    # Grime in the cavities: darker and a touch warmer.
    if recipe.grime and field.cavity.any():
        g = field.cavity * (recipe.grime * k)
        rgb *= (1.0 - 0.55 * g)[..., None]
        rgb[..., 0] += g * 10.0
        rgb[..., 2] -= g * 6.0

    # Wear on the exposed edges: lighter and desaturated, paint rubbed back to primer.
    if recipe.wear and field.edge.any():
        e = field.edge * (recipe.wear * k)
        lum = _luminance(rgb)
        rgb = rgb * (1.0 - e[..., None]) + np.stack([lum] * 3, -1) * e[..., None]
        rgb += (e * 26.0)[..., None]

    # Dust settles on what faces up.
    if recipe.dust:
        settle = (field.slope * recipe.dust * k)[..., None]
        rgb = rgb * (1.0 - settle) + np.asarray(recipe.tone, dtype=np.float32) * settle

    if recipe.darken:
        rgb *= 1.0 - recipe.darken * k

    if recipe.desat:
        lum = _luminance(rgb)
        d = recipe.desat * k
        rgb = rgb * (1.0 - d) + np.stack([lum] * 3, -1) * d

    if recipe.highlight_desat:
        _, _, val = _rgb_to_hsv(rgb)
        hi = np.clip((val - 0.5) * 2.0, 0.0, 1.0) * (recipe.highlight_desat * k)
        lum = _luminance(rgb)
        rgb = rgb * (1.0 - hi[..., None]) + np.stack([lum] * 3, -1) * hi[..., None]

    if recipe.warm:
        rgb[..., 0] += recipe.warm * k * 255.0
        rgb[..., 2] -= recipe.warm * k * 255.0

    if recipe.lift:
        lift = recipe.lift * k
        rgb = rgb * (1.0 - lift) + 255.0 * lift

    if recipe.sheen:
        s = _noise_field((h, w), max(8.0, min(h, w) / 6), rng)
        rgb += np.clip((s - 0.6) * 3.0, 0.0, 1.0)[..., None] * (100.0 * recipe.sheen * k)

    if recipe.wash:
        wash = recipe.wash * k
        rgb = rgb * (1.0 - wash) + np.asarray(recipe.tone, dtype=np.float32) * wash

    if recipe.grain:
        g = rng.standard_normal((h, w)).astype(np.float32)
        g -= g.min()
        g = (g / (g.max() + 1e-6)) * 2.0 - 1.0
        rgb += g[..., None] * (recipe.grain * k)

    rgb = saturation_guard(rgb, MAX_SATURATION)
    return _from_float(rgb, alpha)


def saturation_guard(rgb: np.ndarray, limit: float = MAX_SATURATION) -> np.ndarray:
    """Pull the image back toward luminance until mean saturation is within ``limit``.

    Global rather than per-pixel: clamping individual pixels flattens the few
    deliberately vivid accents that carry a palette, while a global pull preserves their
    relationship to everything else.

    The blend factor is found by bisection rather than computed in closed form, because
    there is no closed form. Saturation is ``(max - min) / max``, and blending toward
    luminance lowers the *numerator and the denominator together* — pulling 22% of the
    way to grey takes saturation from 0.92 only to 0.84, not to 0.72. A one-shot
    ``1 - limit/mean`` looks right, silently undershoots, and leaves the ceiling
    unenforced.
    """
    rgb = np.clip(rgb, 0.0, 255.0)
    lum3 = np.stack([_luminance(rgb)] * 3, -1)

    # Bisect on a subsample; the relationship is monotone and a few thousand pixels
    # describe the mean well enough to place the blend factor.
    flat = rgb.reshape(-1, 3)
    probe = flat[:: max(1, flat.shape[0] // 4096)]
    probe_lum = np.stack([_luminance(probe)] * 3, -1)

    def mean_sat(t: float) -> float:
        blended = probe * (1.0 - t) + probe_lum * t
        _, s, _ = _rgb_to_hsv(blended)
        return float(s.mean())

    # Aim a hair below the ceiling: the result is written back as 8-bit, and rounding a
    # channel by one code value moves saturation by up to 1/255. Without the headroom
    # the guard lands exactly on the limit in float and lands just over it on disk.
    limit = max(0.0, limit - 0.005)

    if mean_sat(0.0) <= limit:
        return rgb

    lo, hi = 0.0, 1.0
    for _ in range(16):
        mid = 0.5 * (lo + hi)
        if mean_sat(mid) > limit:
            lo = mid
        else:
            hi = mid
    return rgb * (1.0 - hi) + lum3 * hi


# ── registry ─────────────────────────────────────────────────────────────────


def _bind(name: str) -> Callable[..., Image.Image]:
    recipe = WORLD_STATE_RECIPES[name]

    def transform(
        img: Image.Image,
        intensity: float,
        depth: Optional[np.ndarray] = None,
        normal: Optional[np.ndarray] = None,
        seed: Optional[int] = None,
    ) -> Image.Image:
        out = _apply_recipe(img, recipe, intensity, name, depth, normal, seed)
        return _HEAT_EXTRA(out, intensity) if name == "heat" else out

    transform.__name__ = f"{name}_transform"
    transform.__doc__ = f"Apply the {name!r} world state. Recipe: {recipe}"
    return transform


def _HEAT_EXTRA(img: Image.Image, intensity: float) -> Image.Image:
    """Heat shimmer — the one effect that is not a surface property.

    A row-wise horizontal displacement plus a blur halo describes the *air* between the
    camera and the actor, so it stays outside the shared pass rather than pretending to
    be weathering.
    """
    k = _clamp01(intensity)
    if k <= 0:
        return img
    rgb, alpha = _to_float(img)
    h = rgb.shape[0]

    amp = 2.0 * k
    freq = 2 * np.pi * 6.0 / max(1, h)
    out = rgb.copy()
    for y in range(h):
        s = int(round(amp * np.sin(y * freq)))
        if s:
            out[y] = np.roll(rgb[y], s, axis=0)
    rgb = out

    blurred = np.asarray(
        _from_float(rgb, alpha).convert("RGB").filter(ImageFilter.GaussianBlur(radius=1.0 * k)),
        dtype=np.float32,
    )
    return _from_float(rgb * (1.0 - 0.25 * k) + blurred * (0.25 * k), alpha)


dust_transform = _bind("dust")
aging_transform = _bind("aging")
heat_transform = _bind("heat")
soot_transform = _bind("soot")
sunbleach_transform = _bind("sunbleach")
humidity_transform = _bind("humidity")
haze_transform = _bind("haze")

WORLD_STATE_TRANSFORMS: Dict[str, Callable[..., Image.Image]] = {
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


def get_world_state_transform(name: str) -> Callable[..., Image.Image]:
    """Return the transform callable for `name` (raises KeyError)."""
    if name not in WORLD_STATE_TRANSFORMS:
        raise KeyError(f"Unknown world state: {name!r}")
    return WORLD_STATE_TRANSFORMS[name]


def apply_world_state(
    img: Image.Image,
    state_name: str,
    intensity: float = 0.5,
    depth: Optional[np.ndarray] = None,
    normal: Optional[np.ndarray] = None,
    seed: Optional[int] = None,
) -> Image.Image:
    """Apply the registered world-state transform `state_name` at `intensity`.

    ``depth`` and ``normal`` are the render's passes, same dimensions as ``img``. With
    them the grime and wear channels follow the geometry; without them those channels
    stay silent and the state is expressed through tone, wash and value alone.
    """
    return get_world_state_transform(state_name)(img, intensity, depth, normal, seed)
