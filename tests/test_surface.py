"""Tests for core/procedural/surface.py — the surface law and its evaluators.

The point of these is not that the evaluators run. It is that they agree with each
other and that they stay quiet when there is nothing to say. A weathering system that
reports relief on a flat object is worse than none, because it looks plausible.
"""
import numpy as np
import pytest
from scipy.stats import spearmanr

from core.procedural import surface as S


# ------------------------------------------------------------------ fixtures


def _l_shape_sdf(p):
    """Two overlapping boxes. One inner corner (crevice), two tips (exposed)."""

    def box(q, c, h):
        d = np.abs(q - c) - h
        return np.linalg.norm(np.maximum(d, 0), axis=-1) + np.minimum(d.max(axis=-1), 0)

    return np.minimum(
        box(p, np.float32([0, 0, 0]), np.float32([2, 0.5, 0.5])),
        box(p, np.float32([0, 0, 0]), np.float32([0.5, 2, 0.5])),
    )


def _l_shape_mesh():
    def box_mesh(c, h):
        c, h = np.float32(c), np.float32(h)
        s = np.array(
            [[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
             [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]], np.float32)
        f = np.array(
            [[0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6], [0, 4, 5], [0, 5, 1],
             [1, 5, 6], [1, 6, 2], [2, 6, 7], [2, 7, 3], [3, 7, 4], [3, 4, 0]])
        return c + s * h, f

    v1, f1 = box_mesh([0, 0, 0], [2, 0.5, 0.5])
    v2, f2 = box_mesh([0, 0, 0], [0.5, 2, 0.5])
    return np.vstack([v1, v2]), np.vstack([f1, f2 + len(v1)])


def _surface_points(eps=0.05, n=100):
    g = np.linspace(-2.6, 2.6, n)
    X, Y, Z = np.meshgrid(g, g, np.linspace(-0.6, 0.6, 7), indexing="ij")
    P = np.stack([X.ravel(), Y.ravel(), Z.ravel()], -1).astype(np.float32)
    return P[np.abs(_l_shape_sdf(P)) < eps]


def _near(values, points, at, radius=0.35):
    m = np.linalg.norm(points - np.float32(at), axis=1) < radius
    return float(values[m].mean())


# ------------------------------------------------------------------ 2D: depth


class TestDepthEvaluator:
    def _full(self, v, shape=(64, 64)):
        return np.full(shape, float(v), dtype=np.float32)

    def test_flat_depth_reports_no_relief(self):
        """The calibration floor's whole job. A uniform object comes out uniform.

        Percentiles alone would stretch quantisation noise across the full 0..1 range
        and paint the entire sprite as worn.
        """
        f = S.from_depth(self._full(128), alpha=self._full(255))
        assert f.cavity.max() == pytest.approx(0.0, abs=1e-6)
        assert f.edge.max() == pytest.approx(0.0, abs=1e-6)

    def test_ridge_is_edge_and_groove_is_cavity(self):
        """Pins the depth sign convention.

        SWIFT's pass stores distance from camera, so a *smaller* value protrudes.
        Reading it backwards puts grime on the ridges and wear in the creases, and
        nothing about that failure is loud.
        """
        alpha = self._full(255)

        ridge = self._full(200)
        ridge[:, 28:36] = 120.0
        r = S.from_depth(ridge, alpha=alpha)
        assert r.edge[:, 28:36].mean() > 0.2
        assert r.edge[:, :20].mean() < 0.01
        assert r.cavity[:, 28:36].mean() < 0.01

        groove = self._full(120)
        groove[:, 28:36] = 200.0
        g = S.from_depth(groove, alpha=alpha)
        assert g.cavity[:, 28:36].mean() > 0.2
        assert g.edge[:, 28:36].mean() < 0.01

    def test_background_does_not_bleed_across_the_silhouette(self):
        """Without normalised convolution every silhouette edge reads as a crevice."""
        depth = self._full(200)
        alpha = np.zeros((64, 64), dtype=np.float32)
        alpha[16:48, 16:48] = 255.0
        f = S.from_depth(depth, alpha=alpha)
        border = np.zeros((64, 64), dtype=bool)
        border[16:48, 16:18] = True
        assert f.cavity[border].max() < 0.05

    def test_empty_mask_is_flat(self):
        f = S.from_depth(self._full(200), alpha=np.zeros((64, 64)))
        assert f.is_flat()

    def test_flat_field_contributes_nothing(self):
        f = S.SurfaceField.flat((8, 8))
        assert f.is_flat()
        assert f.slope.mean() == pytest.approx(0.5)


# ------------------------------------------------------------------ 3D


class TestThreeDEvaluators:
    def test_sdf_finds_the_crevice_and_the_tip(self):
        pts = _surface_points()
        f = S.from_sdf(_l_shape_sdf, pts, radius=0.30)
        assert _near(f.cavity, pts, [0.5, 0.5, 0]) > _near(f.cavity, pts, [2.0, 0, 0])

    def test_mesh_finds_the_crevice_and_the_tip(self):
        pts = _surface_points()
        v, faces = _l_shape_mesh()
        grid = S.occupancy(v, faces, cell=0.18)
        cav, _ = S.calibrate(S.bake_occupancy(pts, grid, radius=0.30))
        assert _near(cav, pts, [0.5, 0.5, 0]) > _near(cav, pts, [2.0, 0, 0])

    def test_occupancy_marks_solid_not_just_surface(self):
        """A fingertip must not read as enclosed just because the surface wraps it.

        Rasterising triangles alone measures surface presence; the interior fill is
        what turns that into a measure of matter.
        """
        v, faces = _l_shape_mesh()
        grid = S.occupancy(v, faces, cell=0.15)
        centre = grid.sample(np.float32([[0.0, 0.0, 0.0]]))
        assert centre[0] == pytest.approx(1.0), "interior was not filled"

    def test_evaluators_agree(self):
        """The two-implementation argument, applied to the surface law.

        A law with one evaluator is indistinguishable from that evaluator's quirks.
        Voxel and analytic paths are written differently and must still rank the same
        points as enclosed.
        """
        pts = _surface_points()
        v, faces = _l_shape_mesh()
        grid = S.occupancy(v, faces, cell=0.18)
        occ = S.bake_occupancy(pts, grid, radius=0.30)
        ref = S.from_sdf(_l_shape_sdf, pts, radius=0.30)
        assert spearmanr(occ, ref.cavity).correlation > 0.75

    def test_agreement_is_stable_under_grid_refinement(self):
        """Cell size is numerical, radius is physical — refining one must not move the
        other. Tied together, the measure drifts as the grid gets finer instead of
        sharpening, which is how the conflation hides.
        """
        pts = _surface_points()
        v, faces = _l_shape_mesh()
        ref = S.from_sdf(_l_shape_sdf, pts, radius=0.30)
        corrs = []
        for cell in (0.30, 0.16, 0.08):
            grid = S.occupancy(v, faces, cell=cell)
            occ = S.bake_occupancy(pts, grid, radius=0.30)
            corrs.append(spearmanr(occ, ref.cavity).correlation)
        assert min(corrs) > 0.75
        assert max(corrs) - min(corrs) < 0.15, f"measure drifts with grid: {corrs}"


# ------------------------------------------------------------------ calibration


class TestCalibration:
    def test_uniform_input_stays_uniform(self):
        cav, edge = S.calibrate(np.full(500, 0.3, dtype=np.float32))
        assert cav.max() == pytest.approx(0.0, abs=1e-6)
        assert edge.max() == pytest.approx(0.0, abs=1e-6)

    def test_narrow_spread_is_not_stretched_to_full_range(self):
        """The landing-leg failure: a few per cent of spread must not become 0..1."""
        rng = np.random.default_rng(0)
        cav, edge = S.calibrate(0.3 + rng.normal(0, 0.004, 2000).astype(np.float32))
        assert cav.max() < 0.05
        assert edge.max() < 0.05

    def test_real_spread_does_produce_relief(self):
        rng = np.random.default_rng(0)
        values = np.concatenate([
            np.full(1000, 0.30), np.full(120, 0.75), np.full(120, 0.05)
        ]).astype(np.float32) + rng.normal(0, 0.005, 1240).astype(np.float32)
        cav, edge = S.calibrate(values)
        assert cav.max() > 0.8
        assert edge.max() > 0.5

    def test_empty_input_does_not_raise(self):
        cav, edge = S.calibrate(np.zeros(0, dtype=np.float32))
        assert cav.size == 0 and edge.size == 0
