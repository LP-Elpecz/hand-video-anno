from __future__ import annotations

import hashlib
import os
import urllib.request
from pathlib import Path

from .core import Cancelled, FrameReader, Project, Shape

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = ROOT / "models" / "hand_yolov8n.pt"
MODEL_URL = "https://huggingface.co/Bingsu/adetailer/resolve/878390f19f369e91111d3c254ee6cc7c55a47510/hand_yolov8n.pt"
MODEL_SHA256 = "f3f23b865741cc8373a76dfac31a71ffd71356a480ca43266f294815b608e174"


def download_model(path=DEFAULT_MODEL):
    path = Path(path)
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError("默认模型校验失败，请移除该文件后重新下载。")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".download")
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=30) as response, temporary.open("wb") as target:
            while chunk := response.read(1024 * 1024):
                target.write(chunk)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError("模型下载校验失败。")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


class HandDetector:
    def __init__(self, model_path=DEFAULT_MODEL, confidence=0.55, device="auto", image_size=960):
        import torch
        from ultralytics import YOLO

        self.device = ("0" if torch.cuda.is_available() else "cpu") if device == "auto" else device
        self.confidence = confidence
        self.image_size = image_size
        path = Path(model_path)
        if path.resolve() == DEFAULT_MODEL.resolve():
            download_model(path)
        if not path.exists():
            raise ValueError(f"找不到模型：{path}")
        self.model = YOLO(str(path), task="detect")
        self.classes = [i for i, name in self.model.names.items() if "hand" in name.lower() or "手" in name]
        if not self.classes:
            raise ValueError(f"模型没有 hand 类别，实际类别为 {self.model.names}。请选择手部检测模型。")

    def detect(self, image):
        result = self.model.predict(image, conf=self.confidence, imgsz=self.image_size,
                                    classes=self.classes, device=self.device, verbose=False, max_det=10)[0]
        return [Shape([float(v) for v in box], "hand", float(score))
                for box, score in zip(result.boxes.xyxy.cpu().tolist(), result.boxes.conf.cpu().tolist())]


def detect_project(project: Project, indices: list[int], model_path=DEFAULT_MODEL, confidence=0.55,
                   device="auto", image_size=960, progress=lambda *_: None, cancelled=lambda: False):
    progress(0, max(1, len(indices)), "加载手部检测模型…")
    detector = HandDetector(model_path, confidence, device, image_size)
    updates = {}
    with FrameReader(project.source) as reader:
        for step, index in enumerate(indices):
            if cancelled():
                raise Cancelled("检测已取消，本次检测结果未应用。")
            image = reader.read(index)
            shapes = detector.detect(image)
            updates[index] = (shapes, image.shape[1], image.shape[0])
            progress(step + 1, len(indices), f"检测 {step + 1}/{len(indices)} · 本帧 {len(shapes)} 只手")
    if cancelled():
        raise Cancelled("检测已取消，本次检测结果未应用。")
    return updates
