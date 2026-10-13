from __future__ import annotations

import copy

import cv2
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .core import Project, Shape


def clock_text(seconds):
    minutes, seconds = divmod(max(0, seconds), 60)
    return f"{int(minutes):02d}:{seconds:06.3f}"


class Canvas(QWidget):
    selected_changed = Signal(int)
    shapes_changed = Signal(object)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(480, 300)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.image = QImage()
        self.shapes = []
        self.selected = -1
        self.drawing = False
        self.editable = True
        self.preview_index = -1
        self.divider = None
        self.gesture = None
        self.draft = None

    def set_frame(self, image, shapes, selected=-1):
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        self.image = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888).copy()
        self.shapes = copy.deepcopy(shapes)
        self.selected = selected if 0 <= selected < len(shapes) else -1
        self.preview_index = -1
        self.gesture = None
        self.draft = None
        self.update()

    def image_rect(self):
        if self.image.isNull():
            return QRectF()
        scale = min((self.width() - 28) / self.image.width(), (self.height() - 28) / self.image.height())
        w, h = self.image.width() * scale, self.image.height() * scale
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def to_image(self, point):
        rect = self.image_rect()
        scale = rect.width() / max(1, self.image.width())
        return QPointF(max(0, min(self.image.width(), (point.x() - rect.x()) / scale)),
                       max(0, min(self.image.height(), (point.y() - rect.y()) / scale)))

    def to_screen(self, x, y):
        rect = self.image_rect()
        scale = rect.width() / max(1, self.image.width())
        return QPointF(rect.x() + x * scale, rect.y() + y * scale)

    def screen_box(self, box):
        return QRectF(self.to_screen(*box[:2]), self.to_screen(*box[2:])).normalized()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#101820"))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.image.isNull():
            painter.setPen(QColor("#91a5b7"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "打开视频或图片文件夹\n\n检测手部 → 选择时间段 → 剔除无关手 → 赋动作标签")
            return
        painter.drawImage(self.image_rect(), self.image)
        if self.divider is not None:
            x = self.to_screen(self.image.width() * self.divider, 0).x()
            painter.setPen(QPen(QColor("#e3e9ef"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(x, self.image_rect().top()), QPointF(x, self.image_rect().bottom()))
        for j, shape in enumerate(self.shapes):
            color = QColor("#ffcc66" if shape.label == "hand" else "#52dab1")
            if j == self.selected:
                color = QColor("#72b7ff")
            if j == self.preview_index:
                color = QColor("#fc7fad")
            rect = self.screen_box(shape.box)
            painter.setPen(QPen(color, 3 if j == self.selected else 2))
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 25))
            painter.drawRect(rect)
            label = f"{j + 1} · {shape.label}"
            if shape.score is not None:
                label += f"  {shape.score:.2f}"
            text_width = painter.fontMetrics().horizontalAdvance(label) + 12
            badge = QRectF(rect.left(), max(self.image_rect().top(), rect.top() - 25), text_width, 24)
            painter.fillRect(badge, color)
            painter.setPen(QColor("#101820"))
            painter.drawText(badge.adjusted(6, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, label)
            if j == self.selected and self.editable:
                painter.setBrush(color)
                for point in (rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()):
                    painter.drawRect(QRectF(point.x() - 4, point.y() - 4, 8, 8))
        if self.draft is not None:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#72b7ff"), 2, Qt.PenStyle.DashLine))
            painter.drawRect(self.screen_box(self.draft))

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.image.isNull() or not self.image_rect().contains(event.position()):
            return
        self.setFocus()
        point = self.to_image(event.position())
        if self.drawing and self.editable:
            self.gesture = ("draw", point)
            self.draft = [point.x(), point.y(), point.x(), point.y()]
            return
        if self.editable and 0 <= self.selected < len(self.shapes):
            rect = self.screen_box(self.shapes[self.selected].box)
            for corner, screen_point in enumerate((rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft())):
                if (event.position() - screen_point).manhattanLength() < 14:
                    self.gesture = ("resize", point, copy.deepcopy(self.shapes[self.selected].box), corner)
                    return
        hit = -1
        # Select the smallest containing box if detections overlap.
        candidates = [j for j, shape in enumerate(self.shapes) if self.screen_box(shape.box).contains(event.position())]
        if candidates:
            hit = min(candidates, key=lambda j: self.screen_box(self.shapes[j].box).width() * self.screen_box(self.shapes[j].box).height())
        self.selected = hit
        self.selected_changed.emit(hit)
        if hit >= 0 and self.editable:
            self.gesture = ("move", point, copy.deepcopy(self.shapes[hit].box))
        self.update()

    def mouseMoveEvent(self, event):
        if self.gesture is None or not self.editable:
            return
        point = self.to_image(event.position())
        kind, start, *rest = self.gesture
        if kind == "draw":
            self.draft = [min(start.x(), point.x()), min(start.y(), point.y()),
                          max(start.x(), point.x()), max(start.y(), point.y())]
        elif kind == "move":
            old = rest[0]
            dx = min(self.image.width() - old[2], max(-old[0], point.x() - start.x()))
            dy = min(self.image.height() - old[3], max(-old[1], point.y() - start.y()))
            self.shapes[self.selected].box = [old[0] + dx, old[1] + dy, old[2] + dx, old[3] + dy]
        else:
            old, corner = rest
            box = old.copy()
            box[0 if corner in (0, 3) else 2] = point.x()
            box[1 if corner in (0, 1) else 3] = point.y()
            box = [min(box[0], box[2]), min(box[1], box[3]), max(box[0], box[2]), max(box[1], box[3])]
            self.shapes[self.selected].box = box
        self.update()

    def mouseReleaseEvent(self, event):
        if self.gesture is None:
            return
        kind = self.gesture[0]
        if kind == "draw" and self.draft is not None:
            if self.draft[2] - self.draft[0] >= 3 and self.draft[3] - self.draft[1] >= 3:
                self.shapes.append(Shape(self.draft.copy()))
                self.selected = len(self.shapes) - 1
                self.selected_changed.emit(self.selected)
                self.shapes_changed.emit(copy.deepcopy(self.shapes))
        elif kind in ("move", "resize"):
            shape = self.shapes[self.selected]
            if shape.box[2] - shape.box[0] >= 3 and shape.box[3] - shape.box[1] >= 3:
                self.shapes_changed.emit(copy.deepcopy(self.shapes))
            else:
                shape.box = self.gesture[2]
        self.gesture = None
        self.draft = None
        self.update()


class Timeline(QWidget):
    seek = Signal(float)
    range_changed = Signal(float, float)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(110)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.project: Project | None = None
        self.indices = []
        self.current = 0.0
        self.start = 0.0
        self.end = 0.0
        self.anchor = None
        self.setToolTip("单击定位；Shift + 拖动选择时间范围。绿色：有动作标签；黄色：待赋动作；灰色：空框或未检测。")

    def x_for(self, timestamp):
        duration = self.project.source.duration if self.project else 1
        return 16 + (self.width() - 32) * timestamp / max(duration, 1e-7)

    def time_for(self, x):
        duration = self.project.source.duration if self.project else 1
        return max(0, min(duration, (x - 16) / max(self.width() - 32, 1) * duration))

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#18232e"))
        if self.project is None:
            return
        duration = self.project.source.duration
        p.fillRect(QRectF(16, 36, self.width() - 32, 24), QColor("#34414f"))
        p.fillRect(QRectF(self.x_for(self.start), 32, max(2, self.x_for(self.end) - self.x_for(self.start)), 32), QColor("#224559"))
        for i in self.indices:
            frame = self.project.frames.get(i)
            color = "#4c6072"
            if frame and frame.processed:
                color = "#92a0ab" if not frame.shapes else "#f4c36b"
                if frame.shapes and all(s.label != "hand" for s in frame.shapes):
                    color = "#52dab1"
            p.setPen(QPen(QColor(color), 2))
            x = self.x_for(self.project.source.timestamp(i))
            p.drawLine(QPointF(x, 40), QPointF(x, 56))
        for s in self.project.segments:
            p.fillRect(QRectF(self.x_for(s.start), 23, max(2, self.x_for(s.end) - self.x_for(s.start)), 5), QColor("#72b7ff"))
        p.setPen(QColor("#98abba"))
        for tick in range(6):
            time = duration * tick / 5
            x = self.x_for(time)
            p.drawText(QRectF(x - 35, 69, 70, 22), Qt.AlignmentFlag.AlignCenter, clock_text(time)[:5])
        p.setPen(QPen(QColor("#72b7ff"), 2))
        p.drawLine(QPointF(self.x_for(self.current), 16), QPointF(self.x_for(self.current), 65))
        p.setPen(QColor("#d9e5ed"))
        p.drawText(16, 15, "时间轴  ·  Shift + 拖动选段")

    def mousePressEvent(self, event):
        if self.project is None:
            return
        time = self.time_for(event.position().x())
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.anchor = time
            self.range_changed.emit(time, time)
        else:
            self.seek.emit(time)

    def mouseMoveEvent(self, event):
        if self.anchor is not None:
            time = self.time_for(event.position().x())
            self.range_changed.emit(min(time, self.anchor), max(time, self.anchor))

    def mouseReleaseEvent(self, event):
        self.anchor = None
