"""Headless tests for the StudioModel (no GUI toolkit required)."""
import math
import pytest
from core.critter.studio import StudioModel
from core.critter.geometry import Vec2


@pytest.fixture
def model():
    return StudioModel(seed=1)


class TestStudioModel:
    def test_boots_with_state(self, model):
        assert len(model.critters) >= 1
        assert model.selected() is not None
        assert model.flow is not None
        assert len(model.npcs) == 60

    def test_add_and_select(self, model):
        cid = model.spawn_random("Newbie")
        model.select(cid)
        assert model.selected().id == cid

    def test_evolution_morphs_selected(self, model):
        sel = model.selected()
        before = sel.skeleton.normalised_length()
        model.set_evolution(1.0)
        after = model.selected().skeleton.normalised_length()
        assert after != before  # skeleton changed

    def test_breed_adds_critter(self, model):
        n0 = len(model.critters)
        child = model.breed_selected(1)
        assert child is not None
        assert len(model.critters) == n0 + 1

    def test_ik_target_drag(self, model):
        model.set_ik_target_screen(26, 39)  # world ~(2,0,1): within chain reach
        model.solve_ik()
        scene = model.render()
        # End effector should be near the (projected) target.
        ex, ey = scene.ik["end"]
        tx, ty = scene.ik["target"]
        assert math.hypot(ex - tx, ey - ty) < 5

    def test_wobbly_step_moves(self, model):
        before = list(model.wobbly.positions[-1])
        for _ in range(20):
            model.step_wobbly(1 / 60.0)
        after = model.wobbly.positions[-1]
        assert after != before

    def test_flow_goal_and_cost(self, model):
        model.set_flow_goal(2, 2)
        scene = model.render()
        assert (2, 2) in [(int(g[0] - 40) // 18, int(g[1] - 40) // 18) for g in scene.flow["goals"]]
        model.set_tile_cost(5, 5, 100)
        assert model.flow.costs[5][5] == 100
        model.set_tile_blocked(6, 6, True)
        assert model.flow.blocked[6][6] is True

    def test_flow_step_moves_npcs(self, model):
        x0 = [n.x for n in model.npcs]
        model.step_flow(dt=1.0)
        x1 = [n.x for n in model.npcs]
        assert any(abs(a - b) > 1e-6 for a, b in zip(x0, x1))

    def test_perlin_preview_grid(self, model):
        grid = model.perlin_preview()
        assert len(grid) == model.perlin_grid
        assert len(grid[0]) == model.perlin_grid

    def test_render_structure(self, model):
        s = model.render()
        assert "creatures" in s.__dict__ and s.creatures
        assert s.ik.get("joints")
        assert s.flow.get("cells") is not None
        assert s.perlin.get("grid")
        assert "move" in s.stick and "aim" in s.stick

    def test_screen_tile_roundtrip(self, model):
        tx, ty = model.screen_to_tile(40 + 5 * 18, 40 + 7 * 18)
        assert tx == 5 and ty == 7


class TestGuiImport:
    def test_gui_importable_when_pyside_present(self):
        try:
            import PySide6  # noqa: F401
        except ImportError:
            pytest.skip("PySide6 not installed in this environment")
        import gui  # noqa: F401
        from gui.app import run_studio  # noqa: F401
        assert True
