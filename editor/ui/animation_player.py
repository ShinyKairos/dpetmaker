from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QPixmap, QColor, QBrush
from PyQt6.QtCore import QTimer, Qt, pyqtSignal, QEvent, QRectF


class AnimationPlayer(QWidget):
    """序列帧播放器。帧数据由外部 set_frames 注入，本类只负责播放。

    里程碑 D 接入 GIF 拆帧后，只需调用 set_frames(真实帧)，播放逻辑完全不变。

    ★ F-1 新增：frame_rect_changed 信号，通知外部"当前帧在控件里的显示区域"，
       用于让 SelectionOverlay 精确贴合到图片范围内。
    """

    frame_rect_changed = pyqtSignal(int, int, int, int)   # x, y, w, h

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frames = []
        self._current = 0
        self._fps = 16
        self._last_frame_rect = None   # (x, y, w, h)，用于去重 emit
        self._fixed_frame_size = None  # (w, h)，画布固定尺寸；None 时跟随第一帧

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_frame)

        self._checker = self._make_checker_brush()
        self.setMinimumSize(200, 200)

    def _make_checker_brush(self):
        """16×16 棋盘格，标识透明画布区域。"""
        pix = QPixmap(32, 32)
        pix.fill(QColor("#ffffff"))
        p = QPainter(pix)
        p.fillRect(0, 0, 16, 16, QColor("#e8e8e8"))
        p.fillRect(16, 16, 16, 16, QColor("#e8e8e8"))
        p.end()
        return QBrush(pix)

    def set_frame_size(self, w, h):
        """设置画布固定像素尺寸（1:1 显示，不做缩放）。

        w/h 为 None 或 <=0 时表示"不固定"，跟随第一帧尺寸。
        """
        if w is None or h is None or w <= 0 or h <= 0:
            self._fixed_frame_size = None
        else:
            self._fixed_frame_size = (int(w), int(h))
        self._apply_size()
        self.update()

    def _apply_size(self):
        """根据固定尺寸 / 第一帧尺寸，setFixedSize。

        ★ DPI 补偿：_fixed_frame_size 记录的是"物理像素"（= 项目 window 尺寸），
        而 setFixedSize 用的是"逻辑像素"。逻辑 = 物理 / dpr。
        这样在 200% 缩放下，画布屏幕渲染尺寸仍然是 364 物理像素。
        """
        dpr = self.devicePixelRatioF()
        if dpr <= 0:
            dpr = 1.0
        if self._fixed_frame_size is not None:
            w, h = self._fixed_frame_size
            self.setFixedSize(
                max(1, int(round(w / dpr))),
                max(1, int(round(h / dpr))),
            )
        elif self._frames:
            pix = self._frames[0]
            if not pix.isNull():
                self.setFixedSize(
                    max(1, int(round(pix.width() / dpr))),
                    max(1, int(round(pix.height() / dpr))),
                )

    # ---------- 外部接口 ----------
    def set_frames(self, frames):
        self._frames = list(frames) if frames else []
        self._current = 0
        self._apply_size()            # ★ 尺寸可能变化，立即应用
        if self._frames:
            self.update()
        else:
            self._timer.stop()

    def set_fps(self, fps):
        self._fps = max(1, int(fps))
        if self._timer.isActive():
            self._timer.setInterval(int(1000 / self._fps))

    def play(self):
        if not self._frames:
            return
        if len(self._frames) == 1:
            self._timer.stop()
            self.update()
            return
        self._timer.setInterval(int(1000 / self._fps))
        self._timer.start()
        self.update()

    def pause(self):
        self._timer.stop()

    def stop(self):
        self._timer.stop()
        self._current = 0
        self.update()

    def is_playing(self):
        return self._timer.isActive()

    def frame_count(self):
        return len(self._frames)

    def current_frame_index(self):
        return self._current

    # ---------- 内部 ----------
    def _next_frame(self):
        if not self._frames:
            self._timer.stop()
            return
        self._current = (self._current + 1) % len(self._frames)
        self.update()

    # ---------- 绘制 ----------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        dpr = self.devicePixelRatioF()
        if dpr <= 0:
            dpr = 1.0

        # 兜底深灰：铺满整块控件（逻辑坐标，屏幕按 dpr 渲染）
        painter.fillRect(self.rect(), QColor("#2b2b2b"))

        # ★ 进入"物理像素坐标空间"：之后所有绘制坐标都以 1 = 1 物理像素计。
        #   控件逻辑 width() × dpr = 控件物理宽（= 画布物理宽）。
        painter.save()
        painter.scale(1.0 / dpr, 1.0 / dpr)

        phys_w = self.width() * dpr
        phys_h = self.height() * dpr

        if not self._frames:
            painter.setPen(QColor("#888"))
            painter.drawText(
                QRectF(0, 0, phys_w, phys_h),
                Qt.AlignmentFlag.AlignCenter,
                "（暂无帧）",
            )
            painter.restore()
            return

        pix = self._frames[self._current]
        if pix.isNull():
            painter.restore()
            return

        # 棋盘格：铺满整块画布（物理像素坐标）
        painter.fillRect(QRectF(0, 0, phys_w, phys_h), self._checker)

        # 帧 1:1 物理像素绘制
        if pix.width() == phys_w and pix.height() == phys_h:
            # 正常路径：物理尺寸完全相等，无损绘制
            draw_rect = QRectF(0, 0, phys_w, phys_h)
            src_rect = QRectF(0, 0, pix.width(), pix.height())
            painter.drawPixmap(draw_rect, pix, src_rect)
            x_l, y_l = 0, 0
            w_l = int(round(phys_w / dpr))
            h_l = int(round(phys_h / dpr))
        else:
            # 兜底路径：帧尺寸异常（旧数据），等比缩放居中
            scale = min(phys_w / pix.width(), phys_h / pix.height())
            dw = pix.width() * scale
            dh = pix.height() * scale
            dx = (phys_w - dw) / 2.0
            dy = (phys_h - dh) / 2.0
            painter.drawPixmap(
                QRectF(dx, dy, dw, dh),
                pix,
                QRectF(0, 0, pix.width(), pix.height()),
            )
            x_l = int(round(dx / dpr))
            y_l = int(round(dy / dpr))
            w_l = int(round(dw / dpr))
            h_l = int(round(dh / dpr))

        painter.restore()

        # ★ 发出的是"逻辑坐标"（overlay 是 player 的子控件，坐标系统一）
        new_rect = (x_l, y_l, w_l, h_l)
        if new_rect != self._last_frame_rect:
            self._last_frame_rect = new_rect
            self.frame_rect_changed.emit(*new_rect)

    # ===================== DPI 变化响应 =====================
    def showEvent(self, event):
        """首次显示时 dpr 才真正可用（attach 到窗口后），重算一次尺寸。"""
        super().showEvent(event)
        self._apply_size()

    def event(self, e):
        """跨屏拖动时 dpr 变化 → 重算画布逻辑尺寸并重绘。"""
        if e.type() == QEvent.Type.DevicePixelRatioChange:
            self._apply_size()
            self.update()
        return super().event(e)