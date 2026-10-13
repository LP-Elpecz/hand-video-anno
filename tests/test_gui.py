import copy
import time

import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
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
        write_image(inputs / f"{i}.png", np.zeros((120, 200, 3), dtype=np.uint8))
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
