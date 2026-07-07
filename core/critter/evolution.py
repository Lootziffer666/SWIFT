"""
Critter Crosser – procedural evolution & breeding.

Creatures are not swapped models but interpolated skeleton data, so every
intermediate form is fully functional and animatable.

  * Real-time morphing : LERP skeleton arrays (width/height/length) between
    larva and adult.
  * Breeding           : average parents, clamp gene counts to the parents'
    span (prevents "gene explosions" like 12 legs), virtual-scale mismatched
    body lengths before blending, then add dominance + small mutations.
"""
import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Skeleton:
    """Procedural skeleton described entirely by numeric arrays + gene counts."""

    segment_widths: List[float] = field(default_factory=list)
    segment_heights: List[float] = field(default_factory=list)
    segment_lengths: List[float] = field(default_factory=list)
    eye_count: int = 2
    limb_count: int = 4
    segment_count: int = 8

    def normalised_length(self) -> float:
        """Total body length used as the 'virtual length' for breeding."""
        return sum(self.segment_lengths)

    @property
    def is_valid(self) -> bool:
        n = self.segment_count
        return (
            len(self.segment_widths) == n
            and len(self.segment_heights) == n
            and len(self.segment_lengths) == n
            and self.eye_count >= 0
            and self.limb_count >= 0
            and n >= 1
        )


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp_lists(a: List[float], b: List[float], t: float) -> List[float]:
    n = max(len(a), len(b))
    out = []
    for i in range(n):
        av = a[i] if i < len(a) else (a[-1] if a else 0.0)
        bv = b[i] if i < len(b) else (b[-1] if b else 0.0)
        out.append(_lerp(av, bv, t))
    return out


def morph(larva: Skeleton, adult: Skeleton, t: float) -> Skeleton:
    """
    Linearly interpolate between larva (t=0) and adult (t=1). At t=0.5 the
    creature is a fully functional 50%-evolved form.
    """
    t = max(0.0, min(1.0, t))
    n = max(larva.segment_count, adult.segment_count)
    child = Skeleton(
        segment_widths=_lerp_lists(larva.segment_widths, adult.segment_widths, t),
        segment_heights=_lerp_lists(larva.segment_heights, adult.segment_heights, t),
        segment_lengths=_lerp_lists(larva.segment_lengths, adult.segment_lengths, t),
        eye_count=round(_lerp(larva.eye_count, adult.eye_count, t)),
        limb_count=round(_lerp(larva.limb_count, adult.limb_count, t)),
        segment_count=n,
    )
    return child


def _virtual_scale(skel: Skeleton, target_length: float) -> Skeleton:
    """Scale segment lengths so total body length == target (virtual scaling)."""
    total = skel.normalised_length()
    if total <= 0:
        return skel
    k = target_length / total
    return Skeleton(
        segment_widths=list(skel.segment_widths),
        segment_heights=list(skel.segment_heights),
        segment_lengths=[l * k for l in skel.segment_lengths],
        eye_count=skel.eye_count,
        limb_count=skel.limb_count,
        segment_count=skel.segment_count,
    )


def _clamp_counts(child: Skeleton, a: Skeleton, b: Skeleton) -> None:
    """Clamp gene counts to the parents' span to avoid gene explosions."""
    child.eye_count = int(max(min(a.eye_count, b.eye_count),
                              min(max(a.eye_count, b.eye_count), child.eye_count)))
    child.limb_count = int(max(min(a.limb_count, b.limb_count),
                               min(max(a.limb_count, b.limb_count), child.limb_count)))
    child.segment_count = int(max(min(a.segment_count, b.segment_count),
                                  min(max(a.segment_count, b.segment_count), child.segment_count)))


def breed(
    parent_a: Skeleton,
    parent_b: Skeleton,
    mutation_rate: float = 0.05,
    mutation_amount: float = 0.1,
    rng: Optional[random.Random] = None,
) -> Skeleton:
    """
    Produce an offspring skeleton:
      1. virtual-scale both parents to a common length (avoid tail overhang),
      2. average segment dimensions + counts,
      3. clamp counts to the parental span,
      4. apply dominance + small random mutations.
    """
    rng = rng or random.Random()
    target = (parent_a.normalised_length() + parent_b.normalised_length()) / 2.0
    a = _virtual_scale(parent_a, target)
    b = _virtual_scale(parent_b, target)

    child = Skeleton(
        segment_widths=[(x + y) / 2.0 for x, y in zip(a.segment_widths, b.segment_widths)],
        segment_heights=[(x + y) / 2.0 for x, y in zip(a.segment_heights, b.segment_heights)],
        segment_lengths=[(x + y) / 2.0 for x, y in zip(a.segment_lengths, b.segment_lengths)],
        eye_count=round((a.eye_count + b.eye_count) / 2.0),
        limb_count=round((a.limb_count + b.limb_count) / 2.0),
        segment_count=round((a.segment_count + b.segment_count) / 2.0),
    )
    _clamp_counts(child, a, b)

    # Dominance + mutation on continuous dims.
    for i in range(len(child.segment_lengths)):
        if rng.random() < mutation_rate:
            delta = (rng.random() * 2 - 1) * mutation_amount * child.segment_lengths[i]
            child.segment_lengths[i] = max(0.01, child.segment_lengths[i] + delta)
    for i in range(len(child.segment_widths)):
        if rng.random() < mutation_rate:
            delta = (rng.random() * 2 - 1) * mutation_amount * child.segment_widths[i]
            child.segment_widths[i] = max(0.01, child.segment_widths[i] + delta)
    return child
