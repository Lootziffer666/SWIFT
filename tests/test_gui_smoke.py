"""
Smoke test for the SWIFT PySide6 GUI.

Constructs MainWindow without calling show()/exec() and asserts that the key
widgets exist — in particular the render tab's world-states control. Skipped
when PySide6 (or pytest-qt) is not importable.
"""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QComboBox, QLineEdit  # noqa: E402

from gui.app import MainWindow  # noqa: E402


def test_mainwindow_builds(qapp):
    window = MainWindow()
    assert window is not None


def test_render_tab_exposes_world_states(qapp):
    window = MainWindow()
    rt = window.render_tab

    # Core render inputs
    assert isinstance(rt.model, object)
    assert isinstance(rt.model.edit, QLineEdit)
    assert isinstance(rt.anim.edit, QLineEdit)
    assert isinstance(rt.output.edit, QLineEdit)
    assert isinstance(rt.format, QComboBox)
    assert isinstance(rt.camera, QComboBox)

    # SHADED world-states control must be present and editable
    assert isinstance(rt.world_states, QLineEdit)
    rt.world_states.set_text("dust,aging=0.7")
    assert rt.world_states.text() == "dust,aging=0.7"


def test_all_command_tabs_present(qapp):
    window = MainWindow()
    assert window.render_tab is not None
    assert window.analyze_tab is not None
    assert window.mocap_tab is not None
    assert window.v2s_tab is not None
    assert window.ss_tab is not None
