from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

from ...core.frame_utils import load_frames_from_dir


class PreviewFrameDialog(QDialog):
    """从帧目录选一帧作为预览图。返回 0-based 索引。"""

    def __init__(self, frames_dir, current_index=0, parent=None):
        super().__init__(parent)
        self._frames = load_frames_from_dir(frames_dir)
        if self._frames:
            self._current = max(0, min(current_index, len(self._frames) - 1))
        else:
            self._current = 0

        self.setWindowTitle("选择预览帧")
        self.resize(520, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._img_label = QLabel()
        self._img_label.setMinimumHeight(320)
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.setStyleSheet(
            "background: #ffffff; border: 1px dashed #c0c0c0; border-radius: 4px;"
        )
        layout.addWidget(self._img_label, 1)

        ctrl = QHBoxLayout()
        ctrl.setSpacing(6)
        self._btn_prev = QPushButton("◀")
        self._btn_prev.setFixedSize(36, 32)
        self._btn_prev.clicked.connect(self._on_prev)
        ctrl.addWidget(self._btn_prev)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, max(0, len(self._frames) - 1))
        self._slider.setValue(self._current)
        self._slider.valueChanged.connect(self._on_slider_changed)
        ctrl.addWidget(self._slider, 1)

        self._btn_next = QPushButton("▶")
        self._btn_next.setFixedSize(36, 32)
        self._btn_next.clicked.connect(self._on_next)
        ctrl.addWidget(self._btn_next)

        self._lbl_idx = QLabel("")
        self._lbl_idx.setMinimumWidth(72)
        self._lbl_idx.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ctrl.addWidget(self._lbl_idx)

        layout.addLayout(ctrl)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btn_ok = QPushButton("✓ 设为预览图")
        btn_ok.setFixedHeight(32)
        btn_ok.setMinimumWidth(130)
        btn_ok.clicked.connect(self.accept)
        btns.addWidget(btn_ok)

        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(32)
        btn_cancel.setMinimumWidth(80)
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)
        btns.addStretch(1)
        layout.addLayout(btns)

        self._update_display()

    def _update_display(self):
        if not self._frames:
            self._img_label.setText("无帧")
            self._lbl_idx.setText("0 / 0")
            return
        pix = self._frames[self._current]
        scaled = pix.scaled(
            self._img_label.size() - self._img_label.size() * 0.05,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._img_label.setPixmap(scaled)
        self._lbl_idx.setText(f"{self._current + 1} / {len(self._frames)}")

    def _on_prev(self):
        if self._current > 0:
            self._slider.setValue(self._current - 1)

    def _on_next(self):
        if self._current < len(self._frames) - 1:
            self._slider.setValue(self._current + 1)

    def _on_slider_changed(self, v):
        self._current = v
        self._update_display()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_display()

    def get_selected_index(self):
        return self._current