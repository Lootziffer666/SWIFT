"""
Critter Crosser – Studio GUI (PySide6).

Assembles the interactive studio: a central viewport (creatures + IK + wobbly
tower), visualiser widgets (flow field, Perlin preview, twin-stick), and the
control panels. A single animation timer advances play modes and repaints.
"""
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDockWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget,
)
from PySide6.QtCore import Qt, QTimer

from core.critter.studio import StudioModel
from gui.viewport import Viewport, FlowView, PerlinView, StickView
from gui.panels import (
    EvolutionPanel, IKPanel, FlowPanel, PalettePanel, PerlinPanel, StickPanel,
)


class StudioWindow(QMainWindow):
    def __init__(self, model: StudioModel):
        super().__init__()
        self.model = model
        self.setWindowTitle("SWIFT · Critter Crosser Studio")
        self.resize(1180, 760)

        # Central: creature / IK viewport.
        self.viewport = Viewport(model)

        central = QWidget()
        cv = QVBoxLayout(central)
        cv.addWidget(self.viewport)
        self.setCentralWidget(central)

        # Animation timer.
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

        self._build_docks()

    def _refresh(self):
        self.viewport.update()
        self.flow_view.update()
        self.perlin_view.update()
        self.stick_view.update()
        self.flow_panel.refresh_info()
        self.stick_panel.refresh_info()

    def _tick(self):
        if self.model.perlin_play:
            self.model.step_perlin()
        if self.model.flow_play:
            self.model.step_flow()
        self.model.step_wobbly()
        self._refresh()

    def _build_docks(self):
        # Left dock: control panels.
        left = QWidget()
        lv = QVBoxLayout(left)
        self.evo_panel = EvolutionPanel(self.model, self._refresh)
        self.ik_panel = IKPanel(self.model, self._refresh)
        lv.addWidget(self.evo_panel)
        lv.addWidget(self.ik_panel)
        lv.addStretch(1)
        left_dock = QDockWidget("Creature & IK", self)
        left_dock.setWidget(left)
        self.addDockWidget(Qt.LeftDockWidgetArea, left_dock)

        # Right dock: visualisers + remaining panels.
        right = QWidget()
        rv = QVBoxLayout(right)

        # Visualisers row.
        vis = QHBoxLayout()
        self.flow_view = FlowView(self.model)
        self.perlin_view = PerlinView(self.model)
        self.stick_view = StickView(self.model)
        vis.addWidget(self.flow_view)
        vis.addWidget(self.perlin_view)
        vis.addWidget(self.stick_view)
        rv.addLayout(vis)

        # Panels.
        self.flow_panel = FlowPanel(self.model, self._refresh)
        self.palette_panel = PalettePanel(self.model, self._refresh)
        self.perlin_panel = PerlinPanel(self.model, self._refresh)
        self.stick_panel = StickPanel(self.model, self._refresh)
        tabs = QTabWidget()
        tabs.addTab(self.flow_panel, "Flow")
        tabs.addTab(self.palette_panel, "Palette")
        tabs.addTab(self.perlin_panel, "Perlin")
        tabs.addTab(self.stick_panel, "Stick")
        rv.addWidget(tabs)

        right_dock = QDockWidget("Simulators & Controls", self)
        right_dock.setWidget(right)
        self.addDockWidget(Qt.RightDockWidgetArea, right_dock)

    def refresh_all(self):
        self._refresh()


def run_studio(seed: int = 1) -> int:
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    model = StudioModel(seed=seed)
    win = StudioWindow(model)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_studio())
