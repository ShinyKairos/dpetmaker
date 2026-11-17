from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QScrollArea, QSizePolicy
)
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import Qt, pyqtSignal

from .animation_player import AnimationPlayer
from .selection_overlay import SelectionOverlay


class PreviewPanel(QWidget):
    """中间预览区。负责播放动画、框选浮层，以及 1:1 画布展示。"""

    selection_rect_changed = pyqtSignal(object, bool)

    def __init__(self, temp_root="", parent=None):
        super().__init__(parent)
        self.temp_root = temp_root
        self._target_size = None    # (w, h) 或 None
        self._overlay_active = False
        self._build_ui()

        # 创建框选浮层（作为 player 的子控件）
        self.overlay = SelectionOverlay(self.player)
        self.player.frame_rect_changed.connect(self._on_frame_rect_changed)
        self.overlay.rect_changed.connect(self._on_overlay_rect_changed)

        self.play_test_frames()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ---------- 工具条 ----------
        bar = QHBoxLayout()
        bar.setSpacing(6)

        self.btn_play = QPushButton("⏸ 暂停")
        self.btn_play.setFixedSize(84, 30)
        self.btn_play.clicked.connect(self._on_toggle_play)
        bar.addWidget(self.btn_play)

        self.btn_stop = QPushButton("⏹ 停止")
        self.btn_stop.setFixedSize(84, 30)
        self.btn_stop.clicked.connect(self._on_stop)
        bar.addWidget(self.btn_stop)

        bar.addStretch(1)

        self.lbl_info = QLabel("")
        # ★ 不强制指定颜色，让它跟随系统主题（亮色为黑，暗色为白）
        self.lbl_info.setStyleSheet("font-size: 12px;")
        # ★ 改为 Preferred：空间不足时会自动显示 "..."，空间充足时正常显示
        self.lbl_info.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        bar.addWidget(self.lbl_info)

        layout.addLayout(bar)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("color: #eee;")
        layout.addWidget(line)

        # 画布 1:1 像素显示
        self.player = AnimationPlayer()

        self._player_scroll = QScrollArea()
        self._player_scroll.setWidgetResizable(False)
        self._player_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._player_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._player_scroll.viewport().setStyleSheet("background-color: #2b2b2b;")
        self._player_scroll.setWidget(self.player)
        layout.addWidget(self._player_scroll, 1)

        self.lbl_hint = QLabel(
            "🎨 当前为测试帧（红→绿→蓝）。从左侧面板导入 GIF 以替换测试素材。"
        )
        self.lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_hint.setStyleSheet("font-size: 12px; color: #888; padding: 4px;")
        self.lbl_hint.setWordWrap(True)
        layout.addWidget(self.lbl_hint)

        self.lbl_selection = QLabel("")
        self.lbl_selection.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_selection.setStyleSheet("font-size: 12px; color: #5a9bd5; padding: 4px;")
        self.lbl_selection.setWordWrap(True)
        layout.addWidget(self.lbl_selection)

    def play_test_frames(self):
        size = self._target_size[0] if self._target_size else 364
        frames = [
            self._make_solid_frame(size, QColor("#e74c3c"), "红 1"),
            self._make_solid_frame(size, QColor("#2ecc71"), "绿 2"),
            self._make_solid_frame(size, QColor("#3498db"), "蓝 3"),
        ]
        self.player.set_frames(frames)
        self.player.set_fps(4)
        self.player.play()
        self.btn_play.setText("⏸ 暂停")
        self._update_info()

    def _make_solid_frame(self, size, color, text):
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(20, 20, size - 40, size - 40)
        p.setPen(QColor("#ffffff"))
        f = QFont("微软雅黑", int(size / 8))
        f.setBold(True)
        p.setFont(f)
        p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, text)
        p.end()
        return pix

    def set_target_size(self, w, h):
        try:
            w, h = int(w), int(h)
            if w > 0 and h > 0:
                self._target_size = (w, h)
                self.player.set_frame_size(w, h)
                
                # ★ 动态计算最小宽度：物理像素转逻辑像素，预留 280 以容纳按钮和文字
                dpr = self.devicePixelRatioF()
                if dpr <= 0: dpr = 1.0
                w_logic = w / dpr
                min_w = max(280, int(w_logic) + 30)
                self.setMinimumWidth(min_w)
            else:
                self._target_size = None
                self.player.set_frame_size(None, None)
                self.setMinimumWidth(280)  # 未打开项目时的保底最小宽度
        except (TypeError, ValueError):
            self._target_size = None
            self.player.set_frame_size(None, None)
            self.setMinimumWidth(280)
        self._update_info()

    def set_frames(self, frames, fps=16, autoplay=True):
        if self._overlay_active:
            self.exit_selection_mode()
        self.player.stop()
        self.player.set_frames(frames)
        self.player.set_fps(fps)
        if autoplay and frames:
            self.player.play()
            self.btn_play.setText("⏸ 暂停")
        else:
            self.btn_play.setText("▶ 播放")
        self._update_info()

    def _on_toggle_play(self):
        if self.player.is_playing():
            self.player.pause()
            self.btn_play.setText("▶ 播放")
        else:
            self.player.play()
            self.btn_play.setText("⏸ 暂停")
        self._update_info()

    def _on_stop(self):
        self.player.stop()
        self.btn_play.setText("▶ 播放")
        self._update_info()

    def _update_info(self):
        n = self.player.frame_count()
        idx = self.player.current_frame_index() + 1 if n else 0
        state = "播放中" if self.player.is_playing() else "已停止"
        size_txt = ""
        if self._target_size:
            size_txt = f" · 画布 {self._target_size[0]}×{self._target_size[1]}（1:1 像素）"
        self.lbl_info.setText(f"{state} · 帧 {idx}/{n}{size_txt}")

    # ===================== 框选相关 =====================
    def _ensure_overlay_geometry(self):
        if self.player._last_frame_rect is not None:
            x, y, w, h = self.player._last_frame_rect
            self.overlay.setGeometry(x, y, w, h)
        else:
            self.overlay.setGeometry(self.player.rect())

    def _on_frame_rect_changed(self, x, y, w, h):
        if self.overlay.isVisible():
            self.overlay.setGeometry(x, y, w, h)

    def enter_selection_mode(self, editing_rect=None, existing_rects=None):
        self._ensure_overlay_geometry()
        self.overlay.activate(editing_rect, existing_rects)
        self.overlay.raise_()
        self._overlay_active = True
        self.lbl_selection.setText("🖱 在图片区域内拖动鼠标画框；画完后点击右侧面板的『✓ 确认选择』")

    def exit_selection_mode(self):
        self.overlay.deactivate()
        self._overlay_active = False
        self.lbl_selection.setText("")

    def get_pending_rect(self):
        return self.overlay.get_current_rect()

    def is_pending_rect_valid(self):
        return self.overlay.is_current_rect_valid()

    def _on_overlay_rect_changed(self, rect_ratio, is_overlapping):
        self.selection_rect_changed.emit(rect_ratio, is_overlapping)
        if rect_ratio is None:
            self.lbl_selection.setText("")
            return
        if is_overlapping:
            self.lbl_selection.setStyleSheet("font-size: 12px; color: #d04040; padding: 4px;")
            self.lbl_selection.setText("⚠ 与已有特殊触摸区域重叠，请重新框选。")
        else:
            self.lbl_selection.setStyleSheet("font-size: 12px; color: #5a9bd5; padding: 4px;")
            self.lbl_selection.setText(
                f"选中区域：x={rect_ratio.x():.4f} · y={rect_ratio.y():.4f} · "
                f"w={rect_ratio.width():.4f} · h={rect_ratio.height():.4f} （比例 0~1）"
            )