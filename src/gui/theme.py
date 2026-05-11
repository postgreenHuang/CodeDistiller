"""
Code-Distiller 主题管理
"""

import sys

_FONT_FAMILY = (
    '"PingFang SC", "SF Pro Display", "Helvetica Neue", sans-serif'
    if sys.platform == "darwin" else
    '"Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif'
)

THEMES = {
    "light": {
        "bg": "#f2f2f5",
        "surface": "#fafafa",
        "text": "#2c2c2e",
        "text_secondary": "#86868b",
        "text_label": "#48484a",
        "accent": "#5b86c4",
        "accent_hover": "#4a75b3",
        "accent_pressed": "#3a65a3",
        "border": "#d2d2d7",
        "border_group": "#e5e5ea",
        "input_bg": "#f2f2f5",
        "input_focus_bg": "#ffffff",
        "btn_secondary": "#e5e5ea",
        "btn_secondary_text": "#2c2c2e",
        "btn_secondary_hover": "#d2d2d7",
        "progress_bg": "#e5e5ea",
        "scrollbar": "#c7c7cc",
        "scrollbar_hover": "#a1a1a6",
        "disabled": "#c7c7cc",
    },
    "dark": {
        "bg": "#1c1c1e",
        "surface": "#2c2c2e",
        "text": "#dcdce2",
        "text_secondary": "#8e8e93",
        "text_label": "#92929a",
        "accent": "#0a84ff",
        "accent_hover": "#409cff",
        "accent_pressed": "#0066d6",
        "border": "#48484a",
        "border_group": "#3a3a3c",
        "input_bg": "#2c2c2e",
        "input_focus_bg": "#3a3a3c",
        "btn_secondary": "#3a3a3c",
        "btn_secondary_text": "#dcdce2",
        "btn_secondary_hover": "#48484a",
        "progress_bg": "#3a3a3c",
        "scrollbar": "#48484a",
        "scrollbar_hover": "#636366",
        "disabled": "#48484a",
    },
}


def build_stylesheet(theme_name: str) -> str:
    c = THEMES[theme_name]
    return f"""
    QMainWindow {{
        background-color: {c['bg']};
    }}

    QWidget {{
        font-family: {_FONT_FAMILY};
        font-size: 13px;
        color: {c['text']};
    }}

    QDialog {{
        background-color: {c['bg']};
    }}

    QDialog QWidget {{
        background-color: transparent;
    }}
    QDialog QGroupBox {{
        background: {c['surface']};
    }}
    QDialog QGroupBox::title {{
        background: {c['surface']};
    }}

    QListWidget {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 2px;
        color: {c['text']};
        outline: none;
    }}
    QListWidget::item {{
        padding: 6px 8px;
        border-radius: 4px;
    }}
    QListWidget::item:selected {{
        background: {c['accent']};
        color: #ffffff;
    }}
    QListWidget::item:hover:!selected {{
        background: {c['btn_secondary']};
    }}

    QSpinBox, QDoubleSpinBox {{
        background: {c['input_bg']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 5px 8px;
        min-height: 18px;
        color: {c['text']};
    }}

    QDialogButtonBox QPushButton {{
        min-width: 80px;
    }}

    QTabWidget::pane {{
        border: none;
        background: {c['surface']};
        border-radius: 10px;
        padding: 12px;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {c['text_secondary']};
        padding: 8px 16px;
        margin-right: 2px;
        border: none;
        border-bottom: 2px solid transparent;
        font-size: 13px;
        font-weight: 500;
    }}
    QTabBar::tab:selected {{
        color: {c['accent']};
        border-bottom: 2px solid {c['accent']};
    }}
    QTabBar::tab:hover:!selected {{
        color: {c['text']};
    }}

    QGroupBox {{
        background: {c['surface']};
        border: 1px solid {c['border_group']};
        border-radius: 8px;
        margin-top: 16px;
        padding: 14px 12px 8px 12px;
        font-weight: 600;
        font-size: 13px;
        color: {c['text']};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        top: 6px;
        padding: 0 4px;
        background: {c['surface']};
        color: {c['text']};
    }}

    QLineEdit {{
        background: {c['input_bg']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 6px 10px;
        min-height: 18px;
        color: {c['text']};
        selection-background-color: {c['accent']};
        selection-color: #ffffff;
    }}
    QLineEdit:focus {{
        border: 1.5px solid {c['accent']};
        background: {c['input_focus_bg']};
    }}

    QComboBox {{
        background: {c['input_bg']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 5px 10px;
        min-width: 110px;
        min-height: 18px;
        color: {c['text']};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    QComboBox QAbstractItemView {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        selection-background-color: {c['accent']};
        selection-color: #ffffff;
        padding: 2px;
        outline: none;
        color: {c['text']};
    }}
    QComboBox QAbstractItemView::item {{
        background: {c['surface']};
        color: {c['text']};
        padding: 4px 8px;
        min-height: 22px;
    }}
    QComboBox QAbstractItemView::item:selected {{
        background: {c['accent']};
        color: #ffffff;
    }}
    QComboBox QLineEdit {{
        background: {c['input_bg']};
        color: {c['text']};
        border: none;
    }}

    QPushButton {{
        background: {c['accent']};
        color: #ffffff;
        border: none;
        border-radius: 6px;
        padding: 7px 16px;
        font-weight: 600;
        font-size: 13px;
        min-height: 28px;
    }}
    QPushButton:hover {{
        background: {c['accent_hover']};
    }}
    QPushButton:pressed {{
        background: {c['accent_pressed']};
    }}
    QPushButton:disabled {{
        background: {c['disabled']};
        color: #ffffff;
    }}

    QPushButton[class="secondary"] {{
        background: {c['btn_secondary']};
        color: {c['btn_secondary_text']};
        padding: 2px 6px;
    }}
    QPushButton[class="secondary"]:hover {{
        background: {c['btn_secondary_hover']};
    }}

    QProgressBar {{
        background: {c['progress_bg']};
        border: none;
        border-radius: 3px;
        height: 5px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c['accent']}, stop:1 #5ac8fa);
        border-radius: 3px;
    }}

    QTextEdit {{
        background: {c['input_bg']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 8px 10px;
        color: {c['text']};
        selection-background-color: {c['accent']};
        selection-color: #ffffff;
    }}
    QTextEdit:focus {{
        border: 1.5px solid {c['accent']};
        background: {c['input_focus_bg']};
    }}

    QLabel {{
        color: {c['text']};
    }}
    QLabel[class="hint"] {{
        color: {c['text_secondary']};
        font-size: 13px;
    }}
    QLabel[class="status"] {{
        color: {c['text_secondary']};
        font-size: 13px;
        padding: 2px 0;
    }}

    QScrollArea {{
        background: transparent;
        border: none;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}

    QSplitter::handle {{
        background: {c['border_group']};
    }}
    QSplitter::handle:hover {{
        background: {c['accent']};
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {c['scrollbar']};
        border-radius: 4px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {c['scrollbar_hover']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    QStatusBar {{
        background: {c['bg']};
        color: {c['text_secondary']};
        border-top: 1px solid {c['border_group']};
        font-size: 13px;
        padding: 3px 10px;
    }}

    QMenu {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 4px;
        color: {c['text']};
    }}
    QMenu::item {{
        padding: 6px 24px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background: {c['accent']};
        color: #ffffff;
    }}

    /* Chat 样式 */
    QWidget[class="chat-right"] {{
        background: {c['bg']};
        border: none;
    }}
    QWidget[class="chat-input-bar"] {{
        background: {c['bg']};
        border: none;
    }}
    QWidget[class="chat-messages"] {{
        background: {c['bg']};
        border: none;
    }}
    QFrame[class="chat-sep"] {{
        background: {c['border_group']};
        border: none;
        max-height: 1px;
    }}
    QLabel[class="chat-status"] {{
        background: {c['bg']};
        color: {c['text_secondary']};
        font-size: 13px;
        border: none;
        padding: 4px 12px;
    }}
    QWidget[class="chat-sidebar"] {{
        background: {c['surface']};
        border: none;
    }}
    QLineEdit[class="chat-search"] {{
        background: {c['input_bg']};
        border: 1px solid {c['border']};
        border-radius: 4px;
        padding: 4px 8px;
        margin: 4px 8px;
        color: {c['text']};
        font-size: 12px;
    }}
    QTreeWidget[class="session-tree"] {{
        background: {c['surface']};
        border: none;
        outline: none;
        padding: 4px 8px;
    }}
    QTreeWidget[class="session-tree"]::item {{
        padding: 6px 4px;
        border-radius: 4px;
        border: none;
    }}
    QTreeWidget[class="session-tree"]::item:selected {{
        background: {c['accent']};
        color: #ffffff;
    }}
    QTreeWidget[class="session-tree"]::item:hover:!selected {{
        background: {c['btn_secondary']};
    }}
    QComboBox[class="chat-model-combo"] {{
        background: {c['input_bg']};
        border: 1px solid {c['border']};
        border-radius: 4px;
        padding: 3px 6px;
        font-size: 13px;
        color: {c['text']};
        min-height: 20px;
    }}
    QComboBox[class="chat-model-combo"]::drop-down {{
        border: none;
        width: 18px;
    }}
    QComboBox[class="chat-model-combo"] QAbstractItemView {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        selection-background-color: {c['accent']};
        selection-color: #ffffff;
        color: {c['text']};
        outline: none;
        padding: 2px;
    }}
    QPushButton[class="chat-quick-btn"] {{
        background: {c['input_bg']};
        border: 1px solid {c['border']};
        border-radius: 4px;
        padding: 3px 6px;
        font-size: 13px;
        color: {c['text']};
        min-height: 20px;
    }}
    QPushButton[class="chat-quick-btn"]:hover {{
        background: {c['surface']};
        border-color: {c['accent']};
    }}
    QTextBrowser[class="msg-user"] {{
        background: {c['accent']};
        color: #e8e8ee;
        border: none;
        border-radius: 10px;
        padding: 12px 18px;
        margin-left: 36px;
    }}
    QTextBrowser[class="msg-assistant"] {{
        background: {c['surface']};
        color: {c['text']};
        border: none;
        border-radius: 10px;
        padding: 12px 18px;
        margin-right: 36px;
    }}
    QScrollArea[class="chat-scroll"] {{
        background: {c['bg']};
        border: none;
    }}
    QScrollArea[class="chat-scroll"] > QWidget > QWidget {{
        background: {c['bg']};
        border: none;
    }}
    """
