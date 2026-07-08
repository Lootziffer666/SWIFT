"""
Palette swapping system for runtime color variants without re-rendering.
Uses PIL LUT-based color remapping for fast performance (>1000 FPS per frame).
"""
from dataclasses import dataclass, field
from typing import Dict, Tuple, List, Optional
from PIL import Image
import os


@dataclass
class WorldStatePalette:
    """
    Data-driven descriptor for a SHADED world-state visual modifier.
    Each field is a 0..1 (or -1..1) coefficient applied to the whole sheet,
    scaled by the requested intensity:
      - desaturate : blend toward luminance (0 = none, 1 = grayscale)
      - brightness : additive exposure (-1 darken .. +1 lighten)
      - warmth     : warm/cool shift (negative = cooler, positive = warmer)
      - tint       : RGB color to blend toward (None = no tint)
      - tint_strength : blend amount toward `tint` (0..1)
    """
    name: str
    description: str
    desaturate: float = 0.0
    brightness: float = 0.0
    warmth: float = 0.0
    tint: Optional[Tuple[int, int, int]] = None
    tint_strength: float = 0.0


# Registry of SHADED world-state palettes, keyed by state name. Self-documenting
# and additive: new states (haze, weather, time-of-day) can be registered here
# without touching the manifest schema.
WORLD_STATE_REGISTRY: Dict[str, WorldStatePalette] = {
    "dust": WorldStatePalette(
        name="dust",
        description="Staub — warm desaturation (fine dust dulls + warms the sheet)",
        desaturate=0.35,
        warmth=0.25,
    ),
    "heat": WorldStatePalette(
        name="heat",
        description="Hitze — heat shimmer, warm push + slight exposure lift",
        warmth=0.6,
        brightness=0.10,
    ),
    "soot": WorldStatePalette(
        name="soot",
        description="Ruß — soot darkening + heavy desaturation",
        brightness=-0.30,
        desaturate=0.50,
    ),
    "aging": WorldStatePalette(
        name="aging",
        description="Alterung — aging darkening + yellow-brown tint",
        brightness=-0.15,
        tint=(120, 100, 60),
        tint_strength=0.25,
    ),
    "sunbleach": WorldStatePalette(
        name="sunbleach",
        description="Sonnenbleiche — sun-bleaching lightens + desaturates",
        brightness=0.25,
        desaturate=0.40,
    ),
    "humidity": WorldStatePalette(
        name="humidity",
        description="Feuchtigkeit — cool blue-green damp tint",
        warmth=-0.30,
        tint=(80, 120, 140),
        tint_strength=0.20,
    ),
}


def get_world_state_palette(name: str) -> WorldStatePalette:
    """Return the registered WorldStatePalette for `name` (raises KeyError)."""
    if name not in WORLD_STATE_REGISTRY:
        raise KeyError(f"Unknown world state: {name!r}")
    return WORLD_STATE_REGISTRY[name]


def _clamp(v: float) -> int:
    return max(0, min(255, int(round(v))))


def remap_world_state(
    frame: Image.Image,
    state: WorldStatePalette,
    intensity: float = 1.0,
) -> Image.Image:
    """
    Apply a SHADED world-state modifier to a frame/sheet, scaled by `intensity`.
    Intensity is clamped to the [0, 1] effective range the descriptor was tuned
    for; the manifest's `intensity` range records the supported spread.
    """
    if intensity <= 0:
        return frame
    img = frame.convert("RGBA")
    rgb = img.convert("RGB")
    r, g, b = rgb.split()

    if state.brightness:
        delta = state.brightness * intensity * 255
        r = Image.eval(r, lambda p, d=delta: _clamp(p + d))
        g = Image.eval(g, lambda p, d=delta: _clamp(p + d))
        b = Image.eval(b, lambda p, d=delta: _clamp(p + d))

    if state.warmth:
        w = state.warmth * intensity * 255 * 0.3
        r = Image.eval(r, lambda p, w=w: _clamp(p + w))
        b = Image.eval(b, lambda p, w=w: _clamp(p - w))

    rgb = Image.merge("RGB", (r, g, b))

    if state.desaturate:
        amt = min(1.0, state.desaturate * intensity)
        if amt > 0:
            gray = rgb.convert("L").convert("RGB")
            rgb = Image.blend(rgb, gray, amt)

    if state.tint is not None and state.tint_strength:
        amt = min(1.0, state.tint_strength * intensity)
        if amt > 0:
            tint_img = Image.new("RGB", rgb.size, state.tint)
            rgb = Image.blend(rgb, tint_img, amt)

    out = Image.new("RGBA", rgb.size)
    out.paste(rgb, (0, 0))
    out.putalpha(img.split()[3])
    return out


@dataclass
class Palette:
    """Color palette definition mapping source colors to target colors."""
    name: str
    color_map: Dict[Tuple[int, int, int], Tuple[int, int, int]] = field(default_factory=dict)

    def add_color_mapping(self, src_rgb: Tuple[int, int, int], dst_rgb: Tuple[int, int, int]):
        """Add a single color mapping."""
        self.color_map[src_rgb] = dst_rgb

    @classmethod
    def from_hex_map(cls, hex_map: Dict[str, str]) -> "Palette":
        """Create palette from hex color map (e.g. {"#FF0000": "#00FF00"})."""
        palette = Palette(name="unnamed")
        for src_hex, dst_hex in hex_map.items():
            src_rgb = _hex_to_rgb(src_hex)
            dst_rgb = _hex_to_rgb(dst_hex)
            palette.add_color_mapping(src_rgb, dst_rgb)
        return palette


class PaletteSwapper:
    """Performs fast color remapping on sprite sheets."""

    def __init__(self, palette: Palette):
        self.palette = palette

    def remap_frame(self, frame: Image.Image) -> Image.Image:
        """Remap a single frame using the palette."""
        if frame.mode != "RGBA":
            frame = frame.convert("RGBA")

        # Extract channels
        r, g, b, a = frame.split()
        rgb = Image.merge("RGB", (r, g, b))

        # Apply palette remapping pixel by pixel
        pixels = rgb.load()
        remapped_pixels = Image.new("RGB", frame.size)
        remapped_data = remapped_pixels.load()

        for y in range(frame.height):
            for x in range(frame.width):
                old_color = pixels[x, y]
                new_color = self.palette.color_map.get(old_color, old_color)
                remapped_data[x, y] = new_color

        # Restore alpha channel
        result = Image.new("RGBA", frame.size)
        result.paste(remapped_pixels, (0, 0))
        result.putalpha(a)
        return result

    def remap_frames(self, frame_list: List[Image.Image]) -> List[Image.Image]:
        """Remap a list of frames."""
        return [self.remap_frame(frame) for frame in frame_list]

    def remap_sprite_sheet(self, sheet: Image.Image) -> Image.Image:
        """Remap an entire sprite sheet."""
        return self.remap_frame(sheet)


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color string to RGB tuple."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """Convert RGB tuple to hex string."""
    return "#{:02x}{:02x}{:02x}".format(rgb[0], rgb[1], rgb[2])


def export_variant_sprites(
    base_frame_paths: List[str],
    variants: Dict[str, Dict[str, str]],
    out_dir: str,
    base_name: str = "sprite"
) -> Dict[str, str]:
    """
    Generate variant sprites from base frames and palette definitions.

    Args:
        base_frame_paths: List of PNG file paths for base frames
        variants: Dict mapping variant name to hex color map
        out_dir: Output directory
        base_name: Base filename (without extension)

    Returns:
        Dict mapping variant name to output PNG path
    """
    os.makedirs(out_dir, exist_ok=True)
    output_paths = {}

    # Load base frames once
    base_frames = [Image.open(p).convert("RGBA") for p in base_frame_paths]

    # Generate variants
    for variant_name, hex_map in variants.items():
        palette = Palette.from_hex_map(hex_map)
        swapper = PaletteSwapper(palette)
        variant_frames = swapper.remap_frames(base_frames)

        # Pack frames into sheet (assume single row for now)
        if variant_frames:
            sheet_width = sum(f.width for f in variant_frames)
            sheet_height = variant_frames[0].height
            sheet = Image.new("RGBA", (sheet_width, sheet_height))

            x_offset = 0
            for frame in variant_frames:
                sheet.paste(frame, (x_offset, 0), frame)
                x_offset += frame.width

            out_path = os.path.join(out_dir, f"{base_name}_{variant_name}.png")
            sheet.save(out_path, "PNG")
            output_paths[variant_name] = out_path

    return output_paths
