"""One surface law, several evaluators — for the 2D and the 3D path alike.

Weathering is not a filter over an image. Dirt collects where there is more matter
around a point than a flat plate has; paint wears through where there is less. That
single question — *how enclosed is this point* — is the whole law, and it is the same
question in a sprite and in a mesh.

What differs is only how it is answered:

    sprite (2D)   height field from the render's depth pass
    mesh   (3D)   coarse voxel occupancy of the geometry
    SDF    (3D)   the distance field itself, sampled around the point

All three fill the same :class:`SurfaceField`, and the weathering pass never learns
which one it got. That is deliberate: a law with two independent evaluators is a law,
a law with one is an implementation detail. ``tests/test_surface.py`` holds the two
against each other for exactly this reason.

Lineage
-------
The height-vs-blurred-height reading (:func:`from_depth`) follows Fallout: Ember's
texture foundry. The voxel occupancy (:func:`occupancy`, :func:`bake_occupancy`)
follows The Long Silence's hull bake. The calibration floor in :func:`calibrate` is
that project's hard-won correction, reproduced here because the failure it prevents
is not obvious and costs a full rebuild to discover.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

import numpy as np

# --------------------------------------------------------------------------- conventions

DEPTH_IS_DISTANCE = True
"""SWIFT's depth pass stores *distance from the camera*.

``scripts/blender_render.py:271`` maps Blender's ``Z`` output through 0.1..100 into
0..255, so a **brighter pixel is farther away**. Height is therefore the negation of
the pass, and :func:`from_depth` applies that inversion once, here, by name.

Reading this backwards is silent and total: cavity and edge swap, so grime lands on
the ridges and the wear sits in the creases. Nothing crashes and every test that only
checks "something changed" still passes.
"""

CALIBRATION_FLOOR = 0.13
"""Minimum half-span the calibration ramp is allowed to have.

See :func:`calibrate`. The number is the one The Long Silence settled on and it is
expressed in units of "fraction of the shell occupied", which both evaluators
normalise into.
"""

_PCT_FLAT_HI = 0.62
_PCT_FLAT_LO = 0.42
_PCT_DEEP = 0.97
_PCT_LIP = 0.03
_EDGE_GAMMA = 2.3


def smoothstep(x: np.ndarray) -> np.ndarray:
    """Hermite ease on an already-clamped 0..1 array."""
    return x * x * (3.0 - 2.0 * x)


@dataclass(frozen=True)
class SurfaceField:
    """What the weathering pass is allowed to know about a surface.

    Every array carries the same shape, which is the *consumer's* shape: pixels for a
    sheet, vertices for a mesh. Values are 0..1.
    """

    cavity: np.ndarray
    """Recessed — a crevice, a corner, a throat. Dirt collects here."""

    edge: np.ndarray
    """Exposed — a lip, a rim, a boss. Paint wears through here."""

    slope: np.ndarray
    """Upward-facing, 0..1. Dust settles here rather than on a vertical face."""

    @property
    def shape(self) -> tuple:
        return self.cavity.shape

    @classmethod
    def flat(cls, shape: tuple) -> "SurfaceField":
        """A surface that tells us nothing.

        The honest answer when no depth pass exists — ``core/video_to_sprite/`` never
        has one. Cavity and edge are zero so the recipes contribute nothing through
        those channels rather than guessing from luminance, which is the very mistake
        this module exists to correct. Slope is 0.5: neither up nor down.
        """
        return cls(
            cavity=np.zeros(shape, dtype=np.float32),
            edge=np.zeros(shape, dtype=np.float32),
            slope=np.full(shape, 0.5, dtype=np.float32),
        )

    def is_flat(self) -> bool:
        return not (self.cavity.any() or self.edge.any())


# --------------------------------------------------------------------------- calibration


def calibrate(
    enclosure: np.ndarray,
    mask: Optional[np.ndarray] = None,
    floor: float = CALIBRATION_FLOOR,
) -> tuple[np.ndarray, np.ndarray]:
    """Turn a raw enclosure measure into (cavity, edge), both 0..1.

    Thresholds come from the distribution, so a 400 m derelict and an 84 m survey boat
    both put "flat plate" at zero — and so does a 64 px sprite. But percentiles *alone*
    are wrong, and this is the trap worth naming:

        A landing leg is nothing but struts. Its enclosure values all sit within a few
        per cent of each other. Stretch that spread to 0..1 and the whole leg comes out
        painted as one exposed edge.

    So the ramp is never allowed to be narrower than ``floor``. A uniform object comes
    out uniform, which is the correct answer. The curves are deliberately steep: wear
    belongs on a couple of per cent of a surface, not a third of it.
    """
    flat = enclosure[mask] if mask is not None else enclosure.ravel()
    if flat.size == 0:
        z = np.zeros(enclosure.shape, dtype=np.float32)
        return z, z.copy()

    order = np.sort(flat.astype(np.float32))

    def q(t: float) -> float:
        return float(order[min(order.size - 1, max(0, int(round(t * (order.size - 1)))))])

    flat_hi, flat_lo = q(_PCT_FLAT_HI), q(_PCT_FLAT_LO)
    deep = max(flat_hi + floor, q(_PCT_DEEP))
    lip = min(flat_lo - floor, q(_PCT_LIP))

    e = enclosure.astype(np.float32)
    cavity = smoothstep(np.clip((e - flat_hi) / (deep - flat_hi), 0.0, 1.0))
    edge = np.power(np.clip((flat_lo - e) / (flat_lo - lip), 0.0, 1.0), _EDGE_GAMMA)

    if mask is not None:
        cavity = np.where(mask, cavity, 0.0).astype(np.float32)
        edge = np.where(mask, edge, 0.0).astype(np.float32)
    return cavity.astype(np.float32), edge.astype(np.float32)


# --------------------------------------------------------------------------- 2D: depth


def _masked_blur(values: np.ndarray, mask: np.ndarray, radius: float) -> np.ndarray:
    """Gaussian blur that does not bleed the background in.

    Normalised convolution: blur the masked signal and the mask itself, then divide.
    Without this the silhouette of a sprite reads as one continuous crevice, because
    every edge pixel is averaged against empty background.
    """
    from scipy.ndimage import gaussian_filter

    m = mask.astype(np.float32)
    num = gaussian_filter(values.astype(np.float32) * m, radius, mode="nearest")
    den = gaussian_filter(m, radius, mode="nearest")
    return np.where(den > 1e-6, num / np.maximum(den, 1e-6), values).astype(np.float32)


def from_depth(
    depth: np.ndarray,
    alpha: Optional[np.ndarray] = None,
    normal: Optional[np.ndarray] = None,
    radius: float = 2.5,
) -> SurfaceField:
    """Evaluate the law on a rendered depth pass. The 2D path.

    ``depth`` is the raw pass as stored, 0..255 or 0..1; ``alpha`` marks the sprite
    against the background; ``normal`` is the optional normal pass, RGB in 0..255.

    The pass is renormalised **over the masked region only** before anything else.
    SWIFT's depth covers 0.1..100 scene units in 8 bits, so a character two units tall
    occupies about five code values out of 255. Cavity and edge are local differences;
    at five levels of contrast there is nothing to measure. Stretching the sprite's own
    range back over the full scale recovers it. Where the object genuinely is flat the
    stretch amplifies only quantisation noise — and :func:`calibrate`'s floor is what
    stops that noise from being reported as relief.
    """
    d = np.asarray(depth, dtype=np.float32)
    if d.ndim == 3:
        d = d[..., 0]

    mask = (
        np.asarray(alpha) > 0
        if alpha is not None
        else np.ones(d.shape, dtype=bool)
    )
    if not mask.any():
        return SurfaceField.flat(d.shape)

    inside = d[mask]
    lo, hi = float(inside.min()), float(inside.max())
    d = (d - lo) / (hi - lo) if hi - lo > 1e-6 else np.zeros_like(d)

    # Distance grows away from the camera; height grows toward it.
    height = -d if DEPTH_IS_DISTANCE else d

    local = _masked_blur(height, mask, radius)
    relief = height - local

    # Enclosure is the inverse of protrusion: recessed points are enclosed.
    cavity, edge = calibrate(-relief, mask)

    if normal is not None:
        n = np.asarray(normal, dtype=np.float32)
        up = (n[..., 1] / 255.0) * 2.0 - 1.0 if n.max() > 1.5 else n[..., 1] * 2.0 - 1.0
        slope = np.clip(up, 0.0, 1.0).astype(np.float32)
    else:
        # Fall back to the depth gradient: a surface tilting toward the top of the
        # frame catches dust. Coarse, but better than assuming everything is level.
        gy = np.gradient(_masked_blur(height, mask, max(1.0, radius)), axis=0)
        span = float(np.abs(gy[mask]).max()) if mask.any() else 0.0
        slope = (
            np.clip(0.5 - gy / (2.0 * span), 0.0, 1.0).astype(np.float32)
            if span > 1e-6
            else np.full(d.shape, 0.5, dtype=np.float32)
        )

    return SurfaceField(cavity=cavity, edge=edge, slope=np.where(mask, slope, 0.5).astype(np.float32))


# --------------------------------------------------------------------------- 3D: occupancy

_DIRS = np.array(
    [
        (x / np.sqrt(x * x + y * y + z * z), y / np.sqrt(x * x + y * y + z * z), z / np.sqrt(x * x + y * y + z * z))
        for x in (-1, 0, 1)
        for y in (-1, 0, 1)
        for z in (-1, 0, 1)
        if (x, y, z) != (0, 0, 0)
    ],
    dtype=np.float32,
)
"""The 26 face, edge and corner neighbours of a cube, normalised."""

_SHELL_RADII = (1.7, 3.4)
_SHELL_WEIGHTS = (0.62, 0.38)


class OccupancyGrid:
    """Coarse voxel occupancy of a mesh. One question: is there matter at this point."""

    def __init__(self, origin: np.ndarray, cell: float, data: np.ndarray):
        self.origin = origin
        self.cell = cell
        self.data = data

    def sample(self, points: np.ndarray) -> np.ndarray:
        idx = np.floor((points - self.origin) / self.cell).astype(np.int64)
        n = np.array(self.data.shape, dtype=np.int64)
        ok = np.all((idx >= 0) & (idx < n), axis=-1)
        out = np.zeros(points.shape[:-1], dtype=np.float32)
        safe = np.clip(idx, 0, n - 1)
        vals = self.data[safe[..., 0], safe[..., 1], safe[..., 2]]
        out[ok] = vals[ok]
        return out


def occupancy(vertices: np.ndarray, faces: np.ndarray, cell: float = 0.85) -> OccupancyGrid:
    """Rasterise a mesh into a coarse voxel grid of **solid** matter.

    Better than one sample per voxel per triangle, which for a character-sized mesh is
    tens of thousands of samples — a bake-time cost of tens of milliseconds and nothing
    per frame.

    The interior is filled, and that is a deliberate departure from the hull bake this
    is ported from. Rasterising triangles alone marks *surface presence*, not matter.
    On a spaceship — plates, struts, thin-walled pressure vessels — the two coincide
    closely enough. On a solid body they do not: at a fingertip the surface wraps
    around, so most directions hit it and the point reads as deeply enclosed. Exactly
    backwards, and it puts grime on every extremity.

    Filling the interior makes this evaluator answer the same question the SDF one does
    — how much of the neighbourhood is solid — which is what lets the two be held
    against each other in ``tests/test_surface.py``. That cross-check is what caught
    the discrepancy in the first place.

    An open or non-manifold mesh has no interior to fill; the fill then does nothing
    and the measure degrades to surface presence, which is the old behaviour.
    """
    v = np.asarray(vertices, dtype=np.float32)
    f = np.asarray(faces, dtype=np.int64)

    pad = cell * 5.0
    origin = v.min(axis=0) - pad
    extent = (v.max(axis=0) + pad) - origin
    dims = np.clip(np.ceil(extent / cell).astype(int), 2, 200)
    data = np.zeros(tuple(dims), dtype=np.float32)

    tri = v[f]  # (n, 3, 3)
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    longest = np.maximum(
        np.linalg.norm(b - a, axis=1),
        np.maximum(np.linalg.norm(c - a, axis=1), np.linalg.norm(c - b, axis=1)),
    )

    # Subdivision is decided per triangle, not once for the whole mesh. A single cap
    # for everything either starves the large triangles — leaving gaps that let the
    # interior fill leak straight out — or drowns the small ones in samples. The total
    # work stays proportional to surface area over cell area either way.
    steps = np.clip(np.ceil(longest / cell * 1.4), 1, 64).astype(int)

    for s in np.unique(steps):
        sel = steps == s
        a_s, b_s, c_s = a[sel], b[sel], c[sel]
        bary = np.array(
            [(u / s, w / s) for u in range(s + 1) for w in range(s - u + 1)],
            dtype=np.float32,
        )
        wu = bary[:, 0][:, None, None]
        wv = bary[:, 1][:, None, None]
        pts = a_s * (1.0 - wu - wv) + b_s * wu + c_s * wv
        idx = np.floor((pts.reshape(-1, 3) - origin) / cell).astype(np.int64)
        idx = np.clip(idx, 0, dims - 1)
        data[idx[:, 0], idx[:, 1], idx[:, 2]] = 1.0

    from scipy.ndimage import binary_fill_holes

    filled = binary_fill_holes(data > 0.5)
    if filled is not None:
        data = filled.astype(np.float32)
    return OccupancyGrid(origin, cell, data)


def bake_occupancy(
    points: np.ndarray, grid: OccupancyGrid, radius: Optional[float] = None
) -> np.ndarray:
    """How enclosed each point is, 0..1, from two shells of 26 directions.

    The near shell finds a lip, the far one finds a pocket.

    ``radius`` is the physical size of the neighbourhood being asked about — how wide a
    crevice has to be to count as one — in world units. It defaults to the grid's cell
    size, which is what the hull bake this is ported from does, but the two are separate
    choices and conflating them is a trap: the cell is a *numerical* parameter and
    refining it should sharpen the answer, while the radius is a *physical* one and
    changing it asks a different question. Tie them together and refining the grid
    silently shrinks the neighbourhood, so the measure drifts instead of converging.
    Pass ``radius`` explicitly whenever grids of different resolution have to agree.
    """
    p = np.asarray(points, dtype=np.float32)
    r_world = grid.cell if radius is None else float(radius)
    total = 0.0
    acc = np.zeros(p.shape[0], dtype=np.float32)
    for r, w in zip(_SHELL_RADII, _SHELL_WEIGHTS):
        offsets = _DIRS * (r_world * r)
        for off in offsets:
            acc += w * grid.sample(p + off)
            total += w
    return acc / max(total, 1e-6)


def from_mesh(
    vertices: np.ndarray,
    faces: np.ndarray,
    normals: Optional[np.ndarray] = None,
    cell: float = 0.85,
    radius: Optional[float] = None,
    up: Sequence[float] = (0.0, 1.0, 0.0),
) -> SurfaceField:
    """Evaluate the law on a triangle mesh. The 3D path.

    Returns fields over *vertices*, which is where a renderer wants them: as a vertex
    attribute they interpolate for free and cost nothing per frame.

    ``cell`` is grid resolution, ``radius`` the neighbourhood size — see
    :func:`bake_occupancy` for why they are separate.
    """
    v = np.asarray(vertices, dtype=np.float32)
    grid = occupancy(v, faces, cell)
    cavity, edge = calibrate(bake_occupancy(v, grid, radius))

    if normals is not None:
        slope = np.clip(np.asarray(normals, dtype=np.float32) @ np.asarray(up, dtype=np.float32), 0.0, 1.0)
    else:
        slope = np.full(v.shape[0], 0.5, dtype=np.float32)
    return SurfaceField(cavity=cavity, edge=edge, slope=slope.astype(np.float32))


# --------------------------------------------------------------------------- 3D: SDF


def from_sdf(
    distance: Callable[[np.ndarray], np.ndarray],
    points: np.ndarray,
    normals: Optional[np.ndarray] = None,
    radius: float = 0.85,
    up: Sequence[float] = (0.0, 1.0, 0.0),
) -> SurfaceField:
    """Evaluate the law on a signed distance field. The analytic 3D path.

    The Long Silence voxelises *because* it holds triangle meshes and has no other way
    to ask what surrounds a point. An SDF answers directly: sample it on the same two
    shells and count how much of the neighbourhood lies inside the solid. Same law, same
    shells, same calibration — no grid, no rasterisation, no quantisation.

    ``distance`` takes an (n, 3) array and returns n signed distances, negative inside.
    """
    p = np.asarray(points, dtype=np.float32)
    total = 0.0
    acc = np.zeros(p.shape[0], dtype=np.float32)
    for r, w in zip(_SHELL_RADII, _SHELL_WEIGHTS):
        for off in _DIRS * (radius * r):
            acc += w * (np.asarray(distance(p + off), dtype=np.float32) < 0.0)
            total += w
    cavity, edge = calibrate(acc / max(total, 1e-6))

    if normals is not None:
        slope = np.clip(np.asarray(normals, dtype=np.float32) @ np.asarray(up, dtype=np.float32), 0.0, 1.0)
    else:
        slope = np.full(p.shape[0], 0.5, dtype=np.float32)
    return SurfaceField(cavity=cavity, edge=edge, slope=slope.astype(np.float32))


# --------------------------------------------------------------------------- noise


def macro_field(shape: tuple, rng: np.random.Generator, scale: float = 6.0) -> np.ndarray:
    """Low-frequency value drift, 0..1, against the flatness of a uniform wash.

    The micro octave stops at the target's own raster — finer than one texel is dither,
    not detail, and in pixel art it reads as mush.
    """
    from PIL import Image

    h, w = shape[:2]
    sh, sw = max(1, int(h / scale)), max(1, int(w / scale))
    n = rng.standard_normal((sh, sw)).astype(np.float32)
    lo, hi = float(n.min()), float(n.max())
    n = (n - lo) / (hi - lo + 1e-6)
    img = Image.fromarray((n * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
    return np.asarray(img, dtype=np.float32) / 255.0
