from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFormLayout,
    QSizePolicy
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


class BehaviorWindowPreview(BasePreview):
    def __init__(self, parent=None):
        super().__init__("行为设置窗口", parent)

        self._container = QFrame()
        # ★ 300 是 5 行表单（label ≈ 100 + value min 140 + spacing）能完整显示的下限
        self._container.setMinimumWidth(300)
        self._container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        v = QVBoxLayout(self._container)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(12)

        # 标题
        self._title = QLabel("自动行为参数")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self._title)

        # 5 行模拟字段（与运行时一致）
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self._field_pairs = []
        fields = [
            ("移动触发等待:", "7 秒"),
            ("移动概率:", "0.60 (0 ~ 1)"),
            ("移动持续时长:", "2 秒"),
            ("移动速度:", "20 像素/帧"),
            ("长待机触发等待:", "30 秒"),
        ]
        for label_text, value_text in fields:
            lbl = QLabel(label_text)
            val = QLabel(value_text)
            val.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            val.setMinimumWidth(140)
            self._field_pairs.append((lbl, val))
            form.addRow(lbl, val)

        v.addLayout(form)
        v.addStretch(1)

        # 保存 / 取消（100 × 36）
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._btn_save = QPushButton("保存")
        self._btn_save.setFixedSize(100, 36)
        btn_row.addWidget(self._btn_save)
        self._btn_cancel = QPushButton("取消")
        self._btn_cancel.setFixedSize(100, 36)
        btn_row.addWidget(self._btn_cancel)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        self._preview_layout.addWidget(self._container)

    def apply_style(self, data):
        window_bg = _safe_css(data.get("window_bg", "#ffffff"))
        text = _safe_css(data.get("text_color", "#000000"))
        btn_bg = _safe_css(data.get("btn_bg", "#ffffff"))
        btn_hover = _safe_css(data.get("btn_hover_bg", "#f0f0f0"))
        border = _safe_css(data.get("border_color", "#dddddd"))

        # 容器
        self._container.setStyleSheet(f"""
            QFrame {{
                background: {window_bg};
                border: 1px solid {border};
                border-radius: 6px;
            }}
        """)

        # 标题：16px 加粗
        self._title.setStyleSheet(
            f"background: transparent; color: {text};"
            " font-size: 16px; font-weight: bold;"
        )

        # 字段行：标签 + 模拟输入框（背景 = btn_bg）
        for lbl, val in self._field_pairs:
            lbl.setStyleSheet(
                f"background: transparent; color: {text}; font-size: 14px;"
            )
            val.setStyleSheet(
                f"background: {btn_bg}; color: {text};"
                f" border: 1px solid {border}; border-radius: 4px;"
                " padding: 0 6px; font-size: 14px; min-height: 28px;"
            )

        # 保存 / 取消按钮
        btn_qss = f"""
            QPushButton {{
                background: {btn_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 4px 16px;
                font-size: 14px;
                min-height: 28px;
            }}
            QPushButton:hover {{
                background: {btn_hover};
            }}
        """
        self._btn_save.setStyleSheet(btn_qss)
        self._btn_cancel.setStyleSheet(btn_qss)