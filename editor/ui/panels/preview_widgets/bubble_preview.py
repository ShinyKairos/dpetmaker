from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import (
    QPainter, QColor, QPainterPath, QPolygonF, QFont, QPen
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer

from .base_preview import BasePreview
from ...widgets.color_utils import parse_color


class BubblePreview(BasePreview):
    def __init__(self, parent=None):
        super().__init__("对话气泡", parent)
        self._canvas = _BubbleCanvas()
        self._preview_layout.addWidget(self._canvas)

    def apply_style(self, data):
        self._canvas.apply_style(data)


class _BubbleCanvas(QWidget):
    """自绘气泡：圆角矩形 + 底部小三角 + 逐字显示示例文字。

    逐字速度由 data["_text_speed"] 控制（字/秒），来自 ai_system.ui_config。
    停留时间与最大宽度不参与预览。
    """

    SAMPLE_TEXT = "示例文字，用于预览气泡样式与逐字速度。"

    def __init__(self):
        super().__init__()
        self._bg = QColor(255, 255, 255, 230)
        self._fg = QColor("#000000")
        self._padding = 12
        self._font = QFont("微软雅黑", 10)
        self._radius = 8

        # 逐字显示状态
        self._char_per_sec = 4.0
        self._show_text = ""

        self._text_timer = QTimer(self)
        self._text_timer.timeout.connect(self._on_char_tick)

        self._restart_timer = QTimer(self)
        self._restart_timer.setSingleShot(True)
        self._restart_timer.timeout.connect(self._restart_typing)

        self.setMinimumHeight(90)
        self.setMaximumHeight(140)

        # 初始启动
        self._restart_typing()

    # ---------- 逐字动画 ----------
    def _restart_typing(self):
        self._restart_timer.stop()
        self._text_timer.stop()
        self._show_text = ""
        interval = max(30, int(1000.0 / max(0.1, self._char_per_sec)))
        self._text_timer.start(interval)
        self.update()

    def _on_char_tick(self):
        if len(self._show_text) < len(self.SAMPLE_TEXT):
            self._show_text += self.SAMPLE_TEXT[len(self._show_text)]
            self.update()
        else:
            self._text_timer.stop()
            # 显示完后停 2 秒再重新播放
            self._restart_timer.start(2000)

    # ---------- 样式 ----------
    def apply_style(self, data):
        self._bg = parse_color(data.get("bg_color", "rgba(255,255,255,230)"))
        self._fg = parse_color(data.get("text_color", "#000000"))
        self._padding = int(data.get("padding", 12))
        self._radius = int(data.get("border_radius", 8))
        family = data.get("font_family", "微软雅黑")
        size = int(data.get("font_size", 10))
        self._font = QFont(family, size)

        # ★ 逐字速度：速度变化时重启动画
        new_speed = float(data.get("_text_speed", 4.0))
        new_speed = max(0.5, min(30.0, new_speed))
        speed_changed = abs(new_speed - self._char_per_sec) > 0.01
        self._char_per_sec = new_speed

        if speed_changed:
            self._restart_typing()

        self.update()

    # ---------- 绘制 ----------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(6, 6, -6, -14)

        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)
        cx = rect.center().x()
        triangle = [
            QPointF(cx - 6, rect.bottom() - 0.5),
            QPointF(cx + 6, rect.bottom() - 0.5),
            QPointF(cx, rect.bottom() + 8),
        ]
        path.addPolygon(QPolygonF(triangle))

        p.fillPath(path, self._bg)

        p.setPen(QPen(self._fg))
        p.setFont(self._font)
        text_rect = rect.adjusted(
            self._padding, self._padding,
            -self._padding, -self._padding
        )
        p.drawText(
            text_rect,
            Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignTop,
            self._show_text
        )