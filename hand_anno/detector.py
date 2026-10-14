from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from pathlib import Path

from .core import Cancelled, FrameReader, Project, Shape

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = ROOT / "models" / "hand_yolov8n.pt"
GLOVED_MODEL = ROOT / "models" / "gloved_grounding_dino.json"
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


class GlovedHandDetector:
    def __init__(self, model_path=GLOVED_MODEL, confidence=0.4, device="auto",
                 progress=lambda *_: None, cancelled=lambda: False):
        import torch
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
        from .gloved_model import DEFAULT_DIRECTORY, download_gloved_model

        profile_path = Path(model_path).resolve()
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        if profile.get("backend") != "grounding_dino":
            raise ValueError("模型配置的 backend 必须为 grounding_dino。")
        self.prompt = str(profile.get("prompt", "gloved hand.")).strip().lower()
        if not self.prompt:
            raise ValueError("模型提示词不能为空。")
        if not self.prompt.endswith("."):
            self.prompt += "."
        self.confidence = confidence
        self.text_threshold = float(profile.get("text_threshold", 0.2))
        self.nms_threshold = float(profile.get("nms_threshold", 0.5))
        if not 0 <= self.text_threshold <= 1 or not 0 <= self.nms_threshold <= 1:
            raise ValueError("文本阈值和 NMS 阈值必须在 0–1 之间。")
        directory = (profile_path.parent / profile["model_directory"]).resolve()
        if directory == DEFAULT_DIRECTORY.resolve():
            download_gloved_model(directory, progress, cancelled)
        elif not directory.is_dir():
            raise ValueError(f"找不到本地模型目录：{directory}")
        if cancelled():
            raise Cancelled("检测已取消，本次检测结果未应用。")
        self.device = ("cuda:0" if torch.cuda.is_available() else "cpu") if device == "auto" else (
            f"cuda:{device}" if str(device).isdigit() else device)
        progress(0, 1, "加载戴手套模型 Grounding DINO…")
        self.processor = AutoProcessor.from_pretrained(directory, local_files_only=True)
        self.model = AutoModelForZeroShotObjectDetection.from_pretrained(directory, local_files_only=True).to(self.device).eval()

    def detect(self, image):
        import cv2
        import torch
        from torchvision.ops import nms

        height, width = image.shape[:2]
        inputs = self.processor(images=cv2.cvtColor(image, cv2.COLOR_BGR2RGB), text=self.prompt,
                                return_tensors="pt").to(self.device)
        with torch.inference_mode():
            outputs = self.model(**inputs)
        result = self.processor.post_process_grounded_object_detection(
            outputs, inputs.input_ids, threshold=self.confidence, text_threshold=self.text_threshold,
            target_sizes=[(height, width)])[0]
        boxes, scores = result["boxes"], result["scores"]
        boxes[:, [0, 2]] = boxes[:, [0, 2]].clamp(0, width)
        boxes[:, [1, 3]] = boxes[:, [1, 3]].clamp(0, height)
        keep = nms(boxes, scores, self.nms_threshold)[:10]
        shapes = []
        for i in keep:
            box, score = boxes[i].cpu().tolist(), scores[i].item()
            if box[2] > box[0] and box[3] > box[1]:
                shapes.append(Shape(box, "hand", float(score)))
        return shapes


def create_detector(model_path, confidence, device, image_size=960,
                    progress=lambda *_: None, cancelled=lambda: False):
    if Path(model_path).suffix.lower() == ".json":
        return GlovedHandDetector(model_path, confidence, device, progress, cancelled)
    return HandDetector(model_path, confidence, device, image_size)


def detect_project(project: Project, indices: list[int], model_path=DEFAULT_MODEL, confidence=0.55,
                   device="auto", image_size=960, progress=lambda *_: None, cancelled=lambda: False):
    progress(0, max(1, len(indices)), "加载手部检测模型…")
    detector = create_detector(model_path, confidence, device, image_size, progress, cancelled)
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
