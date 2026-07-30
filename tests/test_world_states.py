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


class TestWearFollowsGeometryNotPaint:
    """The defect this module was restructured to fix.

    ``aging`` used to derive "edge wear" from ``np.gradient(luminance)``. A painted
    stripe and a real groove produce the same luminance gradient, so the wear followed
    the artwork. It looked like weathering and was actually an edge-detect filter.
    """

    SIZE = 64

    def _painted_edge(self):
        """Uniform geometry, hard colour boundary down the middle."""
        arr = np.zeros((self.SIZE, self.SIZE, 4), dtype=np.uint8)
        arr[..., 3] = 255
        arr[:, : self.SIZE // 2, :3] = 40
        arr[:, self.SIZE // 2 :, :3] = 210
        flat_depth = np.full((self.SIZE, self.SIZE), 128.0, dtype=np.float32)
        return Image.fromarray(arr, "RGBA"), flat_depth

    def _geometric_ridge(self):
        """Uniform colour, a real ridge down the middle (nearer camera = smaller Z)."""
        arr = np.full((self.SIZE, self.SIZE, 4), 255, dtype=np.uint8)
        arr[..., :3] = 125
        depth = np.full((self.SIZE, self.SIZE), 200.0, dtype=np.float32)
        depth[:, self.SIZE // 2 - 4 : self.SIZE // 2 + 4] = 120.0
        return Image.fromarray(arr, "RGBA"), depth

    def _band_delta(self, before, after, lo, hi):
        """How much the transform changed a vertical band, in luma."""
        b = np.asarray(before.convert("RGB"), dtype=np.float32)[:, lo:hi].mean()
        a = np.asarray(after.convert("RGB"), dtype=np.float32)[:, lo:hi].mean()
        return abs(a - b)

    def _wear_only(self, img, depth):
        """Apply wear alone.

        ``aging`` also carries macro breakup at ±20 luma, which is louder than the wear
        it would be measuring. Isolating the channel tests the claim instead of the
        noise floor of one particular recipe.
        """
        from core.procedural.world_states import SurfaceRecipe, _apply_recipe

        return _apply_recipe(img, SurfaceRecipe(wear=1.0), 1.0, "probe", depth=depth)

    def test_painted_edge_gets_no_extra_wear(self):
        img, depth = self._painted_edge()
        out = self._wear_only(img, depth)
        mid = self.SIZE // 2
        at_boundary = self._band_delta(img, out, mid - 6, mid + 6)
        away = self._band_delta(img, out, 4, 16)
        assert at_boundary == pytest.approx(away, abs=1.0), (
            "wear tracked the painted edge — the luminance-gradient defect is back"
        )

    def test_geometric_ridge_does_get_wear(self):
        """The band spans the ridge *and its lips*.

        Wear peaks at the rim rather than the crown, which is where paint actually rubs
        through — measuring only the flat top of the bar understates it.
        """
        img, depth = self._geometric_ridge()
        out = self._wear_only(img, depth)
        mid = self.SIZE // 2
        on_ridge = self._band_delta(img, out, mid - 6, mid + 6)
        off_ridge = self._band_delta(img, out, 4, 16)
        assert on_ridge > off_ridge + 4.0, (
            "a real ridge produced no more wear than flat plate"
        )

    def test_luminance_gradient_would_fail_the_pair(self):
        """Guards the guard.

        Reproduces the old approach and shows it cannot tell the two cases apart, so
        the pair above genuinely discriminates rather than passing for free.
        """
        def old_edge_response(img):
            rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
            lum = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
            gy, gx = np.gradient(lum)
            e = np.sqrt(gx**2 + gy**2)
            return e / (e.max() + 1e-6)

        painted, _ = self._painted_edge()
        ridge, _ = self._geometric_ridge()
        mid = self.SIZE // 2
        # The old proxy fires hard on the painted edge...
        assert old_edge_response(painted)[:, mid - 2 : mid + 2].mean() > 0.4
        # ...and not at all on the geometric one, which carries no colour change.
        assert old_edge_response(ridge)[:, mid - 2 : mid + 2].mean() < 0.01


class TestSaturationGuard:
    def test_no_recipe_exceeds_the_ceiling(self):
        from core.procedural.world_states import MAX_SATURATION, _rgb_to_hsv

        img = Image.new("RGBA", (64, 64), (255, 20, 20, 255))
        for state in list_world_states():
            out = apply_world_state(img, state, 1.0)
            rgb = np.asarray(out.convert("RGB"), dtype=np.float32)
            _, sat, _ = _rgb_to_hsv(rgb)
            assert float(sat.mean()) <= MAX_SATURATION + 1e-6, state


class TestDepthIsOptional:
    def test_every_state_runs_without_depth(self):
        img = Image.new("RGBA", (48, 48), (150, 130, 110, 255))
        for state in list_world_states():
            out = apply_world_state(img, state, 0.8)
            assert out.mode == "RGBA" and out.size == img.size

    def test_depth_changes_the_result(self):
        img = Image.new("RGBA", (64, 64), (150, 130, 110, 255))
        depth = np.full((64, 64), 200.0, dtype=np.float32)
        depth[:, 28:36] = 120.0
        without = np.asarray(apply_world_state(img, "aging", 0.9))
        with_ = np.asarray(apply_world_state(img, "aging", 0.9, depth=depth))
        assert not np.array_equal(without, with_)
