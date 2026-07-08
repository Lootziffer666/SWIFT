"""
SWIFT PySide6 GUI.

Wraps the existing CLI subcommands (render, analyze, mocap, video2sprite,
spritesheet) in a Qt6 application. Each command's output — including the
`progress_cb` lines the cmd_* functions print — is captured into a shared log
widget by redirecting ``sys.stdout`` while the command runs on a worker thread.

Launch with::

    python -m gui.app

or via the CLI::

    swift gui
"""
import argparse
import sys
from types import SimpleNamespace

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QMessageBox,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from main import (
    cmd_analyze,
    cmd_mocap,
    cmd_render,
    cmd_spritesheet,
    cmd_video2sprite,
)


# ── stdout capture ─────────────────────────────────────────────────────────────

class _LogStream(QObject):
    """A writable stream that forwards every write to Qt as a signal."""

    text_written = Signal(str)

    def write(self, text):
        if text:
            self.text_written.emit(text)

    def flush(self):
        pass


class _Worker(QThread):
    """Runs a callable on a background thread, capturing its stdout."""

    log_line = Signal(str)
    finished = Signal(object)
    errored = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        stream = _LogStream()
        stream.text_written.connect(self.log_line)
        old_out = sys.stdout
        sys.stdout = stream
        try:
            result = self._fn()
            self.finished.emit(result)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            self.errored.emit(f"Process exited (code {code})")
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
            self.errored.emit(f"{type(exc).__name__}: {exc}")
        finally:
            sys.stdout = old_out


# ── shared helpers ─────────────────────────────────────────────────────────────

class _Field(QWidget):
    """A label + QLineEdit + optional browse button."""

    def __init__(self, label, browse="file", placeholder=""):
        super().__init__()
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label))
        layout.addWidget(self.edit, 1)
        if browse:
            btn = QPushButton("Browse")
            btn.clicked.connect(self._browse)
            layout.addWidget(btn)
        self._browse_mode = browse

    def _browse(self):
        if self._browse_mode == "dir":
            path = QFileDialog.getExistingDirectory(self, "Select directory")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select file")
        if path:
            self.edit.setText(path)

    def text(self):
        return self.edit.text().strip()

    def set_text(self, value):
        self.edit.setText(value or "")


class _CommandTab(QWidget):
    """Base tab that owns a Run button and emits a callable to run."""

    run_requested = Signal(object)

    def __init__(self, title="Run"):
        super().__init__()
        self._layout = QVBoxLayout(self)
        self._build_controls()
        self._layout.addStretch(1)
        self.run_button = QPushButton(title)
        self.run_button.clicked.connect(self._on_run)
        self._layout.addWidget(self.run_button)

    def _build_controls(self):
        raise NotImplementedError

    def _on_run(self):
        raise NotImplementedError

    def _emit(self, fn):
        self.run_requested.emit(fn)


# ── render tab ─────────────────────────────────────────────────────────────────

class RenderTab(_CommandTab):
    def _build_controls(self):
        self.model = _Field("Model FBX", "file", "character.fbx")
        self.anim = _Field("Anim FBX", "file", "animation.fbx (optional)")
        self.output = _Field("Output dir", "dir", "output/ (optional)")
        self.blender = _Field("Blender", "file", "path to blender (optional)")

        self.format = QComboBox()
        self.format.addItems(["sprite_sheet", "gif", "frames_json"])
        self.camera = QComboBox()
        self.camera.addItems(["front", "side", "three-quarter"])

        self.width = QSpinBox()
        self.width.setRange(1, 4096)
        self.width.setValue(64)
        self.height = QSpinBox()
        self.height.setRange(1, 4096)
        self.height.setValue(64)
        self.fps = QSpinBox()
        self.fps.setRange(1, 120)
        self.fps.setValue(12)
        self.pixel_size = QSpinBox()
        self.pixel_size.setRange(1, 64)
        self.pixel_size.setValue(4)

        self.depth_pass = QCheckBox("Depth pass (Z-buffer)")
        self.anim_name = QLineEdit()
        self.anim_name.setPlaceholderText("manifest anim key (optional)")

        # Procedural skeleton generator
        self.skeleton_gen = QCheckBox("Use skeleton generator")
        self.height_cm = QDoubleSpinBox()
        self.height_cm.setRange(1, 400)
        self.height_cm.setValue(170.0)
        self.weight_kg = QDoubleSpinBox()
        self.weight_kg.setRange(1, 500)
        self.weight_kg.setValue(70.0)
        self.with_ik = QCheckBox("Apply 2-bone IK")
        self.mesh_bodies = QCheckBox("Generate mesh bodies")

        # World states (SHADED) + palette variants
        self.world_states = QLineEdit()
        self.world_states.setPlaceholderText("e.g. dust,aging=0.7")
        self.variants = QLineEdit()
        self.variants.setPlaceholderText("e.g. red,green,gold")

        # Layout
        basic = QGroupBox("Render")
        form = QFormLayout(basic)
        form.addRow(self.model)
        form.addRow(self.anim)
        form.addRow(self.output)
        form.addRow(self.blender)
        form.addRow("Format", self.format)
        form.addRow("Camera", self.camera)
        form.addRow("Width", self.width)
        form.addRow("Height", self.height)
        form.addRow("FPS", self.fps)
        form.addRow("Pixel size", self.pixel_size)
        form.addRow(self.depth_pass)
        form.addRow("Anim name", self.anim_name)
        self._layout.addWidget(basic)

        skel = QGroupBox("Skeleton generator")
        sform = QFormLayout(skel)
        sform.addRow(self.skeleton_gen)
        sform.addRow("Height (cm)", self.height_cm)
        sform.addRow("Weight (kg)", self.weight_kg)
        sform.addRow(self.with_ik)
        sform.addRow(self.mesh_bodies)
        self._layout.addWidget(skel)

        ws = QGroupBox("SHADED world states & variants")
        wform = QFormLayout(ws)
        wform.addRow("World states", self.world_states)
        wform.addRow("Variants", self.variants)
        self._layout.addWidget(ws)

    def _on_run(self):
        if not self.model.text():
            QMessageBox.warning(self, "Missing input", "A Model FBX is required.")
            return

        ns = SimpleNamespace(
            model=self.model.text(),
            anim=self.anim.text() or None,
            output=self.output.text() or None,
            format=self.format.currentText(),
            width=self.width.value(),
            height=self.height.value(),
            fps=self.fps.value(),
            camera=self.camera.currentText(),
            pixel_size=self.pixel_size.value(),
            blender=self.blender.text() or None,
            anim_name=self.anim_name.text() or None,
            skeleton_generator=self.skeleton_gen.isChecked(),
            height_cm=self.height_cm.value(),
            weight_kg=self.weight_kg.value(),
            with_ik=self.with_ik.isChecked(),
            mesh_bodies=self.mesh_bodies.isChecked(),
            depth_pass=self.depth_pass.isChecked(),
            variants=self.variants.text() or None,
            world_states=self.world_states.text() or None,
        )

        # Gracefully handle a missing Blender before launching the job.
        from core.renderer import Renderer, RendererConfig

        ok, version = Renderer(RendererConfig(blender_path=ns.blender)).check()
        if not ok:
            QMessageBox.warning(
                self,
                "Blender required",
                f"Rendering requires Blender, but it was not found.\n\nDetails: {version}",
            )
            return

        self._emit(lambda: cmd_render(ns))


# ── analyze tab ────────────────────────────────────────────────────────────────

class AnalyzeTab(_CommandTab):
    def _build_controls(self):
        self.sheet = _Field("Sheet", "file", "reference sprite sheet")
        self.api_key = QLineEdit()
        self.api_key.setPlaceholderText("ANTHROPIC_API_KEY (optional)")
        box = QGroupBox("Analyze")
        form = QFormLayout(box)
        form.addRow(self.sheet)
        form.addRow("API key", self.api_key)
        self._layout.addWidget(box)

    def _on_run(self):
        if not self.sheet.text():
            QMessageBox.warning(self, "Missing input", "A sheet image is required.")
            return
        ns = SimpleNamespace(
            sheet=self.sheet.text(),
            api_key=self.api_key.text() or None,
        )
        self._emit(lambda: cmd_analyze(ns))


# ── mocap tab ──────────────────────────────────────────────────────────────────

class MocapTab(_CommandTab):
    def _build_controls(self):
        self.video = _Field("Video", "file", "input video")
        self.output = _Field("Output BVH", "file", "output.bvh (optional)")
        box = QGroupBox("Motion capture")
        form = QFormLayout(box)
        form.addRow(self.video)
        form.addRow(self.output)
        self._layout.addWidget(box)

    def _on_run(self):
        if not self.video.text():
            QMessageBox.warning(self, "Missing input", "A video file is required.")
            return
        ns = SimpleNamespace(
            video=self.video.text(),
            output=self.output.text() or None,
        )
        self._emit(lambda: cmd_mocap(ns))


# ── video2sprite tab ───────────────────────────────────────────────────────────

class Video2SpriteTab(_CommandTab):
    def _build_controls(self):
        self.video = _Field("Video", "file", "input video")
        self.output = _Field("Output", "file", "output (optional)")
        self.format = QComboBox()
        self.format.addItems(["sprite_sheet", "gif", "frames"])
        self.width = QSpinBox()
        self.width.setRange(1, 4096)
        self.width.setValue(64)
        self.height = QSpinBox()
        self.height.setRange(1, 4096)
        self.height.setValue(64)
        self.colors = QSpinBox()
        self.colors.setRange(2, 256)
        self.colors.setValue(16)
        self.keyframes = QCheckBox("Keyframes only")

        box = QGroupBox("Video → sprite")
        form = QFormLayout(box)
        form.addRow(self.video)
        form.addRow(self.output)
        form.addRow("Format", self.format)
        form.addRow("Width", self.width)
        form.addRow("Height", self.height)
        form.addRow("Colors", self.colors)
        form.addRow(self.keyframes)
        self._layout.addWidget(box)

    def _on_run(self):
        if not self.video.text():
            QMessageBox.warning(self, "Missing input", "A video file is required.")
            return
        ns = SimpleNamespace(
            video=self.video.text(),
            output=self.output.text() or None,
            format=self.format.currentText(),
            width=self.width.value(),
            height=self.height.value(),
            colors=self.colors.value(),
            keyframes=self.keyframes.isChecked(),
        )
        self._emit(lambda: cmd_video2sprite(ns))


# ── spritesheet tab ────────────────────────────────────────────────────────────

class SpriteSheetTab(_CommandTab):
    def _build_controls(self):
        self.action = QComboBox()
        self.action.addItems(["list", "export", "extract"])
        self.image = _Field("Image", "file", "sprite sheet PNG")
        self.manifest = _Field("Manifest", "file", "manifest JSON")
        self.anim = QLineEdit()
        self.anim.setPlaceholderText("animation name (export)")
        self.frame = QLineEdit()
        self.frame.setPlaceholderText("frame id (extract)")
        self.format = QComboBox()
        self.format.addItems(["sprite_sheet", "gif"])
        self.output = _Field("Output", "file", "output (optional)")

        box = QGroupBox("Sprite sheet")
        form = QFormLayout(box)
        form.addRow("Action", self.action)
        form.addRow(self.image)
        form.addRow(self.manifest)
        form.addRow("Anim", self.anim)
        form.addRow("Frame", self.frame)
        form.addRow("Format", self.format)
        form.addRow(self.output)
        self._layout.addWidget(box)

    def _on_run(self):
        if not self.image.text() or not self.manifest.text():
            QMessageBox.warning(self, "Missing input", "Image and manifest are required.")
            return
        ns = SimpleNamespace(
            action=self.action.currentText(),
            image=self.image.text(),
            manifest=self.manifest.text(),
            anim=self.anim.text() or None,
            frame=self.frame.text() or None,
            format=self.format.currentText(),
            output=self.output.text() or None,
        )
        self._emit(lambda: cmd_spritesheet(ns))


# ── main window ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SWIFT — Sprite Animation AI Workflow")
        self.resize(880, 720)

        self.tabs = QTabWidget()
        self.render_tab = RenderTab("Render")
        self.analyze_tab = AnalyzeTab("Analyze")
        self.mocap_tab = MocapTab("Run mocap")
        self.v2s_tab = Video2SpriteTab("Convert")
        self.ss_tab = SpriteSheetTab("Run")
        self.tabs.addTab(self.render_tab, "Render")
        self.tabs.addTab(self.analyze_tab, "Analyze")
        self.tabs.addTab(self.mocap_tab, "Mocap")
        self.tabs.addTab(self.v2s_tab, "Video2Sprite")
        self.tabs.addTab(self.ss_tab, "SpriteSheet")

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(150)
        self.log.setMaximumHeight(220)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(QLabel("Log / Progress"))
        layout.addWidget(self.log)
        self.setCentralWidget(central)

        self._workers = []
        for tab in (self.render_tab, self.analyze_tab, self.mocap_tab,
                    self.v2s_tab, self.ss_tab):
            tab.run_requested.connect(self._run)

    def _append_log(self, text):
        self.log.moveCursor(self.log.textCursor().End)
        self.log.insertPlainText(text)
        self.log.ensureCursorVisible()

    def _run(self, fn):
        worker = _Worker(fn)
        worker.log_line.connect(self._append_log)
        worker.finished.connect(lambda _: self._append_log("\n[done]\n"))
        worker.errored.connect(lambda msg: self._append_log(f"\n[ERROR] {msg}\n"))
        self._workers.append(worker)
        worker.finished.connect(lambda _: self._workers.remove(worker))
        worker.errored.connect(lambda _: self._workers.remove(worker))
        worker.start()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
