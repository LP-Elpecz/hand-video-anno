import copy
import json
from pathlib import Path

import numpy as np
import pytest

from hand_anno.core import (
    Cancelled, EditHistory, Frame, Project, SamplingSegment, Shape, Source,
    export_project, side_indices, track_reference, write_image,
)


def synthetic(count=180, fps=30):
    return Project(Source("unused.mp4", "video", fps, count, 1000, 600), 2)


def test_piecewise_sampling_native_frames_and_boundaries():
    project = synthetic()
    project.segments = [SamplingSegment(1, 2, 10), SamplingSegment(3, 4, 5)]
    indices = project.sample_indices()
    assert len(indices) == 23
    assert len(indices) == len(set(indices))
    assert [i for i in indices if 30 <= i < 60] == list(range(30, 60, 3))
    assert [i for i in indices if 90 <= i < 120] == list(range(90, 120, 6))
    assert 60 in indices and 120 in indices and 180 not in indices


def test_oversampling_clamps_to_available_frames():
    project = synthetic()
    project.default_fps = 120
    assert project.sample_indices() == list(range(180))


@pytest.mark.parametrize("segments", [
    [SamplingSegment(1, 3, 5), SamplingSegment(2, 4, 5)],
    [SamplingSegment(1, 1, 5)], [SamplingSegment(-1, 1, 5)],
    [SamplingSegment(0, 7, 5)], [SamplingSegment(0, 1, 0)],
    [SamplingSegment(0, 1, float("nan"))],
])
def test_invalid_sampling_is_rejected(segments):
    project = synthetic()
    project.segments = segments
    with pytest.raises(ValueError):
        project.sample_indices()


def test_schedule_changes_retain_off_schedule_annotations():
    project = synthetic()
    project.frame(15).shapes = [Shape([20, 20, 60, 60], "装配")]
    project.default_fps = 1
    assert 15 not in project.sample_indices()
    project.default_fps = 2
    assert 15 in project.sample_indices()
    assert project.frame(15).shapes[0].label == "装配"


def test_millisecond_range_rounding_includes_current_frame():
    project = synthetic(fps=30.000043)
    project.default_fps = 5
    assert 300 in Project(Source("unused", "video", 30.000043, 600, 960, 544), 5).range_indices(10, 10)


def test_rectangle_import_export_preserves_metadata():
    data = {"label": "拧螺丝", "points": [[50, 70], [10, 20]], "shape_type": "rectangle",
            "group_id": 9, "attributes": {"operator": "A"}, "flags": {"occluded": True}, "custom": [1, 2]}
    shape = Shape.from_dict(data)
    document = shape.to_dict()
    assert document["points"] == [[10, 20], [50, 20], [50, 70], [10, 70]]
    assert document["label"] == "拧螺丝"
    assert document["group_id"] == 9 and document["custom"] == [1, 2]
    assert document["attributes"] == data["attributes"] and document["flags"] == data["flags"]
    with pytest.raises(ValueError):
        Shape.from_dict({**data, "shape_type": "polygon"})


def test_side_selection_relative_vs_divider_and_single_hand():
    frame = Frame(0, 0, 1000, 600, [Shape([80, 0, 180, 100]), Shape([280, 0, 380, 100])])
    assert side_indices(frame, "left") == [0]
    assert side_indices(frame, "right") == [1]
    assert side_indices(frame, "left", "divider") == [0, 1]
    frame.shapes.pop(0)
    assert side_indices(frame, "right") == []
    assert side_indices(frame, "left") == [0]


def test_history_restores_empty_frame_processing_state_and_metadata():
    project = synthetic()
    history = EditHistory(project)
    original = Shape([10, 10, 50, 50], "hand", 0.9, {"group_id": 8})
    history.apply("检测", {0: [original]}, {0: True})
    history.apply("删除", {0: []})
    assert project.frame(0).processed and not project.frame(0).shapes
    history.undo()
    assert project.frame(0).shapes == [original]
    history.undo()
    assert not project.frame(0).processed and not project.frame(0).shapes
    history.redo()
    assert project.frame(0).shapes[0].extra["group_id"] == 8
    history.apply("动作", {0: [Shape([10, 10, 50, 50], "检查")]})
    assert not history.redo_stack


def tracking_project():
    project = synthetic(count=10, fps=5)
    project.default_fps = 5
    for i in range(10):
        project.frame(i).shapes = [Shape([100 + i * 4, 100, 200 + i * 4, 200]), Shape([700, 100, 800, 200])]
    return project


def test_bidirectional_reference_tracking_and_short_missing_gap():
    project = tracking_project()
    project.frame(6).shapes = []
    result = track_reference(project, list(range(10)), 5, 0)
    assert result.matches == {i: 0 for i in range(10) if i != 6}
    assert not result.uncertain and not result.stopped


def test_tracker_stops_on_long_gap_without_switching_to_other_hand():
    project = tracking_project()
    for i in range(6, 10):
        project.frame(i).shapes.pop(0)
    result = track_reference(project, list(range(10)), 5, 0, max_gap=0.5)
    assert all(i <= 5 for i in result.matches)
    assert result.stopped == [8]


def test_tracker_stops_on_ambiguous_nearby_candidates():
    project = tracking_project()
    project.frame(6).shapes = [Shape([123, 100, 223, 200]), Shape([125, 100, 225, 200])]
    result = track_reference(project, list(range(10)), 5, 0)
    assert result.uncertain == [6]
    assert 6 not in result.matches and 7 not in result.matches
    with pytest.raises(ValueError):
        track_reference(project, [0, 1, 2], 5, 0)


@pytest.fixture
def image_project(tmp_path):
    inputs = tmp_path / "输入图片"
    inputs.mkdir()
    for name in ["image10.png", "image2.png", "image1.jpg"]:
        write_image(inputs / name, np.zeros((60, 100, 3), dtype=np.uint8))
    label = {"version": "3.0", "flags": {"checked": True}, "imagePath": "image1.jpg",
             "imageData": None, "imageWidth": 100, "imageHeight": 60, "custom_image": "keep",
             "shapes": [Shape([10, 10, 40, 50], "装配", extra={"group_id": 4}).to_dict()]}
    (inputs / "image1.json").write_text(json.dumps(label, ensure_ascii=False), encoding="utf-8")
    return Project.open(inputs, 5)


def test_image_folder_natural_order_annotations_and_project_roundtrip(image_project, tmp_path):
    project = image_project
    assert [Path(p).name for p in project.source.images] == ["image1.jpg", "image2.png", "image10.png"]
    assert project.frame(0).shapes[0].label == "装配"
    project.save(tmp_path / "test.handproj")
    loaded = Project.load(tmp_path / "test.handproj")
    assert loaded.to_dict() == project.to_dict()
    assert loaded.frame(0).extra["custom_image"] == "keep"


def test_export_every_sample_including_empty_frames_and_reimport(image_project, tmp_path):
    destination = tmp_path / "导出结果"
    before = copy.deepcopy(image_project.to_dict())
    result = export_project(copy.deepcopy(image_project), destination)
    assert result["frames"] == 3 and result["boxes"] == 1
    documents = [json.loads(p.read_text(encoding="utf-8")) for p in destination.glob("frame_*.json")]
    assert len(documents) == 3 and sum(not d["shapes"] for d in documents) == 2
    assert all((destination / d["imagePath"]).exists() for d in documents)
    imported = Project.open(destination)
    assert imported.source.times == [0, 0.2, 0.4]
    assert imported.source.duration == image_project.source.duration
    assert imported.frame(0).processed and not imported.frame(1).processed
    assert imported.frame(0).shapes[0].extra["group_id"] == 4
    assert image_project.to_dict() == before
    with pytest.raises(ValueError):
        export_project(image_project, destination)


def test_cancel_export_leaves_no_partial_dataset(image_project, tmp_path):
    destination = tmp_path / "cancelled"
    with pytest.raises(Cancelled):
        export_project(image_project, destination, cancelled=lambda: True)
    assert not destination.exists()
    assert not list(tmp_path.glob(".hand-anno-export-*"))


def test_corrupt_annotations_fail_without_silent_loss(image_project):
    path = Path(image_project.source.images[1]).with_suffix(".json")
    path.write_text("{invalid", encoding="utf-8")
    with pytest.raises(ValueError, match=path.name):
        Project.open(image_project.source.path)
