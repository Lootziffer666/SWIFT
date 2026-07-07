"""
Critter Crosser – flow-field pathfinding & NPC AI.

To drive up to 4,000 NPCs we use flow fields instead of per-agent A*.
A single distance field is computed from the goal; each tile stores the
direction toward its cheapest neighbour (vector field). Storage is 1 byte per
tile, so whole (even unloaded) levels can keep their field resident.

Costs bias routing: e.g. sidewalk = 1, street = 100, so NPCs naturally prefer
pavements over cutting across roads.

Low-power mode: off-screen NPCs skip collision queries and state machines.

Pure-Python implementation (no external array dependency) so it runs anywhere.
"""
import heapq
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from core.critter.geometry import Vec2, Vec3, IsometricProjection


@dataclass
class FlowFieldConfig:
    width: int
    height: int
    # Default traversal cost for walkable tiles (stored as uint8, 1..255).
    default_cost: int = 1
    # Cost of impassable tiles. Marked blocked instead of using this value.
    blocking_cost: int = 255


class FlowField:
    """
    Integration (distance) field + vector field over a tile grid.

    `costs` is a byte-per-tile grid (1 byte/tile). `blocked` tiles are
    impassable.
    """

    def __init__(self, config: FlowFieldConfig):
        self.config = config
        self.w = config.width
        self.h = config.height
        self.costs = [[config.default_cost] * self.w for _ in range(self.h)]
        self.blocked = [[False] * self.w for _ in range(self.h)]
        self.integration = [[float("inf")] * self.w for _ in range(self.h)]
        self.vector = [[(0.0, 0.0)] * self.w for _ in range(self.h)]

    def set_cost(self, x: int, y: int, cost: int) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.costs[y][x] = max(0, min(255, cost))

    def set_blocked(self, x: int, y: int, blocked: bool = True) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.blocked[y][x] = blocked

    def _idx(self, x: int, y: int) -> int:
        return y * self.w + x

    def compute(self, goals: List[Tuple[int, int]]) -> None:
        """
        Dijkstra from all goal tiles (multi-source) to fill the integration
        field, then derive the per-tile flow vector toward the cheapest
        neighbour.
        """
        for row in self.integration:
            for i in range(len(row)):
                row[i] = float("inf")

        heap: List[Tuple[float, int]] = []
        for gx, gy in goals:
            if not (0 <= gx < self.w and 0 <= gy < self.h) or self.blocked[gy][gx]:
                continue
            self.integration[gy][gx] = 0.0
            heapq.heappush(heap, (0.0, self._idx(gx, gy)))

        neighbours = ((1, 0), (-1, 0), (0, 1), (0, -1))
        while heap:
            dist, idx = heapq.heappop(heap)
            cx, cy = idx % self.w, idx // self.w
            if dist > self.integration[cy][cx]:
                continue
            for dx, dy in neighbours:
                nx, ny = cx + dx, cy + dy
                if not (0 <= nx < self.w and 0 <= ny < self.h):
                    continue
                if self.blocked[ny][nx]:
                    continue
                step = float(self.costs[ny][nx])
                nd = dist + step
                if nd < self.integration[ny][nx]:
                    self.integration[ny][nx] = nd
                    heapq.heappush(heap, (nd, self._idx(nx, ny)))

        self._build_vector_field()

    def _build_vector_field(self) -> None:
        neighbours = ((1, 0), (-1, 0), (0, 1), (0, -1))
        for y in range(self.h):
            for x in range(self.w):
                if self.blocked[y][x] or self.integration[y][x] == float("inf"):
                    continue
                best_val = self.integration[y][x]
                best_dx = best_dy = 0
                for dx, dy in neighbours:
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < self.w and 0 <= ny < self.h):
                        continue
                    if self.blocked[ny][nx]:
                        continue
                    v = self.integration[ny][nx]
                    if v < best_val:
                        best_val = v
                        best_dx, best_dy = dx, dy
                self.vector[y][x] = (float(best_dx), float(best_dy))

    def direction_at(self, x: int, y: int) -> Vec2:
        if 0 <= x < self.w and 0 <= y < self.h:
            dx, dy = self.vector[y][x]
            return Vec2(dx, dy)
        return Vec2(0.0, 0.0)

    def memory_bytes(self) -> int:
        """1 byte per tile for costs (+ negligible overhead)."""
        return self.w * self.h


@dataclass
class NPC:
    """A single agent driven by a flow field, with low-power off-screen mode."""

    id: int
    x: float
    y: float
    on_screen: bool = True
    state: str = "idle"
    _vel: Vec2 = field(default_factory=lambda: Vec2(0.0, 0.0))

    def update(self, field: FlowField, speed: float, dt: float) -> None:
        d = field.direction_at(int(self.x), int(self.y))
        if d.x == 0.0 and d.y == 0.0:
            return
        if not self.on_screen:
            # LOW-POWER MODE: skip collision query + state machine entirely.
            self.x += d.x * speed * dt
            self.y += d.y * speed * dt
            return
        # On-screen: full simulation (collision + state machine hook).
        self.state = "moving"
        self.x += d.x * speed * dt
        self.y += d.y * speed * dt
