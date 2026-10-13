"""Palette aligned to AI-SOP-DEMO's app.py :root and primary button styles."""
from pathlib import Path

ASSETS = (Path(__file__).resolve().parent.parent / "assets" / "icons").as_posix()

PALETTE = {
    "bg": "#050c14", "panel": "#0b1724", "panel2": "#102032", "panel3": "#13263a",
    "line": "#294158", "text": "#f2f7fb", "muted": "#9aafc1", "subtle": "#71879a",
    "accent": "#42dbc8", "accent2": "#42a9df", "success": "#41d5a2",
    "warning": "#f3bb62", "danger": "#ff707c", "reference": "#ff9aa2",
    "on_accent": "#061519", "video": "#040a10", "video_line": "#253b4e",
    "brand": "#55dccc", "badge": "#102f3f", "badge_text": "#86eee1",
}

STYLE = """
QMainWindow, QWidget { background: @bg@; color: @text@; font-size: 13px; }
QWidget#sectionCard { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0e1d2c,stop:1 #081420); border: 1px solid @line@; border-radius: 12px; }
QWidget#sectionBody, QWidget#controlRow { background: transparent; }
QWidget#toolbarSpacer { background: transparent; }
QLabel { background: transparent; }
QLabel[role="hint"] { color: @muted@; font-size: 11px; }
QLabel#sectionNumber { background: @badge@; color: @badge_text@; border-radius: 7px; font-size: 11px; font-weight: 600; }
QLabel#brandName { color: @text@; font-size: 19px; font-weight: 600; }
QLabel#brandNote { color: @subtle@; font-size: 11px; }
QLabel#sourceTitle { color: @text@; font-size: 20px; font-weight: 600; }
QLabel#sourceMeta, QLabel#frameMeta { color: @muted@; font-size: 12px; }
QLabel#frameClock { color: #9af1e7; font-family: 'Consolas'; font-size: 15px; }
QLabel#viewerTitle { color: @muted@; font-size: 12px; }
QLabel#handBadge { background: @panel3@; color: @muted@; border-radius: 6px; padding: 4px 9px; font-size: 11px; }
QLabel#handBadge[single="true"] { background: #0e3029; color: #70e1b5; }
QLabel#samplingBadge { background: @badge@; color: @badge_text@; border: 1px solid #286566; border-radius: 6px; padding: 5px 9px; font-size: 12px; }
QLabel#viewInfo { color: @subtle@; font-family: 'Consolas'; font-size: 11px; }
QLabel#summary { color: #b2c1cd; font-size: 12px; }
QLabel#statusMessage { color: @muted@; font-size: 12px; padding: 3px 0; }
QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #14263a,stop:1 #0d1b2a); color: #d8e5ee; border: 1px solid #304960; border-radius: 7px; padding: 7px 10px; }
QPushButton:hover { background: @panel3@; border-color: #4f708d; color: @text@; }
QPushButton:pressed { background: @panel2@; }
QPushButton:focus { border-color: @accent@; }
QPushButton:disabled { color: @subtle@; background: @panel@; border-color: @line@; }
QPushButton[primary="true"] { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #6be8d7,stop:1 #3db4db); color: @on_accent@; border-color: #55e3d1; font-weight: 600; }
QPushButton[primary="true"]:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #8aefe2,stop:1 #57c5e5); border-color: #8aefe2; }
QPushButton[danger="true"] { color: @reference@; background: #2a1e2a; border-color: #743d4b; }
QPushButton[danger="true"]:hover { background: #412332; border-color: @danger@; }
QToolButton { background: transparent; color: #b2c1cd; border: 1px solid transparent; border-radius: 7px; padding: 7px 10px; }
QToolButton:hover { background: @panel3@; color: @text@; }
QToolButton:disabled { color: @subtle@; }
QToolButton#sectionTitle { font-weight: 600; color: @text@; text-align: left; padding: 2px 0; }
QToolButton#sectionToggle { padding: 2px; }
QToolButton[primary="true"] { background: #123d46; color: #92f0e5; border-color: #2d7779; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #0a1724; color: @text@; border: 1px solid #2b4258; border-radius: 6px; padding: 5px 8px; min-height: 20px; selection-background-color: #205967; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: @accent@; }
QLineEdit:disabled, QDoubleSpinBox:disabled, QComboBox:disabled { color: @subtle@; border-color: @line@; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: url(__ASSETS__/chevron-down.svg); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: @panel2@; color: @text@; selection-background-color: #205967; outline: 0; border: 1px solid @line@; }
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button { width: 19px; background: @panel3@; border: none; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url(__ASSETS__/chevron-up.svg); width: 10px; height: 10px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url(__ASSETS__/chevron-down.svg); width: 10px; height: 10px; }
QCheckBox { spacing: 8px; color: #b2c1cd; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #47657e; border-radius: 4px; background: @panel@; }
QCheckBox::indicator:checked { background: @accent@; border-color: @accent@; image: url(__ASSETS__/check.svg); }
QListWidget { background: #081522; color: #dce7ef; border: 1px solid #29445c; border-radius: 7px; padding: 4px; outline: 0; }
QListWidget::item { padding: 3px 7px; border-radius: 4px; }
QListWidget::item:selected { background: #174a52; color: #92f0e5; }
QListWidget::item:hover { background: @panel3@; }
QProgressBar { border: 1px solid @line@; border-radius: 6px; text-align: center; background: @panel2@; color: @text@; min-height: 20px; }
QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #6be8d7,stop:1 #3db4db); border-radius: 5px; }
QToolBar { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #112335,stop:1 #091826); border-bottom: 1px solid @line@; spacing: 5px; padding: 8px 12px; }
QToolBar::separator { background: @line@; width: 1px; margin: 5px 9px; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: @panel@; width: 10px; margin: 0; }
QScrollBar:horizontal { background: @panel2@; height: 10px; margin: 0; border-radius: 4px; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: #47657e; border-radius: 4px; min-width: 24px; min-height: 24px; }
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #4c718d; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; background: transparent; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QSlider::groove:horizontal { height: 4px; background: @line@; border-radius: 2px; }
QSlider::handle:horizontal { width: 12px; margin: -4px 0; background: @accent@; border-radius: 6px; }
QSplitter::handle { background: @bg@; width: 12px; }
QToolTip { background: @panel3@; color: @text@; border: 1px solid #47657e; padding: 6px; }
""".replace("__ASSETS__", ASSETS)

for name, value in PALETTE.items():
    STYLE = STYLE.replace(f"@{name}@", value)
