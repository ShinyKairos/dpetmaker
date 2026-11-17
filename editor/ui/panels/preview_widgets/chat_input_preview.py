from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLineEdit
)

from .base_preview import BasePreview
from editor.ui.widgets.color_utils import parse_color


BAR_HEIGHT = 36   # 与运行时 ChatInputBar.BAR_HEIGHT 保持一致


def _safe_css(s):
    """把颜色字符串归一化为 QSS 合法格式（整数 alpha）"""
    if not s:
        return "transparent"
    try:
        c = parse_color(str(s))
        if not c.isValid():
            return str(s)
        if c.alpha() == 255:
            return c.name()
        return f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"
    except Exception:
        return str(s)


class ChatInputPreview(BasePreview):
    def __init__(self, parent=None):
        super().__init__("对话输入栏", parent)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        h = QHBoxLayout(self._container)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)

        self._edit = QLineEdit("和我说点什么吧~")
        self._edit.setFixedHeight(BAR_HEIGHT)
        self._edit.setMinimumWidth(160)
        self._edit.setReadOnly(True)
        h.addWidget(self._edit, 1)

        self._btns = []
        for txt in ["←", "…", "×"]:
            btn = QPushButton(txt)
            btn.setFixedSize(BAR_HEIGHT, BAR_HEIGHT)   # 正方形，与输入框同高
            h.addWidget(btn)
            self._btns.append(btn)

        self._preview_layout.addWidget(self._container)

    def apply_style(self, data):
        btn_bg = _safe_css(data.get("btn_bg", "rgba(255,255,255,0.9)"))
        btn_hover = _safe_css(data.get("btn_hover_bg", "#f0f0f0"))
        text = _safe_css(data.get("text_color", "#000000"))
        border = _safe_css(data.get("border_color", "#dddddd"))

        self._edit.setStyleSheet(f"""
            QLineEdit {{
                background: {btn_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 0 8px;
                font-size: 12px;
            }}
        """)

        btn_qss = f"""
            QPushButton {{
                background: {btn_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background: {btn_hover};
            }}
        """
        for btn in self._btns:
            btn.setStyleSheet(btn_qss)