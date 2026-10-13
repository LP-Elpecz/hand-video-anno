"""Small, original SVG line icons rendered locally at high DPI."""
from functools import lru_cache

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from .theme import PALETTE as C


PATHS = {
    "video": '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="m10 8 6 4-6 4z"/>',
    "images": '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 2h11M3 16l5-5 5 5 3-3 5 5"/><circle cx="16" cy="10" r="1"/>',
    "folder": '<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v2M3 7h15a2 2 0 0 1 2 2l-2 10H4L2 9a2 2 0 0 1 1-2z"/>',
    "save": '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12l4 4v12a2 2 0 0 1-2 2z"/><path d="M7 3v6h9V3M7 21v-7h10v7"/>',
    "export": '<path d="M12 15V3m-4 4 4-4 4 4M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6"/>',
    "undo": '<path d="M8 4 3 9l5 5M3 9h11a6 6 0 0 1 0 12h-2"/>',
    "redo": '<path d="m16 4 5 5-5 5M21 9H10a6 6 0 0 0 0 12h2"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 1 1 5 2c-2 1-2 2-2 3M12 17h.01"/>',
    "play": '<path d="m8 4 12 8-12 8z"/>',
    "pause": '<path d="M8 5v14M16 5v14"/>',
    "previous": '<path d="M5 5v14m14-14L7 12l12 7z"/>',
    "next": '<path d="M19 5v14M5 5l12 7-12 7z"/>',
    "trash": '<path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 11v6M14 11v6"/>',
    "draw": '<path d="M3 9V3h6M15 21h6v-6M5 19l3-1L20 6l-3-3L5 15zM14 6l3 3"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/>',
    "start": '<path d="M4 3v18M8 5h12l-4 5 4 5H8"/>',
    "end": '<path d="M20 3v18M16 5H4l4 5-4 5h12"/>',
    "select": '<path d="M9 3H3v6M15 3h6v6M21 15v6h-6M9 21H3v-6"/><rect x="7" y="7" width="10" height="10" rx="1"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "minus": '<path d="M5 12h14"/>',
    "zoom-in": '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6M10 7v6M7 10h6"/>',
    "zoom-out": '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6M7 10h6"/>',
    "scan": '<path d="M8 3H3v5M16 3h5v5M21 16v5h-5M8 21H3v-5M3 12h18"/>',
    "target": '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
    "eye": '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "tag": '<path d="M3 3h8l10 10-8 8L3 11z"/><circle cx="7.5" cy="7.5" r="1"/>',
    "hand": '<path d="M8 12V6a2 2 0 0 1 4 0v5-7a2 2 0 0 1 4 0v8-5a2 2 0 0 1 4 0v8c0 5-3 7-7 7-3 0-5-2-7-5l-3-4a2 2 0 0 1 3-3l2 2z"/>',
    "timeline": '<path d="M3 12h18M5 6v12M10 8v8M15 4v16M20 8v8"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-right": '<path d="m9 6 6 6-6 6"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "logo": f'<rect x="1" y="1" width="22" height="22" rx="6" fill="{C["brand"]}" stroke="none"/><path d="M9 6H6v3M15 6h3v3M18 15v3h-3M9 18H6v-3M9 12h6" stroke="{C["on_accent"]}"/>',
}


@lru_cache(maxsize=128)
def icon(name, color=C["muted"], size=20):
    body = PATHS.get(name, PATHS["select"])
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def button_icon(text):
    for prefix, name in (
        ("上一帧", "previous"), ("下一帧", "next"), ("播放", "play"), ("暂停", "pause"),
        ("放大", "zoom-in"), ("缩小", "zoom-out"), ("全览", "select"), ("聚焦", "target"),
        ("设为起点", "start"), ("设为终点", "end"), ("选择整个", "select"),
        ("将当前时间", "plus"), ("移除", "minus"), ("清空", "trash"),
        ("检测", "scan"), ("将当前所选", "target"), ("预览", "eye"),
        ("删除", "trash"), ("为时间", "tag"), ("仅修改", "tag"), ("取消", "minus"),
    ):
        if text.startswith(prefix):
            return name
    return "folder"
