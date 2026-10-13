"""Run the real model on the example, export every sample, and render review images."""
from __future__ import annotations

import collections
import copy
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hand_anno.core import (EditHistory, FrameReader, Project, SamplingSegment, export_project,
                            side_indices, track_reference, write_image, write_json)
from hand_anno.detector import detect_project

ROOT = Path(__file__).resolve().parents[1]


def run():
    project = Project.open(ROOT / "示例视频.mp4")
    project.segments = [SamplingSegment(0, 15, 10), SamplingSegment(15, 30, 2)]
    indices = project.sample_indices()
    started = time.perf_counter()

    def progress(done, total, message):
        if done % 100 == 0 or done == total:
            print(message, flush=True)

    detections = detect_project(project, indices, progress=progress)
    history = EditHistory(project)
    history.apply("模型检测", {i: result[0] for i, result in detections.items()}, {i: True for i in indices})
    for i, (_, w, h) in detections.items():
        project.frame(i).width, project.frame(i).height = w, h
    elapsed = time.perf_counter() - started
    output = ROOT / "projects" / "示例视频_已检测.handproj"
    project.save(output)
    restored = Project.load(output)
    assert restored.to_dict() == project.to_dict()
    # Validate real-box edits on a separate snapshot; the delivered project stays unedited.
    edit_project = copy.deepcopy(project)
    edit_history = EditHistory(edit_project)
    interval = edit_project.range_indices(10, 12)
    anchor = min(interval, key=lambda i: abs(edit_project.frame(i).time - 11))
    reference = min(range(len(edit_project.frame(anchor).shapes)), key=lambda j: edit_project.frame(anchor).shapes[j].center[0])
    tracked = track_reference(edit_project, interval, anchor, reference)
    assert len(tracked.matches) > 1
    originals = {i: copy.deepcopy(edit_project.frame(i).shapes) for i in tracked.matches}
    edit_history.apply("参考手删除", {i: [s for j, s in enumerate(edit_project.frame(i).shapes) if j != target]
                                     for i, target in tracked.matches.items()})
    for i, target in tracked.matches.items():
        assert len(edit_project.frame(i).shapes) == len(originals[i]) - 1
    edit_history.undo()
    assert all(edit_project.frame(i).shapes == originals[i] for i in originals)
    edit_history.redo()
    edits = {}
    for i in interval:
        shapes = copy.deepcopy(edit_project.frame(i).shapes)
        for s in shapes:
            s.label = "示例动作"
        edits[i] = shapes
    edit_history.apply("动作赋值", edits)
    export_dir = ROOT / "artifacts" / "示例视频_导出验证"
    if export_dir.exists():
        export_dir = ROOT / "artifacts" / f"示例视频_导出验证_{int(time.time())}"
    exported = export_project(project, export_dir, progress=progress)
    assert len(list(export_dir.glob("*.jpg"))) == len(indices)
    assert len(list(export_dir.glob("frame_*.json"))) == len(indices)
    for label_path in export_dir.glob("frame_*.json"):
        data = json.loads(label_path.read_text(encoding="utf-8"))
        assert (export_dir / data["imagePath"]).exists()
        assert data["imageWidth"] == 960 and data["imageHeight"] == 544
        for shape in data["shapes"]:
            assert shape["shape_type"] == "rectangle" and len(shape["points"]) == 4
    # Reimport the dataset with original timestamps and all annotations.
    imported = Project.open(export_dir)
    assert imported.source.times
    assert imported.source.duration == project.source.duration
    assert sum(len(f.shapes) for f in imported.frames.values()) == sum(len(project.frame(i).shapes) for i in indices)
    with FrameReader(project.source) as reader:
        tiles = []
        for timestamp in [10, 40, 80, 120, 170, 220]:
            i = min(indices, key=lambda k: abs(project.source.timestamp(k) - timestamp))
            image = reader.read(i)
            for j, shape in enumerate(project.frame(i).shapes):
                x1, y1, x2, y2 = map(int, shape.box)
                cv2.rectangle(image, (x1, y1), (x2, y2), (110, 240, 100), 3)
                cv2.putText(image, f"hand {shape.score:.2f}", (x1, max(24, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (110, 240, 100), 2)
            cv2.rectangle(image, (0, 0), (270, 32), (20, 28, 36), -1)
            cv2.putText(image, f"{project.frame(i).time:.1f}s | {len(project.frame(i).shapes)} hands", (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            tiles.append(cv2.resize(image, (480, 272)))
        write_image(ROOT / "artifacts" / "detection_review.jpg", np.vstack([np.hstack(tiles[:3]), np.hstack(tiles[3:])]))
    counts = collections.Counter(len(project.frame(i).shapes) for i in indices)
    report = {"source_frames": project.source.count, "source_fps": project.source.fps,
              "sampled_frames": len(indices), "detected_boxes": sum(k * v for k, v in counts.items()),
              "frames_by_box_count": dict(counts), "inference_seconds": round(elapsed, 2),
              "reference_track_matched_frames": len(tracked.matches), "export": exported,
              "project": str(output), "confidence": 0.55, "image_size": 960,
              "checks": ["real GPU inference", "project roundtrip", "reference deletion/undo/redo", "action assignment",
                         "image + four-point rectangle JSON export", "dataset reimport with timestamps"]}
    write_json(ROOT / "artifacts" / "verification_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    run()
