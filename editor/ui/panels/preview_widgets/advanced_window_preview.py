from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
)

from .base_preview import BasePreview


class AdvancedWindowPreview(BasePreview):
    def __init__(self, parent=None):
        super().__init__("高级对话气泡", parent)

        self._container = QWidget()
        v = QVBoxLayout(self._container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        # 用户气泡（右对齐）
        user_row = QHBoxLayout()
        user_row.addStretch(1)
        self._user_bubble = QFrame()
        uv = QVBoxLayout(self._user_bubble)
        uv.setContentsMargins(10, 6, 10, 6)
        uv.setSpacing(2)
        self._user_lbl = QLabel("用户发送的一条消息")
        self._user_time = QLabel("2026-01-01 12:00")
        uv.addWidget(self._user_lbl)
        uv.addWidget(self._user_time)
        user_row.addWidget(self._user_bubble)
        v.addLayout(user_row)

        # 助手气泡（左对齐）
        asst_row = QHBoxLayout()
        self._asst_bubble = QFrame()
        av = QVBoxLayout(self._asst_bubble)
        av.setContentsMargins(10, 6, 10, 6)
        av.setSpacing(2)
        self._asst_lbl = QLabel("助手回复的一条消息，稍长用于展示换行效果。")
        self._asst_lbl.setWordWrap(True)
        self._asst_time = QLabel("2026-01-01 12:00")
        av.addWidget(self._asst_lbl)
        av.addWidget(self._asst_time)
        asst_row.addWidget(self._asst_bubble)
        asst_row.addStretch(1)
        v.addLayout(asst_row)

        self._preview_layout.addWidget(self._container)

    def apply_style(self, data):
        user_bg = data.get("user_bg", "#d0e8ff")
        asst_bg = data.get("assistant_bg", "#f0f0f0")
        radius = int(data.get("border_radius", 8))
        font_size = int(data.get("font_size", 14))
        time_color = data.get("time_color", "#999999")
        time_font_size = int(data.get("time_font_size", 11))
        text_color = data.get("text_color", "#000000")
        max_width = int(data.get("max_width", 520))

        self._user_bubble.setStyleSheet(
            f"QFrame {{ background: {user_bg}; border-radius: {radius}px; }}"
        )
        self._asst_bubble.setStyleSheet(
            f"QFrame {{ background: {asst_bg}; border-radius: {radius}px; }}"
        )
        for lbl in (self._user_lbl, self._asst_lbl):
            lbl.setStyleSheet(
                f"background: transparent; color: {text_color};"
                f" font-size: {font_size}px;"
            )
        for lbl in (self._user_time, self._asst_time):
            lbl.setStyleSheet(
                f"background: transparent; color: {time_color};"
                f" font-size: {time_font_size}px;"
            )
        self._user_bubble.setMaximumWidth(max_width)
        self._asst_bubble.setMaximumWidth(max_width)