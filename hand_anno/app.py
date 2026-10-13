from __future__ import annotations

import bisect
import copy
import hashlib
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QAction, QFont, QFontDatabase, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSlider, QSpinBox,
    QSizePolicy, QSplitter, QVBoxLayout, QWidget,
)

from .core import (Cancelled, EditHistory, FrameReader, Project, SamplingSegment,
                   export_project, side_indices, track_reference)
from .detector import DEFAULT_MODEL, ROOT, detect_project
from .widgets import Canvas, Timeline, clock_text


STYLE = """
QMainWindow, QWidget { background: #f3f6f9; color: #233548; font-size: 13px; }
QGroupBox { background: white; border: 1px solid #d9e2e9; border-radius: 8px; margin-top: 16px; padding: 12px 10px 9px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; top: 1px; padding: 0 5px; }
QGroupBox QWidget { background: transparent; }
QPushButton { background: #fff; border: 1px solid #cbd8e2; border-radius: 5px; padding: 7px 10px; }
QPushButton:hover { background: #e8f1fa; border-color: #6aa5d9; }
QPushButton:disabled { color: #9ba7b2; background: #edf0f4; }
QPushButton[primary="true"] { background: #1968a4; color: white; border-color: #1968a4; font-weight: 600; }
QPushButton[danger="true"] { color: #af3b3b; border-color: #e4b9b9; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: white; border: 1px solid #cbd8e2; border-radius: 4px; padding: 5px; min-height: 20px; }
QListWidget { background: #f8fafc; border: 1px solid #d9e2e9; border-radius: 4px; }
QProgressBar { border: 1px solid #d9e2e9; border-radius: 4px; text-align: center; background: #e7eef4; }
QProgressBar::chunk { background: #3b8abc; border-radius: 3px; }
QToolBar { background: white; border-bottom: 1px solid #d9e2e9; spacing: 8px; padding: 8px; }
QToolButton { background: transparent; border-radius: 5px; padding: 6px 9px; }
QToolButton:hover { background: #e8f1fa; }
QScrollArea { border: none; }
QSlider::groove:horizontal { height: 5px; background: #d3dee7; border-radius: 2px; }
QSlider::handle:horizontal { width: 15px; margin: -5px 0; background: #1968a4; border-radius: 7px; }
"""


class Worker(QThread):
    progress = Signal(int, int, str)
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, operation, parent):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            value = self.operation(self.progress.emit, self.isInterruptionRequested)
            self.result.emit(value)
        except Cancelled as error:
            self.failed.emit(str(error))
        except Exception as error:
            traceback.print_exc()
            self.failed.emit(f"{type(error).__name__}: {error}")


class CollapsibleGroup(QGroupBox):
    """Click the title to collapse setup controls while editing annotations."""
    def __init__(self, title):
        super().__init__()
        self.base_title = title
        self.collapsed = False
        self.setTitle("−  " + title)
        self.body = QWidget()
        root = QVBoxLayout(self)
        root.addWidget(self.body)
        self.content = QVBoxLayout(self.body)
        self.content.setContentsMargins(0, 0, 0, 0)

    def set_collapsed(self, collapsed):
        self.collapsed = collapsed
        self.body.setVisible(not collapsed)
        self.setTitle(("+  " if collapsed else "−  ") + self.base_title)
        self.setMinimumHeight(32 if collapsed else 0)
        self.setMaximumHeight(32 if collapsed else 16777215)

    def mousePressEvent(self, event):
        if event.position().y() < 28:
            self.set_collapsed(not self.collapsed)
        else:
            super().mousePressEvent(event)


def spin(value=0.0, maximum=100000, minimum=0.0, decimals=3):
    widget = QDoubleSpinBox()
    widget.setRange(minimum, maximum)
    widget.setDecimals(decimals)
    widget.setValue(value)
    widget.setKeyboardTracking(False)
    return widget


def row(*widgets):
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    for widget in widgets:
        layout.addWidget(widget)
    return container


def button(text, callback, primary=False, danger=False):
    widget = QPushButton(text)
    widget.clicked.connect(callback)
    if primary:
        widget.setProperty("primary", True)
    if danger:
        widget.setProperty("danger", True)
    return widget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("手部动作标注工作台")
        self.resize(1500, 1000)
        self.project = None
        self.history = None
        self.reader = None
        self.indices = []
        self.position = 0
        self.project_path = None
        self.recovery_path = None
        self.reference = None
        self.track = None
        self.worker = None
        self.job_kind = None
        self.pending_close = False
        self.is_loading = False
        self.dirty = False
        self._build_ui()
        self.play_timer = QTimer(self)
        self.play_timer.setSingleShot(True)
        self.play_timer.timeout.connect(self._play_step)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(800)
        self.save_timer.timeout.connect(self._autosave)
        self._shortcuts()

    def _build_ui(self):
        toolbar = self.addToolBar("文件")
        toolbar.setMovable(False)
        self.file_actions = []
        for title, callback, shortcut in (
            ("打开视频", self.open_video, "Ctrl+O"), ("打开图片目录", self.open_images, None),
            ("打开项目", self.open_project, None), ("保存项目", self.save_project, "Ctrl+S"),
            ("导出数据集", self.export, "Ctrl+E"), ("撤销", self.undo, "Ctrl+Z"),
            ("重做", self.redo, "Ctrl+Shift+Z"),
        ):
            action = QAction(title, self)
            action.triggered.connect(callback)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            toolbar.addAction(action)
            self.file_actions.append(action)
        toolbar.addSeparator()
        toolbar.addAction("使用说明", self.show_help)
        central = QWidget()
        main = QVBoxLayout(central)
        main.setContentsMargins(16, 10, 16, 12)
        self.source_label = QLabel("手部动作标注工作台  /  SOP 视频标注")
        self.source_label.setStyleSheet("font-size: 18px; font-weight: 600; padding: 5px;")
        main.addWidget(self.source_label)
        self.source_info = QLabel("选择素材，按时间段批量处理手框。所有操作在本地完成。")
        main.addWidget(self.source_info)
        splitter = QSplitter()
        left = QWidget()
        self.preview_panel = left
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        self.canvas = Canvas()
        self.canvas.selected_changed.connect(self._selection_changed)
        self.canvas.shapes_changed.connect(self._canvas_edited)
        left_layout.addWidget(self.canvas, 1)
        self.frame_info = QLabel("未打开素材")
        self.frame_info.setStyleSheet("padding: 4px 0;")
        left_layout.addWidget(self.frame_info)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.valueChanged.connect(self.show_position)
        left_layout.addWidget(self.slider)
        self.play_button = button("播放 · Space", self.toggle_play)
        self.draw_button = QCheckBox("补框 · R")
        self.draw_button.toggled.connect(self._drawing_changed)
        self.speed = QComboBox()
        for text, value in (("0.5×", 0.5), ("1×", 1), ("2×", 2), ("4×", 4)):
            self.speed.addItem(text, value)
        self.speed.setCurrentIndex(1)
        left_layout.addWidget(row(button("上一帧 · A", lambda: self.step(-1)), self.play_button,
                                  button("下一帧 · D", lambda: self.step(1)), self.speed,
                                  self.draw_button, button("删除所选框 · Del", self.delete_current)))
        self.timeline = Timeline()
        self.timeline.seek.connect(self.seek_time)
        self.timeline.range_changed.connect(self.set_range)
        left_layout.addWidget(self.timeline)
        self.summary = QLabel("时间轴：蓝色为抽帧特例段；黄色为待赋动作；绿色为已赋动作。")
        left_layout.addWidget(self.summary)
        self.box_list = QListWidget()
        self.box_list.setMaximumHeight(105)
        self.box_list.currentRowChanged.connect(self._list_selected)
        left_layout.addWidget(self.box_list)
        splitter.addWidget(left)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(370)
        self.controls = QWidget()
        self.controls.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        control_layout = QVBoxLayout(self.controls)
        control_layout.setContentsMargins(4, 0, 4, 0)
        # The range is shared by sampling, detection, deletion and action assignment.
        group, layout = self._group("1  选择时间范围（秒）")
        self.start = spin()
        self.end = spin()
        self.start.valueChanged.connect(self.range_updated)
        self.end.valueChanged.connect(self.range_updated)
        layout.addWidget(row(QLabel("起"), self.start, QLabel("止"), self.end))
        layout.addWidget(row(button("设为起点 · I", self.start_here), button("设为终点 · O", self.end_here)))
        layout.addWidget(button("选择整个素材", self.select_all))
        self.range_info = QLabel("范围内 0 帧")
        layout.addWidget(self.range_info)
        control_layout.addWidget(group)
        group, layout = self._group("2  抽帧计划（可分段设置）")
        self.sampling_group = group
        self.default_fps = spin(5, 240, 0.01, 2)
        self.default_fps.valueChanged.connect(self.default_sampling_changed)
        layout.addWidget(row(QLabel("默认 FPS"), self.default_fps))
        self.segment_fps = spin(10, 240, 0.01, 2)
        layout.addWidget(row(QLabel("当前范围 FPS"), self.segment_fps))
        layout.addWidget(button("将当前时间范围加入抽帧计划", self.add_segment))
        self.segment_list = QListWidget()
        self.segment_list.setFixedHeight(78)
        layout.addWidget(self.segment_list)
        layout.addWidget(row(button("移除所选段", self.remove_segment), button("清空分段", self.clear_segments)))
        hint = QLabel("区间使用 [起点, 终点)，不能重叠；其余时间使用默认 FPS。\n改动抽帧计划会保留已有标注，导出仅包含当前抽帧。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        control_layout.addWidget(group)
        group, layout = self._group("3  手部模型初次打标")
        self.detector_group = group
        self.model_path = QLineEdit(str(DEFAULT_MODEL))
        layout.addWidget(row(self.model_path, button("选择", self.choose_model)))
        self.confidence = spin(0.55, 0.99, 0.01, 2)
        self.device = QComboBox()
        for label, value in (("自动（优先 GPU）", "auto"), ("GPU 0", "0"), ("CPU", "cpu")):
            self.device.addItem(label, value)
        layout.addWidget(row(QLabel("置信度"), self.confidence, self.device))
        self.overwrite = QCheckBox("重新检测并覆盖范围内已有标注（可撤销）")
        layout.addWidget(self.overwrite)
        layout.addWidget(button("检测所选时间范围", self.detect, primary=True))
        control_layout.addWidget(group)
        group, layout = self._group("4  剔除无关手")
        self.position_method = QComboBox()
        self.position_method.addItem("相对位置：删除最左 / 最右的一只", "relative")
        self.position_method.addItem("画面分区：按可调分界线删除", "divider")
        self.position_method.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.position_method.setMinimumContentsLength(12)
        self.position_method.currentIndexChanged.connect(self._divider_changed)
        layout.addWidget(self.position_method)
        self.divider = spin(50, 100, 0, 1)
        self.divider.valueChanged.connect(self._divider_changed)
        layout.addWidget(row(QLabel("分界线（画面宽度 %）"), self.divider))
        layout.addWidget(row(button("删除画面左手", lambda: self.delete_side("left"), danger=True),
                             button("删除画面右手", lambda: self.delete_side("right"), danger=True)))
        hint = QLabel("相对模式：有两只以上时取最左 / 最右框；只有一只时按分界线判断。\n手交叉或遮挡时，使用下方参考手跟踪。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.reference_info = QLabel("参考手：在画面中点选手框，再设为参考")
        self.reference_info.setWordWrap(True)
        layout.addWidget(self.reference_info)
        layout.addWidget(button("将当前所选手框设为参考", self.set_reference))
        self.max_gap = spin(0.8, 10, 0.05, 2)
        layout.addWidget(row(QLabel("允许失联时间（秒）"), self.max_gap))
        self.max_gap.valueChanged.connect(self.clear_track)
        layout.addWidget(row(button("预览跟踪范围", self.preview_track), button("删除跟踪到的手", self.delete_track, danger=True)))
        self.track_info = QLabel("粉色框显示跟踪目标；遇到歧义会停止该方向。")
        self.track_info.setWordWrap(True)
        layout.addWidget(self.track_info)
        control_layout.addWidget(group)
        group, layout = self._group("5  批量赋动作标签")
        self.action_name = QComboBox()
        self.action_name.setEditable(True)
        self.action_name.addItems(["", "拿取零件", "放置零件", "装配", "拧螺丝", "检查"])
        self.action_name.setCurrentIndex(0)
        self.action_name.lineEdit().setPlaceholderText("输入动作名，或选择常用动作")
        layout.addWidget(self.action_name)
        self.label_scope = QComboBox()
        for label, value in (("范围内所有保留手框", "all"), ("范围内画面左手", "left"),
                             ("范围内画面右手", "right"), ("参考手跟踪结果", "track")):
            self.label_scope.addItem(label, value)
        layout.addWidget(self.label_scope)
        layout.addWidget(button("为时间范围赋动作标签", self.apply_label, primary=True))
        layout.addWidget(button("仅修改当前所选框的动作", self.label_current))
        control_layout.addWidget(group)
        control_layout.addStretch()
        scroll.setWidget(self.controls)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([1050, 390])
        main.addWidget(splitter, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.cancel_button = button("取消任务", self.cancel_job)
        self.cancel_button.setEnabled(False)
        main.addWidget(row(self.progress, self.cancel_button))
        self.message = QLabel("就绪  ·  Ctrl+S 保存项目；标注修改同时自动保存恢复副本。")
        self.message.setWordWrap(True)
        main.addWidget(self.message)
        self.setCentralWidget(central)

    @staticmethod
    def _group(title):
        group = CollapsibleGroup(title)
        return group, group.content

    def _shortcuts(self):
        self.shortcuts = []
        for key, callback in (("A", lambda: self.step(-1)), ("D", lambda: self.step(1)),
                              ("Space", self.toggle_play), ("I", self.start_here), ("O", self.end_here),
                              ("Delete", self.delete_current), ("R", lambda: self.draw_button.toggle())):
            shortcut = QShortcut(QKeySequence(key), self.preview_panel)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(lambda cb=callback: self._shortcut_action(cb))
            self.shortcuts.append(shortcut)

    def _shortcut_action(self, callback):
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox)):
            return
        callback()

    def report(self, text):
        self.message.setText(text)

    def problem(self, error):
        self.report(str(error))
        QMessageBox.warning(self, "操作未完成", str(error))

    def ready(self):
        if self.project is None:
            self.report("请先打开视频、图片目录或项目。")
            return False
        return not self.busy()

    def busy(self):
        return self.worker is not None and self.worker.isRunning()

    def open_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择视频", str(ROOT), "视频 (*.mp4 *.avi *.webm *.mov *.mkv *.m4v);;所有文件 (*)")
        if path:
            self.load_source(path)

    def open_images(self):
        path = QFileDialog.getExistingDirectory(self, "选择抽帧图片目录", str(ROOT))
        if not path:
            return
        fps, ok = QInputDialog.getDouble(self, "图片序列时间轴", "原图片序列 FPS（有 manifest.json 时自动使用原时间戳）：", 5, 0.01, 240, 3)
        if ok:
            self.load_source(path, fps)

    def load_source(self, path, folder_fps=5.0, restore=True):
        if self.busy():
            return
        try:
            project = Project.open(path, folder_fps)
            digest = hashlib.sha256(project.source.path.encode()).hexdigest()[:10]
            recovery = ROOT / "projects" / f"recovery_{digest}.handproj"
            if restore and recovery.exists():
                answer = QMessageBox.question(self, "发现恢复副本", "此素材存在自动保存的项目，是否恢复标注和抽帧计划？")
                if answer == QMessageBox.StandardButton.Yes:
                    project = Project.load(recovery)
            self.set_project(project)
        except Exception as error:
            self.problem(error)

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开标注项目", str(ROOT / "projects"), "标注项目 (*.handproj)")
        if path:
            self.load_project(path)

    def load_project(self, path):
        try:
            self.set_project(Project.load(path))
            self.project_path = Path(path)
            self.dirty = False
            self.report(f"已打开项目：{path}")
        except Exception as error:
            self.problem(error)

    def set_project(self, project):
        if self.project is not None:
            self._autosave()
        self.stop_play()
        if self.reader:
            self.reader.close()
        self.project = project
        self.indices = []
        self.position = 0
        self.history = EditHistory(project)
        self.reader = FrameReader(project.source)
        self.project_path = None
        digest = hashlib.sha256(project.source.path.encode()).hexdigest()[:10]
        self.recovery_path = ROOT / "projects" / f"recovery_{digest}.handproj"
        self.reference = None
        self.clear_track()
        self.reference_info.setText("参考手：在画面中点选手框，再设为参考")
        self.is_loading = True
        self.default_fps.setValue(project.default_fps)
        self.start.setMaximum(project.source.duration)
        self.end.setMaximum(project.source.duration)
        self.start.setValue(0)
        self.end.setValue(project.source.duration)
        self.is_loading = False
        self.source_label.setText(Path(project.source.path).name)
        self.source_info.setText(f"{'视频' if project.source.kind == 'video' else '图片序列'}  ·  {project.source.width} × {project.source.height}  ·  "
                                 f"源帧率 {project.source.fps:.3f} FPS  ·  {project.source.count:,} 帧  ·  {clock_text(project.source.duration)}")
        self.dirty = False
        self.refresh_plan()
        self.show_position(0)
        has_annotations = any(f.processed for f in project.frames.values())
        self.sampling_group.set_collapsed(has_annotations)
        self.detector_group.set_collapsed(has_annotations)
        self.report("素材已就绪：调整抽帧计划后，点击“检测所选时间范围”。")

    def current_index(self):
        return self.indices[self.position] if self.indices else None

    def current_time(self):
        return self.project.source.timestamp(self.current_index()) if self.indices and self.project else 0

    def refresh_plan(self):
        if self.project is None:
            return
        old_time = self.current_time()
        self.indices = self.project.sample_indices()
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, len(self.indices) - 1))
        self.slider.blockSignals(False)
        self.timeline.project, self.timeline.indices = self.project, self.indices
        self.segment_list.clear()
        for s in self.project.segments:
            self.segment_list.addItem(f"{s.start:.3f} → {s.end:.3f} 秒   |   {s.fps:g} FPS")
        self.clear_track()
        self.range_updated()
        self.seek_time(old_time)
        self.refresh_summary()

    def refresh_summary(self):
        if self.project is None:
            return
        processed = sum(self.project.frames[i].processed for i in self.indices if i in self.project.frames)
        boxes = sum(len(self.project.frames[i].shapes) for i in self.indices if i in self.project.frames)
        pending = sum(s.label == "hand" for i in self.indices if i in self.project.frames for s in self.project.frames[i].shapes)
        self.summary.setText(f"当前抽帧 {len(self.indices):,}  ·  已检测 / 编辑 {processed:,}  ·  保留框 {boxes:,}  ·  待赋动作框 {pending:,}")
        self.timeline.update()

    def show_position(self, position):
        if not self.indices or self.project is None:
            return
        self.position = max(0, min(position, len(self.indices) - 1))
        index = self.current_index()
        frame = self.project.frame(index)
        selected = self.canvas.selected if self.canvas.property("frame_index") == index else -1
        try:
            image = self.reader.read(index)
        except Exception as error:
            self.stop_play()
            self.report(str(error))
            return
        frame.height, frame.width = image.shape[:2]
        self.canvas.set_frame(image, frame.shapes, selected)
        self.canvas.setProperty("frame_index", index)
        if self.track:
            self.canvas.preview_index = self.track.matches.get(index, -1)
        self.canvas.update()
        self.slider.blockSignals(True)
        self.slider.setValue(self.position)
        self.slider.blockSignals(False)
        self.timeline.current = frame.time
        self.timeline.update()
        self.frame_info.setText(f"{clock_text(frame.time)}  /  {clock_text(self.project.source.duration)}   ·   "
                                f"抽帧 {self.position + 1:,}/{len(self.indices):,}   ·   源帧 #{index}   ·   {len(frame.shapes)} 个手框   ·   "
                                f"{'已检测 / 编辑' if frame.processed else '未检测'}")
        self.box_list.blockSignals(True)
        self.box_list.clear()
        for j, shape in enumerate(frame.shapes):
            self.box_list.addItem(f"{j + 1}   {shape.label}   |   ({shape.center[0]:.0f}, {shape.center[1]:.0f})")
        self.box_list.setCurrentRow(self.canvas.selected)
        self.box_list.blockSignals(False)

    def seek_time(self, time):
        if not self.indices:
            return
        times = [self.project.source.timestamp(i) for i in self.indices]
        p = bisect.bisect_left(times, time)
        if p >= len(times):
            p = len(times) - 1
        if p and abs(times[p - 1] - time) < abs(times[p] - time):
            p -= 1
        self.show_position(p)

    def step(self, amount):
        self.stop_play()
        self.show_position(self.position + amount)

    def toggle_play(self):
        if not self.indices:
            return
        if self.play_timer.isActive():
            self.stop_play()
        else:
            if self.position == len(self.indices) - 1:
                self.show_position(0)
            self.play_button.setText("暂停 · Space")
            self._schedule_play()

    def _schedule_play(self):
        if self.position + 1 >= len(self.indices):
            self.stop_play()
            return
        delta = self.project.source.timestamp(self.indices[self.position + 1]) - self.current_time()
        self.play_timer.start(max(10, int(1000 * delta / self.speed.currentData())))

    def _play_step(self):
        self.show_position(self.position + 1)
        self._schedule_play()

    def stop_play(self):
        if hasattr(self, "play_timer"):
            self.play_timer.stop()
        self.play_button.setText("播放 · Space")

    def set_range(self, start, end):
        self.start.blockSignals(True)
        self.end.blockSignals(True)
        self.start.setValue(start)
        self.end.setValue(end)
        self.start.blockSignals(False)
        self.end.blockSignals(False)
        self.range_updated()

    def start_here(self):
        if self.project:
            self.start.setValue(self.current_time())

    def end_here(self):
        if self.project:
            self.end.setValue(self.current_time())

    def select_all(self):
        if self.project:
            self.set_range(0, self.project.source.duration)

    def range_updated(self, *_):
        if self.is_loading or not self.project:
            return
        self.clear_track()
        self.timeline.start, self.timeline.end = self.start.value(), self.end.value()
        self.timeline.update()
        if self.start.value() <= self.end.value():
            count = len(self.range_indices())
            self.range_info.setText(f"范围内 {count:,} 个当前抽帧 · 批量操作包含起止点")
        else:
            self.range_info.setText("起点大于终点，请调整时间范围。")

    def range_indices(self):
        return self.project.range_indices(self.start.value(), self.end.value())

    def default_sampling_changed(self, *_):
        if self.is_loading or not self.ready():
            return
        self.project.default_fps = self.default_fps.value()
        self.refresh_plan()
        self.changed()

    def add_segment(self):
        if not self.ready():
            return
        end = self.end.value()
        if abs(end - self.project.source.duration) < 0.001:
            end = self.project.source.duration
        segment = SamplingSegment(self.start.value(), end, self.segment_fps.value())
        self.project.segments.append(segment)
        try:
            self.project.sample_indices()
        except Exception as error:
            self.project.segments.pop()
            self.problem(error)
            return
        self.project.segments.sort(key=lambda s: s.start)
        self.refresh_plan()
        self.changed()

    def remove_segment(self):
        if not self.ready():
            return
        index = self.segment_list.currentRow()
        if index >= 0:
            self.project.segments.pop(index)
            self.refresh_plan()
            self.changed()

    def clear_segments(self):
        if self.ready():
            self.project.segments.clear()
            self.refresh_plan()
            self.changed()

    def _divider_changed(self, *_):
        self.canvas.divider = self.divider.value() / 100 if self.position_method.currentData() == "divider" else None
        self.canvas.update()

    def _drawing_changed(self, value):
        self.canvas.drawing = value
        self.canvas.setCursor(Qt.CursorShape.CrossCursor if value else Qt.CursorShape.ArrowCursor)

    def _selection_changed(self, index):
        self.box_list.blockSignals(True)
        self.box_list.setCurrentRow(index)
        self.box_list.blockSignals(False)

    def _list_selected(self, index):
        self.canvas.selected = index
        self.canvas.update()

    def changed(self, invalidate=True):
        self.dirty = True
        if invalidate:
            self.clear_track()
            self.reference = None
            self.reference_info.setText("参考手：标注已改变，请重新选择参考框")
        self.refresh_summary()
        self.show_position(self.position)
        self.save_timer.start()

    def _canvas_edited(self, shapes):
        if self.ready():
            index = self.current_index()
            self.history.apply("手动补框 / 调整框", {index: shapes}, {index: True})
            self.changed()

    def delete_current(self):
        if not self.ready() or self.canvas.selected < 0:
            return
        index, selected = self.current_index(), self.canvas.selected
        shapes = [s for j, s in enumerate(self.project.frame(index).shapes) if j != selected]
        self.history.apply("删除当前所选框", {index: shapes})
        self.canvas.selected = -1
        self.changed()
        self.report("已删除当前手框，可使用 Ctrl+Z 撤销。")

    def delete_side(self, side):
        if not self.ready():
            return
        try:
            updates, removed = {}, 0
            for i in self.range_indices():
                frame = self.project.frame(i)
                chosen = side_indices(frame, side, self.position_method.currentData(), self.divider.value() / 100)
                if chosen:
                    updates[i] = [s for j, s in enumerate(frame.shapes) if j not in chosen]
                    removed += len(chosen)
            count = self.history.apply("批量删除画面" + ("左手" if side == "left" else "右手"), updates)
            self.changed()
            self.report(f"已在 {count} 帧中删除 {removed} 个手框，可使用 Ctrl+Z 撤销。")
        except Exception as error:
            self.problem(error)

    def set_reference(self):
        if not self.ready():
            return
        if self.canvas.selected < 0:
            self.report("请先点选画面中的一个手框。")
            return
        self.reference = (self.current_index(), self.canvas.selected)
        self.clear_track()
        self.reference_info.setText(f"参考手：{clock_text(self.current_time())} · 源帧 #{self.current_index()} · 框 {self.canvas.selected + 1}")
        self.report("参考手已设置，可预览跟踪，再批量删除或赋动作。")

    def clear_track(self, *_):
        self.track = None
        if hasattr(self, "canvas"):
            self.canvas.preview_index = -1
            self.canvas.update()
        if hasattr(self, "track_info"):
            self.track_info.setText("粉色框显示跟踪目标；遇到歧义会停止该方向。")

    def preview_track(self):
        if not self.ready():
            return False
        if self.reference is None:
            self.set_reference()
        if self.reference is None:
            return False
        try:
            self.track = track_reference(self.project, self.range_indices(), *self.reference, max_gap=self.max_gap.value())
            self.track_info.setText(f"匹配 {len(self.track.matches)} 帧 · 歧义停止 {len(self.track.uncertain)} 处 · 超时停止 {len(self.track.stopped)} 处。\n"
                                    "只处理匹配帧，漏检和停止后的帧保留原标注。")
            self.show_position(self.position)
            self.report("跟踪预览已生成：粉色为将处理的框，浏览时间轴可复查。")
            return True
        except Exception as error:
            self.problem(error)
            return False

    def delete_track(self):
        if not self.ready() or (self.track is None and not self.preview_track()):
            return
        updates = {i: [s for j, s in enumerate(self.project.frame(i).shapes) if j != target]
                   for i, target in self.track.matches.items()}
        count = self.history.apply("删除参考手跟踪结果", updates)
        self.changed()
        self.report(f"已删除跟踪匹配的 {count} 个手框，可使用 Ctrl+Z 撤销。")

    def label_value(self):
        label = self.action_name.currentText().strip()
        if not label or label == "hand":
            self.report("请输入动作名；hand 保留为尚未赋动作的检测标签。")
            return None
        if self.action_name.findText(label) < 0:
            self.action_name.addItem(label)
        return label

    def apply_label(self):
        if not self.ready():
            return
        label = self.label_value()
        if label is None:
            return
        try:
            scope = self.label_scope.currentData()
            if scope == "track":
                if self.track is None and not self.preview_track():
                    return
                targets = {i: [j] for i, j in self.track.matches.items()}
            else:
                targets = {i: side_indices(self.project.frame(i), scope, self.position_method.currentData(), self.divider.value() / 100)
                           for i in self.range_indices()}
            updates, boxes = {}, 0
            for i, chosen in targets.items():
                if not chosen:
                    continue
                shapes = copy.deepcopy(self.project.frame(i).shapes)
                for j in chosen:
                    shapes[j].label = label
                    boxes += 1
                updates[i] = shapes
            count = self.history.apply(f"批量赋动作：{label}", updates)
            self.changed()
            self.report(f"已为 {boxes} 个手框赋动作“{label}”（{count} 帧发生变化），可撤销。")
        except Exception as error:
            self.problem(error)

    def label_current(self):
        if not self.ready() or self.canvas.selected < 0:
            return
        label = self.label_value()
        if label:
            index = self.current_index()
            shapes = copy.deepcopy(self.project.frame(index).shapes)
            shapes[self.canvas.selected].label = label
            self.history.apply(f"修改所选动作：{label}", {index: shapes})
            self.changed()

    def undo(self):
        if self.ready():
            name = self.history.undo()
            if name:
                self.changed()
                self.report(f"已撤销：{name}")

    def redo(self):
        if self.ready():
            name = self.history.redo()
            if name:
                self.changed()
                self.report(f"已重做：{name}")

    def choose_model(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择手部检测模型", str(ROOT / "models"), "YOLO 模型 (*.pt *.onnx)")
        if path:
            self.model_path.setText(path)

    def detect(self):
        if not self.ready():
            return
        try:
            indices = self.range_indices()
            if not self.overwrite.isChecked():
                indices = [i for i in indices if not self.project.frame(i).processed]
            if not indices:
                self.report("范围中没有未检测抽帧；如需重跑，请勾选覆盖已有标注。")
                return
            snapshot = copy.deepcopy(self.project)
            path, confidence, device = self.model_path.text(), self.confidence.value(), self.device.currentData()
            self.start_job("detect", lambda progress, cancel: detect_project(snapshot, indices, path, confidence, device,
                                                                             progress=progress, cancelled=cancel))
        except Exception as error:
            self.problem(error)

    def start_job(self, kind, operation):
        self.stop_play()
        self.save_timer.stop()
        self._autosave()
        self.job_kind = kind
        self.controls.setEnabled(False)
        self.canvas.editable = False
        self.draw_button.setEnabled(False)
        for action in self.file_actions:
            action.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.worker = Worker(operation, self)
        self.worker.progress.connect(self._job_progress)
        self.worker.result.connect(self._job_result)
        self.worker.failed.connect(self._job_error)
        self.worker.finished.connect(self._job_finished)
        self.worker.start()

    @Slot(int, int, str)
    def _job_progress(self, done, total, message):
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        self.report(message)

    @Slot(object)
    def _job_result(self, result):
        if self.job_kind == "detect":
            updates = {i: data[0] for i, data in result.items()}
            self.history.apply("模型检测", updates, {i: True for i in updates})
            for i, (_, width, height) in result.items():
                self.project.frame(i).width, self.project.frame(i).height = width, height
            self.changed()
            self.sampling_group.set_collapsed(True)
            self.detector_group.set_collapsed(True)
            self.report(f"检测完成：{len(updates):,} 帧、{sum(len(s) for s in updates.values()):,} 个手框。可以开始剔除与赋动作。")
        elif self.job_kind == "export":
            self.report(f"导出完成：{result['frames']:,} 帧、{result['boxes']:,} 个手框 → {result['directory']}")

    @Slot(str)
    def _job_error(self, message):
        self.report(message)
        if "取消" not in message:
            QMessageBox.warning(self, "任务失败", message)

    @Slot()
    def _job_finished(self):
        self.controls.setEnabled(True)
        self.canvas.editable = True
        self.draw_button.setEnabled(True)
        for action in self.file_actions:
            action.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.canvas.update()
        if self.worker:
            self.worker.deleteLater()
        self.worker = None
        self._autosave()
        if self.pending_close:
            self.close()

    def cancel_job(self):
        if self.busy():
            self.worker.requestInterruption()
            self.report("正在取消，等待当前帧处理结束…")

    def _autosave(self):
        if self.project and self.recovery_path and self.dirty:
            try:
                self.project.save(self.recovery_path)
            except Exception as error:
                self.report(f"自动保存失败：{error}；请使用“保存项目”另存。")

    def save_project(self):
        if not self.ready():
            return
        suggestion = self.project_path or ROOT / "projects" / (Path(self.project.source.path).stem + ".handproj")
        path, _ = QFileDialog.getSaveFileName(self, "保存标注项目", str(suggestion), "标注项目 (*.handproj)")
        if path:
            if not path.endswith(".handproj"):
                path += ".handproj"
            try:
                self.project.save(path)
                self.project_path = Path(path)
                self._autosave()
                self.dirty = False
                self.report(f"项目已保存：{path}")
            except Exception as error:
                self.problem(error)

    def export(self):
        if not self.ready():
            return
        suggestion = ROOT / "outputs" / f"{Path(self.project.source.path).stem}_{datetime.now():%Y%m%d_%H%M%S}"
        path, _ = QFileDialog.getSaveFileName(self, "选择新的数据集目录名（导出全部当前抽帧）", str(suggestion), "目录名 (*)")
        if not path:
            return
        indices = self.project.sample_indices()
        pending = sum(not self.project.frame(i).processed for i in indices)
        raw_labels = sum(s.label == "hand" for i in indices for s in self.project.frame(i).shapes)
        if pending or raw_labels:
            answer = QMessageBox.question(self, "导出待复核标注", f"有 {pending} 帧未检测、{raw_labels} 个框尚未赋动作（hand）。\n"
                                          "这些帧仍会生成 JSON；未检测帧可能是空标注。继续导出？",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        if Path(path).exists():
            self.problem("导出目录已存在，请使用新的目录名。")
            return
        snapshot = copy.deepcopy(self.project)
        self.start_job("export", lambda progress, cancel: export_project(snapshot, path, progress=progress, cancelled=cancel))

    def show_help(self):
        QMessageBox.information(self, "使用说明", "1. 打开视频或图片目录（自动读取同名 rectangle JSON）。\n"
                                 "2. 默认 FPS 控制全局抽帧；选择时间范围后可添加独立 FPS 段。\n"
                                 "3. 模型仅检测当前范围未处理的抽帧；重跑需勾选覆盖。\n"
                                 "4. 相对位置删除最左 / 最右手；单手按分界线判断。\n"
                                 "5. 手交叉时：点选框 → 设为参考 → 预览跟踪 → 删除或赋标签。\n"
                                 "6. 纯动作名写入 label；框可拖动、拖角调整，R 补框，Del 删除。\n"
                                 "7. Ctrl+Z / Ctrl+Shift+Z 撤销 / 重做标注操作（最多 40 步）。\n"
                                 "8. Ctrl+S 保存项目；Ctrl+E 导出全部当前抽帧和每帧 JSON。\n\n"
                                 "快捷键：A / D 上下帧；I / O 设置区间；Space 播放；Shift+拖时间轴选段。\n"
                                 "跟踪依赖 IoU 和运动距离，遮挡、低 FPS 或相似手框可能使其停止，需人工复核。")

    def closeEvent(self, event):
        if self.busy():
            self.pending_close = True
            self.cancel_job()
            event.ignore()
            return
        self._autosave()
        if self.reader:
            self.reader.close()
        event.accept()


def create_application():
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Hand Annotation Workbench")
    # The Windows offscreen plugin has no system font database; explicitly load CJK.
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    if font_path.exists():
        QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont("Microsoft YaHei", 10))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    return app
