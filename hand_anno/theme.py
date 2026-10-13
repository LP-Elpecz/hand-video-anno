"""HandFlow's shared desktop palette and widget styles."""
from pathlib import Path

ASSETS = (Path(__file__).resolve().parent.parent / "assets" / "icons").as_posix()

STYLE = """
QMainWindow, QWidget { background: #0b111a; color: #e0e8f4; font-size: 13px; }
QWidget#sectionCard { background: #121c29; border: 1px solid #263447; border-radius: 12px; }
QWidget#sectionBody, QWidget#controlRow { background: transparent; }
QWidget#toolbarSpacer { background: transparent; }
QLabel { background: transparent; }
QLabel[role="hint"] { color: #94a5bc; font-size: 11px; }
QLabel#sectionNumber { background: #213147; color: #9cc2ff; border-radius: 7px; font-size: 11px; font-weight: 600; }
QLabel#brandName { color: #f1f5ff; font-size: 19px; font-weight: 600; }
QLabel#brandNote { color: #7e92ac; font-size: 11px; }
QLabel#sourceTitle { color: #f1f5ff; font-size: 20px; font-weight: 600; }
QLabel#sourceMeta, QLabel#frameMeta { color: #91a5bf; font-size: 12px; }
QLabel#frameClock { color: #c4d9ff; font-family: 'Consolas'; font-size: 15px; }
QLabel#viewerTitle { color: #91a5bf; font-size: 12px; }
QLabel#handBadge { background: #263447; color: #bac9dd; border-radius: 6px; padding: 4px 9px; font-size: 11px; }
QLabel#handBadge[single="true"] { background: #163c35; color: #74dfbe; }
QLabel#samplingBadge { background: #172b42; color: #a2c9ff; border: 1px solid #294664; border-radius: 6px; padding: 5px 9px; font-size: 12px; }
QLabel#viewInfo { color: #839bb9; font-family: 'Consolas'; font-size: 11px; }
QLabel#summary { color: #a9bbd2; font-size: 12px; }
QLabel#statusMessage { color: #92a7c2; font-size: 12px; padding: 3px 0; }
QPushButton { background: #1a283a; color: #d4e0f1; border: 1px solid #34465e; border-radius: 7px; padding: 7px 10px; }
QPushButton:hover { background: #253b56; border-color: #5c7ba4; color: #f2f7ff; }
QPushButton:pressed { background: #14263c; }
QPushButton:focus { border-color: #77acff; }
QPushButton:disabled { color: #576981; background: #141f2e; border-color: #243247; }
QPushButton[primary="true"] { background: #77acff; color: #0b1b31; border-color: #77acff; font-weight: 600; }
QPushButton[primary="true"]:hover { background: #9ac2ff; border-color: #9ac2ff; }
QPushButton[danger="true"] { color: #f49b9c; background: #2b202b; border-color: #66414e; }
QPushButton[danger="true"]:hover { background: #432a37; border-color: #be7485; }
QToolButton { background: transparent; color: #b7c7dc; border: 1px solid transparent; border-radius: 7px; padding: 7px 10px; }
QToolButton:hover { background: #21354e; color: #f3f7ff; }
QToolButton:disabled { color: #52657e; }
QToolButton#sectionTitle { font-weight: 600; color: #e4ecf9; text-align: left; padding: 2px 0; }
QToolButton#sectionToggle { padding: 2px; }
QToolButton[primary="true"] { background: #254c7b; color: #c9e0ff; border-color: #3a6495; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #0e1723; color: #e0e9f6; border: 1px solid #34475e; border-radius: 6px; padding: 5px 8px; min-height: 20px; selection-background-color: #315b8d; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: #77acff; }
QLineEdit:disabled, QDoubleSpinBox:disabled, QComboBox:disabled { color: #63768f; border-color: #26364c; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: url(__ASSETS__/chevron-down.svg); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: #18283c; color: #e0e9f6; selection-background-color: #315b8d; outline: 0; border: 1px solid #405978; }
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button { width: 19px; background: #1b2b40; border: none; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url(__ASSETS__/chevron-up.svg); width: 10px; height: 10px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url(__ASSETS__/chevron-down.svg); width: 10px; height: 10px; }
QCheckBox { spacing: 8px; color: #a7bdd5; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #476079; border-radius: 4px; background: #111d2b; }
QCheckBox::indicator:checked { background: #77acff; border-color: #77acff; image: url(__ASSETS__/check.svg); }
QListWidget { background: #0e1723; color: #b6c8e0; border: 1px solid #263a50; border-radius: 7px; padding: 4px; outline: 0; }
QListWidget::item { padding: 3px 7px; border-radius: 4px; }
QListWidget::item:selected { background: #254468; color: #edf5ff; }
QListWidget::item:hover { background: #1d314b; }
QProgressBar { border: 1px solid #2c4561; border-radius: 6px; text-align: center; background: #17263b; color: #c7def8; min-height: 20px; }
QProgressBar::chunk { background: #377fbd; border-radius: 5px; }
QToolBar { background: #111c2b; border-bottom: 1px solid #283b53; spacing: 5px; padding: 8px 12px; }
QToolBar::separator { background: #2b405b; width: 1px; margin: 5px 9px; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #111c2b; width: 10px; margin: 0; }
QScrollBar:horizontal { background: #152236; height: 10px; margin: 0; border-radius: 4px; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: #3c5676; border-radius: 4px; min-width: 24px; min-height: 24px; }
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #5c7fa7; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; background: transparent; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QSlider::groove:horizontal { height: 4px; background: #293d58; border-radius: 2px; }
QSlider::handle:horizontal { width: 12px; margin: -4px 0; background: #77acff; border-radius: 6px; }
QSplitter::handle { background: #0b111a; width: 12px; }
QToolTip { background: #21334b; color: #e6effb; border: 1px solid #547496; padding: 6px; }
""".replace("__ASSETS__", ASSETS)
