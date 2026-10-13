from __future__ import annotations

import argparse
import os
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description="手部动作标注桌面工作台")
    parser.add_argument("source", nargs="?", help="视频、图片目录或 .handproj 项目")
    parser.add_argument("--folder-fps", type=float, default=5, help="图片序列源 FPS")
    parser.add_argument("--screenshot", help="离屏生成界面截图并退出（验证用）")
    args = parser.parse_args()
    if args.screenshot:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtCore import QTimer
    from hand_anno.app import MainWindow, create_application

    app = create_application()
    preview_recovery = tempfile.TemporaryDirectory(prefix="handflow-preview-") if args.screenshot else None
    window = MainWindow(recovery_directory=preview_recovery.name if preview_recovery else None)
    if args.source:
        if args.source.endswith(".handproj"):
            window.load_project(args.source)
        else:
            window.load_source(args.source, args.folder_fps, restore=not bool(args.screenshot))
    window.show()
    if args.screenshot:
        def capture():
            window.grab().save(args.screenshot)
            window.close()
            app.quit()
        QTimer.singleShot(350, capture)
    try:
        return app.exec()
    finally:
        if preview_recovery:
            preview_recovery.cleanup()


if __name__ == "__main__":
    sys.exit(main())
