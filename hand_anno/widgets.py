from __future__ import annotations

import copy
import math

import cv2
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .core import Project, Shape
from .icons import icon
from .theme import PALETTE as C


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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(C["bg"]))
        painter.setPen(QPen(QColor(C["video_line"]), 1))
        painter.setBrush(QColor(C["video"]))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
        if self.image.isNull():
            center = self.rect().center()
            painter.drawPixmap(center.x() - 32, center.y() - 82, icon("video", C["accent"], 64).pixmap(64, 64))
            painter.setPen(QColor(C["muted"]))
            painter.drawText(self.rect().adjusted(20, 52, -20, 0), Qt.AlignmentFlag.AlignCenter,
                             "打开视频或图片目录，开始标注\n\n自动检测  /  选段删手  /  批量赋动作")
            return
        painter.drawImage(self.image_rect(), self.image)
        if self.divider is not None:
            x = self.to_screen(self.image.width() * self.divider, 0).x()
            painter.setPen(QPen(QColor(C["text"]), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(x, self.image_rect().top()), QPointF(x, self.image_rect().bottom()))
        for j, shape in enumerate(self.shapes):
            color = QColor(C["warning"] if shape.label == "hand" else C["success"])
            if j == self.selected:
                color = QColor(C["accent2"])
            if j == self.preview_index:
                color = QColor(C["reference"])
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
            painter.setPen(QColor(C["on_accent"]))
            painter.drawText(badge.adjusted(6, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, label)
            if j == self.selected and self.editable:
                painter.setBrush(color)
                for point in (rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()):
                    painter.drawRect(QRectF(point.x() - 4, point.y() - 4, 8, 8))
        if self.draft is not None:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(C["accent2"]), 2, Qt.PenStyle.DashLine))
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
    view_changed = Signal(float, float)

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
        self.dragging = False
        self.view_start = 0.0
        self.view_end = 1.0
        self.setToolTip("滚轮以鼠标位置为中心缩放；下方滚动条平移视区。左键拖动预览；Shift + 左键拖动选段并预览。绿色：1 个手框；黄色：多个手框；灰色：空框或未检测。")

    @property
    def view_span(self):
        return max(self.view_end - self.view_start, 1e-7)

    def set_view(self, start, end):
        if self.project is None:
            return
        duration = self.project.source.duration
        minimum_span = min(duration, max(0.1, 2 / self.project.source.fps))
        span = min(duration, max(minimum_span, end - start))
        start = (start + end - span) / 2
        self.view_start = max(0, min(duration - span, start))
        self.view_end = self.view_start + span
        self.update()
        self.view_changed.emit(self.view_start, self.view_end)

    def reset_view(self):
        if self.project is not None:
            self.set_view(0, self.project.source.duration)

    def zoom(self, factor, anchor=None):
        if self.project is None or self.dragging or factor <= 0:
            return
        if anchor is None:
            anchor = self.current if self.view_start <= self.current <= self.view_end else (self.view_start + self.view_end) / 2
        fraction = max(0, min(1, (anchor - self.view_start) / self.view_span))
        duration = self.project.source.duration
        minimum_span = min(duration, max(0.1, 2 / self.project.source.fps))
        span = min(duration, max(minimum_span, self.view_span / factor))
        start = anchor - fraction * span
        self.set_view(start, start + span)

    def focus_range(self, start, end):
        if start > end:
            raise ValueError("起点大于终点，请先调整时间范围。")
        padding = max((end - start) * 0.1, 0.01)
        self.set_view(start - padding, end + padding)

    def pan_to(self, fraction):
        if self.project is not None:
            start = max(0, min(1, fraction)) * (self.project.source.duration - self.view_span)
            self.set_view(start, start + self.view_span)

    def ensure_visible(self, time):
        if self.project is None or self.dragging:
            return
        if time < self.view_start or time > self.view_end:
            start = time - self.view_span * (0.1 if time < self.view_start else 0.9)
            self.set_view(start, start + self.view_span)

    def x_for(self, timestamp):
        return 16 + (self.width() - 32) * (timestamp - self.view_start) / self.view_span

    def time_for(self, x):
        fraction = max(0, min(1, (x - 16) / max(self.width() - 32, 1)))
        return self.view_start + fraction * self.view_span

    def wheelEvent(self, event):
        if self.project is None or self.dragging:
            event.ignore()
            return
        steps = event.angleDelta().y() / 120
        if steps:
            self.zoom(1.25 ** max(-10, min(10, steps)), self.time_for(event.position().x()))
            event.accept()
        else:
            event.ignore()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(C["bg"]))
        p.setPen(QPen(QColor(C["line"]), 1))
        p.setBrush(QColor(C["panel"]))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 9, 9)
        if self.project is None:
            return
        p.fillRect(QRectF(16, 36, self.width() - 32, 24), QColor(C["panel3"]))
        p.save()
        p.setClipRect(QRectF(16, 23, self.width() - 32, 42))
        p.fillRect(QRectF(self.x_for(self.start), 32, max(2, self.x_for(self.end) - self.x_for(self.start)), 32), QColor(C["badge"]))
        for i in self.indices:
            timestamp = self.project.source.timestamp(i)
            if not self.view_start <= timestamp <= self.view_end:
                continue
            frame = self.project.frames.get(i)
            color = C["subtle"]
            if frame and len(frame.shapes) == 1:
                color = C["success"]
            elif frame and frame.shapes:
                color = C["warning"]
            elif frame and frame.processed:
                color = C["muted"]
            p.setPen(QPen(QColor(color), 2))
            x = self.x_for(timestamp)
            p.drawLine(QPointF(x, 40), QPointF(x, 56))
        for s in self.project.segments:
            p.fillRect(QRectF(self.x_for(s.start), 23, max(2, self.x_for(s.end) - self.x_for(s.start)), 5), QColor(C["accent2"]))
        p.restore()
        p.setPen(QColor(C["muted"]))
        desired_step = self.view_span / max(2, (self.width() - 32) / 100)
        base = 10 ** math.floor(math.log10(desired_step))
        tick_step = next(multiplier * base for multiplier in (1, 2, 5, 10) if multiplier * base >= desired_step)
        first_tick = math.ceil(self.view_start / tick_step - 1e-8)
        last_tick = math.floor(self.view_end / tick_step + 1e-8)
        for tick in range(first_tick, last_tick + 1):
            time = tick * tick_step
            x = self.x_for(time)
            label = clock_text(time) if tick_step < 1 else clock_text(time)[:5]
            left = max(0, min(self.width() - 90, x - 45))
            p.drawText(QRectF(left, 69, 90, 22), Qt.AlignmentFlag.AlignCenter, label)
        p.setPen(QPen(QColor(C["accent"]), 2))
        if self.view_start <= self.current <= self.view_end:
            p.drawLine(QPointF(self.x_for(self.current), 16), QPointF(self.x_for(self.current), 65))
            p.setBrush(QColor(C["accent"]))
            p.drawEllipse(QPointF(self.x_for(self.current), 18), 3, 3)
        p.setPen(QColor(C["text"]))
        p.drawText(16, 15, "时间轴  ·  左键拖动预览  ·  Shift + 拖动选段并预览")

    def mousePressEvent(self, event):
        if self.project is None or event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus()
        self.dragging = True
        time = self.time_for(event.position().x())
        self.anchor = time if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else None
        self._drag_to(time)

    def _drag_to(self, time):
        if self.anchor is not None:
            self.range_changed.emit(min(time, self.anchor), max(time, self.anchor))
        self.seek.emit(time)

    def mouseMoveEvent(self, event):
        if self.dragging and self.project is not None:
            self._drag_to(self.time_for(event.position().x()))

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.dragging:
            return
        if self.project is not None:
            self._drag_to(self.time_for(event.position().x()))
        self.dragging = False
        self.anchor = None
