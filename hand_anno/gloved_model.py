"""Pinned, verified local Grounding DINO assets; inference stays offline."""
from __future__ import annotations

import hashlib
import os
import urllib.request
from pathlib import Path

from .core import Cancelled

MODEL_REVISION = "a2bb814dd30d776dcf7e30523b00659f4f141c71"
MODEL_REPO = "IDEA-Research/grounding-dino-tiny"
DEFAULT_DIRECTORY = Path(__file__).resolve().parents[1] / "models" / "grounding-dino-tiny"
ASSETS = {
    "added_tokens.json": "909e96cb32d92ce728a01bc99850cbba26196d74115c17ebeb019275412588f2",
    "config.json": "eec82c5ab66e16df12a9a212e68ac011779927c2536cf9078658e35d85f0c67a",
    "model.safetensors": "1a2412ef99bd74bcd3c2a246fa1e48581f8889a1300c9051974741314fc042f3",
    "preprocessor_config.json": "8454179ba95e2ad22947835aad7b45862a601fc0055ab88bf1ee70892d3aea60",
    "special_tokens_map.json": "b6d346be366a7d1d48332dbc9fdf3bf8960b5d879522b7799ddba59e76237ee3",
    "tokenizer_config.json": "d40ab645b68211910b9170d22433d43186a6ec8ee6fd10ba170524b25bf4fb56",
    "tokenizer.json": "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",
    "vocab.txt": "07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3",
}


def download_gloved_model(directory=DEFAULT_DIRECTORY, progress=lambda *_: None, cancelled=lambda: False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for filename, expected in ASSETS.items():
        if cancelled():
            raise Cancelled("模型准备已取消，本次检测结果未应用。")
        path = directory / filename
        if path.exists():
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != expected:
                raise ValueError(f"模型文件校验失败：{path}，请移除此文件后重新下载。")
            continue
        temporary = path.with_suffix(path.suffix + ".download")
        try:
            url = f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{filename}"
            progress(0, 1, f"下载戴手套模型：{filename}…")
            with urllib.request.urlopen(url, timeout=30) as response, temporary.open("wb") as target:
                digest = hashlib.sha256()
                downloaded = 0
                while chunk := response.read(1024 * 1024):
                    if cancelled():
                        raise Cancelled("模型下载已取消，本次检测结果未应用。")
                    target.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    progress(0, 1, f"下载 {filename} · {downloaded / 1024 ** 2:.1f} MB")
            if digest.hexdigest() != expected:
                raise ValueError(f"模型下载校验失败：{filename}。")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    if cancelled():
        raise Cancelled("模型准备已取消，本次检测结果未应用。")
    return directory
