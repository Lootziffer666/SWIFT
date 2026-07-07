"""
Critter Crosser – control panels (PySide6).

Each panel mutates the StudioModel and calls a `refresh` callback so the views
redraw. Pure UI glue; all state lives in the model.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton,
    QComboBox, QCheckBox, QListWidget, QColorDialog, QGroupBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from core.critter.shaders import PaletteSwap


class EvolutionPanel(QGroupBox):
    def __init__(self, model, refresh):
        super().__init__("Evolution & Breeding")
        self.model = model
        self.refresh = refresh
        lay = QVBoxLayout(self)

        self.list = QListWidget()
        self._fill()
        self.list.currentRowChanged.connect(self._on_select)
        lay.addWidget(self.list)

        self.evo = QSlider(Qt.Horizontal)
        self.evo.setRange(0, 100)
        self.evo.setValue(50)
        self.evo.valueChanged.connect(lambda v: (self.model.set_evolution(v / 100.0), self.refresh()))
        lay.addWidget(QLabel("Evolution (larva → adult)"))
        lay.addWidget(self.evo)

        row = QHBoxLayout()
        b1 = QPushButton("Random critter")
        b1.clicked.connect(lambda: (self.model.spawn_random(), self._fill(), self.refresh()))
        b2 = QPushButton("Breed with next")
        b2.clicked.connect(lambda: (self.model.breed_selected(1), self._fill(), self.refresh()))
        row.addWidget(b1); row.addWidget(b2)
        lay.addLayout(row)

    def _fill(self):
        self.list.blockSignals(True)
        self.list.clear()
        for c in self.model.critters:
            self.list.addItem(f"#{c.id} {c.name}")
        self.list.blockSignals(False)

    def _on_select(self, row):
        if 0 <= row < len(self.model.critters):
            self.model.select(self.model.critters[row].id)
            self.refresh()


class IKPanel(QGroupBox):
    def __init__(self, model, refresh):
        super().__init__("Inverse Kinematics")
        self.model = model
        self.refresh = refresh
        lay = QVBoxLayout(self)

        self.solver = QComboBox()
        self.solver.addItems(["fabrik", "law_of_cosines"])
        self.solver.setCurrentText(self.model.ik_solver)
        self.solver.currentTextChanged.connect(lambda t: (setattr(self.model, "ik_solver", t), self.model.solve_ik(), self.refresh()))
        lay.addWidget(QLabel("Solver"))
        lay.addWidget(self.solver)

        self.zb = QCheckBox("Z-bend (mammal gallop)")
        self.zb.setChecked(self.model.show_z_bend)
        self.zb.toggled.connect(lambda v: (setattr(self.model, "show_z_bend", v), self.model.solve_ik(), self.refresh()))
        lay.addWidget(self.zb)

        self.fpull = QSlider(Qt.Horizontal)
        self.fpull.setRange(0, 100)
        self.fpull.setValue(int(self.model.zbend.forward_pull * 100))
        self.fpull.valueChanged.connect(lambda v: (setattr(self.model.zbend, "forward_pull", v / 100.0), self.model.solve_ik(), self.refresh()))
        lay.addWidget(QLabel("Forward pull"))
        lay.addWidget(self.fpull)

        self.bpull = QSlider(Qt.Horizontal)
        self.bpull.setRange(0, 100)
        self.bpull.setValue(int(self.model.zbend.backward_pull * 100))
        self.bpull.valueChanged.connect(lambda v: (setattr(self.model.zbend, "backward_pull", v / 100.0), self.model.solve_ik(), self.refresh()))
        lay.addWidget(QLabel("Backward pull"))
        lay.addWidget(self.bpull)

        b = QPushButton("Solve IK")
        b.clicked.connect(lambda: (self.model.solve_ik(), self.refresh()))
        lay.addWidget(b)
        wob = QPushButton("Flick trunk (wobbly)")
        wob.clicked.connect(lambda: (setattr(self.model, "wobbly_target",
                              self.model.wobbly_target + (0, 0, 1.5)), self.refresh()))
        lay.addWidget(wob)


class FlowPanel(QGroupBox):
    def __init__(self, model, refresh):
        super().__init__("Flow Field (NPCs)")
        self.model = model
        self.refresh = refresh
        lay = QVBoxLayout(self)

        self.info = QLabel()
        lay.addWidget(self.info)

        row = QHBoxLayout()
        step = QPushButton("Step")
        step.clicked.connect(lambda: (self.model.step_flow(), self.refresh()))
        play = QPushButton("Play / Pause")
        play.clicked.connect(lambda: (setattr(self.model, "flow_play", not self.model.flow_play), self.refresh()))
        row.addWidget(step); row.addWidget(play)
        lay.addLayout(row)

        reset = QPushButton("Reset goal to center")
        reset.clicked.connect(lambda: (self.model.set_flow_goal(self.model.ff_config.width // 2,
                                                               self.model.ff_config.height // 2), self.refresh()))
        lay.addWidget(reset)
        lay.addWidget(QLabel("Left-click: goal · Shift-click: street(100) · Right-click: block"))

    def refresh_info(self):
        self.info.setText(f"NPCs: {len(self.model.npcs)}  Grid: "
                          f"{self.model.ff_config.width}×{self.model.ff_config.height}  "
                          f"Field: {self.model.flow.memory_bytes()} B")


class PalettePanel(QGroupBox):
    def __init__(self, model, refresh):
        super().__init__("Palette Swap (region masks)")
        self.model = model
        self.refresh = refresh
        lay = QVBoxLayout(self)
        self.buttons = []
        for i, col in enumerate(self.model.palette.palette):
            b = QPushButton(f"Region {i}")
            b.setStyleSheet(f"background-color: rgb({int(col.r*255)},{int(col.g*255)},{int(col.b*255)})")
            b.clicked.connect(lambda _checked, idx=i: self._pick(idx))
            self.buttons.append(b)
            lay.addWidget(b)
        lay.addWidget(QLabel("Click to recolor (0–255 → shader floats)"))

    def _pick(self, idx):
        cur = self.model.palette.palette[idx]
        qc = QColorDialog.getColor(QColor(int(cur.r * 255), int(cur.g * 255), int(cur.b * 255)), self)
        if not qc.isValid():
            return
        self.model.palette.palette[idx] = PaletteSwap.to_shader_color(qc.red(), qc.green(), qc.blue())
        self.buttons[idx].setStyleSheet(f"background-color: rgb({qc.red()},{qc.green()},{qc.blue()})")
        self.refresh()


class PerlinPanel(QGroupBox):
    def __init__(self, model, refresh):
        super().__init__("Perlin Noise VFX")
        self.model = model
        self.refresh = refresh
        lay = QVBoxLayout(self)

        self.mode = QComboBox()
        self.mode.addItems(["scroll", "distort", "stretch"])
        self.mode.setCurrentText(self.model.perlin_mode)
        self.mode.currentTextChanged.connect(lambda t: (setattr(self.model, "perlin_mode", t), self.refresh()))
        lay.addWidget(QLabel("Mode"))
        lay.addWidget(self.mode)

        self.scale = QSlider(Qt.Horizontal)
        self.scale.setRange(1, 100)
        self.scale.setValue(int(self.model.perlin_scale * 100))
        self.scale.valueChanged.connect(lambda v: (setattr(self.model, "perlin_scale", v / 100.0), self.refresh()))
        lay.addWidget(QLabel("Scale"))
        lay.addWidget(self.scale)

        play = QCheckBox("Animate")
        play.setChecked(self.model.perlin_play)
        play.toggled.connect(lambda v: setattr(self.model, "perlin_play", v))
        lay.addWidget(play)


class StickPanel(QGroupBox):
    def __init__(self, model, refresh):
        super().__init__("Twin-Stick Input")
        self.model = model
        self.refresh = refresh
        lay = QVBoxLayout(self)
        self.readout = QLabel()
        lay.addWidget(self.readout)
        lay.addWidget(QLabel("Left-drag: move · Right-drag: aim"))

    def refresh_info(self):
        m = self.model.stick.movement
        a = self.model.stick.aim
        side = "YES" if self.model.stick.can_side_step() else "no"
        self.readout.setText(f"move ({m.x:.2f},{m.y:.2f})  aim ({a.x:.2f},{a.y:.2f})\n"
                             f"side-step: {side}")
