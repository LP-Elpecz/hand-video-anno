# 手部动作标注工作台

用于 SOP 装配视频的本地 Python 桌面工具：先自动检测手框，再按时间段删除无关手，给保留框赋纯动作标签，最后输出 X-AnyLabeling 的 rectangle JSON 和图片。

## 启动

本机 `common` Conda 环境已配置好依赖和 CUDA，默认手部模型也已下载。双击 **启动.bat**，或执行：

```powershell
conda activate common
python main.py
```

可以直接带入素材或项目：

```powershell
python main.py "示例视频.mp4"
python main.py "projects/示例视频_已检测.handproj"
python main.py "D:/抽帧图片" --folder-fps 5
```

已检测的示例项目在本机 `projects/示例视频_已检测.handproj`，导出验证结果和验证报告在 `artifacts/`。原始视频、权重、项目恢复副本和导出数据集不上传 Git。

新电脑已有 `common` 环境时：

```powershell
conda run -n common python -m pip install -r requirements.txt
conda run -n common python tools/download_model.py
conda run -n common python main.py
```

没有 `common` 时，先用 `conda create -n common python=3.12` 创建环境。Ultralytics 会安装所需 PyTorch；GPU 使用需要与显卡兼容的 CUDA PyTorch 构建。CPU 也可运行，速度随机器变化。

## 使用流程

1. **打开素材**：支持 MP4、AVI、WebM、MOV、MKV 等 OpenCV 可解码视频；图片目录支持 JPG、PNG、BMP、WebP、TIFF，使用自然数字排序。图片同名 JSON 会自动导入，支持两点或四点 rectangle；输出统一四点。其他形状会明确报错，避免静默丢失。
2. **设置时间范围**：输入秒数，或用 I / O 把当前帧设为起止点；Shift + 左键拖动时间轴也能选段，并实时预览鼠标位置附近的抽帧画面。普通左键拖动可连续预览，不改变所选范围；拖动时暂停播放，松开后停留在对应帧。后续检测、删除、赋动作使用该范围。批量编辑包含起止时间；精度为毫秒。
3. **设置抽帧计划**：全局默认 5 FPS；选择时间范围后输入独立 FPS 并加入计划。分段使用 `[起点, 终点)`，互相不能重叠；剩余时间使用默认频率。大于源 FPS 时按源帧上限处理。调整计划不清除已有标注，但导出只包含当前计划中的帧。
4. **模型打标**：默认 YOLOv8n 手部模型，960 推理尺寸、0.55 置信度，自动优先 GPU。只检测当前范围中未检测 / 编辑的抽帧；重新检测需要勾选覆盖已有标注。整个检测完成后统一应用，取消或失败不应用部分结果。模型检测可撤销。
5. **剔除无关手**：相对位置模式在有多个框时删除最左或最右的一只；只有一只时按可调分界线判断。画面分区模式删除分界线一侧的所有框。两种模式都按画面坐标判断，和操作者生理左右无关。
6. **参考手跟踪**：点选手框，设为参考，然后预览。软件从参考帧向前、向后使用 IoU、中心距离、速度预测及尺寸约束匹配。粉色框为匹配目标；歧义或超过允许失联时间会停止该方向。删除或赋标签只作用于匹配到的框，不处理漏检及停止后的帧。允许失联时间按秒计算，分段 FPS 改变时仍一致。低 FPS、大幅运动、交叉或遮挡时需缩短范围、更换参考帧或增加 FPS。
7. **批量赋动作**：输入动作名，选择范围内全部保留框、画面左 / 右手或参考手跟踪结果。`label` 只写动作名，不拼接左右。初次检测的 `hand` 表示尚未赋动作。也能只修改当前框。
8. **手动复核**：点选框后可拖动，拖角调整尺寸；R 开启拖动补框，Del 删除当前框。导入 JSON 的额外字段（如 `group_id`、flags、attributes）会保留。
9. **保存与导出**：Ctrl+S 保存 `.handproj`（含素材位置、所有已存标注和抽帧计划）。修改会自动保存到 `projects/recovery_*.handproj`；重新打开同一素材可恢复。Ctrl+E 选择新的目录名，输出全部当前抽帧和每帧 JSON，包括无手帧的空 `shapes`。导出通过临时目录完整生成后再提交，取消不留下半成品、不覆盖既有目录。尚未检测或仍有 `hand` 标签时，界面提示复核。

界面各区标题可点击折叠；已检测项目会自动折叠抽帧和模型设置，使删除和动作操作更容易访问。撤销 / 重做保留最近 40 次标注操作；抽帧计划改动不在标注撤销栈内。

## 时间轴与导出格式

- 时间轴按真实时间比例显示。蓝色横条表示独立 FPS 段，绿色抽帧表示这一帧只有 1 个手框，黄色表示有 2 个及以上手框，灰色表示未检测或空框。手框数量的颜色不受动作标签影响，删除、补框和撤销后会实时更新。
- 视频图片命名为 `frame_00000300.jpg`，数字是从 0 开始的原视频帧号；JSON 与图片同目录、同名。
- 图片目录输出使用源编号前缀保留原图片名，避免不同图片同名 stem 导致 JSON 冲突；源图片内容直接复制。
- `manifest.json` 记录源 FPS、原帧号、精确时间戳、处理状态和抽帧计划。重新打开导出图片目录时会自动恢复时间戳，支持不同时间段不同 FPS。
- `annotation.handproj` 同时保存项目。它引用原始素材；继续编辑导出图片本身可直接打开该图片目录。
- `.handproj` 不内嵌视频或图片。保留原素材路径；若迁移到新目录，项目与同名源素材放在一起可恢复路径。视频时间轴按 OpenCV 报告的平均 FPS 构建，适合此示例的固定帧率视频；可变帧率视频需先转固定帧率才能得到准确时间。

例子：

```json
{
  "version": "3.3.0",
  "flags": {},
  "shapes": [{
    "label": "拧螺丝",
    "score": 0.9,
    "points": [[100, 80], [180, 80], [180, 160], [100, 160]],
    "group_id": null,
    "description": "",
    "difficult": false,
    "shape_type": "rectangle",
    "flags": {},
    "attributes": {}
  }],
  "imagePath": "frame_00000300.jpg",
  "imageData": null,
  "imageHeight": 544,
  "imageWidth": 960,
  "description": ""
}
```

## 验证与可复用组件

```powershell
conda run -n common python -m pytest -q
conda run -n common python tools/verify_example.py
```

第二条需要项目根目录存在 `示例视频.mp4`，会真实运行 GPU / CPU 推理，设置 0–15 秒 10 FPS、15–30 秒 2 FPS，其余 5 FPS；检查项目保存读取、参考手删除 / 撤销 / 重做、纯动作赋值、所有抽帧的图片和 JSON 导出及重新导入。结果在 `artifacts/verification_report.json`，多时段检测预览在 `artifacts/detection_review.jpg`。检测计数不代表精度评测，示例没有人工逐帧真值。

本机验证环境：Python 3.12.13、PySide6-Essentials 6.10.2、Ultralytics 8.4.176、PyTorch 2.11.0+cu128、RTX 4090。预训练模型仍可能误检布料或漏掉遮挡手，因此最终动作标注需复查；可调整置信度、手动补框或使用领域微调模型。

复用了 OpenCV 解码 / 图像读写、PySide6 桌面组件、Ultralytics 推理及公开手部权重，按官方 X-AnyLabeling JSON 结构输出。时间段抽帧、批量编辑、跟踪关联、历史和事务导出为本项目实现。

- [手部权重来源与模型卡](https://huggingface.co/Bingsu/adetailer)
- [Ultralytics Python 推理接口](https://docs.ultralytics.com/usage/python/)
- [X-AnyLabeling 标注数据规范](https://github.com/CVHub520/X-AnyLabeling/blob/main/docs/en/user_guide.md)
- [X-AnyLabeling rectangle 序列化参考](https://github.com/CVHub520/X-AnyLabeling/blob/main/anylabeling/services/auto_labeling/__base__/yolo.py)
