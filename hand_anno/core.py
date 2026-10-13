from __future__ import annotations

import copy
import json
import math
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def read_image(path: str | Path) -> np.ndarray:
    image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"无法读取图片：{path}")
    return image


def write_image(path: str | Path, image: np.ndarray) -> None:
    path = Path(path)
    ok, data = cv2.imencode(path.suffix, image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise ValueError(f"无法编码图片：{path}")
    data.tofile(str(path))


def write_json(path: str | Path, data: dict) -> None:
    """Atomic replacement, including on Windows; never truncate an existing project."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def natural_key(path: Path):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


@dataclass
class Shape:
    box: list[float]
    label: str = "hand"
    score: float | None = None
    extra: dict = field(default_factory=dict)

    @property
    def center(self):
        x1, y1, x2, y2 = self.box
        return ((x1 + x2) / 2, (y1 + y2) / 2)

    @classmethod
    def from_dict(cls, data: dict):
        if data.get("shape_type") != "rectangle":
            raise ValueError("当前只支持 rectangle；为避免丢失标注，请先转换其他形状。")
        points = np.asarray(data["points"], dtype=float)
        if points.shape not in ((2, 2), (4, 2)) or not np.isfinite(points).all():
            raise ValueError("rectangle 必须有两个对角点或四个顶点，且坐标为有限数值。")
        low, high = points.min(axis=0), points.max(axis=0)
        if np.any(high <= low):
            raise ValueError("rectangle 的宽和高必须大于零。")
        return cls([*low.tolist(), *high.tolist()], str(data["label"]), data.get("score"), copy.deepcopy(data))

    def to_dict(self):
        x1, y1, x2, y2 = self.box
        data = copy.deepcopy(self.extra)
        data.update(label=self.label, score=self.score,
                    points=[[x1, y1], [x2, y1], [x2, y2], [x1, y2]], shape_type="rectangle")
        for name, default in {"group_id": None, "description": "", "difficult": False,
                              "flags": {}, "attributes": {}}.items():
            data.setdefault(name, default)
        return data


@dataclass
class Frame:
    index: int
    time: float
    width: int
    height: int
    shapes: list[Shape] = field(default_factory=list)
    processed: bool = False
    extra: dict = field(default_factory=dict)

    def label_document(self, image_name: str):
        data = copy.deepcopy(self.extra)
        data.update(version="3.3.0", shapes=[s.to_dict() for s in self.shapes], imagePath=image_name,
                    imageData=None, imageWidth=self.width, imageHeight=self.height)
        data.setdefault("flags", {})
        data.setdefault("description", "")
        return data


@dataclass
class SamplingSegment:
    start: float
    end: float
    fps: float


@dataclass
class Source:
    path: str
    kind: str
    fps: float
    count: int
    width: int
    height: int
    images: list[str] = field(default_factory=list)
    times: list[float] = field(default_factory=list)
    duration_seconds: float | None = None

    @property
    def duration(self):
        if self.duration_seconds is not None:
            return self.duration_seconds
        return self.times[-1] + 1 / self.fps if self.times else self.count / self.fps

    def timestamp(self, index: int):
        return self.times[index] if self.times else index / self.fps

    @classmethod
    def open(cls, path: str | Path, folder_fps=5.0):
        path = Path(path).resolve()
        if not path.exists():
            raise ValueError(f"输入不存在：{path}")
        if path.is_dir():
            if folder_fps <= 0 or not math.isfinite(folder_fps):
                raise ValueError("图片序列 FPS 必须大于零。")
            images = sorted((p for p in path.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS), key=natural_key)
            if not images:
                raise ValueError("文件夹中没有支持的图片。")
            times = []
            original_duration = None
            manifest = path / "manifest.json"
            if manifest.exists():
                metadata = json.loads(manifest.read_text(encoding="utf-8"))
                rows = metadata.get("frames", [])
                lookup = {row["image"]: row for row in rows}
                if all(p.name in lookup for p in images):
                    images.sort(key=lambda p: lookup[p.name]["timestamp"])
                    times = [float(lookup[p.name]["timestamp"]) for p in images]
                    if any(not math.isfinite(t) or t < 0 for t in times) or any(a >= b for a, b in zip(times, times[1:])):
                        raise ValueError("manifest.json 中的时间戳必须非负、有限且严格递增。")
                    folder_fps = float(metadata.get("source_fps", folder_fps))
                    original_duration = metadata.get("source_duration")
                    if original_duration is not None:
                        original_duration = float(original_duration)
                        if not math.isfinite(original_duration) or original_duration <= times[-1]:
                            raise ValueError("manifest.json 中的源时长无效。")
            if folder_fps <= 0 or not math.isfinite(folder_fps):
                raise ValueError("manifest.json 中的源 FPS 无效。")
            image = read_image(images[0])
            h, w = image.shape[:2]
            return cls(str(path), "images", folder_fps, len(images), w, h, [str(p) for p in images], times, original_duration)
        cap = cv2.VideoCapture(str(path))
        try:
            if not cap.isOpened():
                raise ValueError("视频无法打开，请确认编解码器和文件内容。")
            fps, count = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if fps <= 0 or not math.isfinite(fps) or count <= 0 or w <= 0 or h <= 0:
                raise ValueError("视频帧数、尺寸或帧率无效。")
            return cls(str(path), "video", fps, count, w, h)
        finally:
            cap.release()


class FrameReader:
    """Each worker owns its reader; no shared VideoCapture between threads."""
    def __init__(self, source: Source):
        self.source = source
        self.cap = cv2.VideoCapture(source.path) if source.kind == "video" else None
        self.next_index = 0

    def read(self, index: int):
        if not 0 <= index < self.source.count:
            raise IndexError(index)
        if self.source.kind == "images":
            return read_image(self.source.images[index])
        if self.cap is None or not self.cap.isOpened():
            raise ValueError("无法打开视频。")
        # Decode short gaps sequentially, seek only for large/backward jumps.
        if index < self.next_index or index - self.next_index > 120:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            self.next_index = index
        while self.next_index < index:
            if not self.cap.grab():
                raise ValueError(f"视频第 {self.next_index} 帧解码失败。")
            self.next_index += 1
        ok, image = self.cap.read()
        self.next_index = index + 1
        if not ok:
            raise ValueError(f"视频第 {index} 帧解码失败。")
        return image

    def close(self):
        if self.cap is not None:
            self.cap.release()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


@dataclass
class Project:
    source: Source
    default_fps: float = 5.0
    segments: list[SamplingSegment] = field(default_factory=list)
    frames: dict[int, Frame] = field(default_factory=dict)

    @classmethod
    def open(cls, path, folder_fps=5.0):
        source = Source.open(path, folder_fps)
        project = cls(source, default_fps=folder_fps if source.kind == "images" else 5.0)
        if source.kind == "images":
            manifest_path = Path(source.path) / "manifest.json"
            exported_states = {}
            if manifest_path.exists():
                exported_states = {r["image"]: r.get("processed", True)
                                   for r in json.loads(manifest_path.read_text(encoding="utf-8" )).get("frames", [])}
            for index, name in enumerate(source.images):
                label_path = Path(name).with_suffix(".json")
                if label_path.exists():
                    try:
                        data = json.loads(label_path.read_text(encoding="utf-8-sig"))
                        frame = project.frame(index)
                        frame.height, frame.width = read_image(name).shape[:2]
                        frame.shapes = [Shape.from_dict(s) for s in data["shapes"]]
                        frame.extra = {k: v for k, v in data.items() if k != "shapes"}
                        frame.processed = bool(exported_states.get(Path(name).name, True))
                    except Exception as error:
                        raise ValueError(f"读取 {label_path.name} 失败：{error}") from error
        return project

    def frame(self, index):
        if index not in self.frames:
            self.frames[index] = Frame(index, self.source.timestamp(index), self.source.width, self.source.height)
        return self.frames[index]

    def sampling_plan_at(self, timestamp):
        """Return the containing half-open plan and its custom segment number, if any."""
        start = 0.0
        for number, segment in enumerate(sorted(self.segments, key=lambda s: s.start), 1):
            if timestamp < segment.start:
                return SamplingSegment(start, segment.start, self.default_fps), None
            if timestamp < segment.end:
                return segment, number
            start = segment.end
        return SamplingSegment(start, self.source.duration, self.default_fps), None

    def sample_indices(self):
        duration = self.source.duration
        if not math.isfinite(self.default_fps) or self.default_fps <= 0:
            raise ValueError("默认抽帧频率必须大于零。")
        segments = sorted(self.segments, key=lambda s: s.start)
        last_end = 0.0
        spans = []
        for s in segments:
            if not all(math.isfinite(v) for v in (s.start, s.end, s.fps)) or not 0 <= s.start < s.end <= duration + 1e-7 or s.fps <= 0:
                raise ValueError("分段起止时间或频率无效。")
            if s.start < last_end - 1e-7:
                raise ValueError("抽帧时间段不能重叠，请先移除已有重叠段。")
            if s.start > last_end:
                spans.append((last_end, s.start, self.default_fps))
            spans.append((s.start, s.end, s.fps))
            last_end = s.end
        if last_end < duration:
            spans.append((last_end, duration, self.default_fps))
        selected = set()
        # Explicit folder timestamps can be irregular. Never synthesize nonexistent frames.
        if self.source.times:
            for start, end, rate in spans:
                next_time = start
                for index, t in enumerate(self.source.times):
                    if start <= t < end and t + 1e-8 >= next_time:
                        selected.add(index)
                        next_time = start + (math.floor((t - start) * rate + 1e-8) + 1) / rate
        else:
            native = self.source.fps
            for start, end, rate in spans:
                first = max(0, math.ceil(start * native - 1e-8))
                stop = min(self.source.count, math.ceil(end * native - 1e-8))
                if rate >= native:
                    selected.update(range(first, stop))
                    continue
                for step in range(math.ceil((end - start) * rate - 1e-8)):
                    index = int(math.floor((start + step / rate) * native + 0.5))
                    index = max(first, index)
                    if first <= index < stop:
                        selected.add(index)
        return sorted(selected)

    def range_indices(self, start, end):
        if start > end:
            raise ValueError("开始时间不能大于结束时间。")
        # The UI uses milliseconds; include a selected frame after spinbox rounding.
        return [i for i in self.sample_indices() if start - 0.000501 <= self.source.timestamp(i) <= end + 0.000501]

    def to_dict(self):
        return {"format": "hand-anno-project", "version": 1, "source": asdict(self.source),
                "default_fps": self.default_fps, "segments": [asdict(s) for s in self.segments],
                "frames": [asdict(f) for f in self.frames.values()]}

    def save(self, path):
        write_json(path, self.to_dict())

    @classmethod
    def load(cls, path):
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if data.get("format") != "hand-anno-project" or data.get("version") != 1:
            raise ValueError("不是支持的手部标注项目文件。")
        source = Source(**data["source"])
        if not Path(source.path).exists():
            # Allow a project folder to be moved with its original media.
            candidate = path.parent / Path(source.path).name
            if not candidate.exists():
                raise ValueError(f"找不到原始素材：{source.path}")
            source.path = str(candidate.resolve())
            if source.kind == "images":
                source.images = [str(candidate / Path(p).name) for p in source.images]
        if source.kind == "images" and any(not Path(p).exists() for p in source.images):
            raise ValueError("项目的图片素材不完整。")
        project = cls(source, data["default_fps"], [SamplingSegment(**s) for s in data["segments"]])
        project.sample_indices()  # validate before editing
        for value in data["frames"]:
            value["shapes"] = [Shape(**s) for s in value["shapes"]]
            frame = Frame(**value)
            if not 0 <= frame.index < source.count:
                raise ValueError("项目中存在超出源素材的帧编号。")
            project.frames[frame.index] = frame
        return project


class EditHistory:
    def __init__(self, project: Project):
        self.project = project
        self.undo_stack = []
        self.redo_stack = []

    def apply(self, name: str, updates: dict[int, list[Shape]], processed: dict[int, bool] | None = None):
        before, after = {}, {}
        for index, shapes in updates.items():
            frame = self.project.frame(index)
            state = (copy.deepcopy(frame.shapes), frame.processed)
            replacement = (copy.deepcopy(shapes), processed.get(index, frame.processed) if processed else frame.processed)
            if state != replacement:
                before[index], after[index] = state, replacement
        if not before:
            return 0
        self._restore(after)
        self.undo_stack.append((name, before, after))
        self.undo_stack = self.undo_stack[-40:]
        self.redo_stack.clear()
        return len(before)

    def _restore(self, values):
        for index, (shapes, processed) in values.items():
            frame = self.project.frame(index)
            frame.shapes, frame.processed = copy.deepcopy(shapes), processed

    def undo(self):
        if self.undo_stack:
            action = self.undo_stack.pop()
            self._restore(action[1])
            self.redo_stack.append(action)
            return action[0]

    def redo(self):
        if self.redo_stack:
            action = self.redo_stack.pop()
            self._restore(action[2])
            self.undo_stack.append(action)
            return action[0]


def side_indices(frame: Frame, side: str, method="relative", divider=0.5):
    if side == "all":
        return list(range(len(frame.shapes)))
    if side not in ("left", "right"):
        raise ValueError("无效的左右手选项。")
    if method == "relative" and len(frame.shapes) >= 2:
        # Remove exactly one extreme, not every box in a half-screen.
        chosen = sorted(range(len(frame.shapes)), key=lambda j: frame.shapes[j].center[0])
        return [chosen[0] if side == "left" else chosen[-1]]
    return [j for j, s in enumerate(frame.shapes)
            if (s.center[0] < frame.width * divider) == (side == "left")]


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    return inter / max(area_a + area_b - inter, 1e-8)


@dataclass
class TrackResult:
    matches: dict[int, int]
    uncertain: list[int]
    stopped: list[int]


def track_reference(project: Project, indices: list[int], reference: int, shape_index: int,
                    min_iou=0.08, max_distance=0.16, max_gap=0.8) -> TrackResult:
    """Bidirectional gated IoU + constant-velocity center association.

    Ambiguous matches and long gaps stop a direction; never jump to the other hand.
    Distance is normalized by image diagonal; gaps use seconds, not sampled-frame counts.
    """
    if reference not in indices:
        raise ValueError("参考帧必须处于所选时间范围，且属于当前抽帧计划。")
    ref_frame = project.frame(reference)
    if not 0 <= shape_index < len(ref_frame.shapes):
        raise ValueError("请在画面中选中参考手框。")
    position = indices.index(reference)
    result = TrackResult({reference: shape_index}, [], [])
    diagonal = math.hypot(ref_frame.width, ref_frame.height)
    for direction in (indices[position + 1:], list(reversed(indices[:position]))):
        last = ref_frame.shapes[shape_index].box
        last_time = ref_frame.time
        velocity = np.zeros(2)
        for index in direction:
            frame = project.frame(index)
            dt = frame.time - last_time
            if abs(dt) > max_gap + 1e-7:
                result.stopped.append(index)
                break
            predicted = np.array(last) + np.tile(velocity * dt, 2)
            center = (predicted[:2] + predicted[2:]) / 2
            candidates = []
            for j, shape in enumerate(frame.shapes):
                distance = float(np.linalg.norm(np.array(shape.center) - center)) / diagonal
                overlap = iou(predicted, shape.box)
                size_ratio = ((shape.box[2] - shape.box[0]) * (shape.box[3] - shape.box[1]) /
                              max((last[2] - last[0]) * (last[3] - last[1]), 1e-8))
                if distance <= max_distance and 0.25 <= size_ratio <= 4 and (overlap >= min_iou or distance < max_distance * 0.35):
                    candidates.append((overlap + 0.35 * (1 - distance / max_distance), j))
            candidates.sort(reverse=True)
            if not candidates:
                continue
            if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < 0.12:
                result.uncertain.append(index)
                break
            chosen = candidates[0][1]
            shape = frame.shapes[chosen]
            old_center = np.array([(last[0] + last[2]) / 2, (last[1] + last[3]) / 2])
            if abs(dt) > 1e-7:
                velocity = 0.5 * velocity + 0.5 * (np.array(shape.center) - old_center) / dt
            result.matches[index] = chosen
            last, last_time = shape.box, frame.time
    return result


class Cancelled(Exception):
    pass


def export_project(project: Project, destination: str | Path, indices: list[int] | None = None,
                   progress: Callable = lambda *_: None, cancelled: Callable = lambda: False):
    """Export to a NEW directory; stage fully before making it visible as completed."""
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("导出目录已存在，请选择新的目录名，避免覆盖已有数据。")
    indices = project.sample_indices() if indices is None else indices
    if not indices:
        raise ValueError("没有可导出的抽帧。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".hand-anno-export-", dir=destination.parent))
    manifest = {"format": "hand-anno-export", "source": project.source.path,
                "source_fps": project.source.fps, "source_duration": project.source.duration, "default_fps": project.default_fps,
                "segments": [asdict(s) for s in project.segments], "frames": []}
    try:
        with FrameReader(project.source) as reader:
            for step, index in enumerate(indices):
                if cancelled():
                    raise Cancelled("导出已取消，未生成不完整的数据集。")
                frame = project.frame(index)
                if project.source.kind == "video":
                    image_name = f"frame_{index:08d}.jpg"
                    image = reader.read(index)
                    write_image(staging / image_name, image)
                    h, w = image.shape[:2]
                else:
                    original = Path(project.source.images[index])
                    image_name = f"frame_{index:08d}_{original.name}"
                    shutil.copy2(original, staging / image_name)
                    h, w = read_image(original).shape[:2]
                frame.width, frame.height = w, h
                write_json(staging / Path(image_name).with_suffix(".json"), frame.label_document(image_name))
                manifest["frames"].append({"index": index, "timestamp": frame.time, "image": image_name,
                                           "processed": frame.processed, "boxes": len(frame.shapes)})
                progress(step + 1, len(indices), f"导出 {step + 1}/{len(indices)}")
        write_json(staging / "manifest.json", manifest)
        project.save(staging / "annotation.handproj")
        if cancelled():
            raise Cancelled("导出已取消。")
        if destination.exists():
            raise ValueError("导出目录在处理期间已被创建，请使用另一个目录名。")
        os.rename(staging, destination)
    finally:
        # This exact tempfile-created child is the only directory eligible for cleanup.
        if staging.exists():
            shutil.rmtree(staging)
    return {"directory": str(destination), "frames": len(indices),
            "boxes": sum(len(project.frame(i).shapes) for i in indices)}
