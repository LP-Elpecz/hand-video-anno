"""Run glove inference, verify X-AnyLabeling export, and create local review sheets."""
from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hand_anno.core import EditHistory, Project, export_project, read_image, write_image, write_json
from hand_anno.detector import GLOVED_MODEL, detect_project


def run():
    parser = argparse.ArgumentParser(description="戴手套模型真实视频验证（不修改原素材或恢复文件）")
    parser.add_argument("source", type=Path)
    parser.add_argument("--fps", type=float, default=1)
    parser.add_argument("--output", type=Path, default=Path("artifacts/gloved_verification"))
    args = parser.parse_args()
    if not 0 < args.fps <= 60:
        parser.error("FPS 应在 0–60 之间且大于零。")
    if args.output.exists():
        parser.error("输出目录已存在，请指定新的 --output。")
    project = Project.open(args.source)
    project.default_fps = args.fps
    indices = project.sample_indices()
    args.output.mkdir(parents=True)
    started = time.perf_counter()

    def progress(done, total, message):
        if done % 25 == 0 or done == total:
            print(message, flush=True)

    results = detect_project(project, indices, GLOVED_MODEL, 0.4, progress=progress)
    detection_seconds = time.perf_counter() - started
    EditHistory(project).apply("戴手套模型检测", {i: data[0] for i, data in results.items()}, {i: True for i in indices})
    for i, (_, width, height) in results.items():
        project.frame(i).width, project.frame(i).height = width, height
    project_path = args.output / "gloved_review.handproj"
    project.save(project_path)
    assert Project.load(project_path).to_dict() == project.to_dict()
    exported = export_project(project, args.output / "export", progress=progress)
    imported = Project.open(args.output / "export")
    assert len(imported.frames) == len(indices)
    for j, i in enumerate(indices):
        source_shapes = [s.to_dict() for s in project.frame(i).shapes]
        restored_shapes = [s.to_dict() for s in imported.frame(j).shapes]
        assert source_shapes == restored_shapes
        assert imported.frame(j).processed
        for shape in source_shapes:
            assert shape["label"] == "hand"
            assert shape["shape_type"] == "rectangle" and len(shape["points"]) == 4
    review = np.linspace(0, len(indices) - 1, min(32, len(indices)), dtype=int).tolist()
    review_files = []
    for page in range((len(review) + 7) // 8):
        sheet = np.zeros((432, 1536, 3), np.uint8)
        for j, position in enumerate(review[page * 8:page * 8 + 8]):
            i = indices[position]
            im = read_image(args.output / "export" / f"frame_{i:08d}.jpg")
            for shape in project.frame(i).shapes:
                x1, y1, x2, y2 = map(int, shape.box)
                cv2.rectangle(im, (x1, y1), (x2, y2), (80, 230, 40), 3)
                cv2.putText(im, f"{shape.score:.2f}", (x1, max(28, y1)), cv2.FONT_HERSHEY_SIMPLEX, .8, (80, 230, 40), 2)
            cv2.rectangle(im, (0, 0), (470, 43), (0, 0, 0), -1)
            text = f"{project.frame(i).time:.1f}s | {len(project.frame(i).shapes)} boxes"
            cv2.putText(im, text, (8, 30), cv2.FONT_HERSHEY_SIMPLEX, .8, (255, 255, 255), 2)
            x, y = j % 4 * 384, j // 4 * 216
            sheet[y:y + 216, x:x + 384] = cv2.resize(im, (384, 216))
        path = args.output / f"review_{page + 1}.jpg"
        write_image(path, sheet)
        review_files.append(str(path.resolve()))
    report = {
        "source": str(args.source.resolve()), "source_fps": project.source.fps,
        "source_duration_seconds": project.source.duration, "sampling_fps": args.fps,
        "model": str(GLOVED_MODEL), "prompt": "gloved hand.", "confidence": 0.4,
        "device": "auto", "frames": len(indices), "boxes": exported["boxes"],
        "box_count_histogram": dict(collections.Counter(len(project.frame(i).shapes) for i in indices)),
        "detection_seconds_including_load_and_decode": detection_seconds,
        "project": str(project_path.resolve()), "export": exported,
        "export_roundtrip_verified": True, "review_files": review_files,
        "note": "无逐帧人工真值；框数量和吞吐量不代表准确率。",
    }
    write_json(args.output / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    run()
