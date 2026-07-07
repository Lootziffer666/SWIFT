"""
Critter Crosser – interactive views (PySide6).

Each view is a thin QWidget that paints `StudioModel.render()` data and pushes
user interaction back into the model. No engine logic lives here.
"""
from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PySide6.QtWidgets import QWidget

from core.critter.geometry import Vec2


class Viewport(QWidget):
    """Creatures + IK chain + wobbly tower. Drag the red handle to move the
    IK end-effector target."""

    def __init__(self, model):
        super().__init__()
        self.model = model
        self.setMinimumSize(420, 360)
        self._dragging = False

    def _ox(self):
        return self.width() / 2

    def _oy(self):
        return self.height() * 0.65

    def _pt(self, sx, sy):
        return QPointF(sx + self._ox(), sy + self._oy())

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(24, 26, 32))
        scene = self.model.render()

        # Creatures (body segment spheres, colored by palette index).
        palette = self.model.palette.palette
        for idx, c in enumerate(scene.creatures):
            col = palette[idx % len(palette)] if palette else None
            qc = QColor(int(col.r * 255), int(col.g * 255), int(col.b * 255)) if col else QColor(200, 200, 200)
            for (sx, sy, r) in c["bodies"]:
                pt = self._pt(sx, sy)
                p.setBrush(QBrush(qc))
                p.setPen(Qt.NoPen)
                p.drawEllipse(pt, r, r)

        # Wobbly tower.
        wob = scene.ik.get("wobbly", [])
        if len(wob) > 1:
            p.setPen(QPen(QColor(120, 220, 160), 3))
            for i in range(len(wob) - 1):
                a = self._pt(*wob[i]); b = self._pt(*wob[i + 1])
                p.drawLine(a, b)

        # IK chain.
        joints = scene.ik.get("joints", [])
        if len(joints) > 1:
            p.setPen(QPen(QColor(230, 230, 230), 3))
            for i in range(len(joints) - 1):
                a = self._pt(*joints[i]); b = self._pt(*joints[i + 1])
                p.drawLine(a, b)
            p.setBrush(QBrush(QColor(230, 230, 230)))
            for j in joints:
                pt = self._pt(*j); p.drawEllipse(pt, 4, 4)
            # target handle
            tx, ty = scene.ik["target"]
            p.setBrush(QBrush(QColor(240, 80, 80)))
            p.drawEllipse(self._pt(tx, ty), 7, 7)

        p.end()

    def mousePressEvent(self, event):
        scene = self.model.render()
        tx, ty = scene.ik["target"]
        hx, hy = tx + self._ox(), ty + self._oy()
        if (event.position() - QPointF(hx, hy)).manhattanLength() < 12:
            self._dragging = True

    def mouseMoveEvent(self, event):
        if self._dragging:
            sx = event.position().x() - self._ox()
            sy = event.position().y() - self._oy()
            self.model.set_ik_target_screen(sx, sy)
            self.model.solve_ik()
            self.update()

    def mouseReleaseEvent(self, event):
        self._dragging = False


class FlowView(QWidget):
    """Flow-field grid. Left-click sets the goal; shift-click paints a costly
    'street'; right-click toggles a blocked tile."""

    def __init__(self, model):
        super().__init__()
        self.model = model
        self.setMinimumSize(300, 240)

    def _cell(self):
        return 18.0

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(20, 22, 28))
        scene = self.model.render()
        cols = scene.flow["cols"]; rows = scene.flow["rows"]
        # grid
        p.setPen(QPen(QColor(60, 64, 72), 1))
        for x in range(cols + 1):
            p.drawLine(40 + x * self._cell(), 40, 40 + x * self._cell(), 40 + rows * self._cell())
        for y in range(rows + 1):
            p.drawLine(40, 40 + y * self._cell(), 40 + cols * self._cell(), 40 + y * self._cell())
        # flow arrows
        p.setPen(QPen(QColor(90, 170, 230), 2))
        for (sx, sy, dx, dy) in scene.flow["cells"]:
            ex, ey = sx + dx * 7, sy + dy * 7
            p.drawLine(QPointF(sx, sy), QPointF(ex, ey))
        # npcs
        p.setBrush(QBrush(QColor(120, 200, 255)))
        p.setPen(Qt.NoPen)
        for (sx, sy) in scene.flow["npcs"]:
            p.drawEllipse(QPointF(sx, sy), 3, 3)
        # goals
        p.setBrush(QBrush(QColor(255, 220, 80)))
        for (sx, sy) in scene.flow["goals"]:
            p.drawRect(int(sx) - 5, int(sy) - 5, 10, 10)
        p.end()

    def _tile(self, event):
        return self.model.screen_to_tile(event.position().x(), event.position().y())

    def mousePressEvent(self, event):
        tx, ty = self._tile(event)
        if not (0 <= tx < self.model.ff_config.width and 0 <= ty < self.model.ff_config.height):
            return
        if event.button() == Qt.RightButton:
            cur = self.model.flow.blocked[ty][tx]
            self.model.set_tile_blocked(tx, ty, not cur)
        elif event.modifiers() & Qt.ShiftModifier:
            self.model.set_tile_cost(tx, ty, 100)
        else:
            self.model.set_flow_goal(tx, ty)
        self.update()


class PerlinView(QWidget):
    """Animated Perlin-noise preview (scroll / distort / stretch)."""

    def __init__(self, model):
        super().__init__()
        self.model = model
        self.setMinimumSize(220, 220)

    def paintEvent(self, event):
        p = QPainter(self)
        grid = self.model.render().perlin["grid"]
        n = len(grid)
        if n == 0:
            return
        cell = min(self.width(), self.height()) / n
        for j in range(n):
            for i in range(n):
                v = grid[j][i]
                shade = int(max(0, min(255, (v + 1) * 127)))
                p.fillRect(int(i * cell), int(j * cell), int(cell) + 1, int(cell) + 1,
                           QColor(shade, shade, shade))
        p.end()


class StickView(QWidget):
    """Twin-stick: left-drag = movement, right-drag = aim."""

    def __init__(self, model):
        super().__init__()
        self.model = model
        self.setMinimumSize(200, 200)
        self._aim = False

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(20, 22, 28))
        cx, cy = self.width() / 2, self.height() / 2
        p.setPen(QPen(QColor(80, 84, 92), 1))
        p.drawEllipse(QPointF(cx, cy), 70, 70)
        scene = self.model.render()
        mx, my = scene.stick["move"]
        ax, ay = scene.stick["aim"]
        # movement (green)
        p.setPen(QPen(QColor(120, 230, 140), 3))
        p.drawLine(QPointF(cx, cy), QPointF(cx + mx * 70, cy - my * 70))
        # aim (orange)
        p.setPen(QPen(QColor(240, 170, 80), 3))
        p.drawLine(QPointF(cx, cy), QPointF(cx + ax * 70, cy - ay * 70))
        p.setPen(QColor(200, 200, 200))
        p.drawText(8, 16, "side-step" if scene.stick["side"] else "facing-locked")
        p.end()

    def _set(self, event):
        cx, cy = self.width() / 2, self.height() / 2
        dx = (event.position().x() - cx) / 70.0
        dy = -(event.position().y() - cy) / 70.0
        mx, my = self.model.stick.movement.x, self.model.stick.movement.y
        ax, ay = self.model.stick.aim.x, self.model.stick.aim.y
        if self._aim:
            self.model.set_stick(mx, my, dx, dy)
        else:
            self.model.set_stick(dx, dy, ax, ay)
        self.update()

    def mousePressEvent(self, event):
        self._aim = (event.button() == Qt.RightButton)
        self._set(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & (Qt.LeftButton | Qt.RightButton):
            self._set(event)
