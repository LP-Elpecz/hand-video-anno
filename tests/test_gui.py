import copy
import time

import numpy as np
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog

from hand_anno.app import MainWindow, create_application
from hand_anno.core import Project, Shape, write_image


@pytest.fixture(scope="module")
def app():
    return create_application()


@pytest.fixture
def window(app, tmp_path):
    inputs = tmp_path / "images"
    inputs.mkdir()
    for i in range(10):
        write_image(inputs / f"{i}.png", np.full((120, 200, 3), i * 20, dtype=np.uint8))
    project = Project.open(inputs, 5)
    for i in range(10):
        frame = project.frame(i)
        frame.shapes = [Shape([10 + i, 10, 45 + i, 60]), Shape([140, 10, 180, 60])]
        frame.processed = True
    widget = MainWindow()
    widget.set_project(project)
    widget.recovery_path = tmp_path / "recovery.handproj"
    widget.show()
    app.processEvents()
    yield widget
    widget.close()
    app.processEvents()


def test_gui_range_deletion_label_and_undo(window):
    window.set_range(0.4, 1.0)
    window.delete_side("left")
    assert len(window.project.frame(1).shapes) == 2
    assert all(len(window.project.frame(i).shapes) == 1 for i in range(2, 6))
    assert len(window.project.frame(6).shapes) == 2
    window.action_name.setCurrentText("拧螺丝")
    window.apply_label()
    assert all(window.project.frame(i).shapes[0].label == "拧螺丝" for i in range(2, 6))
    window.undo()
    assert window.project.frame(2).shapes[0].label == "hand"
    window.undo()
    assert len(window.project.frame(2).shapes) == 2
    window.redo()
    assert len(window.project.frame(2).shapes) == 1


def test_gui_reference_preview_navigation_and_delete(window):
    window.show_position(4)
    window.canvas.selected = 0
    window.set_reference()
    assert window.preview_track()
    assert len(window.track.matches) == 10
    window.show_position(8)
    assert window.canvas.preview_index == 0
    window.delete_track()
    assert all(len(f.shapes) == 1 for f in window.project.frames.values())
    window.undo()
    assert all(len(f.shapes) == 2 for f in window.project.frames.values())


def test_gui_draw_adjust_and_delete_frame_box(window, app):
    window.draw_button.setChecked(True)
    canvas = window.canvas
    first = canvas.to_screen(65, 65).toPoint()
    second = canvas.to_screen(115, 105).toPoint()
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=first)
    QTest.mouseMove(canvas, second)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=second)
    app.processEvents()
    assert len(window.project.frame(0).shapes) == 3
    assert window.project.frame(0).shapes[-1].box[2] > 110
    window.draw_button.setChecked(False)
    window.delete_current()
    assert len(window.project.frame(0).shapes) == 2


def test_typing_action_name_does_not_trigger_shortcuts(window):
    field = window.action_name.lineEdit()
    field.setFocus()
    QTest.keyClicks(field, "assembly")
    assert field.text() == "assembly"
    assert window.position == 0


def test_worker_results_are_applied_and_undoable(window, app):
    window.project.frame(0).processed = False
    expected = Shape([20, 20, 80, 80], "hand", 0.9)
    window.start_job("detect", lambda progress, cancel: {0: ([expected], 200, 120)})
    deadline = time.monotonic() + 5
    while window.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        QTest.qWait(10)
    assert window.worker is None
    assert window.project.frame(0).shapes == [expected]
    assert window.project.frame(0).processed
    window.undo()
    assert len(window.project.frame(0).shapes) == 2
    assert not window.project.frame(0).processed


def test_switch_sources_with_different_frame_counts(window, tmp_path):
    window.show_position(9)
    folder = tmp_path / "short"
    folder.mkdir()
    write_image(folder / "0.png", np.zeros((80, 100, 3), np.uint8))
    window.set_project(Project.open(folder))
    assert window.current_index() == 0 and len(window.indices) == 1


def test_manual_save_updates_recovery_before_debounce(window, tmp_path, monkeypatch):
    destination = tmp_path / "manual.handproj"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(destination), ""))
    window.canvas.selected = 0
    window.action_name.setCurrentText("检查")
    window.label_current()
    window.save_project()
    assert Project.load(destination).frame(0).shapes[0].label == "检查"
    assert Project.load(window.recovery_path).frame(0).shapes[0].label == "检查"


@pytest.mark.parametrize("select_range", [False, True])
@pytest.mark.parametrize("zoomed", [False, True])
def test_timeline_drag_previews_frames_forward_backward_and_on_release(window, app, select_range, zoomed):
    timeline = window.timeline
    if zoomed:
        timeline.zoom(1.2, anchor=0.8)
    original_range = (window.start.value(), window.end.value())
    modifier = Qt.KeyboardModifier.ShiftModifier if select_range else Qt.KeyboardModifier.NoModifier

    def point(seconds):
        return QPoint(round(timeline.x_for(seconds)), 48)

    def assert_frame(index):
        app.processEvents()
        assert window.current_index() == index
        assert window.canvas.image.pixelColor(0, 0).red() == index * 20
        assert timeline.current == pytest.approx(index / 5)

    window.toggle_play()
    assert window.play_timer.isActive()
    QTest.mousePress(timeline, Qt.MouseButton.LeftButton, modifier, point(0.4))
    assert_frame(2)
    assert not window.play_timer.isActive()
    QTest.mouseMove(timeline, point(1.4))
    assert_frame(7)
    QTest.mouseMove(timeline, point(0.2))
    assert_frame(1)
    if select_range:
        assert window.start.value() == pytest.approx(0.2, abs=0.003)
        assert window.end.value() == pytest.approx(0.4, abs=0.003)
    QTest.mouseRelease(timeline, Qt.MouseButton.LeftButton, modifier, point(1.6))
    assert_frame(8)
    if select_range:
        assert window.start.value() == pytest.approx(0.4, abs=0.003)
        assert window.end.value() == pytest.approx(1.6, abs=0.003)
    else:
        assert (window.start.value(), window.end.value()) == original_range
    QTest.mouseMove(timeline, point(0.8))
    assert_frame(8)  # Moving without a held left button must leave the preview alone.


def test_timeline_drag_clamps_preview_at_edges_and_ignores_right_button(window, app):
    timeline = window.timeline
    QTest.mouseClick(timeline, Qt.MouseButton.RightButton, pos=QPoint(round(timeline.x_for(1.0)), 48))
    assert window.current_index() == 0
    QTest.mousePress(timeline, Qt.MouseButton.LeftButton, pos=QPoint(round(timeline.x_for(0.4)), 48))
    QTest.mouseMove(timeline, QPoint(timeline.width() - 1, 48))
    app.processEvents()
    assert window.current_index() == 9
    QTest.mouseRelease(timeline, Qt.MouseButton.LeftButton, pos=QPoint(0, 48))
    app.processEvents()
    assert window.current_index() == 0


def test_timeline_zoom_pan_and_reset_preserve_selection_and_annotations(window, app):
    timeline = window.timeline
    window.show_position(5)
    window.set_range(0.4, 1.6)
    original = copy.deepcopy(window.project.to_dict())
    timeline.zoom(2)
    assert (timeline.view_start, timeline.view_end) == pytest.approx((0.5, 1.5))
    assert window.timeline_scroll.isEnabled()
    assert timeline.time_for(timeline.x_for(1.2)) == pytest.approx(1.2)
    window.timeline_scroll.setValue(window.timeline_scroll.maximum())
    assert (timeline.view_start, timeline.view_end) == pytest.approx((1.0, 2.0))
    window.timeline_scroll.setValue(0)
    assert (timeline.view_start, timeline.view_end) == pytest.approx((0.0, 1.0))
    timeline.reset_view()
    assert (timeline.view_start, timeline.view_end) == pytest.approx((0, 2))
    assert not window.timeline_scroll.isEnabled()
    assert window.current_index() == 5
    assert (window.start.value(), window.end.value()) == (0.4, 1.6)
    assert window.project.to_dict() == original


def test_wheel_zoom_keeps_time_under_pointer_fixed(window, app):
    timeline = window.timeline
    position = QPointF(timeline.x_for(0.8), 48)
    event = QWheelEvent(position, QPointF(timeline.mapToGlobal(position.toPoint())),
                        QPoint(), QPoint(0, 120), Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(timeline, event)
    assert timeline.view_span == pytest.approx(1.6)
    assert timeline.time_for(position.x()) == pytest.approx(0.8)
    assert window.current_index() == 0


def test_zoom_limits_source_edges_and_focus_selected_range(window):
    timeline = window.timeline
    for _ in range(20):
        timeline.zoom(2, anchor=1.8)
    assert timeline.view_span == pytest.approx(0.4)
    timeline.pan_to(1)
    assert timeline.view_end == pytest.approx(2)
    timeline.pan_to(0)
    assert timeline.view_start == 0
    window.set_range(0.6, 1.0)
    window.focus_timeline_range()
    assert timeline.view_start < 0.6 and timeline.view_end > 1.0
    assert timeline.view_span < 1
    timeline.zoom(0.001)
    assert (timeline.view_start, timeline.view_end) == pytest.approx((0, 2))


def test_frame_navigation_follows_zoomed_view_but_keeps_selection(window):
    timeline = window.timeline
    timeline.zoom(2, anchor=0)
    assert timeline.view_end == pytest.approx(1)
    selected = (window.start.value(), window.end.value())
    window.show_position(9)
    assert timeline.view_start <= 1.8 <= timeline.view_end
    assert timeline.view_span == pytest.approx(1)
    assert (window.start.value(), window.end.value()) == selected
    window.show_position(0)
    assert timeline.view_start == 0
