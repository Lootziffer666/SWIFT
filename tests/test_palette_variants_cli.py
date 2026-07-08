"""
Non-Blender tests for the ``--variants`` palette-swapping path.

These exercise the same helpers ``main.cmd_render`` uses
(``parse_palette_variant_spec`` / ``apply_palette_variants``) against a
synthetic base sheet, so the full runtime-variant pipeline is verified without
Blender. They also confirm the manifest ``variants`` list round-trips through
``SpriteSheetManifest`` and that PNG output is deterministic.
"""
import json
import os
import tempfile

import pytest
from PIL import Image

from main import (
    apply_palette_variants,
    parse_palette_variant_spec,
    parse_palette_variants_arg,
    _load_preset_palettes,
)
from core.sprite_sheet import SpriteSheetManifest


PRESET_SOURCES = {
    "#4169E1": (65, 105, 225),
    "#6495ED": (100, 149, 237),
    "#1E90FF": (30, 144, 255),
}


def _make_base_sheet(path):
    """Create a 64x64 sheet using the canonical preset source colors."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    px = img.load()
    for y in range(64):
        for x in range(64):
            src = list(PRESET_SOURCES.values())[(x // 22) % 3]
            px[x, y] = (src[0], src[1], src[2], 255)
    img.save(path, "PNG")
    return path


def _write_manifest(path):
    manifest = {
        "mappingVersion": "1.4.0",
        "sourceImage": {"w": 64, "h": 64},
        "frameRects": {"F01": {"x": 0, "y": 0, "w": 64, "h": 64}},
        "frames": [{"id": "F01", "key": "idle_01"}],
        "animations": {"idle": {"frames": ["F01"], "fps": 12, "loop": True}},
    }
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)


def _pixel_at(path, x=10, y=10):
    return Image.open(path).convert("RGBA").getpixel((x, y))[:3]


@pytest.fixture
def sheet_dir():
    with tempfile.TemporaryDirectory() as d:
        base = os.path.join(d, "hero.png")
        _make_base_sheet(base)
        manifest = os.path.join(d, "hero_manifest.json")
        _write_manifest(manifest)
        yield d, base, manifest


def test_preset_variant_spec_resolves():
    presets = _load_preset_palettes()
    name, pal = parse_palette_variant_spec("red", presets)
    assert name == "red"
    assert (65, 105, 225) in pal.color_map


def test_custom_hex_map_spec():
    name, pal = parse_palette_variant_spec("team_red=#4169E1:#FF6347")
    assert name == "team_red"
    assert pal.color_map[(65, 105, 225)] == (255, 99, 71)


def test_custom_hex_map_multiple():
    name, pal = parse_palette_variant_spec("x=#AABBCC:#112233;#DDEEFF:#445566")
    assert name == "x"
    assert pal.color_map[(0xAA, 0xBB, 0xCC)] == (0x11, 0x22, 0x33)
    assert pal.color_map[(0xDD, 0xEE, 0xFF)] == (0x44, 0x55, 0x66)


def test_unknown_preset_raises():
    presets = _load_preset_palettes()
    with pytest.raises(KeyError):
        parse_palette_variant_spec("not_a_preset", presets)


def test_invalid_custom_spec_raises():
    with pytest.raises(ValueError):
        parse_palette_variant_spec("bad=#4169E1")  # missing src:dst


def test_presets_produce_distinct_variant_pngs(sheet_dir):
    d, base, manifest = sheet_dir
    presets = _load_preset_palettes()
    specs = parse_palette_variants_arg("red,green", presets)

    results = apply_palette_variants(base, manifest, specs)

    assert {n for n, _ in results} == {"red", "green"}
    red_path = os.path.join(d, "hero_red.png")
    green_path = os.path.join(d, "hero_green.png")
    assert os.path.isfile(red_path)
    assert os.path.isfile(green_path)
    # Distinct variants must differ in pixel content.
    assert _pixel_at(red_path) != _pixel_at(green_path)
    # Each variant must actually change the source color.
    assert _pixel_at(red_path) != _pixel_at(base)


def test_manifest_variants_listed_and_roundtrips(sheet_dir):
    d, base, manifest = sheet_dir
    presets = _load_preset_palettes()
    specs = parse_palette_variants_arg("red,green,purple", presets)

    apply_palette_variants(base, manifest, specs)

    with open(manifest) as f:
        raw = json.load(f)
    assert raw["variants"] == [
        {"name": "red", "path": "hero_red.png"},
        {"name": "green", "path": "hero_green.png"},
        {"name": "purple", "path": "hero_purple.png"},
    ]

    # Reload via SpriteSheetManifest and confirm the list is preserved.
    m = SpriteSheetManifest.from_file(manifest)
    assert m.variants == raw["variants"]


def test_custom_hex_map_end_to_end(sheet_dir):
    d, base, manifest = sheet_dir
    specs = parse_palette_variants_arg("team_red=#4169E1:#FF6347", None)

    apply_palette_variants(base, manifest, specs)

    red_path = os.path.join(d, "hero_team_red.png")
    assert os.path.isfile(red_path)
    # The canonical source blue (65,105,225) must now be the custom target.
    assert _pixel_at(red_path) == (255, 99, 71)


def test_output_is_deterministic(sheet_dir):
    d, base, manifest = sheet_dir
    presets = _load_preset_palettes()
    specs = parse_palette_variants_arg("red,gold", presets)

    apply_palette_variants(base, manifest, specs)
    first = open(os.path.join(d, "hero_red.png"), "rb").read()

    # Re-run on a fresh base (same content) -> byte-identical PNG.
    base2 = os.path.join(d, "hero2.png")
    _make_base_sheet(base2)
    manifest2 = os.path.join(d, "hero2_manifest.json")
    _write_manifest(manifest2)
    apply_palette_variants(base2, manifest2, specs)
    second = open(os.path.join(d, "hero2_red.png"), "rb").read()

    assert first == second
