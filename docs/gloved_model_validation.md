# A 工位戴手套检测验证

验证日期：2026-10-14。素材仅使用 `A工位参考视频/video_crop2.mp4`（1280×720、60 FPS、326.13 秒），未测试另外两个视频。工位为俯视白色织物手套，包含双手操作、单手、工具握持、遮挡、画面边缘和运动模糊。

## 选型结果

推荐 Grounding DINO Tiny，提示词 `gloved hand.`，框置信度 0.40、文本阈值 0.20、NMS IoU 0.50。采用原始预训练权重，没有工位微调。它能生成手部矩形框，动作标签仍由人选择。

先在六个分散时间点试验，再在覆盖视频首尾的 32 个等间隔帧比较。下表的框数是检测输出，**不是人工真值或准确率**；模型之间的分数不直接可比。

| 模型 | 实际试验设置 | 结果与判断 |
| --- | --- | --- |
| Bingsu 手部 YOLOv8n | 32 帧，置信度 0.55，960 尺寸 | 17 个框，15 帧无框；白色手套漏检明显。另六帧降低到 0.20 仍漏检。 |
| Bingsu 手部 YOLOv8s | 六帧，置信度 0.20，960 尺寸 | 六帧输出框数为 2、1、1、1、0、0，仍有明显漏检。 |
| Buildvision hazards v0.3 | 六帧，置信度 0.15，筛选 gloves | 六帧均无手套框。施工场景模型不适配当前俯视工位。 |
| Tanishjain9 YOLOv8n PPE | 六帧，置信度 0.15，筛选 Gloves | 输出 2、1、1、0、1、0；目视可见部分框覆盖桌面或袖子，不推荐。 |
| Safetyvision YOLOv8 v2 | 六帧，置信度 0.15，筛选 Gloves | 六帧均无手套框。 |
| YOLOv8s-World v2 | 32 帧，固定 glove / gloved hand / hand 词表，输入旋转 180°，置信度 0.20，960 尺寸 | 46 个框，8 帧无框；比裸手模型好，但后半段握工具手漏检较多，部分帧多框。 |
| Grounding DINO Tiny | 同一组 32 帧，gloved hand.，置信度 0.40 | 56 个框，仅首帧无框；目视更稳定，仍漏掉一些边缘截断手和模糊手。当前推荐。 |

32 帧初始比较在本机 RTX 4090、FP32 下，排除首帧后单次调用中位耗时：普通手 YOLO 约 7 ms、旋转 YOLO-World 约 12 ms、Grounding DINO 约 140 ms。包括预处理和结果处理，未包含视频解码和模型加载；适用于离线初次标注，不能据此推断实时系统性能。不是多轮基准测试。

## 软件集成与复验

- 界面默认“戴手套 · Grounding DINO”，同时保留普通手 YOLO 预设和自定义模型入口。
- 本地配置：`models/gloved_grounding_dino.json`。本地权重：`models/grounding-dino-tiny/`。
- Transformers 5.6.2 使用 `post_process_grounded_object_detection(threshold=...)`，结果转换回原始图像尺寸，截断到边界，NMS 去重；输出 `hand` 标签，支持现有批量剔除、动作赋值与 rectangle 导出。
- 对完整视频按 1 FPS 运行集成后的检测器。项目保存 / 读取以及全部已导出 JSON 的重新导入都进行一致性检查。
- 整段共 327 帧、577 个输出框；0 / 1 / 2 / 3 框的帧数分别为 5 / 75 / 239 / 8。模型加载、解码和检测总耗时约 55.3 秒（不含导出），**这些计数不代表真实手数或准确率**。
- 结果在本机 `artifacts/gloved_verification_crop2/`：`gloved_review.handproj`、`export/`、四张 `review_*.jpg`、`report.json`。复验命令为 `python tools/verify_gloved.py <视频路径> --fps 1 --output <新目录>`。
- 验证不使用 GUI 自动恢复文件；源视频只读。原始视频、预览图片、导出数据和模型权重均不提交 Git。

## 限制

目前仅验证一个视频，尚未绘制逐帧真值框，也未计算 IoU、precision、recall 或 mAP。32 帧目视比较足以排除明显不适配的候选，但不构成工位全场景精度保证。降低到 0.20 的 DINO 试验会误检螺丝刀、六角工具等，因此采用 0.40；有少量边缘手因此漏检。

完整 1 FPS 检测后检查了全部 8 个“三框帧”，可见擦拭时手 / 抹布重叠重复框（17、18、20 秒），鞋子误检（202、212、270 秒）和红色六角工具误检（270、274、279 秒）。因此即使阈值 0.40，仍有少量误检；不能把初标直接当最终标注。相关预览在本机 `artifacts/gloved_verification_crop2/anomalies.jpg`。模型只按文字提示识别外观，不理解 SOP 相关手，也未强制每帧最多两只手。

若要进一步提升并用于 SOP 自动检测，应使用当前模型生成初标，人工修正后构建本工位的训练 / 验证集，再微调小型检测器；本次未实施训练。其他颜色、材质手套和另外两个视频的表现尚未验证。

## 来源与可复现版本

- [Grounding DINO Tiny 官方模型卡](https://huggingface.co/IDEA-Research/grounding-dino-tiny)，Apache-2.0。固定 revision `a2bb814dd30d776dcf7e30523b00659f4f141c71`，主权重 SHA256 `1a2412ef99bd74bcd3c2a246fa1e48581f8889a1300c9051974741314fc042f3`；其他文件校验值内置在 `hand_anno/gloved_model.py`。
- [Transformers Grounding DINO 官方接口](https://huggingface.co/docs/transformers/model_doc/grounding-dino)。
- [Ultralytics YOLO-World 官方文档](https://docs.ultralytics.com/models/yolo-world/)，用于自定义词表和离线保存；未对候选权重做训练。
- [Bingsu/adetailer](https://huggingface.co/Bingsu/adetailer)：固定 revision `878390f19f369e91111d3c254ee6cc7c55a47510`。
- [Buildvision PPE 模型卡](https://huggingface.co/constructelligence/construction-site-safety-hazards)：revision `1e9364849470d0c69f7c5bc4c26a81c286fae8b5`，`buildvision-hazards-v0.3.pt`。
- [Tanishjain9 PPE 模型卡](https://huggingface.co/Tanishjain9/yolov8n-ppe-detection-6classes)：revision `a2c1a97646ade96e48adda74781dd455d0456c40`，`best.pt`。
- [Safetyvision PPE 模型卡](https://huggingface.co/ayushgupta7777/safetyvision-yolov8)：revision `56a71758b55f0e9f2b4b2d6b51a779a1f882da10`，`v2/best.pt`。
