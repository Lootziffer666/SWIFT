"""Tests for evolution (morphing) and breeding."""
import random
from core.critter.evolution import Skeleton, morph, breed, _clamp_counts


def _larva():
    return Skeleton(
        segment_widths=[0.2] * 4,
        segment_heights=[0.2] * 4,
        segment_lengths=[0.3] * 4,
        eye_count=2,
        limb_count=0,
        segment_count=4,
    )


def _adult():
    return Skeleton(
        segment_widths=[0.6] * 8,
        segment_heights=[0.6] * 8,
        segment_lengths=[0.8] * 8,
        eye_count=2,
        limb_count=4,
        segment_count=8,
    )


class TestMorph:
    def test_endpoints(self):
        larva, adult = _larva(), _adult()
        l = morph(larva, adult, 0.0)
        a = morph(larva, adult, 1.0)
        assert l.segment_count == 4
        assert a.segment_count == 8
        # Adult length > larva length.
        assert a.normalised_length() > l.normalised_length()

    def test_intermediate_functional(self):
        larva, adult = _larva(), _adult()
        mid = morph(larva, adult, 0.5)
        assert mid.is_valid
        # Intermediate length between the two extremes.
        assert larva.normalised_length() < mid.normalised_length() < adult.normalised_length()

    def test_monotonic_length(self):
        larva, adult = _larva(), _adult()
        prev = -1.0
        for t in [i / 10 for i in range(11)]:
            cur = morph(larva, adult, t).normalised_length()
            assert cur >= prev - 1e-6
            prev = cur


class TestBreeding:
    def test_averages_dimensions(self):
        a = Skeleton(
            segment_widths=[1.0, 1.0], segment_heights=[1.0, 1.0],
            segment_lengths=[1.0, 1.0], eye_count=2, limb_count=4, segment_count=2,
        )
        b = Skeleton(
            segment_widths=[3.0, 3.0], segment_heights=[3.0, 3.0],
            segment_lengths=[3.0, 3.0], eye_count=4, limb_count=6, segment_count=2,
        )
        child = breed(a, b, mutation_rate=0.0)
        assert child.segment_lengths[0] == 2.0
        assert child.eye_count == 3
        assert child.limb_count == 5

    def test_clamps_gene_explosion(self):
        a = Skeleton(
            segment_widths=[1.0], segment_heights=[1.0],
            segment_lengths=[1.0], eye_count=2, limb_count=2, segment_count=1,
        )
        b = Skeleton(
            segment_widths=[1.0], segment_heights=[1.0],
            segment_lengths=[1.0], eye_count=4, limb_count=4, segment_count=1,
        )
        # Force a crazy averaged value then clamp.
        child = breed(a, b, mutation_rate=0.0)
        child.limb_count = 12  # simulate gene explosion
        _clamp_counts(child, a, b)
        assert child.limb_count <= max(a.limb_count, b.limb_count)

    def test_virtual_scaling_handles_mismatch(self):
        small = Skeleton(
            segment_widths=[0.5] * 2, segment_heights=[0.5] * 2,
            segment_lengths=[0.3] * 2, eye_count=2, limb_count=2, segment_count=2,
        )
        long = Skeleton(
            segment_widths=[0.5] * 2, segment_heights=[0.5] * 2,
            segment_lengths=[2.0] * 2, eye_count=2, limb_count=2, segment_count=2,
        )
        child = breed(small, long, mutation_rate=0.0)
        # Child total length should be near the average of the two parents.
        avg = (small.normalised_length() + long.normalised_length()) / 2.0
        assert abs(child.normalised_length() - avg) < 1e-6

    def test_mutation_varies(self):
        a = Skeleton(
            segment_widths=[1.0] * 3, segment_heights=[1.0] * 3,
            segment_lengths=[1.0] * 3, eye_count=2, limb_count=4, segment_count=3,
        )
        b = Skeleton(
            segment_widths=[1.0] * 3, segment_heights=[1.0] * 3,
            segment_lengths=[1.0] * 3, eye_count=2, limb_count=4, segment_count=3,
        )
        rng = random.Random(123)
        child = breed(a, b, mutation_rate=1.0, mutation_amount=0.5, rng=rng)
        # With full mutation some segment length should differ from 1.0.
        assert any(abs(l - 1.0) > 1e-6 for l in child.segment_lengths)
