"""Headless-Renderer: Knochen und Boxen als PNG.

Bewusst haesslich. Der Zweck ist nicht Darstellung, sondern der Nachweis, dass das
Format **ohne Engine** sichtbar und pruefbar ist. Wer Clips nur in PlayCanvas
betrachten kann, hat keine engine-agnostische Pipeline, sondern eine mit einem
bequemen Betrachter.

Zeichnet die gebakenen Boxen, nicht die autorisierten -- damit zeigt das Bild, was die
Simulation wirklich sieht, und ein Bake-Fehler wird sichtbar statt nur messbar.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from . import fixed, fk
from .glb import Clip
from .rig import Rig

BG = (250, 250, 250)
GRID = (228, 228, 232)
BONE = (45, 45, 52)
JOINT = (215, 60, 60)
HIT = (220, 40, 40)
HURT = (50, 110, 220)
GROUND = (170, 170, 178)
LABEL = (90, 90, 96)

_AXIS = {"x": 0, "y": 1, "z": 2}


def _axis(spec: str) -> tuple[int, float]:
    """Zerlegt eine Achsenangabe wie ``"x"`` oder ``"-z"`` in Index und Vorzeichen.

    Das Vorzeichen wird gebraucht, weil die Blickrichtung des Rigs -Z ist: eine
    Seitenansicht, die nach vorn gerichtete Bewegung nach rechts zeichnet, projiziert
    also ``-z``.
    """
    spec = spec.strip().lower()
    sign = -1.0 if spec.startswith("-") else 1.0
    return _AXIS[spec.lstrip("+-")], sign


def render_frame(
    rig: Rig,
    clip: Clip,
    frame: int,
    baked: dict | None = None,
    size: tuple[int, int] = (420, 520),
    axes: tuple[str, str] = ("x", "y"),
    scale: float | None = None,
) -> Image.Image:
    """Rendert einen Frame orthographisch."""
    w, h = size
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)

    pose = fk.solve(rig, clip, frame, include_root_translation=True)
    (ai, asign), (bi, bsign) = _axis(axes[0]), _axis(axes[1])

    if scale is None:
        ys = [p.position[bi] for p in pose.values()]
        span = max(max(ys) - min(ys), 0.5)
        scale = (h * 0.72) / span

    cx = w * 0.5
    base = h * 0.88  # y = 0 liegt hier

    def to_px(p) -> tuple[float, float]:
        return (cx + p[ai] * asign * scale, base - p[bi] * bsign * scale)

    for gy in range(0, h, 40):
        d.line([(0, gy), (w, gy)], fill=GRID)
    for gx in range(0, w, 40):
        d.line([(gx, 0), (gx, h)], fill=GRID)
    d.line([(0, base), (w, base)], fill=GROUND, width=2)

    if baked is not None and frame < len(baked["frames"]):
        bf = baked["frames"][frame]
        for kind, colour in (("hurt", HURT), ("hit", HIT)):
            for box in bf.get(kind, []):
                lo = [fixed.to_float(c) for c in box["min"]]
                hi = [fixed.to_float(c) for c in box["max"]]
                # Der Bake setzt die Wurzel in den Ursprung; zum Zeichnen kommt die
                # visuelle Root-Motion wieder dazu, damit Boxen und Skelett
                # uebereinanderliegen.
                off = clip.root_at(frame)
                x0, y0 = to_px((lo[0] + off[0], lo[1] + off[1], lo[2] + off[2]))
                x1, y1 = to_px((hi[0] + off[0], hi[1] + off[1], hi[2] + off[2]))
                d.rectangle(
                    [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)],
                    outline=colour,
                    width=2,
                )

    for _name, start, end in fk.segments(rig, pose):
        d.line([to_px(start), to_px(end)], fill=BONE, width=4)

    for bone in rig:
        x, y = to_px(pose[bone.name].position)
        r = 3.5
        d.ellipse([x - r, y - r, x + r, y + r], fill=JOINT)

    com = fk.center_of_mass(rig, pose)
    cxp, cyp = to_px(com)
    d.line([(cxp - 6, cyp), (cxp + 6, cyp)], fill=(30, 150, 90), width=2)
    d.line([(cxp, cyp - 6), (cxp, cyp + 6)], fill=(30, 150, 90), width=2)

    d.text((8, 8), f"{clip.name}  frame {frame}/{clip.frame_count - 1}", fill=LABEL)
    d.text((8, 22), f"rig {rig.id}   view {axes[0]}/{axes[1]}", fill=LABEL)
    return img


def render_sequence(
    rig: Rig,
    clip: Clip,
    out_dir: str | Path,
    baked: dict | None = None,
    contact_sheet: bool = True,
    axes: tuple[str, str] = ("x", "y"),
    tag: str = "",
) -> list[Path]:
    """Rendert alle Frames einzeln und optional als Kontaktbogen."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    images: list[Image.Image] = []
    for frame in range(clip.frame_count):
        img = render_frame(rig, clip, frame, baked=baked, axes=axes)
        p = out / f"{clip.name}{tag}_{frame:03d}.png"
        img.save(p)
        images.append(img)
        paths.append(p)

    if contact_sheet and images:
        w, h = images[0].size
        sheet = Image.new("RGB", (w * len(images), h), BG)
        for i, im in enumerate(images):
            sheet.paste(im, (i * w, 0))
        p = out / f"{clip.name}{tag}_sheet.png"
        sheet.save(p)
        paths.append(p)

    return paths
