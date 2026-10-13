# 手部检测权重

默认文件为 `hand_yolov8n.pt`，来自 [Bingsu/adetailer](https://huggingface.co/Bingsu/adetailer)。权重已下载到此本地目录，Git 不跟踪二进制权重。

新电脑运行 `conda run -n common python tools/download_model.py` 下载。界面也会在默认权重不存在时下载；离线使用前请提前准备文件。

- 固定版本：`878390f19f369e91111d3c254ee6cc7c55a47510`
- [权重来源与下载](https://huggingface.co/Bingsu/adetailer/blob/878390f19f369e91111d3c254ee6cc7c55a47510/hand_yolov8n.pt)
- SHA256：`f3f23b865741cc8373a76dfac31a71ffd71356a480ca43266f294815b608e174`
- 模型卡标明权重许可证为 Apache-2.0；推理库 Ultralytics 的许可证见其官方仓库。

界面可选择其他含 `hand` 类别的 Ultralytics 兼容 `.pt` 或 `.onnx` 模型。也已在本地试验 `hand_yolov8s.pt`，但它在此视频上同样存在布料误检，因此默认保持轻量模型。
