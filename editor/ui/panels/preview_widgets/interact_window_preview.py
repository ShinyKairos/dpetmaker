from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QSizePolicy
)
from PyQt6.QtCore import Qt

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


class _ActionCell(QWidget):
    """模拟运行时的 ActionButton：64×64 预览图 + 动作名"""

    def __init__(self, emoji, name, parent=None):
        super().__init__(parent)
        self.setFixedSize(72, 86)

        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(4)

        self._preview = QLabel(emoji)
        self._preview.setFixedSize(64, 64)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._name = QLabel(name)
        self._name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name.setWordWrap(True)

        v.addWidget(self._preview)
        v.addWidget(self._name)

    def apply_style(self, text_color):
        self._preview.setStyleSheet(
            "border: 1px solid #ddd; border-radius: 4px;"
            f" background: #fafafa; font-size: 28px; color: {text_color};"
        )
        self._name.setStyleSheet(
            f"font-size: 11px; color: {text_color}; background: transparent;"
        )


class InteractWindowPreview(BasePreview):
    def __init__(self, parent=None):
        super().__init__("互动选择窗口", parent)

        self._container = QFrame()
        self._container.setObjectName("interact_container")
        # ★ 340 是 2×4 网格（4×72 + 3×10 spacing + 24 padding）能完整显示的下限
        self._container.setMinimumWidth(340)
        self._container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        main = QVBoxLayout(self._container)
        main.setContentsMargins(12, 10, 12, 10)
        main.setSpacing(10)

        # ---- 顶部标签栏 ----
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(6)

        self._btn_prev_tab = QPushButton("◀")
        self._btn_prev_tab.setFixedSize(24, 24)
        self._btn_prev_tab.setEnabled(False)
        top_bar.addWidget(self._btn_prev_tab)

        self._tab_btns = []
        for i, txt in enumerate(["日常互动", "特殊动作"]):
            tab = QPushButton(txt)
            tab.setCheckable(True)
            if i == 0:
                tab.setChecked(True)
            self._tab_btns.append(tab)
            top_bar.addWidget(tab)
        top_bar.addStretch(1)

        self._btn_next_tab = QPushButton("▶")
        self._btn_next_tab.setFixedSize(24, 24)
        self._btn_next_tab.setEnabled(False)
        top_bar.addWidget(self._btn_next_tab)

        self._btn_close = QPushButton("×")
        self._btn_close.setFixedSize(24, 24)
        top_bar.addWidget(self._btn_close)

        main.addLayout(top_bar)

        # ---- 中间：2 行 × 4 列 动作格 ----
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)

        self._cells = []
        emojis = ["😀", "🎉", "😴", "🤔", "🎈", "💤", "🎨", "📚"]
        names = ["打招呼", "转圈", "休息", "思考", "庆祝", "睡觉", "画画", "读书"]
        for i, (em, nm) in enumerate(zip(emojis, names)):
            cell = _ActionCell(em, nm)
            self._cells.append(cell)
            grid.addWidget(cell, i // 4, i % 4)
        main.addLayout(grid)

        # ---- 底部翻页栏 ----
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(8)
        bottom.addStretch(1)

        self._btn_prev_action = QPushButton("◀")
        self._btn_prev_action.setFixedSize(28, 24)
        self._btn_prev_action.setEnabled(False)
        bottom.addWidget(self._btn_prev_action)

        self._dots = []
        for _ in range(2):
            dot = QLabel("●")
            dot.setFixedWidth(12)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._dots.append(dot)
            bottom.addWidget(dot)

        self._btn_next_action = QPushButton("▶")
        self._btn_next_action.setFixedSize(28, 24)
        bottom.addWidget(self._btn_next_action)

        bottom.addStretch(1)
        main.addLayout(bottom)

        self._preview_layout.addWidget(self._container)

    def apply_style(self, data):
        window_bg = _safe_css(data.get("window_bg", "rgba(255,255,255,0.95)"))
        btn_bg = _safe_css(data.get("btn_bg", "#ffffff"))
        btn_hover = _safe_css(data.get("btn_hover_bg", "#f0f0f0"))
        text = _safe_css(data.get("text_color", "#000000"))
        border = _safe_css(data.get("border_color", "#dddddd"))
        tab_bg = _safe_css(data.get("tab_bg", "#f5f5f5"))
        tab_sel = _safe_css(data.get("tab_selected_bg", "#ffffff"))
        disabled_bg = _safe_css(data.get("btn_disabled_bg", "#f5f5f5"))
        disabled_color = _safe_css(data.get("btn_disabled_color", "#bbbbbb"))

        # 容器（QFrame 圆角边框）
        self._container.setStyleSheet(f"""
            QFrame#interact_container {{
                background: {window_bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
        """)

        # 通用按钮
        general_qss = f"""
            QPushButton {{
                background: {btn_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background: {btn_hover}; }}
        """

        # 标签按钮
        tab_qss = f"""
            QPushButton {{
                background: {tab_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                border-bottom-left-radius: 0;
                border-bottom-right-radius: 0;
                padding: 6px 10px;
                font-size: 12px;
            }}
            QPushButton:checked {{
                background: {tab_sel};
                font-weight: bold;
            }}
        """

        # 翻页按钮（禁用时透明融入背景 —— 与运行时一致）
        page_qss = f"""
            QPushButton {{
                background: {btn_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background: {btn_hover}; }}
            QPushButton:disabled {{
                background: transparent;
                color: {disabled_color};
                border: 1px solid transparent;
            }}
        """

        self._btn_prev_tab.setStyleSheet(page_qss)
        self._btn_next_tab.setStyleSheet(page_qss)
        self._btn_prev_action.setStyleSheet(page_qss)
        self._btn_next_action.setStyleSheet(page_qss)
        self._btn_close.setStyleSheet(general_qss)

        for tab in self._tab_btns:
            tab.setStyleSheet(tab_qss)

        for cell in self._cells:
            cell.apply_style(text)

        for i, dot in enumerate(self._dots):
            color = "#000" if i == 0 else "#bbb"
            dot.setStyleSheet(
                f"color: {color}; font-size: 10px; background: transparent;"
            )