"""
Tests for core/procedural/palette_swap.py color remapping.
"""
import pytest
from PIL import Image
import tempfile
import os
from core.procedural.palette_swap import Palette, PaletteSwapper, _hex_to_rgb, _rgb_to_hex


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
