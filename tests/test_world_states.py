"""
Tests for core/procedural/world_states.py real SHADED world-state transforms.
"""
import pytest
from PIL import Image
import numpy as np

from core.procedural.world_states import (
    apply_world_state,
    list_world_states,
    get_world_state_transform,
    dust_transform,
    aging_transform,
    heat_transform,
    soot_transform,
    sunbleach_transform,
    humidity_transform,
    haze_transform,
)


def _saturation(rgb):
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    sat = np.where(mx > 0, (mx - mn) / (mx + 1e-9), 0.0)
    return float(sat.mean())


def _brightness(rgb):
    return float(rgb[..., :3].mean())


def _mean_channel(rgb, idx):
    return float(rgb[..., idx].mean())


class TestWorldStateRegistry:
    def test_registry_has_core_states(self):
        for state in ("dust", "aging", "heat", "soot", "sunbleach", "humidity", "haze"):
            assert state in list_world_states()
            assert get_world_state_transform(state) is not None

    def test_unknown_state_raises(self):
        with pytest.raises(KeyError):
            get_world_state_transform("not-a-state")
        with pytest.raises(KeyError):
            apply_world_state(Image.new("RGBA", (8, 8)), "not-a-state")

    def test_identity_at_zero_intensity(self):
        img = Image.new("RGBA", (32, 32), (100, 150, 200, 255))
        for state in list_world_states():
            out = apply_world_state(img, state, 0.0)
            assert out.getpixel((16, 16))[:3] == (100, 150, 200)


class TestWorldStateDeterminism:
    def _img(self, color=(200, 80, 80)):
        return Image.new("RGBA", (64, 64), color + (255,))

    def test_deterministic_per_state(self):
        for state in list_world_states():
            img = self._img()
            a = np.asarray(apply_world_state(img, state, 0.7))
            b = np.asarray(apply_world_state(img, state, 0.7))
            assert np.array_equal(a, b), f"{state} not deterministic"

    def test_different_inputs_differ(self):
        warm = apply_world_state(Image.new("RGBA", (64, 64), (220, 60, 60, 255)), "dust", 0.7)
        cool = apply_world_state(Image.new("RGBA", (64, 64), (60, 60, 220, 255)), "dust", 0.7)
        assert not np.array_equal(np.asarray(warm), np.asarray(cool))


class TestWorldStateStats:
    def _rgb(self, img):
        return np.asarray(img.convert("RGB"), dtype=np.float32)

    def test_dust_lowers_saturation(self):
        img = Image.new("RGBA", (64, 64), (220, 40, 40, 255))
        out = apply_world_state(img, "dust", 0.9)
        assert _saturation(self._rgb(out)) < _saturation(self._rgb(img))

    def test_aging_lowers_brightness(self):
        img = Image.new("RGBA", (96, 96), (180, 180, 180, 255))
        out = apply_world_state(img, "aging", 0.9)
        assert _brightness(self._rgb(out)) < _brightness(self._rgb(img))

    def test_heat_warms(self):
        img = Image.new("RGBA", (64, 64), (128, 128, 128, 255))
        out = apply_world_state(img, "heat", 0.9)
        rgb = self._rgb(out)
        assert (_mean_channel(rgb, 0) - _mean_channel(rgb, 2)) > 1.0

    def test_soot_lowers_brightness(self):
        img = Image.new("RGBA", (96, 96), (200, 200, 200, 255))
        out = apply_world_state(img, "soot", 0.9)
        assert _brightness(self._rgb(out)) < _brightness(self._rgb(img))

    def test_sunbleach_raises_brightness(self):
        img = Image.new("RGBA", (96, 96), (90, 90, 90, 255))
        out = apply_world_state(img, "sunbleach", 0.9)
        assert _brightness(self._rgb(out)) > _brightness(self._rgb(img))

    def test_humidity_cools(self):
        img = Image.new("RGBA", (64, 64), (128, 128, 128, 255))
        out = apply_world_state(img, "humidity", 0.9)
        rgb = self._rgb(out)
        assert (_mean_channel(rgb, 2) - _mean_channel(rgb, 0)) > 1.0

    def test_haze_lowers_saturation(self):
        img = Image.new("RGBA", (64, 64), (220, 40, 40, 255))
        out = apply_world_state(img, "haze", 0.9)
        assert _saturation(self._rgb(out)) < _saturation(self._rgb(img))

    def test_intensity_scales_effect(self):
        img = Image.new("RGBA", (64, 64), (220, 40, 40, 255))
        low = _saturation(self._rgb(apply_world_state(img, "dust", 0.1)))
        high = _saturation(self._rgb(apply_world_state(img, "dust", 0.9)))
        assert high < low

    def test_preserves_alpha(self):
        img = Image.new("RGBA", (64, 64), (200, 50, 50, 128))
        out = apply_world_state(img, "aging", 0.9)
        assert out.getpixel((32, 32))[3] == 128

    def test_variant_is_same_size(self):
        base = Image.new("RGBA", (128, 64), (200, 80, 80, 255))
        out = apply_world_state(base, "soot", 0.8)
        assert out.size == (128, 64)

    def test_each_transform_runs(self):
        base = Image.new("RGBA", (64, 64), (160, 120, 100, 255))
        for fn in (dust_transform, aging_transform, heat_transform, soot_transform,
                   sunbleach_transform, humidity_transform, haze_transform):
            out = fn(base, 0.5)
            assert out.size == base.size
            assert out.mode == "RGBA"
