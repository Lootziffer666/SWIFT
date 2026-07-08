"""
Tests for core/procedural/palette_swap.py color remapping.
"""
import pytest
from PIL import Image
import tempfile
import os
from core.procedural.palette_swap import (
    Palette,
    PaletteSwapper,
    _hex_to_rgb,
    _rgb_to_hex,
    WORLD_STATE_REGISTRY,
    get_world_state_palette,
    remap_world_state,
)


class TestPaletteUtils:
    def test_hex_to_rgb(self):
        assert _hex_to_rgb("#FF0000") == (255, 0, 0)
        assert _hex_to_rgb("#00FF00") == (0, 255, 0)
        assert _hex_to_rgb("#0000FF") == (0, 0, 255)
        assert _hex_to_rgb("#FFFFFF") == (255, 255, 255)

    def test_rgb_to_hex(self):
        assert _rgb_to_hex((255, 0, 0)) == "#ff0000"
        assert _rgb_to_hex((0, 255, 0)) == "#00ff00"
        assert _rgb_to_hex((0, 0, 255)) == "#0000ff"


class TestPalette:
    def test_palette_add_mapping(self):
        pal = Palette(name="test")
        pal.add_color_mapping((255, 0, 0), (0, 255, 0))

        assert (255, 0, 0) in pal.color_map
        assert pal.color_map[(255, 0, 0)] == (0, 255, 0)

    def test_palette_from_hex_map(self):
        hex_map = {"#FF0000": "#00FF00", "#0000FF": "#FFFF00"}
        pal = Palette.from_hex_map(hex_map)

        assert (255, 0, 0) in pal.color_map
        assert pal.color_map[(255, 0, 0)] == (0, 255, 0)


class TestPaletteSwapper:
    def _create_test_image(self, width=64, height=64, color=(255, 0, 0)):
        """Create a simple test image with a single color."""
        img = Image.new("RGBA", (width, height), color + (255,))
        return img

    def test_remap_frame_basic(self):
        img = self._create_test_image(64, 64, (255, 0, 0))  # Red
        pal = Palette(name="test")
        pal.add_color_mapping((255, 0, 0), (0, 255, 0))  # Red → Green

        swapper = PaletteSwapper(pal)
        remapped = swapper.remap_frame(img)

        # Sample a pixel and check color changed
        pixel = remapped.getpixel((32, 32))
        assert pixel[:3] == (0, 255, 0), f"Expected green, got {pixel[:3]}"

    def test_remap_preserves_alpha(self):
        """Remapping should preserve alpha channel."""
        img = Image.new("RGBA", (64, 64), (255, 0, 0, 128))
        pal = Palette(name="test")
        pal.add_color_mapping((255, 0, 0), (0, 255, 0))

        swapper = PaletteSwapper(pal)
        remapped = swapper.remap_frame(img)

        pixel = remapped.getpixel((32, 32))
        assert pixel[3] == 128, "Alpha channel should be preserved"

    def test_remap_frame_list(self):
        """Remap multiple frames."""
        frames = [
            self._create_test_image(32, 32, (255, 0, 0)),  # Red
            self._create_test_image(32, 32, (255, 0, 0)),
        ]
        pal = Palette(name="test")
        pal.add_color_mapping((255, 0, 0), (0, 0, 255))  # Red → Blue

        swapper = PaletteSwapper(pal)
        remapped = swapper.remap_frames(frames)

        assert len(remapped) == 2
        for frame in remapped:
            pixel = frame.getpixel((16, 16))
            assert pixel[:3] == (0, 0, 255)

    def test_remap_sprite_sheet(self):
        """Remap an entire sprite sheet."""
        sheet = Image.new("RGBA", (128, 64))
        # Paint left half red, right half green
        red_pixels = sheet.load()
        for x in range(64):
            for y in range(64):
                red_pixels[x, y] = (255, 0, 0, 255)
        for x in range(64, 128):
            for y in range(64):
                red_pixels[x, y] = (0, 255, 0, 255)

        pal = Palette(name="test")
        pal.add_color_mapping((255, 0, 0), (0, 255, 255))  # Red → Cyan
        pal.add_color_mapping((0, 255, 0), (255, 0, 255))  # Green → Magenta

        swapper = PaletteSwapper(pal)
        remapped = swapper.remap_sprite_sheet(sheet)

        # Check left half is now cyan
        pixel = remapped.getpixel((32, 32))
        assert pixel[:3] == (0, 255, 255)
        # Check right half is now magenta
        pixel = remapped.getpixel((96, 32))
        assert pixel[:3] == (255, 0, 255)

    def test_unmapped_colors_unchanged(self):
        """Colors not in palette should remain unchanged."""
        img = Image.new("RGBA", (64, 64), (128, 128, 128, 255))  # Gray
        pal = Palette(name="test")
        pal.add_color_mapping((255, 0, 0), (0, 255, 0))

        swapper = PaletteSwapper(pal)
        remapped = swapper.remap_frame(img)

        pixel = remapped.getpixel((32, 32))
        # Gray should remain gray
        assert pixel[:3] == (128, 128, 128)


class TestWorldStatePalettes:
    def _create_test_image(self, width=64, height=64, color=(200, 50, 50)):
        """Create a simple saturated test image."""
        return Image.new("RGBA", (width, height), color + (255,))

    def test_registry_has_core_states(self):
        for state in ("dust", "heat", "soot", "aging", "sunbleach", "humidity"):
            assert state in WORLD_STATE_REGISTRY
            assert get_world_state_palette(state).name == state

    def test_unknown_state_raises(self):
        import pytest
        with pytest.raises(KeyError):
            get_world_state_palette("not-a-state")

    def _saturation(self, rgb):
        r, g, b = rgb
        mx, mn = max(r, g, b), min(r, g, b)
        if mx == 0:
            return 0.0
        return (mx - mn) / mx

    def test_dust_desaturates_and_warms(self):
        """Dust should reduce saturation vs. the original."""
        img = self._create_test_image(64, 64, (200, 60, 60))
        palette = get_world_state_palette("dust")
        remapped = remap_world_state(img, palette, intensity=1.0)

        orig_sat = self._saturation(img.getpixel((32, 32))[:3])
        new_sat = self._saturation(remapped.getpixel((32, 32))[:3])
        assert new_sat < orig_sat

    def test_soot_darkens(self):
        """Soot should reduce brightness."""
        img = self._create_test_image(64, 64, (180, 180, 180))
        palette = get_world_state_palette("soot")
        remapped = remap_world_state(img, palette, intensity=1.0)

        orig = sum(img.getpixel((32, 32))[:3])
        new = sum(remapped.getpixel((32, 32))[:3])
        assert new < orig

    def test_zero_intensity_is_identity(self):
        img = self._create_test_image(32, 32, (100, 150, 200))
        palette = get_world_state_palette("heat")
        remapped = remap_world_state(img, palette, intensity=0.0)
        assert remapped.getpixel((16, 16))[:3] == (100, 150, 200)

    def test_world_state_preserves_alpha(self):
        img = Image.new("RGBA", (64, 64), (200, 50, 50, 128))
        palette = get_world_state_palette("aging")
        remapped = remap_world_state(img, palette, intensity=1.0)
        assert remapped.getpixel((32, 32))[3] == 128

    def test_world_state_variant_is_png_size(self):
        from core.procedural.palette_swap import remap_world_state
        base = self._create_test_image(128, 64, (200, 80, 80))
        remapped = remap_world_state(base, get_world_state_palette("humidity"), 1.0)
        assert remapped.size == (128, 64)
