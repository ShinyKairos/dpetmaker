from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton

from .base_preview import BasePreview
from editor.ui.widgets.color_utils import parse_color


def _safe_css(s):
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


class RightMenuPreview(BasePreview):
    def __init__(self, parent=None):
        super().__init__("右键菜单", parent)

        # 与运行时 resize(120, 180) 一致；容器透明
        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._container.setFixedWidth(120)

        v = QVBoxLayout(self._container)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        self._btns = []
        for txt in ["互动", "对话", "行为设置", "关闭菜单", "退出"]:
            btn = QPushButton(txt)
            # 不固定高度：让 padding 8px 撑开（与运行时一致）
            v.addWidget(btn)
            self._btns.append(btn)

        # ★ 居中包装：120 宽的菜单在父级里居中，视觉上和真实右键菜单更贴近
        wrapper = QWidget()
        wl = QHBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addStretch(1)
        wl.addWidget(self._container)
        wl.addStretch(1)

        self._preview_layout.addWidget(wrapper)

    def apply_style(self, data):
        btn_bg = _safe_css(data.get("btn_bg", "rgba(255,255,255,0.9)"))
        btn_hover = _safe_css(data.get("btn_hover_bg", "#f0f0f0"))
        text = _safe_css(data.get("text_color", "#000000"))
        border = _safe_css(data.get("border_color", "#dddddd"))

        btn_qss = f"""
            QPushButton {{
                background: {btn_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {btn_hover};
            }}
        """
        for btn in self._btns:
            btn.setStyleSheet(btn_qss)