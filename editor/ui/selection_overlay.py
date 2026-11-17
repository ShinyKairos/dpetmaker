from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen
from PyQt6.QtCore import Qt, QRect, QRectF, pyqtSignal


class SelectionOverlay(QWidget):
    """框选浮层，内置重叠校验。"""
    # ★ F-3：发射当前矩形与是否重叠，供外部实时更新按钮状态
    rect_changed = pyqtSignal(object, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.hide()

        self._start_point = None
        self._current_rect = None
        self._editing_rect = None
        self._existing_rects = []
        self._is_overlapping = False

    # ===================== 对外接口 =====================
    def activate(self, editing_rect=None, existing_rects=None):
        self._start_point = None
        self._current_rect = None
        self._editing_rect = editing_rect
        self._existing_rects = list(existing_rects or [])
        self._is_overlapping = False
        if self._editing_rect:
            self._is_overlapping = self._check_overlap(self._editing_rect)
        self.show()
        self.raise_()
        self.update()

    def deactivate(self):
        self._start_point = None
        self._current_rect = None
        self._editing_rect = None
        self._existing_rects = []
        self._is_overlapping = False
        self.hide()
        self.rect_changed.emit(None, False)

    def get_current_rect(self):
        return self._current_rect or self._editing_rect

    def is_current_rect_valid(self):
        rect = self._current_rect or self._editing_rect
        if not rect:
            return False
        return not self._check_overlap(rect)

    def clear_current(self):
        self._current_rect = None
        self._editing_rect = None
        self._is_overlapping = False
        self.rect_changed.emit(None, False)
        self.update()

    # ===================== 内部逻辑 =====================
    def _check_overlap(self, rect):
        """检查当前矩形是否与已有矩形重叠（包括边缘触碰）。"""
        for rn in self._existing_rects:
            if rect.intersects(rn):
                return True
        return False

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._start_point = event.position().toPoint()
        self._current_rect = None
        self._editing_rect = None
        self.rect_changed.emit(None, False)
        self.update()

    def mouseMoveEvent(self, event):
        if self._start_point is None:
            return
        cur = event.position().toPoint()
        rect = QRect(self._start_point, cur).normalized()
        rect = rect.intersected(self.rect())
        if rect.width() < 4 or rect.height() < 4:
            self.update()
            return
        
        w = max(1, self.width())
        h = max(1, self.height())
        self._current_rect = QRectF(
            rect.x() / w,
            rect.y() / h,
            rect.width() / w,
            rect.height() / h,
        )
        self._is_overlapping = self._check_overlap(self._current_rect)
        self.rect_changed.emit(self._current_rect, self._is_overlapping)
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._start_point is None:
            return
        self._start_point = None
        if self._current_rect is not None:
            self._is_overlapping = self._check_overlap(self._current_rect)
            self.rect_changed.emit(self._current_rect, self._is_overlapping)
        self.update()

    # ===================== 绘制 =====================
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 已有区域（黄色参考，用于区分当前正在画的红色重叠框）
        for rn in self._existing_rects:
            self._draw_normalized_rect(
                p, rn,
                fill=QColor(255, 193, 7, 70),       # 半透明琥珀黄
                border=QColor(255, 160, 0, 220),    # 深橙黄边框
                dashed=False,
            )

        # 当前矩形（有效蓝色虚线，无效红色虚线）
        cur = self._current_rect or self._editing_rect
        if cur is not None:
            if self._current_rect is not None:
                is_overlap = self._is_overlapping
            else:
                is_overlap = self._check_overlap(self._editing_rect)
                
            border = QColor(220, 60, 60, 255) if is_overlap else QColor(90, 155, 213, 255)
            fill = QColor(220, 60, 60, 90) if is_overlap else QColor(90, 155, 213, 90)
            
            self._draw_normalized_rect(p, cur, fill=fill, border=border, dashed=True)

    def _draw_normalized_rect(self, p, rn, fill, border, dashed):
        w = max(1, self.width())
        h = max(1, self.height())
        x = int(rn.x() * w)
        y = int(rn.y() * h)
        rw = int(rn.width() * w)
        rh = int(rn.height() * h)
        p.fillRect(x, y, rw, rh, fill)
        pen = QPen(border, 2)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawRect(x, y, rw, rh)