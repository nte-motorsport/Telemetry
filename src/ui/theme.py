"""Look of the app: the NTE Motorsport design tokens (Site / Rivals / Wiki) with a yellow accent."""
import os

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# src/assets; PyInstaller puts it at the same place relative to the modules
ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

# Tokens, as in the sites' :root. The accent is the site red (#fb514d) turned yellow at the
# same saturation and brightness, the same way Rivals and the Wiki recolour it.
ACCENT = "#fbcf4d"
ACCENT_HOVER = "#fddb7c"
ACCENT_DARK = "#2a230d"
DANGER = "#fb514d"
DANGER_DARK = "#2a0d0d"
BG = "#060607"
MENU_BG = "#0a0b0d"
TEXT = "#ffffff"
MUTED = "#999999"
GRID = "#2e2e2e"
DISABLED_TEXT = "#808080"    # white, the accent and the danger red at half strength on the black of a button
DISABLED_ACCENT = "#7e6827"
DISABLED_DANGER = "#7e2927"
RADIUS = 10
GAP = 10
CONTROL_HEIGHT = 38

FS_TITLE = 30
FS_BRAND = 29
FS_LG = 16
FS_MD = 12


def asset(*parts):
    return os.path.join(ASSETS, *parts).replace("\\", "/")


def load_fonts():
    """Momo Trust Display has no Cyrillic, so - like the sites' 'Momo Trust Display', 'Segoe UI' -
    Cyrillic letters fall back to Segoe UI glyph by glyph."""
    QFontDatabase.addApplicationFont(asset("MomoTrustDisplay-Regular.ttf"))
    f = QFont()
    f.setFamilies(["Momo Trust Display", "Segoe UI"])
    f.setPixelSize(FS_MD)
    f.setHintingPreference(QFont.PreferNoHinting)
    return f


def font(px):
    f = QFont()
    f.setFamilies(["Momo Trust Display", "Segoe UI"])
    f.setPixelSize(px)
    return f


_icons = {}


def icon(name, color=ACCENT, size=24):
    """A Tabler outline icon drawn in the given colour (the SVGs use currentColor)."""
    key = (name, color, size)
    if key not in _icons:
        svg = open(asset("icons", name + ".svg"), encoding="utf-8").read().replace("currentColor", color)
        r = QSvgRenderer(QByteArray(svg.encode()))
        pm = QPixmap(QSize(size, size) * 2)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        r.render(p)
        p.end()
        pm.setDevicePixelRatio(2)
        _icons[key] = QIcon(pm)
    return _icons[key]


STYLE = f"""
* {{ color: {TEXT}; }}
QToolTip {{ color: {TEXT}; background: {MENU_BG}; border: 2px solid {ACCENT}; border-radius: {RADIUS}px; padding: 6px; }}

#navbar, #statusBar {{ background: {BG}; }}
#siteTitle {{ font-size: {FS_BRAND}px; }}
#eyebrow {{ color: {ACCENT}; font-size: {FS_MD}px; }}
#pageTitle {{ font-size: {FS_TITLE}px; }}

*[role="panel"] {{ background: rgba(0, 0, 0, 128); border-radius: {RADIUS}px; }}
*[role="sectionTitle"] {{ font-size: {FS_LG}px; }}
*[role="muted"] {{ color: {MUTED}; }}
*[role="tileValue"] {{ font-size: {FS_TITLE}px; }}
*[role="tileValueBig"] {{ font-size: {FS_TITLE}px; color: {ACCENT}; }}

QPushButton {{
    min-height: {CONTROL_HEIGHT - 4}px; max-height: {CONTROL_HEIGHT - 4}px; padding: 0 10px;
    font-size: {FS_MD}px; background: #000; border: 2px solid {ACCENT}; border-radius: {RADIUS}px;
}}
QPushButton:hover {{ background: {ACCENT_DARK}; }}
QPushButton:checked, QPushButton[primary="true"] {{ color: #000; background: {ACCENT}; border-color: #000; }}
QPushButton:checked:hover, QPushButton[primary="true"]:hover {{ background: {ACCENT_HOVER}; }}
QPushButton[danger="true"] {{ border-color: {DANGER}; }}
QPushButton[danger="true"]:hover {{ background: {DANGER_DARK}; }}
QPushButton:disabled {{ color: {DISABLED_TEXT}; border-color: {DISABLED_ACCENT}; }}
QPushButton[danger="true"]:disabled {{ border-color: {DISABLED_DANGER}; }}
QPushButton[iconOnly="true"] {{ min-width: {CONTROL_HEIGHT - 4}px; max-width: {CONTROL_HEIGHT - 4}px; padding: 0; }}

QComboBox {{
    min-height: {CONTROL_HEIGHT - 4}px; max-height: {CONTROL_HEIGHT - 4}px; padding: 0 44px 0 10px;
    font-size: {FS_MD}px; background: rgba(0, 0, 0, 128); border: 2px solid {ACCENT}; border-radius: {RADIUS}px;
}}
QComboBox:focus {{ border-color: {ACCENT_HOVER}; }}
QComboBox::drop-down {{ border: none; width: 40px; }}
QComboBox::down-arrow {{ image: url({asset("icons", "chevron-down-accent.svg")}); width: 20px; height: 20px; }}
QComboBox QAbstractItemView {{
    background: {MENU_BG}; border: 2px solid {ACCENT}; border-radius: {RADIUS}px; padding: 4px; outline: none;
    selection-background-color: {ACCENT_DARK}; selection-color: {TEXT};
}}

QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; border: 2px solid {ACCENT}; background: #000; }}
QCheckBox::indicator {{ border-radius: 5px; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; image: url({asset("icons", "check-black.svg")}); }}
QRadioButton::indicator {{ border-radius: 10px; }}
QRadioButton::indicator:checked {{
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                                stop:0 {ACCENT}, stop:0.55 {ACCENT}, stop:0.6 #000, stop:1 #000);
}}

QLineEdit {{
    font-size: {FS_LG}px; background: transparent; border: 2px solid transparent; border-radius: {RADIUS}px; padding: 2px 6px;
}}
QLineEdit:hover {{ border-color: rgba(251, 207, 77, 90); }}
QLineEdit:focus {{ border-color: {ACCENT}; background: rgba(0, 0, 0, 128); }}

QTableWidget {{ background: transparent; border: none; font-size: {FS_LG}px; outline: none; }}
QTableWidget::item {{ padding-right: {GAP}px; border: none; }}
QTableWidget::item:selected {{ background: transparent; color: {TEXT}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: transparent; color: {MUTED}; font-size: {FS_MD}px; border: none; padding: 0 {GAP}px {GAP}px 0;
}}
QTableCornerButton::section {{ background: transparent; border: none; }}

QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle {{ background: rgba(255, 255, 255, 40); border-radius: 5px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {ACCENT}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ width: 0; height: 0; background: none; }}

QListWidget {{ background: transparent; border: none; outline: none; font-size: {FS_MD}px; }}
QListWidget::item {{ padding: 8px 6px; border: 2px solid transparent; border-radius: {RADIUS}px; color: {TEXT}; }}
QListWidget::item:hover {{ background: {ACCENT_DARK}; }}
QListWidget::item:selected {{ background: {ACCENT_DARK}; border-color: {ACCENT}; color: {TEXT}; }}

QSlider::groove:horizontal {{ height: 6px; background: rgba(255, 255, 255, 40); border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -5px 0; background: {ACCENT}; border-radius: 8px; }}
QSlider::handle:horizontal:hover {{ background: {ACCENT_HOVER}; }}
QSlider::groove:horizontal:disabled, QSlider::sub-page:horizontal:disabled {{ background: rgba(255, 255, 255, 20); }}

QMessageBox {{ background: {MENU_BG}; }}
QMessageBox QLabel {{ font-size: {FS_MD}px; }}
"""
